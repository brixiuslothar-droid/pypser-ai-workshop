# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""
Role 6 (grid analysis): map a solved 10-node (clustered) market result onto the
full-resolution German grid and check line loading and redispatch.

The market model runs on 10 nodes (``results/<run>/networks/solved_<horizon>.nc``).
Its transmission limits are aggregated over each cluster. This module rebuilds
the same market dispatch on the full German grid from ``resources/<run>/networks/
base.nc`` (780 AC buses, 1019 AC lines), so that internal line loading,
overloads and the redispatch needed to clear them become visible.

Spatial allocation of the clustered market quantities, per technology:

* variable renewables (on/offshore wind, solar) - by the available land/sea cells
  from the availability matrices (a proxy for the spatial ``p_max_pu``);
* conventional plants, run-of-river and hydro - by the location and capacity of
  the existing plants (``powerplants.csv``);
* demand - by population (``pop_layout_total.nc``);
* the Brazil cable - as a fixed injection at the German landing bus.

The DC power flow uses PyPSA's linear power flow (``n.lpf``); the redispatch is a
minimum-adjustment linear program built on the DC power-transfer distribution
factors (PTDF).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa
import xarray as xr
from scipy import sparse
from scipy.optimize import linprog
from scipy.spatial import cKDTree
from scipy.sparse.linalg import splu

logger = logging.getLogger(__name__)

RESOURCES = Path("resources")
RESULTS = Path("results")

VRE_CARRIERS = {
    "onwind",
    "offwind-ac",
    "offwind-dc",
    "offwind-float",
    "solar",
    "solar-hsat",
}
WIND_CARRIERS = {"onwind", "offwind-ac", "offwind-dc", "offwind-float"}

AVAILABILITY = {
    "onwind": "onwind",
    "offwind-ac": "offwind-ac",
    "offwind-dc": "offwind-dc",
    "offwind-float": "offwind-float",
    "solar": "solar",
    "solar-hsat": "solar-hsat",
}

PLANT_CARRIER = {
    ("Hydro", "Run-Of-River"): "ror",
    ("Hydro", "Reservoir"): "hydro",
    ("Hydro", "Pumped Storage"): "PHS",
    ("Bioenergy", "*"): "biomass",
    ("Natural Gas", "CCGT"): "CCGT",
    ("Natural Gas", "OCGT"): "OCGT",
    ("Natural Gas", "Combustion Engine"): "OCGT",
    ("Hard Coal", "*"): "coal",
    ("Lignite", "*"): "lignite",
    ("Oil", "*"): "oil",
    ("Waste", "*"): "waste",
    ("Geothermal", "*"): "geothermal",
    ("Nuclear", "*"): "nuclear",
    ("Wind", "Onshore"): "onwind",
    ("Wind", "Offshore"): "offwind",
    ("Solar", "*"): "solar",
}


@lru_cache(maxsize=None)
def read_cluster_map(run: str) -> pd.Series:
    """bus -> cluster bus (the simplify+cluster map, on the simplified grid)."""
    cluster = pd.read_csv(
        RESOURCES / run / "busmap_cluster_network.csv", index_col=0
    ).iloc[:, 0]
    if cluster.isna().any():
        logger.warning("%d buses without a cluster", int(cluster.isna().sum()))
    return cluster.dropna()


@lru_cache(maxsize=None)
def base_grid(run: str) -> pypsa.Network:
    """
    Full German AC grid (buses and lines).

    Uses the *simplified* network: the raw ``base.nc`` is fragmented into 28
    islands (an OSM extraction artefact), while the simplify step yields one
    connected grid of 470 AC buses and 831 AC lines.
    """
    n = pypsa.Network(RESOURCES / run / "networks" / "simplified.nc")
    ac = n.buses.index[n.buses.carrier == "AC"]
    bad_lines = n.lines.index[~(n.lines.bus0.isin(ac) & n.lines.bus1.isin(ac))]
    n.remove("Line", bad_lines)
    n.remove("Bus", n.buses.index[~n.buses.index.isin(ac)])
    n.lines["dc"] = False
    logger.info("full grid: %d AC buses, %d AC lines", len(n.buses), len(n.lines))
    return n


def _nearest_bus(
    coords: np.ndarray, bus_xy: pd.DataFrame, candidates: np.ndarray | None = None
) -> np.ndarray:
    if candidates is None:
        candidates = bus_xy.index.to_numpy()
    else:
        candidates = pd.Index(candidates).intersection(bus_xy.index).to_numpy()
    tree = cKDTree(bus_xy.loc[candidates, ["x", "y"]].to_numpy())
    _, idx = tree.query(coords)
    return candidates[idx]


def _shares(weights: pd.Series, buses: pd.Index) -> pd.Series:
    w = weights.reindex(buses, fill_value=0.0).clip(lower=0.0)
    total = w.sum()
    if not np.isfinite(total) or total <= 0:
        return pd.Series(1.0 / len(buses), index=buses)
    return w / total


def population_weights(n: pypsa.Network, run: str) -> pd.Series:
    ds = xr.open_dataset(RESOURCES / run / "pop_layout_total.nc")
    da = ds[list(ds.data_vars)[0]]
    xx, yy = np.meshgrid(da.x.values, da.y.values)
    vals = da.values.ravel()
    mask = np.isfinite(vals) & (vals > 0)
    coords = np.column_stack([xx.ravel()[mask], yy.ravel()[mask]])
    ds.close()
    if not mask.any():
        return pd.Series(0.0, index=n.buses.index)
    buses = _nearest_bus(coords, n.buses)
    w = pd.Series(vals[mask], index=buses).groupby(level=0).sum()
    return w.reindex(n.buses.index, fill_value=0.0)


def area_weights(n: pypsa.Network, run: str, base2cluster: pd.Series) -> pd.DataFrame:
    out = {}
    for carrier, fname in AVAILABILITY.items():
        path = RESOURCES / run / f"availability_matrix_{fname}.nc"
        if not path.exists():
            continue
        ds = xr.open_dataset(path)
        da = ds[list(ds.data_vars)[0]]
        xx, yy = np.meshgrid(da.x.values, da.y.values)
        acc = pd.Series(0.0, index=n.buses.index)
        for cluster in da.bus.values:
            grid = da.sel(bus=cluster).values
            mask = np.isfinite(grid) & (grid > 0)
            if not mask.any():
                continue
            coords = np.column_stack([xx[mask], yy[mask]])
            cand = base2cluster.index[base2cluster == cluster].to_numpy()
            if len(cand) == 0:
                continue
            buses = _nearest_bus(coords, n.buses, candidates=cand)
            cnt = pd.Series(1.0, index=buses).groupby(level=0).sum()
            acc = acc.add(cnt, fill_value=0.0)
        ds.close()
        out[carrier] = acc
    return pd.DataFrame(out)


def plant_weights(n: pypsa.Network, run: str, base2cluster: pd.Series) -> pd.DataFrame:
    pp = pd.read_csv(RESOURCES / run / "powerplants.csv").dropna(
        subset=["lat", "lon", "Capacity"]
    )
    carriers = [
        PLANT_CARRIER.get((f, t), PLANT_CARRIER.get((f, "*")))
        for f, t in zip(pp["Fueltype"], pp["Technology"])
    ]
    pp = pp.assign(carrier=carriers).dropna(subset=["carrier"])
    pp = pp.assign(bus=_nearest_bus(pp[["lon", "lat"]].to_numpy(), n.buses))
    w = pp.groupby(["bus", "carrier"])["Capacity"].sum().unstack(fill_value=0.0)
    return w.reindex(index=n.buses.index).fillna(0.0)


def _block(series: pd.Series, share: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(
        np.outer(series.values, share.values),
        index=series.index,
        columns=share.index,
    )


def reconstruct_injections(
    run: str,
    horizon: int,
    base2cluster: pd.Series,
    pop_w: pd.Series,
    area_w: pd.DataFrame,
    plant_w: pd.DataFrame,
) -> dict:
    """Distribute the clustered market result onto the base buses."""
    n = pypsa.Network(RESULTS / run / "networks" / f"solved_{horizon}.nc")
    snapshots = n.snapshots
    buses = base2cluster.index

    gen_parts = []
    for (cluster, carrier), grp in n.generators.groupby(["bus", "carrier"]):
        if carrier == "Brazil import":
            continue
        gb = buses[base2cluster == cluster]
        series = n.generators_t.p[grp.index].sum(axis=1)
        if carrier in VRE_CARRIERS and carrier in area_w:
            w = area_w[carrier]
        elif carrier in plant_w:
            w = plant_w[carrier]
        else:
            w = pd.Series(dtype=float)
        share = _shares(w, gb) if len(w) else _shares(pop_w, gb)
        blk = _block(series, share)
        blk.columns = pd.MultiIndex.from_product([[carrier], blk.columns])
        gen_parts.append(blk)
    gen = pd.concat(gen_parts, axis=1)

    load_parts = []
    for cluster, ld in n.loads.groupby("bus"):
        gb = buses[base2cluster == cluster]
        load_parts.append(_block(n.loads_t.p[ld.index].sum(axis=1), _shares(pop_w, gb)))
    load = pd.concat(load_parts, axis=1)
    load = load.T.groupby(level=0).sum().T

    su_parts = []
    for (cluster, carrier), su in n.storage_units.groupby(["bus", "carrier"]):
        gb = buses[base2cluster == cluster]
        w = plant_w[carrier] if carrier in plant_w else pd.Series(dtype=float)
        share = _shares(w, gb) if len(w) else _shares(pop_w, gb)
        su_parts.append(_block(n.storage_units_t.p[su.index].sum(axis=1), share))

    link_parts = []
    for k, row in n.links.iterrows():
        if row.carrier == "Brazil HVDC":
            continue
        for i in (0, 1):
            bus = row.get(f"bus{i}")
            if bus is None or bus not in n.buses.index:
                continue
            if n.buses.at[bus, "carrier"] != "AC":
                continue
            gb = buses[base2cluster == bus]
            link_parts.append(_block(-n.links_t[f"p{i}"][k], _shares(pop_w, gb)))

    parts = su_parts + link_parts
    storage = (
        pd.concat(parts, axis=1).T.groupby(level=0).sum().T
        if parts
        else pd.DataFrame(index=snapshots)
    )

    import_series = pd.Series(0.0, index=snapshots)
    landing = None
    hvdc = n.links[n.links.carrier == "Brazil HVDC"]
    if len(hvdc):
        link = hvdc.index[0]
        eff = float(n.links.at[link, "efficiency"])
        cluster = n.links.at[link, "bus1"]
        gb = buses[base2cluster == cluster]
        if len(gb):
            bg = base_grid(run)
            lon, lat = float(n.buses.at[cluster, "x"]), float(n.buses.at[cluster, "y"])
            d = np.hypot(bg.buses.loc[gb, "x"] - lon, bg.buses.loc[gb, "y"] - lat)
            landing = d.idxmin()
            import_series = n.links_t.p0[link] * eff

    return {
        "gen": gen,
        "load": load,
        "storage": storage,
        "import": import_series,
        "import_bus": landing,
        "market": n,
    }


def build_network(run: str, injections: dict) -> pypsa.Network:
    """Assemble the full-resolution network with the reconstructed injections."""
    n = base_grid(run)
    market = injections["market"]
    snapshots = market.snapshots
    n.set_snapshots(snapshots)
    n.snapshot_weightings = market.snapshot_weightings.copy()

    gen = injections["gen"]
    load = injections["load"].reindex(snapshots).fillna(0.0)
    st = injections["storage"].reindex(snapshots).fillna(0.0) if len(injections["storage"]) else pd.DataFrame(index=snapshots)
    imp = injections["import"].reindex(snapshots).fillna(0.0)

    net_gen = gen.sum(axis=1) + (st.sum(axis=1) if len(st.columns) else 0.0) + imp
    tot = load.sum(axis=1).replace(0, np.nan)
    residual = net_gen - load.sum(axis=1)
    load = load.add(load.div(tot, axis=0).mul(residual, axis=0).fillna(0.0))

    def add_oneport(kind, names, buses, carriers, psets):
        if not names:
            return
        for c in sorted(set(carriers)):
            if c not in n.carriers.index:
                n.add("Carrier", c)
        df = pd.DataFrame({"bus": buses, "carrier": carriers}, index=names)
        if kind == "Generator":
            df["p_nom"] = [float(np.abs(p).max()) + 1.0 for p in psets]
        n._import_components_from_df(df, kind)
        dyn = n.generators_t if kind == "Generator" else n.loads_t
        dyn.p_set = pd.DataFrame(np.array(psets).T, index=snapshots, columns=names)

    gnames, gbus, gcar, gpset = [], [], [], []
    for (carrier, bus), series in gen.items():
        s = series.reindex(snapshots).fillna(0.0)
        if s.abs().max() <= 0:
            continue
        gnames.append(f"{bus} {carrier}")
        gbus.append(bus)
        gcar.append(carrier)
        gpset.append(s.values)
    if imp.abs().max() > 0 and injections["import_bus"] is not None:
        gnames.append(f"{injections['import_bus']} Brazil import")
        gbus.append(injections["import_bus"])
        gcar.append("Brazil import")
        gpset.append(imp.values)
    if len(st.columns):
        for bus, series in st.items():
            s = series.reindex(snapshots).fillna(0.0)
            if s.abs().max() <= 0:
                continue
            gnames.append(f"{bus} storage")
            gbus.append(bus)
            gcar.append("storage")
            gpset.append(s.values)
    add_oneport("Generator", gnames, gbus, gcar, gpset)

    lnames, lbus, lpset = [], [], []
    for bus, series in load.items():
        s = series.reindex(snapshots).fillna(0.0)
        if s.abs().max() <= 0:
            continue
        lnames.append(f"{bus} load")
        lbus.append(bus)
        lpset.append(s.values)
    add_oneport("Load", lnames, lbus, ["load"] * len(lnames), lpset)

    inj = net_gen - load.sum(axis=1)
    logger.info("injection balance: max |sum| = %.3e MW", float(inj.abs().max()))
    return n


def line_loading(n: pypsa.Network, snapshots=None) -> pd.DataFrame:
    n.lpf(snapshots=snapshots)
    limit = (n.lines.s_nom * n.lines.s_max_pu).replace(0, np.nan)
    return n.lines_t.p0.div(limit, axis=1)


def select_weeks(injections: dict) -> dict[str, pd.DatetimeIndex]:
    """Pick the week (Mon-Sun) with the highest wind, Brazil import and load."""
    market = injections["market"]
    gen = injections["gen"]
    snap = market.snapshots
    wind_cols = [c for c in gen.columns if c[0] in WIND_CARRIERS]
    wind = gen[wind_cols].sum(axis=1)
    imp = injections["import"]
    load = injections["load"].sum(axis=1)
    week = pd.Series(snap.isocalendar().week.to_numpy(), index=snap)
    out = {}
    for label, series in [("max_wind", wind), ("max_import", imp), ("max_load", load)]:
        if series.abs().max() <= 0:
            continue
        w = series.groupby(week).sum().idxmax()
        out[label] = snap[(week == w).to_numpy()]
    return out


def nodal_injection(injections: dict) -> pd.DataFrame:
    """Net injection per bus and snapshot (generation + storage + import - load)."""
    gen = injections["gen"]
    bus_index = sorted(set(gen.columns.get_level_values(1)) | set(injections["load"].columns))
    net = gen.T.groupby(level=1).sum().T.reindex(columns=bus_index, fill_value=0.0)
    st = injections["storage"]
    if len(st.columns):
        net = net.add(st.reindex(columns=bus_index, fill_value=0.0), fill_value=0.0)
    load = injections["load"].reindex(columns=bus_index, fill_value=0.0)
    net = net.sub(load, fill_value=0.0)
    imp = injections["import"]
    if injections["import_bus"] is not None and imp.abs().max() > 0:
        net[injections["import_bus"]] = net[injections["import_bus"]] + imp
    residual = net.sum(axis=1)
    tot = load.sum(axis=1).replace(0, np.nan)
    net = net.sub(load.div(tot, axis=0).mul(residual, axis=0).fillna(0.0), fill_value=0.0)
    return net


def ptdf(n: pypsa.Network):
    """DC power-transfer distribution factors (lines x buses) of the AC grid."""
    n.calculate_dependent_values()
    lines = n.lines[n.lines.active]
    bus_index = n.buses.index
    bus_of = {b: i for i, b in enumerate(bus_index)}
    nbus = len(bus_index)
    nbr = len(lines)
    rows = np.concatenate([lines.bus0.map(bus_of).to_numpy(), lines.bus1.map(bus_of).to_numpy()])
    cols = np.concatenate([np.arange(nbr), np.arange(nbr)])
    vals = np.concatenate([np.ones(nbr), -np.ones(nbr)])
    K = sparse.csc_matrix((vals, (rows, cols)), shape=(nbus, nbr))
    b = 1.0 / lines.x_pu_eff.to_numpy()
    Bbus = (K * sparse.diags(b)) * K.T
    Bred = Bbus[1:, 1:].tocsc()
    lu = splu(Bred)
    T = np.zeros((nbus, nbus))
    T[1:, 1:] = lu.solve(np.eye(nbus - 1))
    return (sparse.diags(b) * K.T) @ T, lines.index


def redispatch(n: pypsa.Network, injections: dict, snapshots: pd.DatetimeIndex, big: float = 1e7):
    """
    Minimum-adjustment redispatch to remove line overloads, per snapshot.

    Nodal adjustments are bounded by the local market generation (down) and a
    dispatchable headroom (up); a costly slack per line keeps the program
    feasible and reports any overload that cannot be relieved.
    """
    P, line_ids = ptdf(n)
    P = sparse.csc_matrix(P)
    limit = (n.lines.s_nom * n.lines.s_max_pu).reindex(line_ids).to_numpy()
    gen = injections["gen"]
    buses = n.buses.index
    gen_bus = gen.T.groupby(level=1).sum().T.reindex(columns=buses, fill_value=0.0)
    net = nodal_injection(injections).reindex(columns=buses, fill_value=0.0)
    up = gen_bus.max(axis=0).to_numpy()
    down = gen_bus.max(axis=0).to_numpy()

    nbus = len(buses)
    nbr = len(line_ids)
    I = sparse.identity(nbr)
    A_ub = sparse.vstack(
        [
            sparse.hstack([P, -P, -I, sparse.csc_matrix((nbr, nbr))]),
            sparse.hstack([-P, P, sparse.csc_matrix((nbr, nbr)), -I]),
        ]
    ).tocsc()
    A_eq = sparse.hstack(
        [np.ones((1, nbus)), -np.ones((1, nbus)), sparse.csc_matrix((1, 2 * nbr))]
    ).tocsc()
    c = np.concatenate([np.ones(2 * nbus), np.full(2 * nbr, big)])
    bounds = (
        [(0, up[i]) for i in range(nbus)]
        + [(0, down[i]) for i in range(nbus)]
        + [(0, None)] * (2 * nbr)
    )

    recs = []
    for t in snapshots:
        p = net.loc[t].to_numpy()
        flow = P @ p
        if (np.abs(flow) <= limit + 1e-6).all():
            recs.append({"snapshot": t, "up": 0.0, "down": 0.0, "residual": 0.0, "slack_used": 0.0})
            continue
        b_ub = np.concatenate([limit - flow, limit + flow])
        res = linprog(
            c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=np.zeros(1), bounds=bounds, method="highs"
        )
        if not res.success:
            logger.warning("redispatch infeasible at %s: %s", t, res.message)
            recs.append({"snapshot": t, "up": np.nan, "down": np.nan, "residual": np.nan})
            continue
        u, d = np.split(res.x[: 2 * nbus], [nbus])
        s = res.x[2 * nbus :]
        over = np.maximum(np.abs(P @ (p + u - d)) - limit, 0.0)
        recs.append(
            {
                "snapshot": t,
                "up": float(u.sum()),
                "down": float(d.sum()),
                "residual": float(over.sum()),
                "slack_used": float(s.sum()),
            }
        )
    return pd.DataFrame(recs).set_index("snapshot")

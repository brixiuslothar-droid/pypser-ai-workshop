# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""Role 3: key figures of the solved baseline per planning year and per node.

Usage: pixi run python workshop/role3/baseline_check.py [run_name]
Writes CSVs to results/<run>/role3/ (ignored by git).
"""

import sys
from pathlib import Path

import pandas as pd
import pypsa

RUN = sys.argv[1] if len(sys.argv) > 1 else "de10-myopic"
YEARS = [2025, 2030, 2035, 2040, 2045, 2050]
OUT = Path(f"results/{RUN}/role3")
OUT.mkdir(parents=True, exist_ok=True)


def year_figures(n, year):
    w = n.snapshot_weightings.generators
    ac = n.buses.index[n.buses.carrier == "AC"]
    load = n.loads_t.p_set.T.groupby(n.loads.bus).sum().T.reindex(columns=ac, fill_value=0)
    price = n.buses_t.marginal_price[ac]
    lw_price = (price * load).mul(w, axis=0).sum().sum() / load.mul(w, axis=0).sum().sum()
    sys_price = (price * load).sum(axis=1) / load.sum(axis=1)  # load-weighted per snapshot

    gen = n.generators_t.p.mul(w, axis=0).sum().groupby(n.generators.carrier).sum() / 1e6
    su = n.storage_units_t.p.clip(lower=0).mul(w, axis=0).sum().groupby(n.storage_units.carrier).sum() / 1e6
    avail = (n.generators_t.p_max_pu * n.generators.p_nom_opt).reindex(columns=n.generators_t.p.columns).dropna(axis=1)
    curt = ((avail - n.generators_t.p[avail.columns]).clip(lower=0).mul(w, axis=0).sum()
            .groupby(n.generators.carrier).sum() / 1e6)
    vres = ["onwind", "offwind-ac", "offwind-dc", "offwind-float", "solar", "solar-hsat"]

    cap_gen = n.generators.groupby("carrier").p_nom_opt.sum() / 1e3
    links = n.links.groupby("carrier").p_nom_opt.sum() / 1e3
    e_store = n.stores.groupby("carrier").e_nom_opt.sum() / 1e3

    co2_eff = n.carriers.co2_emissions.reindex(n.generators.carrier).values
    eff = n.generators.efficiency.values
    fuel = n.generators_t.p.mul(w, axis=0).sum().values / eff
    co2 = (fuel * co2_eff).sum() / 1e6

    gc = n.global_constraints
    co2_mu = -gc.loc["CO2Limit-upper", "mu"] if "CO2Limit-upper" in gc.index else float("nan")

    lines = n.lines_t.p0.abs() / (n.lines.s_nom_opt * n.lines.s_max_pu)
    rec = {
        "year": year,
        "demand_TWh": load.mul(w, axis=0).sum().sum() / 1e6,
        "price_loadweighted": lw_price,
        "price_max": sys_price.max(),
        "price_p99": sys_price.quantile(0.99),
        "hours_price_gt_300": (sys_price > 300).mul(w).sum(),
        "hours_price_lt_1": (sys_price < 1).mul(w).sum(),
        "co2_Mt": co2,
        "co2_cap_shadow_EUR_t": co2_mu,
        "curtailment_vres_TWh": curt.reindex(vres).sum(),
        "curtailment_share": curt.reindex(vres).sum() / (gen.reindex(vres).sum() + curt.reindex(vres).sum()),
        "mean_line_loading": lines.mean().mean(),
        "line_hours_congested_share": (lines > 0.99).mean().mean(),
        "line_volume_TWkm": (n.lines.s_nom_opt * n.lines.length).sum() / 1e6,
    }
    for k, v in gen.items():
        rec[f"gen_{k}_TWh"] = v
    for k, v in su.items():
        rec[f"gen_{k}_TWh"] = v
    for k, v in cap_gen.items():
        rec[f"cap_{k}_GW"] = v
    for k, v in links.items():
        rec[f"cap_{k}_GW"] = v
    for k, v in e_store.items():
        rec[f"store_{k}_GWh"] = v

    node = pd.DataFrame({
        "x": n.buses.loc[ac, "x"], "y": n.buses.loc[ac, "y"],
        "price_mean": price.mul(w, axis=0).sum() / w.sum(),
        "price_p95": price.quantile(0.95),
        "demand_TWh": load.mul(w, axis=0).sum() / 1e6,
        "gen_TWh": n.generators_t.p.mul(w, axis=0).sum().groupby(n.generators.bus).sum().reindex(ac) / 1e6,
        "offwind_GW": n.generators[n.generators.carrier.str.startswith("offwind")].groupby("bus").p_nom_opt.sum().reindex(ac).fillna(0) / 1e3,
        "onwind_GW": n.generators[n.generators.carrier == "onwind"].groupby("bus").p_nom_opt.sum().reindex(ac).fillna(0) / 1e3,
        "solar_GW": n.generators[n.generators.carrier.str.startswith("solar")].groupby("bus").p_nom_opt.sum().reindex(ac).fillna(0) / 1e3,
        "battery_GWh": n.stores[n.stores.carrier == "battery"].groupby(n.stores.bus.str.replace(" battery", "")).e_nom_opt.sum().reindex(ac).fillna(0) / 1e3,
        "h2_GWh": n.stores[n.stores.carrier == "H2"].groupby(n.stores.bus.str.replace(" H2", "")).e_nom_opt.sum().reindex(ac).fillna(0) / 1e3,
    })
    node["net_export_TWh"] = node.gen_TWh - node.demand_TWh
    node["year"] = year
    return rec, node


recs, nodes = [], []
for y in YEARS:
    n = pypsa.Network(f"results/{RUN}/networks/solved_{y}.nc")
    r, nd = year_figures(n, y)
    r["status"] = n.meta.get("status", "") if hasattr(n, "meta") else ""
    recs.append(r)
    nodes.append(nd)

years = pd.DataFrame(recs).set_index("year").T
nodes = pd.concat(nodes)
years.to_csv(OUT / "years.csv")
nodes.to_csv(OUT / "nodes.csv")
pd.set_option("display.width", 200, "display.max_rows", 200, "display.float_format", "{:,.2f}".format)
print(years)
print(nodes[nodes.year.isin([2035, 2045])])

# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""
Results pipeline of role 4 (workshop/decisions.md E6).

Reads the solved networks of every run listed in ``workshop/analysis/runs.yaml``
that has results, computes one set of metrics per run and planning year, the
differences of the comparison pairs, and writes

- ``workshop/results/metrics.csv``      long table: run, horizon, section, metric, unit, value
- ``workshop/results/comparisons.csv``  the same for "run - reference"
- ``workshop/results/figures/*.png|pdf`` figures in the workshop plot style
- ``workshop/results/RESULTS.md``        the report: status, tables, figures, checks

Runs without results are listed as "planned". Only public model results are
used; nothing is read from workshop/inputs/ (decisions.md E7).

    pixi run python workshop/analysis/evaluate.py
    pixi run python workshop/analysis/evaluate.py --runs BASE REF CABLE
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa
import yaml

ROOT = next(p for p in [Path(__file__).resolve(), *Path(__file__).resolve().parents]
            if (p / "workshop/plotstyle").is_dir())
sys.path.insert(0, str(ROOT / "workshop/plotstyle"))
import studystyle as st  # noqa: E402

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HOME = "DE"                        # the country whose actors the study reports
VRE = ("solar", "onwind", "offwind", "ror")
CABLE_TAG = "brazil hvdc"          # carrier of the cable link (role 1/2: "Brazil HVDC")
PRICE_SPIKE = 1000.0               # EUR/MWh: a price above counts as a spike
CAP_FLAG = 1000.0                  # EUR/t: a cap shadow price above is flagged as cap-driven
NET_IMPORT_LIMIT = 25.0           # TWh/a, E3 (role3.net_import_limit)
SHED = "load"                     # carrier of load-shedding generators (solving.options.load_shedding)

# --------------------------------------------------------------------------- config


def deep_update(base: dict, new: dict) -> dict:
    for k, v in (new or {}).items():
        base[k] = deep_update(dict(base.get(k) or {}), v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return base


def run_config(spec: dict) -> dict:
    """Config of a run as Snakemake sees it: default, then the run's config files, then its scenario entry."""
    cfg = yaml.safe_load((ROOT / "config/config.default.yaml").read_text())
    for f in spec.get("configs", []):
        deep_update(cfg, yaml.safe_load((ROOT / f).read_text()) or {})
    if spec.get("scenario"):
        scen = yaml.safe_load((ROOT / spec.get("scenario_file", "config/scenarios.yaml")).read_text())
        deep_update(cfg, scen[spec["scenario"]])
    return cfg


def co2_price(cfg: dict, year: int) -> float:
    ep = cfg.get("costs", {}).get("emission_prices", {})
    if not ep.get("enable"):
        return 0.0
    p = ep.get("co2", 0.0)
    return float(p.get(year, p.get(str(year), 0.0))) if isinstance(p, dict) else float(p)


# --------------------------------------------------------------------------- run logs


def solver_log(run: str, year: int) -> dict:
    d = ROOT / "results" / run / "logs" / "solve_network"
    out = {"status": "n/a", "solve_min": np.nan, "peak_gb": np.nan}
    f = d / f"solver_{year}.log"
    if f.exists():
        m = re.findall(r"Status:\s*(\w+).*?Time:\s*([\d.]+)s", f.read_text())
        if m:
            out["status"], out["solve_min"] = m[-1][0], float(m[-1][1]) / 60
    f = d / f"memory_{year}.log"
    if f.exists():
        mem = [float(x) for x in re.findall(r"MEM\s+([\d.]+)", f.read_text())]
        out["peak_gb"] = max(mem) / 1024 if mem else np.nan
    return out


# --------------------------------------------------------------------------- metrics


def locate(n: pypsa.Network) -> pd.DataFrame:
    """Per component and name: carrier, country (or 'cross-border'), whether it is the cable."""
    rows = []
    for c in ["Generator", "StorageUnit", "Store", "Load", "Link", "Line"]:
        df = n.components[c].static
        if df.empty:
            continue
        if c in ("Link", "Line"):
            c0, c1 = df.bus0.map(n.buses.country), df.bus1.map(n.buses.country)
            country = c0.where(c0 == c1, "cross-border")
        else:
            country = df.bus.map(n.buses.country)
        rows.append(pd.DataFrame({"component": c, "name": df.index, "carrier": df.carrier.values,
                                  "country": country.values}))
    loc = pd.concat(rows).set_index(["component", "name"])
    loc["cable"] = loc.carrier.str.lower().str.contains(CABLE_TAG)
    loc["group"] = loc.carrier.map(st.group)
    return loc


def actor(row) -> str:
    """Who carries the costs and revenues of a component (E6)."""
    if row.cable:
        return "Kabelbetreiber"
    if row.carrier == SHED:
        return f"Verbraucher {row.country}" + ("" if row.country == HOME else " (Ausland)")
    if row.component == "Load":
        return f"Verbraucher {HOME}" if row.country == HOME else f"Verbraucher {row.country}"
    if row.country == "BR":
        return "Erzeuger BR"
    if row.country == "cross-border":
        return "Interkonnektoren"
    if row.country != HOME:
        return f"Ausland {row.country}"
    if row.component in ("Line",) or row.carrier == "DC":
        return f"Netz {HOME}"
    return f"Erzeuger {HOME}: {row.group}"


def metrics(n: pypsa.Network, year: int, cfg: dict) -> list[tuple]:
    """(section, metric, unit, value) for one solved network."""
    out = []
    add = lambda s, m, u, v: out.append((s, m, u, float(v)))  # noqa: E731
    w = n.snapshot_weightings.generators
    loc = locate(n)
    s = n.statistics
    home_ac = n.buses.query("carrier == 'AC' and country == @HOME").index

    # demand and prices ------------------------------------------------------
    loads = n.loads[n.loads.bus.isin(home_ac)]
    lp = n.loads_t.p[loads.index]
    price = n.buses_t.marginal_price[loads.bus.values].set_axis(loads.index, axis=1)
    demand = lp.mul(w, axis=0).sum().sum()
    payments = (lp * price).mul(w, axis=0).sum().sum()
    add("Nachfrage", "Stromnachfrage", "TWh", demand / 1e6)
    ap = n.buses_t.marginal_price[home_ac]
    add("Preise", "Strompreis lastgewichtet", "EUR/MWh", payments / demand)
    add("Preise", "Strompreis Mittel", "EUR/MWh", ap.mean().mean())
    add("Preise", "Strompreis Maximum", "EUR/MWh", ap.max().max())
    add("Preise", f"Stunden mit Preis > {PRICE_SPIKE:.0f} EUR/MWh", "h",
        (ap.max(axis=1) > PRICE_SPIKE).mul(w).sum())
    add("Preise", "Stunden mit Preis < 1 EUR/MWh", "h", (ap.min(axis=1) < 1).mul(w).sum())

    # generation and capacity by group, home country ---------------------------
    sup = s.supply(bus_carrier="AC", groupby=False)
    sup = sup[sup.index.isin(loc.index)]
    gen = loc.loc[sup.index].assign(v=sup.values).reset_index()
    gen = gen[(gen.country == HOME) & gen.component.isin(["Generator", "StorageUnit", "Link"])
              & ~gen.carrier.isin(["DC", "AC", SHED]) & ~gen.cable]
    for g, v in st.by_group(gen.groupby("carrier").v.sum()).items():
        add("Erzeugung", g, "TWh", v / 1e6)

    # load shedding (allowed at 100,000 EUR/MWh in runs with neighbours, E3): must be ~0
    shed = n.generators[(n.generators.carrier == SHED)]
    if not shed.empty:
        p_shed = n.generators_t.p[shed.index].mul(w, axis=0).sum()
        add("Versorgung", "Lastabwurf DE", "GWh",
            p_shed[shed.bus.map(n.buses.country) == HOME].sum() / 1e3)
        add("Versorgung", "Lastabwurf alle Länder", "GWh", p_shed.sum() / 1e3)

    cap = []
    for c, attr in [("Generator", "p_nom_opt"), ("StorageUnit", "p_nom_opt"), ("Link", "p_nom_opt")]:
        df = n.components[c].static
        df = df[df.bus.isin(home_ac)] if c != "Link" else df[df.bus1.isin(home_ac) & df.carrier.isin(
            ["battery discharger", "H2 Fuel Cell"])]
        eff = df.efficiency if c == "Link" else 1.0
        df = df[df.carrier != SHED] if c == "Generator" else df
        cap.append((df[attr] * eff).groupby(df.carrier).sum())
    for g, v in st.by_group(pd.concat(cap).groupby(level=0).sum()).items():
        add("Kapazität", g, "GW", v / 1e3)
    st_e = n.stores[n.stores.bus.map(n.buses.country) == HOME].groupby("carrier").e_nom_opt.sum()
    add("Speicher", "Batteriespeicher Energie", "GWh", st_e.get("battery", 0) / 1e3)
    add("Speicher", "Wasserstoffspeicher Energie", "TWh", st_e.get("H2", 0) / 1e6)

    # curtailment of wind, solar and run-of-river ------------------------------
    g = n.generators[n.generators.carrier.str.startswith(VRE) & n.generators.bus.isin(home_ac)]
    avail = n.get_switchable_as_dense("Generator", "p_max_pu")[g.index] * g.p_nom_opt
    curt = (avail - n.generators_t.p[g.index]).clip(lower=0).mul(w, axis=0).sum().sum()
    add("Erzeugung", "Abregelung Wind, Solar, Laufwasser", "TWh", curt / 1e6)

    # emissions and CO2 prices -------------------------------------------------
    gens = n.generators
    intensity = gens.carrier.map(n.carriers.co2_emissions).fillna(0) / gens.efficiency
    em_by = n.generators_t.p.mul(w, axis=0).sum().mul(intensity.reindex(n.generators_t.p.columns)).fillna(0)
    em_country = em_by.groupby(gens.loc[em_by.index, "bus"].map(n.buses.country)).sum()
    em_home = em_country.get(HOME, 0.0)
    add("CO2", "Emissionen", "Mt", em_home / 1e6)
    cap_name = next((i for i in n.global_constraints.index if i.startswith("CO2Limit-upper")), None)
    shadow = -n.global_constraints.at[cap_name, "mu"] if cap_name else 0.0
    shadow = 0.0 if abs(shadow) < 1e-6 else shadow
    pco2 = co2_price(cfg, year)
    if cap_name:
        add("CO2", "Obergrenze", "Mt", n.global_constraints.at[cap_name, "constant"] / 1e6)
    add("CO2", "CO2-Preis (Config)", "EUR/t", pco2)
    add("CO2", "Schattenpreis der Obergrenze", "EUR/t", shadow)
    add("CO2", "CO2-Preis effektiv", "EUR/t", pco2 + shadow)

    # system cost -------------------------------------------------------------
    capex, opex = s.capex(groupby=False), s.opex(groupby=False)
    add("Systemkosten", "Systemkosten gesamt", "Mrd EUR/a", (capex.sum() + opex.sum()) / 1e9)
    add("Systemkosten", "davon Kapitalkosten", "Mrd EUR/a", capex.sum() / 1e9)
    add("Systemkosten", "davon Betriebskosten", "Mrd EUR/a", opex.sum() / 1e9)
    add("Systemkosten", "davon CO2-Preis (Transfer an den Staat)", "Mrd EUR/a", em_by.sum() * pco2 / 1e9)
    cost_by = loc.reindex(capex.index.union(opex.index)).assign(
        v=capex.reindex(capex.index.union(opex.index), fill_value=0) + opex.reindex(
            capex.index.union(opex.index), fill_value=0))
    cost_by["g"] = np.where(cost_by.carrier.isin(["AC", "DC"]), "Grid", cost_by.group)
    for g_, v in cost_by.groupby("g").v.sum().items():
        add("Systemkosten nach Gruppe", g_, "Mrd EUR/a", v / 1e9)

    # trade with neighbours (cross-border branches without the cable) ----------
    imp = 0.0
    gross_imp = gross_exp = 0.0
    for c in ["Line", "Link"]:
        df = n.components[c].static
        if df.empty:
            continue
        cb = df[(loc.loc[c].reindex(df.index).country == "cross-border") & ~loc.loc[c].reindex(df.index).cable]
        for i, b in [("0", "bus0"), ("1", "bus1")]:
            at_home = cb[cb[b].map(n.buses.country) == HOME].index
            if len(at_home):
                p = n.components[c].dynamic[f"p{i}"][at_home].sum(axis=1)  # >0: power leaves the home bus
                imp -= p.mul(w).sum()
                gross_exp += p.clip(lower=0).mul(w).sum()
                gross_imp += (-p).clip(lower=0).mul(w).sum()
    add("Handel", "Netto-Import", "TWh", imp / 1e6)
    add("Handel", "Import brutto", "TWh", gross_imp / 1e6)
    add("Handel", "Export brutto", "TWh", gross_exp / 1e6)

    # the cable ----------------------------------------------------------------
    cab = n.links[n.links.carrier.str.lower().str.contains(CABLE_TAG)]
    if not cab.empty:
        pn = cab.p_nom_opt.sum()
        p0 = n.links_t.p0[cab.index].sum(axis=1)
        delivered = -n.links_t.p1[cab.index].sum(axis=1).mul(w).sum()
        rev = s.revenue(groupby=False).reindex([("Link", i) for i in cab.index]).sum()
        ccost = (cab.p_nom_opt * cab.capital_cost).sum()
        add("Kabel", "Kapazität", "GW", pn / 1e3)
        br = n.generators[(n.generators.bus.map(n.buses.country) == "BR") & (n.generators.carrier != SHED)]
        if not br.empty:
            add("Kabel", "Erzeugung BR Kapazität", "GW", br.p_nom_opt.sum() / 1e3)
            add("Kabel", "Erzeugung BR", "TWh", n.generators_t.p[br.index].mul(w, axis=0).sum().sum() / 1e6)
        add("Kabel", "Lieferung nach DE", "TWh", delivered / 1e6)
        add("Kabel", "Auslastung", "%", 100 * p0.mul(w).sum() / (pn * w.sum()) if pn > 0 else 0)
        add("Kabel", "Engpasserlös", "Mrd EUR/a", rev / 1e9)
        add("Kabel", "Annuität inkl. FOM", "Mrd EUR/a", ccost / 1e9)
        if pn > 1:
            add("Kabel", "Engpasserlös pro kW", "EUR/kW/a", rev / pn / 1e3)
            add("Kabel", "Annuität pro kW", "EUR/kW/a", ccost / pn / 1e3)
            add("Kabel", "Abstand zum Break-even pro kW", "EUR/kW/a", (rev - ccost) / pn / 1e3)

    # actors (E6): revenue - capital cost - operating cost ---------------------
    rev = s.revenue(groupby=False)
    idx = rev.index.union(capex.index).union(opex.index)
    a = loc.reindex(idx).dropna(subset=["carrier"]).reset_index()
    a["surplus"] = (rev.reindex(idx, fill_value=0) - capex.reindex(idx, fill_value=0)
                    - opex.reindex(idx, fill_value=0)).reindex(pd.MultiIndex.from_frame(a[["component", "name"]])).values
    a["actor"] = a.apply(actor, axis=1)
    # CO2: emitters pay the CO2 price (in opex) to the state; the cap's shadow price is
    # treated as an auctioned certificate, paid by the emitters to the state too.
    co2_pay = em_by * shadow
    emit = a.component.eq("Generator") & a.name.isin(co2_pay.index)
    a.loc[emit, "surplus"] -= co2_pay.reindex(a.loc[emit, "name"]).values
    act = a.groupby("actor").surplus.sum()
    for country, e in em_country.items():
        if e > 0 or country == HOME:
            act[f"Staat {country} (CO2)"] = e * (pco2 + shadow)
    for k, v in act.items():
        add("Akteure", k, "Mrd EUR/a", v / 1e9)
    # CO2 payments are a cost in the objective but a transfer between actors:
    # sum of actors = -(system cost - CO2 price payments)
    add("Akteure", "Summe aller Akteure", "Mrd EUR/a", act.sum() / 1e9)
    return out


# --------------------------------------------------------------------------- hand-off (role 3)


def handoff_metrics(folder: Path, cfg: dict) -> tuple[list[tuple], list[dict]]:
    """
    Metrics of a run from role 3's hand-off CSVs (workshop/role3/handoff/<run>/), used when the
    solved networks are not in this workspace. Same section and metric names as metrics() where the
    definition is the same; where it differs, the metric name says so. Not available from the
    hand-off: actors (no revenues), curtailment, gross trade, nodal price maximum.
    """
    rd = lambda f: pd.read_csv(folder / f) if (folder / f).exists() else pd.DataFrame()  # noqa: E731
    man = yaml.safe_load((folder / "manifest.yaml").read_text())
    pr, sc, eb, cap, co2, tr, cab = (rd(f"{x}.csv") for x in
                                     ("prices_de", "system_costs", "energy_balance", "capacities", "co2",
                                      "trade", "cable"))
    rows, status = [], []
    for y in man["horizons"]:
        out = []
        add = lambda s_, m_, u, v: out.append((s_, m_, u, float(v)))  # noqa: E731
        p = pr[pr.year == y].iloc[0]
        add("Nachfrage", "Stromnachfrage", "TWh", p.demand_twh)
        add("Preise", "Strompreis lastgewichtet", "EUR/MWh", p.price_loadweighted)
        add("Preise", "Strompreis Maximum (lastgewichtetes Mittel DE)", "EUR/MWh", p.price_max)
        add("Preise", "Stunden mit Preis > 300 EUR/MWh", "h", p.hours_gt_300)
        add("Preise", "Stunden mit Preis < 1 EUR/MWh", "h", p.hours_lt_1)

        e = eb[(eb.year == y) & (eb.country == HOME)]
        sup = e[e.component.isin(["Generator", "StorageUnit", "Link"]) & (e.TWh > 0)
                & ~e.carrier.isin(["AC", "DC", SHED])]
        for g, v in st.by_group(sup.groupby("carrier").TWh.sum()).items():
            add("Erzeugung", g, "TWh", v)
        shed = e[e.carrier == SHED].TWh.sum()
        add("Versorgung", "Lastabwurf DE", "GWh", shed * 1e3)
        add("Versorgung", "Lastabwurf alle Länder", "GWh", eb[(eb.year == y) & (eb.carrier == SHED)].TWh.sum() * 1e3)

        c = cap[(cap.year == y) & (cap.country == HOME)]
        gen_cap = c[c.component.isin(["Generator", "StorageUnit"]) & (c.carrier != SHED)]
        dis = c[(c.component == "Link") & c.carrier.isin(["battery discharger", "H2 Fuel Cell"])]
        for g, v in st.by_group(pd.concat([gen_cap, dis]).groupby("carrier").capacity_mw_or_mwh.sum()).items():
            add("Kapazität", g, "GW", v / 1e3)
        stores = c[c.component == "Store"].set_index("carrier").capacity_mw_or_mwh
        add("Speicher", "Batteriespeicher Energie", "GWh", stores.get("Battery Storage", 0) / 1e3)
        add("Speicher", "Wasserstoffspeicher Energie", "TWh", stores.get("Hydrogen Storage", 0) / 1e6)

        k = co2[(co2.year == y)]
        kd = k[k.country == HOME]
        shadow = float(k.cap_shadow_eur_t.iloc[0]) if len(k) else 0.0
        shadow = 0.0 if not np.isfinite(shadow) or abs(shadow) < 1e-6 else shadow
        pco2 = float(k.co2_price_eur_t.iloc[0]) if len(k) else co2_price(cfg, y)
        add("CO2", "Emissionen", "Mt", kd.emissions_mt.sum())
        add("CO2", "CO2-Preis (Config)", "EUR/t", pco2)
        add("CO2", "Schattenpreis der Obergrenze", "EUR/t", shadow)
        add("CO2", "CO2-Preis effektiv", "EUR/t", pco2 + shadow)

        cost = sc[sc.year == y]
        add("Systemkosten", "Systemkosten gesamt", "Mrd EUR/a", (cost.capex_eur_a.sum() + cost.opex_eur_a.sum()) / 1e9)
        add("Systemkosten", "davon Kapitalkosten", "Mrd EUR/a", cost.capex_eur_a.sum() / 1e9)
        add("Systemkosten", "davon Betriebskosten", "Mrd EUR/a", cost.opex_eur_a.sum() / 1e9)
        add("Systemkosten", "davon CO2-Preis (Transfer an den Staat)", "Mrd EUR/a",
            k.emissions_mt.sum() * 1e6 * pco2 / 1e9)
        cg = cost.assign(v=cost.capex_eur_a + cost.opex_eur_a)
        cg["g"] = np.where(cg.carrier.isin(["AC", "DC"]), "Grid",
                           np.where(cg.carrier.str.lower().str.contains(CABLE_TAG), "Brazil cable",
                                    cg.carrier.map(st.group)))
        for g_, v in cg.groupby("g").v.sum().items():
            add("Systemkosten nach Gruppe", g_, "Mrd EUR/a", v / 1e9)

        t = tr[tr.year == y]
        t = t[(t.country_a == HOME) ^ (t.country_b == HOME)]
        t = t[~t.country_a.isin(["BR"]) & ~t.country_b.isin(["BR"])]
        net_imp = (t.loc[t.country_b == HOME, "net_flow_a_to_b_twh"].sum()
                   - t.loc[t.country_a == HOME, "net_flow_a_to_b_twh"].sum())
        add("Handel", "Netto-Import", "TWh", net_imp)

        if not cab.empty and (cab.year == y).any():
            cb = cab[cab.year == y]
            pn = cb.p_nom_opt_mw.sum()
            add("Kabel", "Kapazität", "GW", pn / 1e3)
            add("Kabel", "Lieferung nach DE", "TWh", cb.delivered_twh.sum())
            add("Kabel", "Auslastung", "%", 100 * cb.utilisation.fillna(0).mean())
            ccost = cost[cost.carrier.str.lower().str.contains(CABLE_TAG) & (cost.component == "Link")]
            add("Kabel", "Annuität inkl. FOM", "Mrd EUR/a", ccost.capex_eur_a.sum() / 1e9)
        rows += [(y, *o) for o in out]
        sv = man.get("solver", {}).get(y, {})
        status.append({"horizon": y, "status": sv.get("status", "n/a"), "solve_min": sv.get("solve_min", np.nan),
                       "peak_gb": sv.get("peak_gb", np.nan)})
    return rows, status


# --------------------------------------------------------------------------- figures

FIG_YEARS = None


def save(fig, out: Path, name: str):
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{name}.png", dpi=300)
    fig.savefig(out / f"{name}.pdf")
    plt.close(fig)
    return f"figures/{name}.png"


def wide(m: pd.DataFrame, run: str, section: str) -> pd.DataFrame:
    d = m[(m.run == run) & (m.section == section)]
    return d.pivot_table(index="horizon", columns="metric", values="value", aggfunc="sum")


def run_figures(m: pd.DataFrame, run: str, out: Path) -> list[tuple[str, str]]:
    figs = []
    years = sorted(m[m.run == run].horizon.unique())
    x = np.arange(len(years))

    for section, title, unit in [("Erzeugung", "Electricity generation in Germany", "TWh"),
                                 ("Kapazität", "Generation and storage discharge capacity in Germany", "GW")]:
        df = wide(m, run, section).reindex(years)
        df = df[[g for g in st.GROUPS if g in df.columns]].fillna(0)
        fig, ax = plt.subplots(figsize=(5.6, 3.4))
        st.stacked_bars(ax, x, df)
        ax.set_xticks(x, years)
        ax.set_title(f"{title}, {run}, {unit}", loc="left")
        st.legend_squares(ax, [(st.GROUPS[g], g) for g in reversed(df.columns)],
                          loc="upper left", bbox_to_anchor=(1.0, 1.0))
        figs.append((f"{title} ({unit})", save(fig, out, f"{run}_{section.lower().replace('ä', 'ae')}")))

    df = wide(m, run, "Systemkosten nach Gruppe").reindex(years).fillna(0)
    order = [g for g in [*st.GROUPS, "Grid"] if g in df.columns]
    df = df[order]
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    st.stacked_bars(ax, x, df.rename(columns={"Grid": "AC"}), fmt="{:,.1f}")
    ax.set_xticks(x, years)
    ax.set_title(f"Annual system cost in Germany, {run}, billion EUR", loc="left")
    st.legend_squares(ax, [(st.color("AC") if g == "Grid" else st.GROUPS[g], g) for g in reversed(order)],
                      loc="upper left", bbox_to_anchor=(1.0, 1.0))
    figs.append(("Annual system cost (billion EUR)", save(fig, out, f"{run}_systemkosten")))

    p = wide(m, run, "Preise").reindex(years)
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 3.0))
    st.line(axs[0], years, p["Strompreis lastgewichtet"], st.TEXT, values=True)
    axs[0].set_title("Load-weighted price, EUR/MWh", loc="left")
    axs[0].set_ylim(0, p["Strompreis lastgewichtet"].max() * 1.25)
    pmax = p["Strompreis Maximum"] if "Strompreis Maximum" in p else p["Strompreis Maximum (lastgewichtetes Mittel DE)"]
    st.bars(axs[1], years, pmax.values, color=st.NEUTRAL, width=3.1)
    axs[1].set_title("Highest price, EUR/MWh", loc="left")
    for ax in axs:
        ax.set_xticks(years)
    fig.suptitle(f"Electricity prices in Germany, {run}", x=0.01, ha="left", fontweight="bold", fontsize=9)
    figs.append(("Electricity prices (EUR/MWh)", save(fig, out, f"{run}_preise")))

    c = wide(m, run, "CO2").reindex(years)
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 3.0))
    st.bars(axs[0], years, c["Emissionen"].values, color=st.GROUPS["Gas"], width=3.1)
    axs[0].set_title("CO2 emissions, Mt", loc="left")
    st.line(axs[1], years, c["CO2-Preis (Config)"], st.NEUTRAL, label="CO2 price")
    st.line(axs[1], years, c["CO2-Preis effektiv"], st.TEXT, label="incl. cap", values=True)
    axs[1].set_yscale("log")
    axs[1].set_title("CO2 price, EUR/t (log scale)", loc="left")
    for ax in axs:
        ax.set_xticks(years)
    fig.suptitle(f"CO2 in the German power sector, {run}", x=0.01, ha="left", fontweight="bold", fontsize=9)
    figs.append(("CO2 emissions and price", save(fig, out, f"{run}_co2")))
    return figs


def cap_driven(m: pd.DataFrame, run: str) -> set:
    """Horizons whose CO2 cap adds more than CAP_FLAG EUR/t (E3): marked or left out in summaries."""
    d = m[(m.run == run) & (m.metric == "Schattenpreis der Obergrenze")]
    return set(d[d.value > CAP_FLAG].horizon)


def comparison_figures(cmp: pd.DataFrame, m: pd.DataFrame, out: Path) -> dict:
    figs = {}
    for (run, ref), d in cmp.groupby(["run", "reference"], sort=False):
        years = sorted(d.horizon.unique())
        flagged = cap_driven(m, run) | cap_driven(m, ref)
        kept = [y for y in years if y not in flagged]
        has_cable = (m[(m.run == run) & (m.section == "Kabel") & (m.metric == "Kapazität")].value > 0).any()
        col = st.GROUPS["Brazil cable"] if has_cable else st.TEXT
        sc = d[(d.section == "Systemkosten") & (d.metric == "Systemkosten gesamt")].set_index("horizon").value
        ac = d[d.section == "Akteure"].pivot_table(index="metric", columns="horizon", values="value")
        ac = ac.drop(index="Summe aller Akteure", errors="ignore")

        if ac.empty:  # actors not available for one of the runs (hand-off): one panel only
            fig, ax0 = plt.subplots(figsize=(5.6, 3.4))
            axs = [ax0]
        else:
            fig, axs = plt.subplots(1, 2, figsize=(7.6, 3.2), width_ratios=[1, 1.4])
        bars = st.bars(axs[0], years, sc.reindex(years).values, color=col, width=3.1, fmt="{:+,.2f}")
        for b, y in zip(bars, years):
            if y in flagged:
                b.set_alpha(st.TINT)
        axs[0].axhline(0, color=st.TEXT, lw=0.6)
        axs[0].set_xticks(years)
        axs[0].set_title("Change in system cost, billion EUR/a", loc="left")
        if flagged:
            axs[0].annotate("light: CO2 cap > 1,000 EUR/t (E3)", (0, -0.16), xycoords="axes fraction",
                            fontsize=7, color=st.FAINT)
        if ac.empty:
            fig.suptitle(f"{run} minus {ref}", x=0.01, ha="left", fontweight="bold", fontsize=9)
            figs[(run, ref)] = [(f"{run} − {ref}", save(fig, out, f"diff_{run}_vs_{ref}"))]
            continue
        tot = ac[kept].mean(axis=1).sort_values() if kept else ac.mean(axis=1).sort_values()
        axs[1].barh(range(len(tot)), tot.values, height=0.6, lw=0,
                    color=[st.GROUPS["Brazil cable"] if ("Kabel" in i or "BR" in i) else st.NEUTRAL
                           for i in tot.index])
        axs[1].set_yticks(range(len(tot)), tot.index, fontsize=7)
        axs[1].axvline(0, color=st.TEXT, lw=0.6)
        axs[1].grid(axis="y", visible=False)
        axs[1].grid(axis="x", visible=True)
        span = f"{kept[0]}-{kept[-1]}" if kept else f"{years[0]}-{years[-1]}"
        axs[1].set_title(f"Change in surplus by actor, mean {span}, billion EUR/a", loc="left")
        fig.suptitle(f"{run} minus {ref}", x=0.01, ha="left", fontweight="bold", fontsize=9)
        figs[(run, ref)] = [(f"{run} − {ref}", save(fig, out, f"diff_{run}_vs_{ref}"))]
    return figs


# --------------------------------------------------------------------------- grid (role 6)

GRID_CSV = "grid.csv"
WEEKS = {"max_wind": "Woche max. Wind", "max_import": "Woche max. Brasilien-Import", "max_load": "Woche max. Last"}


def grid_metrics(run_name: str, horizon: int) -> pd.DataFrame:
    """
    Full-grid loading and redispatch of one solved run (role 6, workshop/network/full_grid.py).

    The 10-node market result is spread onto the simplified German grid (470 buses), a DC load flow
    runs over three stress weeks and a PTDF redispatch clears the overloads. Absolute values are a
    reconstruction (order of magnitude); the comparison with/without cable is the robust part.
    Weights each snapshot with its duration (2 h baseline, 4 h runs with neighbours).
    """
    import os
    cwd = os.getcwd()
    os.chdir(ROOT)                       # full_grid.py uses paths relative to the repo root
    try:
        sys.path.insert(0, str(ROOT))
        import workshop.network.full_grid as fg
        b2c = fg.read_cluster_map(run_name)
        grid = fg.base_grid(run_name)
        inj = fg.reconstruct_injections(run_name, horizon, b2c, fg.population_weights(grid, run_name),
                                         fg.area_weights(grid, run_name, b2c), fg.plant_weights(grid, run_name, b2c))
        n = fg.build_network(run_name, inj)
        weeks = fg.select_weeks(inj)
        snaps = pd.DatetimeIndex(sorted(set().union(*weeks.values())))
        loading = fg.line_loading(n, snaps).abs()
        rd = fg.redispatch(n, inj, snaps)
        hours = inj["market"].snapshot_weightings.generators
    finally:
        os.chdir(cwd)
    rows = []
    for key, w in weeks.items():
        ld = loading.reindex(w)
        label = WEEKS.get(key, key)
        r = rd.set_index("snapshot") if "snapshot" in rd.columns else rd
        r = r.reindex(w)
        rows += [
            ("Netz", f"{label}: überlastete Leitungsstunden", "%", 100 * float(ld.gt(1).to_numpy().mean())),
            ("Netz", f"{label}: Leitungen über 2x Grenze", "Anzahl", float(ld.max().gt(2).sum())),
            ("Netz", f"{label}: Redispatch (abregeln)", "GWh/Woche",
             float((r["down"] * hours.reindex(w)).sum() / 1e3)),
        ]
    return pd.DataFrame(rows, columns=["section", "metric", "unit", "value"])


def run_grid(spec: dict, jobs: list[str], out: Path) -> None:
    """--grid LABEL:YEAR ...: compute and store in grid.csv (kept between pipeline runs)."""
    f = out / GRID_CSV
    old = pd.read_csv(f) if f.exists() else pd.DataFrame(columns=["run", "horizon", "section", "metric", "unit", "value"])
    for job in jobs:
        label, year = job.split(":")
        year = int(year)
        r = spec["runs"][label]
        if not (ROOT / "results" / r["run_name"] / "networks" / f"solved_{year}.nc").exists():
            print(f"grid {label} {year}: no solved network, skipped")
            continue
        if not (ROOT / "resources" / r["run_name"] / "networks" / "simplified.nc").exists():
            print(f"grid {label} {year}: resources/{r['run_name']}/networks/simplified.nc missing, skipped")
            continue
        print(f"grid {label} {year} (several minutes)", flush=True)
        g = grid_metrics(r["run_name"], year).assign(run=label, horizon=year)
        old = pd.concat([old[~((old.run == label) & (old.horizon == year))], g])
    old[["run", "horizon", "section", "metric", "unit", "value"]].to_csv(f, index=False)


# --------------------------------------------------------------------------- report


def md_table(df: pd.DataFrame, fmt="{:,.1f}") -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join([df.index.name or ""] + cols) + " |",
             "|" + "---|" * (len(cols) + 1)]
    for i, r in df.iterrows():
        cells = ["" if pd.isna(v) else (fmt.format(v) if isinstance(v, (int, float, np.floating)) else str(v))
                 for v in r.values]
        lines.append("| " + " | ".join([str(i)] + cells) + " |")
    return "\n".join(lines)


def section_tables(m: pd.DataFrame, run: str) -> str:
    d = m[m.run == run]
    parts = []
    for section in d.section.unique():
        t = d[d.section == section].pivot_table(index=["metric", "unit"], columns="horizon", values="value",
                                                sort=False)
        t.index = [f"{a} ({u})" for a, u in t.index]
        t.index.name = section
        fmt = "{:,.0f}" if section in ("Preise", "Akteure_") else "{:,.1f}"
        parts.append(f"#### {section}\n\n" + md_table(t, fmt))
    return "\n\n".join(parts)


def checks(m: pd.DataFrame, status: pd.DataFrame) -> list[str]:
    out = []
    for _, r in status.iterrows():
        if r.status not in ("Optimal", "n/a"):
            out.append(f"- {r.run} {r.horizon}: Solverstatus **{r.status}** (BASELINE.md: imprecise ist nutzbar)")
        if r.peak_gb > 7.0:
            out.append(f"- {r.run} {r.horizon}: Spitzenspeicher {r.peak_gb:.1f} GB, nahe an der Grenze von 8 GB")
    v = m.set_index(["run", "horizon", "section", "metric"]).value
    for (run, y, sec, met), val in v.items():
        if sec == "CO2" and met == "Schattenpreis der Obergrenze" and val > CAP_FLAG:
            out.append(f"- {run} {y}: Die CO2-Obergrenze kostet {val:,.0f} EUR/t zusätzlich: Ergebnis ist "
                       "cap-getrieben (README, E3)")
        if sec == "Preise" and met == "Strompreis Maximum" and val > PRICE_SPIKE:
            out.append(f"- {run} {y}: Höchster Strompreis {val:,.0f} EUR/MWh")
        if sec == "Akteure" and met.startswith("Summe"):
            sc = v.get((run, y, "Systemkosten", "Systemkosten gesamt"), np.nan) - v.get(
                (run, y, "Systemkosten", "davon CO2-Preis (Transfer an den Staat)"), 0.0)
            if abs(val + sc) > 0.01 * abs(sc):
                out.append(f"- {run} {y}: Akteure schließen nicht: Summe {val:,.1f} gegen "
                           f"−(Systemkosten − CO2-Transfer) {-sc:,.1f} Mrd EUR/a")
        if sec == "Handel" and met == "Netto-Import" and val > NET_IMPORT_LIMIT * 1.02:
            out.append(f"- {run} {y}: Netto-Import {val:,.1f} TWh über der Grenze von E3 "
                       f"({NET_IMPORT_LIMIT:.0f} TWh/a); nur zulässig in Läufen ohne E3-Grenze")
        if sec == "Versorgung" and met == "Lastabwurf alle Länder" and val > 1.0:
            out.append(f"- {run} {y}: Lastabwurf {val:,.1f} GWh (zugelassen zu 100.000 EUR/MWh, sollte ~0 sein)")
        if sec == "Kabel" and met == "Kapazität" and val > 19.9:
            out.append(f"- {run} {y}: Kabel an der Obergrenze von 20 GW (E1)")
    return out or ["- keine Auffälligkeiten"]


def git_rev() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True).stdout.strip()
    except Exception:
        return "n/a"


def report(spec: dict, m: pd.DataFrame, cmp: pd.DataFrame, status: pd.DataFrame, figs: dict, out: Path,
           source: dict | None = None):
    source = source or {}
    L = []
    L += ["<!--", "SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>", "",
          "SPDX-License-Identifier: CC-BY-4.0", "-->", "",
          "# Ergebnisse der Studie: Kabel Brasilien–Deutschland", "",
          f"Erzeugt von `workshop/analysis/evaluate.py` am {datetime.now():%Y-%m-%d %H:%M}, Commit {git_rev()}. "
          "Nicht von Hand ändern: Die Datei wird bei jedem Lauf neu geschrieben. Befunde und Deutung stehen "
          "in `workshop/results/notes.md` und werden unten eingebunden.", "",
          "Studiendesign, Parameter und Szenarien: `workshop/decisions.md`. Nur öffentliche Modellergebnisse; "
          "keine Daten aus `workshop/inputs/` (E7).", "",
          "## Inhalt", "", "1. [Status der Läufe](#1-status-der-läufe)", "2. [Befunde](#2-befunde)",
          "3. [Auffälligkeiten](#3-auffälligkeiten)", "4. [Vergleiche](#4-vergleiche)",
          "5. [Ergebnisse je Lauf](#5-ergebnisse-je-lauf)", "6. [Definitionen](#6-definitionen)",
          "7. [Dateien](#7-dateien)", ""]

    L += ["## 1. Status der Läufe", ""]
    rows = []
    for name, r in spec["runs"].items():
        st_ = status[status.run == name]
        done = sorted(m[m.run == name].horizon.unique())
        rows.append({"Lauf": name, "Run-Name": f"`{r['run_name']}`", "Status":
                     "fertig" if len(done) == len(spec["horizons"]) else ("teilweise" if done else "geplant"),
                     "Jahre": ", ".join(map(str, done)) or "–",
                     "Solver": ", ".join(sorted(set(st_.status))) or "–",
                     "Spitzenspeicher (GB)": f"{st_.peak_gb.max():.1f}" if len(st_) and st_.peak_gb.notna().any() else "–",
                     "Quelle": source.get(name, "–"),
                     "Beschreibung": r.get("description", "")
                     + (f" — **fehlt:** {'; '.join(r['missing'])}" if r.get("missing") and not done else "")})
    L += [md_table(pd.DataFrame(rows).set_index("Lauf")), ""]

    notes = out / "notes.md"
    L += ["## 2. Befunde", "", notes.read_text().strip() if notes.exists() else "_noch keine_", ""]
    L += ["## 3. Auffälligkeiten", "", "Automatisch geprüft (Schwellen in `evaluate.py`).", "",
          *checks(m, status), ""]

    L += ["## 4. Vergleiche", ""]
    if cmp.empty:
        L += ["_Noch kein Vergleichspaar mit Ergebnissen für beide Läufe._", ""]
    for (run, ref), d in cmp.groupby(["run", "reference"], sort=False):
        L += [f"### {run} − {ref}", ""]
        desc = {k: spec["runs"][k].get("description", "") for k in (run, ref)}
        L += [f"- **{run}**: {desc[run]}", f"- **{ref}**: {desc[ref]}", ""]
        flagged = cap_driven(m, run) | cap_driven(m, ref)
        sc = d[(d.section == "Systemkosten") & (d.metric == "Systemkosten gesamt")].set_index("horizon").value
        years = sorted(sc.index)
        kept = [y for y in years if y not in flagged]
        summ = {"alle Jahre": years}
        if flagged:
            summ[f"ohne {', '.join(map(str, sorted(flagged)))} (cap-getrieben, E3)"] = kept
        rows = []
        for label, ys in summ.items():
            rows.append({"Zusammenfassung": label,
                         "Δ Systemkosten, Mittel (Mrd EUR/a)": sc.reindex(ys).mean(),
                         "Δ Systemkosten, Summe der Jahre (Mrd EUR/a)": sc.reindex(ys).sum()})
        L += [md_table(pd.DataFrame(rows).set_index("Zusammenfassung"), "{:+,.2f}"),
              "", "Negativ = der Lauf ist billiger als die Referenz. Jedes Jahr ist ein Stichjahr "
              "(ein Jahr Betrieb), kein Barwert.", ""]
        key = d[d.section.isin(["Systemkosten", "Preise", "CO2", "Handel", "Versorgung", "Kabel", "Netz",
                                "Akteure"])]
        t = key.pivot_table(index=["section", "metric", "unit"], columns="horizon", values="value", sort=False)
        t.index = [f"{s}: {a} ({u})" for s, a, u in t.index]
        t.index.name = "Differenz"
        L += [md_table(t, "{:+,.2f}"), ""]
        for title, path in figs.get(("cmp", run, ref), []):
            L += [f"![{title}]({path})", ""]

    L += ["## 5. Ergebnisse je Lauf", ""]
    for name in spec["runs"]:
        if name not in m.run.unique():
            continue
        L += [f"### {name}: {spec['runs'][name].get('description', '')}", ""]
        for title, path in figs.get(("run", name), []):
            L += [f"![{title}]({path})", ""]
        L += [section_tables(m, name), ""]

    L += ["## 6. Definitionen", "",
          "- **Deutschland**: alle AC-Knoten mit `country == DE`. Erzeugung, Kapazität, Preise, Emissionen "
          "und Akteure beziehen sich darauf; Systemkosten auf das ganze Modell.",
          "- **Systemkosten**: Kapitalkosten (Annuität inkl. FOM aller aktiven Anlagen, auch Bestand) + "
          "Betriebskosten (inkl. CO2-Preis) eines Jahres, `n.statistics.capex()` + `opex()`. In Differenzen "
          "heben sich die Bestandsanlagen auf. Die Zielfunktion des Solvers ist kleiner: Bei myopic stehen "
          "die Kapitalkosten des Bestands dort nicht drin.",
          "- **Strompreis lastgewichtet**: Σ Last × Knotenpreis / Σ Last.",
          "- **Kapazität**: Generatoren und Speicher am deutschen AC-Netz; Batterie und Brennstoffzelle als "
          "Entladeleistung.",
          "- **CO2-Preis effektiv**: CO2-Preis aus der Config + Schattenpreis der CO2-Obergrenze.",
          "- **Netto-Import**: Fluss über grenzüberschreitende Leitungen nach Deutschland, ohne das Kabel.",
          "- **Kabel**: Link mit Carrier „Brazil HVDC“. Engpasserlös = Σ (Preis DE × Lieferung − Preis BR × "
          "Einspeisung); Abstand zum Break-even = Engpasserlös pro kW − Annuität pro kW (E5).",
          "- **Akteure** (E6): je Akteur Erlöse − Kapitalkosten − Betriebskosten. Verbraucher: −Zahlungen. "
          "Emittenten zahlen den CO2-Preis und den Schattenpreis der Obergrenze an den Staat (als ob "
          "Zertifikate versteigert würden). CO2-Zahlungen sind Transfers zwischen Akteuren: Die Summe aller "
          "Akteure = −(Systemkosten − CO2-Preis-Zahlungen). In Differenzen zweier Läufe ist das der "
          "Wohlfahrtsgewinn ohne CO2-Bewertung; die Emissionsänderung steht getrennt unter CO2.",
          "- **Quelle Handoff**: Läufe, deren gelöste Netze nicht in diesem Workspace liegen, werden aus den "
          "CSVs von Rolle 3 gelesen (`workshop/role3/handoff/<run>/`, `export_handoff.py`). Gleiche Definitionen "
          "wie oben, mit drei Abweichungen: Netto-Import an der Sendeseite (wie die Importgrenze ihn zählt); "
          "Höchstpreis = Maximum des lastgewichteten DE-Preises statt des höchsten Knotenpreises; Spitzenstunden "
          "> 300 statt > 1.000 EUR/MWh. Erzeugung = positive Netto-Einspeisung je Technologie. Nicht verfügbar: "
          "Akteure, Abregelung, Brutto-Handel.",
          "- **Lastabwurf**: in Läufen mit Nachbarn zu 100.000 EUR/MWh zugelassen (E3); zählt als Kosten der "
          "Verbraucher, nicht als Erzeugung.",
          "- **Netz** (Rolle 6, `workshop/network/`, nur auf Anforderung mit `--grid`): Marktergebnis auf das "
          "vereinfachte deutsche Netz (470 Knoten) verteilt, DC-Lastfluss in drei Stresswochen, Redispatch über "
          "PTDF. **Rekonstruktion**: absolute Werte sind eine Größenordnung, belastbar ist der Vergleich mit/ohne "
          "Kabel. Heutige Leitungskapazitäten, kein N-1. Von Rolle 5 noch nicht geprüft.",
          ""]
    L += ["## 7. Dateien", "",
          "| Datei | Inhalt |", "|---|---|",
          "| `metrics.csv` | alle Kennzahlen, lang: run, horizon, section, metric, unit, value |",
          "| `comparisons.csv` | Differenzen run − reference, gleiche Spalten + reference |",
          "| `status.csv` | Solverstatus, Lösezeit und Spitzenspeicher je Lauf und Jahr |",
          "| `grid.csv` | Netzanalyse (Rolle 6) je Lauf und Jahr, bleibt zwischen Läufen erhalten |",
          "| `figures/` | Abbildungen als PNG (300 dpi) und PDF |",
          "| `notes.md` | Befunde und Deutung, von Hand gepflegt |", ""]
    (out / "RESULTS.md").write_text("\n".join(L))


# --------------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--spec", type=Path, default=ROOT / "workshop/analysis/runs.yaml")
    ap.add_argument("--out", type=Path, default=ROOT / "workshop/results")
    ap.add_argument("--runs", nargs="*", help="only these runs (default: all with results)")
    ap.add_argument("--grid", nargs="*", default=[], metavar="LABEL:YEAR",
                    help="also run the full-grid analysis (role 6) for these runs and years, e.g. BASE:2040 "
                         "BRIMP:2040; several minutes each; stored in grid.csv and kept")
    ap.add_argument("--force", action="store_true",
                    help="evaluate even while a solve is running (risks killing the solve, see skill)")
    a = ap.parse_args()

    # The workspace's memory limit is shared: a solve needs up to ~7 GB, loading a network ~1-2 GB.
    # Running both at once has already got a solve killed (OOM). Do not evaluate during a solve.
    # match the solve's python process only; "pgrep -f" alone also matches shells whose command line
    # merely mentions the pattern (e.g. a wrapper that calls this script)
    busy = [line for line in subprocess.run(["pgrep", "-af", "solve_network"], capture_output=True,
                                             text=True).stdout.splitlines()
            if "python" in line.split(maxsplit=2)[1] and "solve_network.py" in line]
    if busy and not a.force:
        sys.exit("A solve is running (solve_network.py). Wait until it has finished, "
                 "or pass --force if you accept the risk of an out-of-memory kill.")

    spec = yaml.safe_load(a.spec.read_text())
    a.out.mkdir(parents=True, exist_ok=True)
    st.use()

    rows, status, source = [], [], {}
    for name, r in spec["runs"].items():
        if a.runs and name not in a.runs:
            continue
        cfg = run_config(r)
        nets = [y for y in spec["horizons"]
                if (ROOT / "results" / r["run_name"] / "networks" / f"solved_{y}.nc").exists()]
        if not nets and r.get("handoff") and (ROOT / r["handoff"] / "manifest.yaml").exists():
            print(f"{name}: from hand-off {r['handoff']} (no solved networks here)", flush=True)
            hr, hs = handoff_metrics(ROOT / r["handoff"], cfg)
            rows += [(name, *t) for t in hr]
            status += [{"run": name, **x} for x in hs]
            source[name] = f"Handoff `{r['handoff']}`"
            continue
        for y in spec["horizons"]:
            f = ROOT / "results" / r["run_name"] / "networks" / f"solved_{y}.nc"
            if not f.exists():
                continue
            source[name] = "gelöste Netze"
            print(f"{name} {y}", flush=True)
            n = pypsa.Network(f)
            rows += [(name, y, *t) for t in metrics(n, y, cfg)]
            status.append({"run": name, "horizon": y, **solver_log(r["run_name"], y)})
            del n
    m = pd.DataFrame(rows, columns=["run", "horizon", "section", "metric", "unit", "value"])
    status = pd.DataFrame(status, columns=["run", "horizon", "status", "solve_min", "peak_gb"])
    if a.runs:  # keep the other runs' results from the last full evaluation
        for df_name in ("metrics", "status"):
            f = a.out / f"{df_name}.csv"
            if f.exists():
                old = pd.read_csv(f)
                old = old[~old.run.isin(a.runs) & old.run.isin(spec["runs"])]
                if df_name == "metrics":
                    m = pd.concat([old[old.section != "Netz"], m], ignore_index=True)
                else:
                    status = pd.concat([old, status], ignore_index=True)
    if a.grid:
        run_grid(spec, a.grid, a.out)
    if (a.out / GRID_CSV).exists():
        g = pd.read_csv(a.out / GRID_CSV)
        m = pd.concat([m, g[g.run.isin(m.run.unique())][m.columns]], ignore_index=True)

    cmp = []
    for run, ref in spec.get("comparisons", []):
        x, y_ = m[m.run == run], m[m.run == ref]
        if x.empty or y_.empty:
            continue
        j = x.merge(y_, on=["horizon", "section", "metric", "unit"], how="outer", suffixes=("", "_ref"))
        j = j[j.horizon.isin(set(x.horizon) & set(y_.horizon))]
        # A metric missing on one side is 0 only for technology groups and the cable (absent = none).
        # Elsewhere it means "not measured" (grid only with --grid; actors, curtailment and gross
        # trade not in role 3's hand-off; differently defined metrics): compare only where both exist.
        zero_ok = j.section.isin(["Erzeugung", "Kapazität", "Systemkosten nach Gruppe", "Kabel", "Speicher"])
        j = j[zero_ok | (j.value.notna() & j.value_ref.notna())]
        j["value"] = j.value.fillna(0) - j.value_ref.fillna(0)
        j["run"], j["reference"] = run, ref
        cmp.append(j[["run", "reference", "horizon", "section", "metric", "unit", "value"]])
    cmp = pd.concat(cmp) if cmp else pd.DataFrame(
        columns=["run", "reference", "horizon", "section", "metric", "unit", "value"])

    m.to_csv(a.out / "metrics.csv", index=False)
    cmp.to_csv(a.out / "comparisons.csv", index=False)
    status.to_csv(a.out / "status.csv", index=False)

    figs = {}
    for name in m.run.unique():
        figs[("run", name)] = run_figures(m, name, a.out / "figures")
    for (run, ref), lst in comparison_figures(cmp, m, a.out / "figures").items():
        figs[("cmp", run, ref)] = lst
    if a.runs and (a.out / "sources.csv").exists():
        old = pd.read_csv(a.out / "sources.csv")
        source = {**dict(zip(old.run, old.source)), **source}
    pd.DataFrame({"run": list(source), "source": list(source.values())}).to_csv(a.out / "sources.csv", index=False)
    report(spec, m, cmp, status, figs, a.out, source)
    print(f"written: {a.out / 'RESULTS.md'}")


if __name__ == "__main__":
    main()

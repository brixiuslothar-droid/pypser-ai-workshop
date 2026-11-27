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
              & ~gen.carrier.isin(["DC", "AC"]) & ~gen.cable]
    for g, v in st.by_group(gen.groupby("carrier").v.sum()).items():
        add("Erzeugung", g, "TWh", v / 1e6)

    cap = []
    for c, attr in [("Generator", "p_nom_opt"), ("StorageUnit", "p_nom_opt"), ("Link", "p_nom_opt")]:
        df = n.components[c].static
        df = df[df.bus.isin(home_ac)] if c != "Link" else df[df.bus1.isin(home_ac) & df.carrier.isin(
            ["battery discharger", "H2 Fuel Cell"])]
        eff = df.efficiency if c == "Link" else 1.0
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
    st.bars(axs[1], years, p["Strompreis Maximum"].values, color=st.NEUTRAL, width=3.1)
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
        if sec == "Handel" and met == "Netto-Import" and val > 25.5:
            out.append(f"- {run} {y}: Netto-Import {val:,.1f} TWh über dem Ziel von E3 (~25 TWh)")
        if sec == "Kabel" and met == "Kapazität" and val > 19.9:
            out.append(f"- {run} {y}: Kabel an der Obergrenze von 20 GW (E1)")
    return out or ["- keine Auffälligkeiten"]


def git_rev() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True).stdout.strip()
    except Exception:
        return "n/a"


def report(spec: dict, m: pd.DataFrame, cmp: pd.DataFrame, status: pd.DataFrame, figs: dict, out: Path):
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
                     "Beschreibung": r.get("description", "")})
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
        key = d[d.section.isin(["Systemkosten", "Preise", "CO2", "Handel", "Kabel", "Akteure"])]
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
          ""]
    L += ["## 7. Dateien", "",
          "| Datei | Inhalt |", "|---|---|",
          "| `metrics.csv` | alle Kennzahlen, lang: run, horizon, section, metric, unit, value |",
          "| `comparisons.csv` | Differenzen run − reference, gleiche Spalten + reference |",
          "| `status.csv` | Solverstatus, Lösezeit und Spitzenspeicher je Lauf und Jahr |",
          "| `figures/` | Abbildungen als PNG (300 dpi) und PDF |",
          "| `notes.md` | Befunde und Deutung, von Hand gepflegt |", ""]
    (out / "RESULTS.md").write_text("\n".join(L))


# --------------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--spec", type=Path, default=ROOT / "workshop/analysis/runs.yaml")
    ap.add_argument("--out", type=Path, default=ROOT / "workshop/results")
    ap.add_argument("--runs", nargs="*", help="only these runs (default: all with results)")
    ap.add_argument("--force", action="store_true",
                    help="evaluate even while a solve is running (risks killing the solve, see skill)")
    a = ap.parse_args()

    # The workspace's memory limit is shared: a solve needs up to ~7 GB, loading a network ~1-2 GB.
    # Running both at once has already got a solve killed (OOM). Do not evaluate during a solve.
    busy = subprocess.run(["pgrep", "-f", "solve_network.py"], capture_output=True, text=True).stdout.split()
    if busy and not a.force:
        sys.exit("A solve is running (solve_network.py). Wait until it has finished, "
                 "or pass --force if you accept the risk of an out-of-memory kill.")

    spec = yaml.safe_load(a.spec.read_text())
    a.out.mkdir(parents=True, exist_ok=True)
    st.use()

    rows, status = [], []
    for name, r in spec["runs"].items():
        if a.runs and name not in a.runs:
            continue
        cfg = run_config(r)
        for y in spec["horizons"]:
            f = ROOT / "results" / r["run_name"] / "networks" / f"solved_{y}.nc"
            if not f.exists():
                continue
            print(f"{name} {y}", flush=True)
            n = pypsa.Network(f)
            rows += [(name, y, *t) for t in metrics(n, y, cfg)]
            status.append({"run": name, "horizon": y, **solver_log(r["run_name"], y)})
            del n
    m = pd.DataFrame(rows, columns=["run", "horizon", "section", "metric", "unit", "value"])
    status = pd.DataFrame(status, columns=["run", "horizon", "status", "solve_min", "peak_gb"])

    cmp = []
    for run, ref in spec.get("comparisons", []):
        x, y_ = m[m.run == run], m[m.run == ref]
        if x.empty or y_.empty:
            continue
        j = x.merge(y_, on=["horizon", "section", "metric", "unit"], how="outer", suffixes=("", "_ref"))
        j = j[j.horizon.isin(set(x.horizon) & set(y_.horizon))]
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
    report(spec, m, cmp, status, figs, a.out)
    print(f"written: {a.out / 'RESULTS.md'}")


if __name__ == "__main__":
    main()

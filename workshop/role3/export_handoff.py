# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""Role 3: compact, run-independent hand-off of a solved run for role 4.

Usage: pixi run python workshop/role3/export_handoff.py RUN [--out DIR] [--configs F [F ...]]

Reads results/RUN/networks/solved_<year>.nc (and the solver logs) and writes
small CSV files plus manifest.yaml, one folder per run, always the same shape:

  manifest.yaml     run, git commit, horizons, solver status, run time, peak memory,
                    config files, cost and trade definitions
  system_costs.csv  year, component, country, carrier: capex, opex (EUR/a)
  objective.csv     year: solver objective (extendable assets only, EUR/a) and the
                    system cost (all assets, EUR/a); the two differ, see manifest
  energy_balance.csv year, country, carrier: TWh on AC buses (+ supply, - use)
  capacities.csv    year, country, carrier: optimal capacity (MW, or MWh for stores)
  prices_nodes.csv  year, bus: mean, p95, hours above 300 and below 1 EUR/MWh
  prices_de.csv     year: DE load-weighted price and the same hour counts
  trade.csv         year, country_a, country_b: net flow a -> b (TWh, sending end)
  co2.csv           year, country: emissions (Mt); cap shadow price; CO2 price used
  cable.csv         only if the run has a Brazil cable: capacity, flows, utilisation

Only aggregates by country and carrier (and per node for prices); nothing per
power plant unit. Does not read workshop/inputs. Run it when no solve is
running: loading a network takes about 1 GB.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa
import yaml

ROOT = Path(__file__).resolve().parents[2]
YEARS = [2025, 2030, 2035, 2040, 2045, 2050]
HOME = "DE"
CABLE_TAG = "brazil"


def log_info(run, year):
    d = ROOT / "results" / run / "logs" / "solve_network"
    out = {"status": "n/a", "solve_min": None, "peak_gb": None}
    f = d / f"solver_{year}.log"
    if f.exists():
        m = re.findall(r"Status:\s*(\w+).*?Time:\s*([\d.]+)s", f.read_text())
        if m:
            out["status"], out["solve_min"] = m[-1][0], round(float(m[-1][1]) / 60, 2)
    f = d / f"memory_{year}.log"
    if f.exists():
        mem = [float(x) for x in re.findall(r"MEM\s+([\d.]+)", f.read_text())]
        out["peak_gb"] = round(max(mem) / 1024, 2) if mem else None
    return out


def merged_config(files):
    def deep(a, b):
        for k, v in b.items():
            a[k] = deep(a.get(k, {}), v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
        return a

    cfg = {}
    for f in ["config/config.default.yaml", *files]:
        p = ROOT / f
        if p.exists():
            cfg = deep(cfg, yaml.safe_load(p.read_text()) or {})
    return cfg


def configs_for(run):
    spec = ROOT / "workshop/analysis/runs.yaml"
    if spec.exists():
        for r in (yaml.safe_load(spec.read_text()).get("runs") or {}).values():
            if r.get("run_name") == run:
                return list(r.get("configs") or [])
    return []


def co2_price(cfg, year):
    p = cfg.get("costs", {}).get("emission_prices", {})
    if not p.get("enable", False):
        return np.nan
    v = p.get("co2")
    if isinstance(v, dict):
        v = v.get(year, v.get(str(year)))
    return np.nan if v is None else float(v)


def country_of(n, component):
    df = n.components[component].static
    if component in ("Line", "Link"):
        c0, c1 = df.bus0.map(n.buses.country), df.bus1.map(n.buses.country)
        return c0.where(c0 == c1, "cross-border")
    return df.bus.map(n.buses.country)


def export_year(n, year, cfg):
    w = n.snapshot_weightings.generators
    g = ["country", "carrier"]
    out = {}

    capex = n.statistics.capex(groupby=g, aggregate_across_components=False)
    opex = n.statistics.opex(groupby=g, aggregate_across_components=False)
    sc = pd.concat({"capex_eur_a": capex, "opex_eur_a": opex}, axis=1).fillna(0.0).reset_index()
    sc.insert(0, "year", year)
    out["system_costs"] = sc

    out["objective"] = pd.DataFrame(
        [{"year": year, "objective_eur_a": n.objective,
          "system_cost_eur_a": float(capex.sum() + opex.sum())}]
    )

    eb = n.statistics.energy_balance(groupby=g, bus_carrier="AC", aggregate_across_components=False)
    eb = (eb / 1e6).rename("TWh").reset_index()
    eb.insert(0, "year", year)
    out["energy_balance"] = eb

    cap = n.statistics.optimal_capacity(groupby=g, aggregate_across_components=False)
    cap = cap.rename("capacity_mw_or_mwh").reset_index()
    cap.insert(0, "year", year)
    out["capacities"] = cap

    ac = n.buses.index[n.buses.carrier == "AC"]
    price = n.buses_t.marginal_price[ac]
    load = n.loads_t.p_set.T.groupby(n.loads.bus).sum().T.reindex(columns=ac, fill_value=0.0)
    nodes = pd.DataFrame({
        "country": n.buses.loc[ac, "country"],
        "price_mean": price.mul(w, axis=0).sum() / w.sum(),
        "price_p95": price.quantile(0.95),
        "hours_gt_300": (price > 300).mul(w, axis=0).sum(),
        "hours_lt_1": (price < 1).mul(w, axis=0).sum(),
        "demand_twh": load.mul(w, axis=0).sum() / 1e6,
    })
    nodes.index.name = "bus"
    nodes = nodes.reset_index()
    nodes.insert(0, "year", year)
    out["prices_nodes"] = nodes

    de = ac[n.buses.loc[ac, "country"] == HOME]
    sysp = (price[de] * load[de]).sum(axis=1) / load[de].sum(axis=1)
    out["prices_de"] = pd.DataFrame([{
        "year": year,
        "price_loadweighted": float((price[de] * load[de]).mul(w, axis=0).sum().sum()
                                    / load[de].mul(w, axis=0).sum().sum()),
        "price_max": float(sysp.max()),
        "hours_gt_300": float((sysp > 300).mul(w).sum()),
        "hours_lt_1": float((sysp < 1).mul(w).sum()),
        "demand_twh": float(load[de].mul(w, axis=0).sum().sum() / 1e6),
    }])

    # trade: net flow between countries at the sending end (p0), as the import limit counts it
    pair = {}
    for comp, ts in (("Line", n.lines_t.p0), ("Link", n.links_t.p0)):
        df = n.components[comp].static
        if comp == "Link":
            df = df[df.carrier.isin(["DC"]) | df.carrier.str.lower().str.contains(CABLE_TAG)]
        for name in df.index:
            a, b = n.buses.country[df.bus0[name]], n.buses.country[df.bus1[name]]
            if a == b or name not in ts.columns:
                continue
            e = float((ts[name] * w).sum()) / 1e6
            key, sign = ((a, b), 1.0) if a < b else ((b, a), -1.0)
            pair[key] = pair.get(key, 0.0) + sign * e
    out["trade"] = pd.DataFrame(
        [{"year": year, "country_a": a, "country_b": b, "net_flow_a_to_b_twh": v}
         for (a, b), v in sorted(pair.items())]
    )

    gen = n.generators
    co2_t = n.carriers.co2_emissions.reindex(gen.carrier).fillna(0.0).values
    em = pd.Series(n.generators_t.p.mul(w, axis=0).sum().values / gen.efficiency.values * co2_t,
                   index=gen.index)
    em = em.groupby(gen.bus.map(n.buses.country)).sum() / 1e6
    gc = n.global_constraints
    shadow = float(-gc.loc["CO2Limit-upper", "mu"]) if "CO2Limit-upper" in gc.index else np.nan
    co2 = em.rename("emissions_mt").reset_index().rename(columns={"bus": "country"})
    co2.insert(0, "year", year)
    co2["cap_shadow_eur_t"] = shadow
    co2["co2_price_eur_t"] = co2_price(cfg, year)
    out["co2"] = co2

    cab = n.links[n.links.carrier.str.lower().str.contains(CABLE_TAG)]
    if not cab.empty:
        rows = []
        for name, r in cab.iterrows():
            sent = float((n.links_t.p0[name] * w).sum()) / 1e6
            recv = float(-(n.links_t.p1[name] * w).sum()) / 1e6
            cap_mw = float(r.p_nom_opt)
            rows.append({"year": year, "link": name, "bus_de": r.bus1, "p_nom_opt_mw": cap_mw,
                         "length_km": r.get("length", np.nan), "efficiency": r.efficiency,
                         "sent_twh": sent, "delivered_twh": recv,
                         "utilisation": sent * 1e6 / (cap_mw * w.sum()) if cap_mw > 1e-6 else np.nan,
                         "price_de_end": float(n.buses_t.marginal_price[r.bus1].mul(w).sum() / w.sum()),
                         "price_br_end": float(n.buses_t.marginal_price[r.bus0].mul(w).sum() / w.sum())})
        out["cable"] = pd.DataFrame(rows)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--configs", nargs="*")
    ap.add_argument("--years", nargs="*", type=int, default=YEARS)
    a = ap.parse_args()

    # only a real solver process counts: its command line is the Snakemake script
    # .snakemake/scripts/<tmp>.solve_network.py (pgrep -f would also match a shell
    # whose command line merely contains that text)
    ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout.splitlines()
    busy = [l for l in ps if ".snakemake/scripts/" in l and "solve_network" in l and "grep" not in l]
    if busy:
        sys.exit("A solve is running (solve_network.py). Wait for it: a network needs about 1 GB.")

    out_dir = a.out or ROOT / "results" / a.run / "handoff"
    out_dir.mkdir(parents=True, exist_ok=True)
    files = a.configs if a.configs is not None else configs_for(a.run)
    cfg = merged_config(files)

    collected, status = {}, {}
    for y in a.years:
        f = ROOT / "results" / a.run / "networks" / f"solved_{y}.nc"
        if not f.exists():
            print(f"skip {y}: {f} missing")
            continue
        n = pypsa.Network(f)
        for k, df in export_year(n, y, cfg).items():
            collected.setdefault(k, []).append(df)
        status[y] = log_info(a.run, y)
        del n
        print(f"exported {a.run} {y}", flush=True)

    for k, dfs in collected.items():
        pd.concat(dfs, ignore_index=True).to_csv(out_dir / f"{k}.csv", index=False, float_format="%.6g")

    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = ""
    manifest = {
        "run": a.run,
        "git_commit": commit,
        "horizons": sorted(status),
        "configs": files,
        "solver": {int(y): s for y, s in status.items()},
        "definitions": {
            "system_cost": "capex + opex of n.statistics over all active assets, EUR/a (the solver "
                           "objective counts extendable assets only and is smaller)",
            "trade": "net flow at the sending end (p0) of AC lines, DC links and the cable, TWh/a; "
                     "same quantity the role3.net_import_limit constrains",
            "germany": "all AC buses with country == DE",
            "time": "4 h steps, weather year 2013; flows and energies are annual sums",
        },
        "contains_unit_level_data": False,
    }
    (out_dir / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True))
    print("written", out_dir)


if __name__ == "__main__":
    main()

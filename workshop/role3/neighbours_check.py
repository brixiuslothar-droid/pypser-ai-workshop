# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""Role 3: German key figures of a run with neighbours, plus trade.

Usage: pixi run python workshop/role3/neighbours_check.py [run_name]
Writes results/<run>/role3/de_years.csv and trade.csv (ignored by git).
"""

import sys
from pathlib import Path

import pandas as pd
import pypsa

RUN = sys.argv[1] if len(sys.argv) > 1 else "de10-nb9"
YEARS = [int(y) for y in sys.argv[2].split(",")] if len(sys.argv) > 2 else [2025, 2030, 2035, 2040, 2045, 2050]
OUT = Path(f"results/{RUN}/role3")
OUT.mkdir(parents=True, exist_ok=True)
VRES = ["onwind", "offwind-ac", "offwind-dc", "offwind-float", "solar", "solar-hsat"]


def figures(n, year):
    w = n.snapshot_weightings.generators
    c = n.buses.country
    ac = n.buses.index[n.buses.carrier == "AC"]
    de = ac[c[ac] == "DE"]
    load = n.loads_t.p_set.T.groupby(n.loads.bus).sum().T.reindex(columns=ac, fill_value=0)
    price = n.buses_t.marginal_price[ac]
    sys_de = (price[de] * load[de]).sum(axis=1) / load[de].sum(axis=1)

    g = n.generators
    p = n.generators_t.p.mul(w, axis=0).sum()
    gde = g.bus.map(c) == "DE"
    gen = p[gde].groupby(g.carrier[gde]).sum() / 1e6
    cap = g[gde].groupby("carrier").p_nom_opt.sum() / 1e3
    shed = gen.get("load", 0.0)
    shed_all = p[g.carrier == "load"].sum() / 1e6

    # cross-border flows seen from Germany (positive = import into DE)
    imp = pd.Series(0.0, index=n.snapshots)
    by_country = {}
    for comp, b0, b1, flow in [
        ("lines", "bus0", "bus1", n.lines_t.p0),
        ("links", "bus0", "bus1", n.links_t.p0),
    ]:
        df = getattr(n, comp)
        if comp == "links":
            df = df[df.carrier == "DC"]
        c0, c1 = df[b0].map(c), df[b1].map(c)
        for i in df.index[(c0 == "DE") & (c1 != "DE")]:
            by_country[c1[i]] = by_country.get(c1[i], 0) - flow[i]
            imp -= flow[i]
        for i in df.index[(c1 == "DE") & (c0 != "DE")]:
            by_country[c0[i]] = by_country.get(c0[i], 0) + flow[i]
            imp += flow[i]
    net_imp = (imp * w).sum() / 1e6
    gross_imp = (imp.clip(lower=0) * w).sum() / 1e6
    gross_exp = (-imp.clip(upper=0) * w).sum() / 1e6

    st = n.stores
    sde = st.bus.map(c) == "DE"
    gc = n.global_constraints
    co2_eff = n.carriers.co2_emissions.reindex(g.carrier).values
    co2 = (p.values / g.efficiency.values * co2_eff)
    co2_de = co2[gde.values].sum() / 1e6
    co2_all = co2.sum() / 1e6

    rec = {
        "year": year,
        "de_demand_TWh": load[de].mul(w, axis=0).sum().sum() / 1e6,
        "de_price_loadweighted": (price[de] * load[de]).mul(w, axis=0).sum().sum() / load[de].mul(w, axis=0).sum().sum(),
        "de_price_max": sys_de.max(),
        "de_hours_price_gt_300": (sys_de > 300).mul(w).sum(),
        "de_hours_price_lt_1": (sys_de < 1).mul(w).sum(),
        "de_net_import_TWh": net_imp,
        "de_gross_import_TWh": gross_imp,
        "de_gross_export_TWh": gross_exp,
        "de_max_import_GW": imp.max() / 1e3,
        "de_co2_Mt": co2_de,
        "all_co2_Mt": co2_all,
        "co2_cap_shadow_EUR_t": -gc.loc["CO2Limit-upper", "mu"] if "CO2Limit-upper" in gc.index else 0,
        "load_shed_all_TWh": shed_all,
        "de_battery_GWh": st[sde & (st.carrier == "battery")].e_nom_opt.sum() / 1e3,
        "de_H2_store_GWh": st[sde & (st.carrier == "H2")].e_nom_opt.sum() / 1e3,
    }
    for k, v in gen.items():
        rec[f"de_gen_{k}_TWh"] = v
    for k, v in cap.items():
        rec[f"de_cap_{k}_GW"] = v
    trade = pd.Series({k: (v * w).sum() / 1e6 for k, v in by_country.items()}, name=year)
    return rec, trade


recs, trades = [], []
for y in YEARS:
    n = pypsa.Network(f"results/{RUN}/networks/solved_{y}.nc")
    r, t = figures(n, y)
    recs.append(r)
    trades.append(t)
years = pd.DataFrame(recs).set_index("year").T
trade = pd.concat(trades, axis=1)
years.to_csv(OUT / "de_years.csv")
trade.to_csv(OUT / "trade.csv")
pd.set_option("display.width", 220, "display.max_rows", 200)
print(years.astype(float).round(2).to_string())
print("Net import into DE by neighbour (TWh, + = import):")
print(trade.round(1).to_string())

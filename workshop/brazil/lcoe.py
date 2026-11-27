# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""LCOE per coastal ERA5 cell for all planning horizons, with the method of PyPSA-Eur (add_electricity.py).

capital_cost [EUR/MW/a] = (annuity(lifetime, r) + FOM) x investment     (process_cost_data.py)
LCOE = capital_cost / (8760 h x capacity factor) + marginal_cost
Two discount rates: 7 % (the baseline's rate for Germany, costs.discount rate in config.default.yaml) and 10 %.
The 10 % is an assumption for a higher cost of capital in Brazil, a sensitivity without a source. The rate is applied
to the plant, station and connection alike. No value from the confidential workshop inputs is used.
Offshore adds station + connection as in attach_wind_and_solar: station + 1.25 x (distance x submarine
  + landfall x underground); AC (within 30 km of the coast, landfall 20 km), DC (beyond, 30 km), floating (40 km).
Tables: resources/de10-myopic/costs_<year>_processed.csv (what the model reads). Marginal cost as in the model
(custom_costs.csv sets 0.015 EUR/MWh for wind, replacing the VOM); lcoe_with_vom adds the table's VOM instead.
Not included: interest during construction, grid connection onshore (the model has none),
distance to the cable landing point, transmission, exchange rate risk.
Output: lcoe_cells.csv (long: year, rate), lcoe_summary.csv and the supply curve of 2030 at 7 %.
"""
import sys
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(next(p for p in [Path.cwd(), *Path.cwd().parents]
                            if (p / "workshop/plotstyle").is_dir()) / "workshop/plotstyle"))
import studystyle as st

OUT = Path("results/brazil-potential")
H, LENGTH_FACTOR = 8760, 1.25
LANDFALL = {"offwind-ac": 20.0, "offwind-dc": 30.0, "offwind-float": 40.0}  # config.default.yaml
DENSITY = {"onwind": 3.0, "solar": 5.1, "solar-hsat": 4.43, "offwind-ac": 2.0, "offwind-dc": 2.0, "offwind-float": 2.0}
RATES = {"r07": 0.07, "r10": 0.10}  # 7 % baseline; 10 % assumed sensitivity
YEARS = [2025, 2030, 2035, 2040, 2045, 2050]


def annuity(n, r):
    return r / (1 - (1 + r) ** -n)


pot = pd.read_csv(OUT / "potential_per_cell.csv")
elig = pd.read_csv(OUT / "eligibility_offshore.csv")
cd = xr.open_dataarray(OUT / "coast_distance_km.nc").to_series().reset_index()
cd.columns = ["lat", "lon", "centre_distance_km"]
cd[["lat", "lon"]] = cd[["lat", "lon"]].round(2)

rows = []
for t, key in [("onwind", "onwind"), ("solar", "solar-utility"), ("solar-hsat", "solar-hsat")]:
    d = pot[pot.tech == t].copy()
    d["cost_key"], d["carrier"] = key, t
    rows.append(d)
base_ = pot[pot.tech == "offwind"].drop(columns=["eligible_km2", "p_nom_max_mw", "energy_gwh", "area_km2"])
for car in ["offwind-ac", "offwind-dc"]:  # fixed foundation, split by eligible area within / beyond 30 km
    d = base_.merge(elig[["lat", "lon", "area_km2", car]], on=["lat", "lon"])
    d["eligible_km2"] = d[car] * d.area_km2
    d["p_nom_max_mw"] = d.eligible_km2 * DENSITY[car]
    d["energy_gwh"] = d.p_nom_max_mw * d.mwh_per_mw / 1e3
    d["cost_key"], d["carrier"] = "offwind", car
    rows.append(d.drop(columns=[car, "area_km2"]))
d = pot[pot.tech == "offwind-float"].copy()
d["cost_key"], d["carrier"] = "offwind-float", "offwind-float"
rows.append(d)
cells = pd.concat(rows, ignore_index=True).merge(cd, on=["lat", "lon"], how="left")
cells = cells[cells.p_nom_max_mw > 0].drop(columns=["tech"]).reset_index(drop=True)
off = cells.carrier.str.startswith("offwind")
dist = cells.centre_distance_km.clip(lower=0)  # distance of the cell centre to the coast
dist = np.where(cells.carrier == "offwind-ac", dist.clip(upper=30), np.where(cells.carrier == "offwind-dc", dist.clip(lower=30), dist))
cells["distance_km"] = np.where(off, dist, 0.0)
cells["north"] = cells.lat >= -7.0
land = cells.carrier.map(LANDFALL)


def annual(inv, fom, life, r):  # EUR/MW/a
    return (annuity(life, r) + fom / 100.0) * inv


out = []
for year in YEARS:
    c = pd.read_csv(f"resources/de10-myopic/costs_{year}_processed.csv", index_col=0)
    for rn, r in RATES.items():
        cap = annual(c.investment, c.FOM.fillna(0), c.lifetime, r)  # all technologies, EUR/MW/a (or per km)
        k = cells.cost_key
        sub = cells.carrier.map(lambda x: cap.get(f"{x}-connection-submarine", np.nan))
        und = cells.carrier.map(lambda x: cap.get(f"{x}-connection-underground", np.nan))
        sta = cells.carrier.map(lambda x: cap.get(f"{x}-station", np.nan))
        conn = np.where(off, LENGTH_FACTOR * (cells.distance_km * sub + land * und), 0.0)
        capital = k.map(cap) + np.where(off, sta, 0.0) + conn
        mcost = k.map(c.marginal_cost)
        vomc = k.map(c.VOM.fillna(0))
        d = cells[["carrier", "lat", "lon", "north", "distance_km", "cf", "mwh_per_mw", "eligible_km2", "p_nom_max_mw", "energy_gwh"]].copy()
        d["year"], d["rate"], d["rate_pct"] = year, rn, 100 * r
        d["capital_eur_mw_a"] = capital
        d["connection_eur_mw_a"] = conn
        d["lcoe_eur_mwh"] = capital / (H * cells.cf) + mcost
        d["lcoe_with_vom_eur_mwh"] = capital / (H * cells.cf) + np.where(mcost < vomc, vomc, mcost)
        out.append(d)
df = pd.concat(out, ignore_index=True)
assert df.lcoe_eur_mwh.notna().all()
df.to_csv(OUT / "lcoe_cells.csv", index=False)

# ---- summary --------------------------------------------------------------------
order = ["onwind", "solar", "solar-hsat", "offwind-ac", "offwind-dc", "offwind-float"]
pd.set_option("display.width", 240)


def wq(d, q=0.5, col="lcoe_eur_mwh"):  # capacity weighted quantile
    d = d.sort_values(col); w = d.p_nom_max_mw.cumsum() / d.p_nom_max_mw.sum()
    return float(d[col][w >= q].iloc[0])


north = df[df.north & (df.p_nom_max_mw >= 100)].copy()
north["gw"] = north.p_nom_max_mw / 1e3
rows = []
for (rate, year, car), d in north.groupby(["rate", "year", "carrier"]):
    rows.append(dict(rate=rate, year=year, carrier=car, cells=len(d), GW=d.gw.sum(), min=d.lcoe_eur_mwh.min(),
                     p50_by_GW=wq(d), GW_below_40=d[d.lcoe_eur_mwh < 40].gw.sum()))
summ = pd.DataFrame(rows)
summ.to_csv(OUT / "lcoe_summary.csv", index=False)


def table(col):
    t = summ.pivot_table(index=["rate", "carrier"], columns="year", values=col)
    return t.reindex(pd.MultiIndex.from_product([["r07", "r10"], order])).round(1).to_string()


print("\nMINIMUM LCOE in the north (cells >= 100 MW), EUR/MWh"); print(table("min"))
print("\nCAPACITY-WEIGHTED MEDIAN LCOE in the north, EUR/MWh"); print(table("p50_by_GW"))
print("\nGW BELOW 40 EUR/MWh in the north"); print(table("GW_below_40"))
m = summ.pivot_table(index=["year", "carrier"], columns="rate", values="min")
print("\nEffect of 10 % against 7 %: minimum LCOE, % change")
print(((m["r10"] / m["r07"] - 1) * 100).unstack("year").reindex(order).round(1).to_string())

# ---- supply curve: north, 2030, 7 % ---------------------------------------------------
st.use()
fig, ax = plt.subplots(figsize=(7.2, 4.2))
col = {"onwind": st.color("onwind"), "solar": st.color("solar"), "solar-hsat": st.color("solar"),
       "offwind-ac": st.color("offwind-ac"), "offwind-dc": st.color("offwind-ac"), "offwind-float": st.color("offwind-float")}
nm = {"onwind": "Onshore wind", "solar": "Solar PV, fixed", "solar-hsat": "Solar PV, tracking",
      "offwind-ac": "Offshore wind, AC", "offwind-dc": "Offshore wind, DC", "offwind-float": "Offshore wind, floating"}
ends = []
sel = df[df.north & (df.year == 2030) & (df.rate == "r07")]
for car in order:
    d = sel[sel.carrier == car].sort_values("lcoe_eur_mwh")
    if d.empty:
        continue
    x = np.r_[0, d.p_nom_max_mw.cumsum() / 1e3]; y = np.r_[d.lcoe_eur_mwh.iloc[0], d.lcoe_eur_mwh]
    ax.step(x, y, where="post", color=col[car], lw=1.6, ls={"solar-hsat": "--", "offwind-dc": "--"}.get(car, "-"))
    ends.append([min(x[-1], 480) + 6, min(y[-1], 118), nm[car]])
ax.set_xlim(0, 480); ax.set_ylim(0, 120)
ends.sort(key=lambda e: e[1])
for i in range(1, len(ends)):
    ends[i][1] = max(ends[i][1], ends[i - 1][1] + 5)  # nudge labels apart
for x, y, n_ in ends:
    ax.text(x, y, n_, fontsize=7.5, color="#222222", va="center", clip_on=False)
ax.set_xlabel("Cumulative installable capacity, GW (cheapest cells first)", fontsize=8)
ax.set_title("LCOE against installable capacity, northern coast of Brazil, 2030, 7 % discount rate, EUR/MWh", loc="left", fontsize=9)
fig.subplots_adjust(right=0.78, bottom=0.14, top=0.9)
fig.savefig(OUT / "lcoe_supply_curve_north.png", dpi=300); fig.savefig(OUT / "lcoe_supply_curve_north.pdf")

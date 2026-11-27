# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""Rank the LCOE of the northern coastal cells (lcoe_cells.csv) and place the shortlist sites in it.

Cells with less than MIN_MW installable capacity are left out: a cell of a few MW is the cheapest by
chance and does not matter for the cable. Shortlist sites are ranked with the cost table at their measured
capacity factor (like the cells), so the comparison is on one cost basis; the offered price is shown aside.
Writes lcoe_ranking_cells.csv and lcoe_ranking_with_shortlist.csv (only ids and technical columns).
"""
import sys
import pandas as pd

# usage: rank_lcoe.py [year] [rate: wacc|r07]   (default 2030, wacc = 7.62 % of the term sheet)
YEAR = int(sys.argv[1]) if len(sys.argv) > 1 else 2030
RATE = sys.argv[2] if len(sys.argv) > 2 else "wacc"
MIN_MW = 100
OUT = "results/brazil-potential/"
c = pd.read_csv(OUT + "lcoe_cells.csv").query("year == @YEAR and rate == @RATE")
print(f"Year {YEAR}, rate {RATE}")
SUF = f"_{YEAR}_{RATE}"
n = c[c.north & (c.p_nom_max_mw >= MIN_MW)].sort_values("lcoe_eur_mwh").reset_index(drop=True)
n["rank"] = n.index + 1
n["cum_gw"] = n.p_nom_max_mw.cumsum() / 1e3
n["cum_twh"] = n.energy_gwh.cumsum() / 1e3
n.to_csv(OUT + f"lcoe_ranking_cells{SUF}.csv", index=False)
pd.set_option("display.width", 220)
cols = ["rank", "carrier", "lat", "lon", "cf", "p_nom_max_mw", "energy_gwh", "lcoe_eur_mwh"]
print(f"North, cells with >= {MIN_MW} MW: {len(n)} rows, {n.p_nom_max_mw.sum()/1e3:.0f} GW (technologies compete for land)")
print("\nTop 15 over all technologies"); print(n[cols].head(15).round(2).to_string(index=False))
print("\nBest 3 per technology")
for car, d in n.groupby("carrier", sort=False):
    pass
for car in ["onwind", "solar", "solar-hsat", "offwind-ac", "offwind-dc", "offwind-float"]:
    d = n[n.carrier == car].head(3)
    print(car); print(d[cols].round(2).to_string(index=False))

# one option per cell: the cheapest technology
best = n.sort_values("lcoe_eur_mwh").drop_duplicates(["lat", "lon"])
print("\nCheapest technology per cell: number of cells and GW")
print(best.groupby("carrier").agg(cells=("lat", "size"), GW=("p_nom_max_mw", lambda x: x.sum() / 1e3),
                                  TWh=("energy_gwh", lambda x: x.sum() / 1e3)).round(1).to_string())

# shortlist in the ranking
s = pd.read_csv(OUT + "shortlist_ranking.csv")
tab, off_ = f"lcoe_table_{RATE}_{YEAR}", f"lcoe_offer_{RATE}"
s = s[["site_id", "technology", "buildable_mw", "capacity_factor_measured", "suitable", tab, off_, "energy_gwh"]].rename(
    columns={tab: "lcoe_eur_mwh", off_: "lcoe_offer_eur_mwh"})
s["carrier"] = s.technology.map({"onwind": "onwind", "solar": "solar", "offwind": "offwind-ac"})
s["rank_among_cells"] = [int((n.lcoe_eur_mwh < v).sum()) + 1 for v in s.lcoe_eur_mwh]
s["cheaper_cells_same_tech"] = [int(((n.carrier == car) & (n.lcoe_eur_mwh < v)).sum()) for car, v in zip(s.carrier, s.lcoe_eur_mwh)]
s = s.sort_values("lcoe_eur_mwh")
s.to_csv(OUT + f"lcoe_ranking_with_shortlist{SUF}.csv", index=False)
print(f"\nShortlist sites at their measured capacity factor, same year and rate as the cells ({YEAR}, {RATE})")
print("\nShortlist sites on the cost table basis (ERA5 cells ranked 1 to %d)" % len(n))
print(s.drop(columns=["technology"]).round(1).to_string(index=False))

# ---- ranking of locations: one row per cell, cheapest technology, all options side by side ----------------
loc = n.pivot_table(index=["lat", "lon"], columns="carrier", values="lcoe_eur_mwh")
loc.columns = ["lcoe_" + c_ for c_ in loc.columns]
best = n.sort_values("lcoe_eur_mwh").drop_duplicates(["lat", "lon"]).set_index(["lat", "lon"])
loc = best[["carrier", "cf", "distance_km", "p_nom_max_mw", "energy_gwh", "lcoe_eur_mwh"]].join(loc).sort_values("lcoe_eur_mwh")
loc.insert(0, "rank", range(1, len(loc) + 1))
loc["cum_gw"] = loc.p_nom_max_mw.cumsum() / 1e3
loc = loc.reset_index()
loc.to_csv(OUT + f"lcoe_ranking_locations{SUF}.csv", index=False)
print("\nRANKING OF LOCATIONS (cheapest option per cell, >= %d MW), %d locations" % (MIN_MW, len(loc)))
print(loc[["rank", "lat", "lon", "carrier", "cf", "p_nom_max_mw", "energy_gwh", "lcoe_eur_mwh", "cum_gw"]].head(20).round(2).to_string(index=False))
print("\nBest 5 locations for wind (onshore, offshore AC/DC)")
w = loc[loc.carrier.isin(["onwind", "offwind-ac", "offwind-dc"])]
print(w[["rank", "lat", "lon", "carrier", "cf", "p_nom_max_mw", "energy_gwh", "lcoe_eur_mwh"]].head(8).round(2).to_string(index=False))

# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""Potential per coastal ERA5 cell: eligible area x power density -> p_nom_max, and annual energy.

Inputs: coastal_cells_annual_energy.csv (annual_energy.py), eligibility_onshore/offshore.csv (eligibility.py).
All WDPA protected areas are excluded (no relaxing). Offshore wind is scaled by correction_factor 0.8855.
Output: potential_per_cell.csv and potential_supply_curve.{png,pdf}.
"""
import sys
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(next(p for p in [Path.cwd(), *Path.cwd().parents]
                            if (p / "workshop/plotstyle").is_dir()) / "workshop/plotstyle"))
import studystyle as st

OUT = Path("results/brazil-potential")
DENSITY = {"onwind": 3.0, "solar": 5.1, "solar-hsat": 4.43, "offwind": 2.0, "offwind-float": 2.0}  # MW/km2
e = pd.read_csv(OUT / "coastal_cells_annual_energy.csv")
on = pd.read_csv(OUT / "eligibility_onshore.csv")
off = pd.read_csv(OUT / "eligibility_offshore.csv")
off["offwind"] = off["offwind-ac"] + off["offwind-dc"]  # same turbine and profile; AC part is within 30 km of the coast

rows = []
for t, el in [("onwind", on), ("solar", on), ("solar-hsat", on), ("offwind", off), ("offwind-float", off)]:
    d = e[e.tech == t].merge(el[["lat", "lon", "area_km2", t]], on=["lat", "lon"], how="left", validate="1:1")
    d["eligible_km2"] = d[t] * d.area_km2
    d["p_nom_max_mw"] = d.eligible_km2 * DENSITY[t]
    d["energy_gwh"] = d.p_nom_max_mw * d.mwh_per_mw / 1e3
    rows.append(d.drop(columns=[t]))
df = pd.concat(rows, ignore_index=True)
assert df.p_nom_max_mw.notna().all(), "cells without eligibility"
df.to_csv(OUT / "potential_per_cell.csv", index=False)

pd.set_option("display.width", 200)
order = ["onwind", "solar", "solar-hsat", "offwind", "offwind-float"]
s = df.groupby("tech").agg(cells=("lat", "size"), cells_with_area=("p_nom_max_mw", lambda x: int((x > 0).sum())),
                           p_nom_max_gw=("p_nom_max_mw", lambda x: x.sum() / 1e3), energy_twh=("energy_gwh", lambda x: x.sum() / 1e3)).loc[order]
s["mwh_per_mw_weighted"] = [(df[df.tech == t].energy_gwh.sum() * 1e3) / df[df.tech == t].p_nom_max_mw.sum() for t in order]
print(s.round(1).to_string())
print("\nBest cells by annual energy that can be produced (GWh), top 3 per technology")
for t in order:
    print(t); print(df[df.tech == t].nlargest(3, "energy_gwh")[["lat", "lon", "coast_km", "cf", "mwh_per_mw", "eligible_km2", "p_nom_max_mw", "energy_gwh"]].round(2).to_string(index=False))

# supply curve: cumulative energy when cells are used from best (MWh per MW) to worst
st.use()
fig, ax = plt.subplots(figsize=(7.2, 4.2))
cols = {"onwind": st.color("onwind"), "solar": st.color("solar"), "solar-hsat": st.color("solar"),
        "offwind": st.color("offwind-ac"), "offwind-float": st.color("offwind-float")}
names = {"onwind": "Onshore wind", "solar": "Solar PV, fixed", "solar-hsat": "Solar PV, tracking",
         "offwind": "Offshore wind, fixed", "offwind-float": "Offshore wind, floating"}
ends = []
for t in order:
    d = df[(df.tech == t) & (df.p_nom_max_mw > 0)].sort_values("mwh_per_mw", ascending=False)
    x = np.r_[0, d.p_nom_max_mw.cumsum() / 1e3]; y = np.r_[d.mwh_per_mw.iloc[0], d.mwh_per_mw]
    ax.step(x, y, where="post", color=cols[t], lw=1.6, ls="--" if t == "solar-hsat" else "-")
    ends.append((x[-1], y[-1], names[t]))
ax.set_xlim(0, 1000); ax.set_ylim(0, 7000)
for x, y, n in sorted(ends, key=lambda v: v[1]):
    ax.text(min(x, 1000) + 8, y, n, fontsize=7.5, color="#222222", va="center", clip_on=False)
ax.set_xlabel("Cumulative installable capacity, GW (best cells first)", fontsize=8)
ax.set_title("Annual energy per MW against installable capacity, Brazil coastal zone, MWh per MW", loc="left", fontsize=9)
fig.subplots_adjust(right=0.8)
fig.savefig(OUT / "potential_supply_curve.png", dpi=300); fig.savefig(OUT / "potential_supply_curve.pdf")

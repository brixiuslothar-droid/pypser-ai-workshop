# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""Plots of the annual energy per MW in the Brazilian coastal zone (workshop plot style).

Reads results/brazil-potential/coastal_cells_annual_energy.csv (annual_energy.py).
Writes annual_energy_maps and annual_energy_distribution (png 300 dpi + pdf).
"""
import sys
from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(next(p for p in [Path.cwd(), *Path.cwd().parents]
                            if (p / "workshop/plotstyle").is_dir()) / "workshop/plotstyle"))
import studystyle as st

st.use()
OUT = Path("results/brazil-potential")
df = pd.read_csv(OUT / "coastal_cells_annual_energy.csv")
land = gpd.read_file("zip://data-brazil/raw/gadm/gadm41_BRA_1.json.zip")
land = gpd.GeoSeries([land.geometry.make_valid().buffer(0).union_all()], crs=4326)
eez = gpd.GeoSeries([gpd.read_file("data-brazil/layers/eez_brazil.gpkg").geometry.make_valid().union_all()], crs=4326)

TECH = [  # key, title, colour for bars
    ("onwind", "Onshore wind", st.color("onwind")),
    ("solar", "Solar PV, fixed", st.color("solar")),
    ("solar-hsat", "Solar PV, tracking", st.color("solar")),
    ("offwind", "Offshore wind, fixed", st.color("offwind-ac")),
    ("offwind-float", "Offshore wind, floating", st.color("offwind-float")),
]
XLIM, YLIM, CELL = (-54, -33), (-12, 6.5), 0.3

# --- 1. maps: energy per MW in every coastal cell --------------------------------
fig, axes = plt.subplots(2, 3, figsize=(9.6, 7.4), layout="none")
fig.subplots_adjust(left=0.02, right=0.98, top=0.92, bottom=0.05, wspace=0.04, hspace=0.2)
for ax, (k, title, _) in zip(axes.flat, TECH):
    d = df[df.tech == k]
    land.plot(ax=ax, color="#eeeeee", edgecolor="#222222", linewidth=0.5)
    eez.boundary.plot(ax=ax, color="#cccccc", linewidth=0.5)
    sc = ax.scatter(d.lon, d.lat, c=d.mwh_per_mw, s=17, marker="s", cmap="viridis", linewidths=0,
                    vmin=0, vmax=d.mwh_per_mw.max())
    ax.set_xlim(XLIM); ax.set_ylim(YLIM); ax.set_aspect("equal")
    st.map_axes(ax)
    ax.set_title(title, loc="left", fontsize=9)
    st.colorbar(fig, sc, ax.inset_axes([0.05, -0.06, 0.6, 0.025]), "Annual energy, MWh per MW", fmt="%d")
axes.flat[5].axis("off")
axes.flat[5].text(0, 0.9, "Coastal zone: cells touching the land strip up to\n100 km from the coast or the sea strip up to 200 km\n"
                  "off it (inside the EEZ, depth not yet filtered).\nOffshore wind with correction factor 0.8855.\n"
                  "Weather year 2013 (ERA5).", fontsize=8, color="#444444", va="top")
fig.suptitle("Annual energy per installed MW in Brazil's coastal zone, MWh per MW", x=0.02, ha="left",
             fontweight="bold", fontsize=11)
fig.savefig(OUT / "annual_energy_maps.png", dpi=300); fig.savefig(OUT / "annual_energy_maps.pdf")
plt.close(fig)

# --- 2. distribution per technology + best cells -----------------------------------
fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 3.8), width_ratios=[1.15, 1])
g = df.groupby("tech").mwh_per_mw
stats = pd.DataFrame({"Median": g.median(), "Best 10 %": g.quantile(0.9), "Best cell": g.max()}).loc[[t[0] for t in TECH]]
pos = np.arange(len(TECH)); w = 0.26
for i, (col, alpha) in enumerate([("Median", 0.35), ("Best 10 %", 0.65), ("Best cell", 1.0)]):
    st.bars(a1, pos + (i - 1) * w, stats[col].values, color=[t[2] for t in TECH], width=w,
            labels=False, alpha=alpha)
    for x, v in zip(pos + (i - 1) * w, stats[col].values):
        a1.text(x, v + 80, f"{v:,.0f}", ha="center", va="bottom", fontsize=6.5, color="#222222", rotation=90)
a1.set_xticks(pos, ["Onshore\nwind", "PV\nfixed", "PV\ntracking", "Offshore\nfixed", "Offshore\nfloating"], fontsize=7.5)
a1.set_ylim(0, stats.values.max() * 1.18)
a1.set_title("Annual energy per MW, MWh", loc="left")
st.legend_squares(a1, [("#888888", "Best cell"), ("#888888", "Best 10 % of cells", 0.65),
                       ("#888888", "Median cell", 0.35)], loc="upper left", fontsize=7.5)

# energy of the best cell versus distance to the coast, wind only
for k, title, c in [t for t in TECH if t[0] in ("onwind", "offwind")]:
    d = df[df.tech == k]; dist = d.coast_km.abs()
    a2.scatter(dist, d.mwh_per_mw, s=7, color=c, linewidths=0, alpha=0.75)
a2.set_xlabel("Distance of the cell centre from the coast, km", fontsize=8)
a2.set_title("Wind cells by distance from the coast, MWh per MW", loc="left")
a2.text(8, 4900, "Onshore wind", color="#222222", fontsize=7.5)
a2.text(95, 6700, "Offshore wind, fixed", color="#222222", fontsize=7.5)
a2.set_ylim(0, 7200)
fig.savefig(OUT / "annual_energy_distribution.png", dpi=300); fig.savefig(OUT / "annual_energy_distribution.pdf")
print(stats.round(0).to_string())

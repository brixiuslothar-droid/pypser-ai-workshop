# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""Map of the landing point candidates: cost of the cheapest 10 TWh a year delivered at each point (workshop style)."""
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
d = pd.read_csv(OUT / "landing_point_candidates.csv")
land = gpd.read_file("zip://data-brazil/raw/gadm/gadm41_BRA_1.json.zip")
fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.6), layout="none")
fig.subplots_adjust(left=0.02, right=0.98, top=0.88, bottom=0.12, wspace=0.05)
for ax, col, title, vmax in [(axes[0], "avg_all", "All technologies", 45), (axes[1], "avg_wind", "Wind only", 75)]:
    land.plot(ax=ax, color="#eeeeee", edgecolor="#222222", linewidth=0.5)
    t = d.dropna(subset=[col]).sort_values(col, ascending=False)
    sc = ax.scatter(t.lon, t.lat, c=t[col], s=14, cmap="viridis_r", vmin=t[col].min(), vmax=vmax, linewidths=0)
    b = t.loc[t[col].idxmin()]
    ax.scatter([b.lon], [b.lat], s=60, facecolor="none", edgecolor="#222222", linewidth=1)
    ax.annotate(f"best: {b[col]:.1f}", (b.lon, b.lat), xytext=(b.lon + 3, b.lat - 4.5), fontsize=7.5, color="#222222",
                arrowprops=dict(arrowstyle="-", color="#222222", lw=0.5))
    ax.set_xlim(-53, -33); ax.set_ylim(-9, 6); ax.set_aspect("equal"); st.map_axes(ax)
    ax.set_title(title, loc="left", fontsize=9)
    st.colorbar(fig, sc, ax.inset_axes([0.05, -0.1, 0.6, 0.03]), "Cost of the cheapest 10 TWh a year at the point, EUR/MWh", fmt="%d")
fig.suptitle("Landing point candidates on the northern coast of Brazil, 2030, 7 % discount rate", x=0.02, ha="left", fontweight="bold", fontsize=11)
fig.savefig(OUT / "landing_point_map.png", dpi=300); fig.savefig(OUT / "landing_point_map.pdf")
print("written landing_point_map")

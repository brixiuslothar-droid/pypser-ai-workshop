# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""Maps of the mean capacity factor per ERA5 cell in Brazil, 2013 (workshop plot style)."""
import sys
from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import shapely
import xarray as xr

sys.path.insert(0, str(next(p for p in [Path.cwd(), *Path.cwd().parents]
                            if (p / "workshop/plotstyle").is_dir()) / "workshop/plotstyle"))
import studystyle as st

st.use()
ds = xr.open_dataset("results/brazil-potential/capacity_factors.nc")
x, y = ds.x.values, ds.y.values
X, Y = np.meshgrid(x, y)

land = gpd.read_file("zip://data-brazil/raw/gadm/gadm41_BRA_1.json.zip")
land_geom = land.geometry.make_valid().buffer(0).union_all()
eez = gpd.read_file("data-brazil/layers/eez_brazil.gpkg").geometry.make_valid().union_all()
sea_geom = eez.difference(land_geom)
on = shapely.contains_xy(land_geom, X, Y)
off = shapely.contains_xy(sea_geom, X, Y)

panels = [  # variable, title, mask, colour
    ("onwind", "Onshore wind", on, st.GROUPS["Onshore wind"] if "Onshore wind" in st.GROUPS else st.color("onwind")),
    ("solar", "Solar PV, fixed, facing north", on, st.color("solar")),
    ("solar-hsat", "Solar PV, single-axis tracking", on, st.color("solar")),
    ("offwind", "Offshore wind, fixed foundation", off, st.color("offwind-ac")),
    ("offwind-float", "Offshore wind, floating", off, st.color("offwind-float")),
]

fig, axes = plt.subplots(2, 3, figsize=(9.6, 7.4), layout="none")
fig.subplots_adjust(left=0.02, right=0.98, top=0.93, bottom=0.04, wspace=0.04, hspace=0.22)
extent = [x.min() - 0.15, x.max() + 0.15, y.min() - 0.15, y.max() + 0.15]
bounds = land.geometry.make_valid().buffer(0)

stats = {}
for ax, (var, title, mask, _) in zip(axes.flat, panels):
    cf = ds[var].values.copy()
    cf[~mask] = np.nan
    stats[var] = cf
    ax.set_facecolor("white")
    ax.imshow(np.where(on | off, 1, np.nan), origin="lower", extent=extent, cmap="Greys", vmin=0, vmax=8,
              interpolation="nearest")  # light grey: land and sea without data stays #eeeeee below
    ax.imshow(np.where(on, 1, np.nan), origin="lower", extent=extent, cmap=plt.matplotlib.colors.ListedColormap(["#eeeeee"]),
              interpolation="nearest")
    im = ax.imshow(cf, origin="lower", extent=extent, cmap="viridis", vmin=0,
                   vmax=np.nanpercentile(np.concatenate([stats[var][np.isfinite(stats[var])]]), 99.5),
                   interpolation="nearest")
    bounds.boundary.plot(ax=ax, color="#222222", linewidth=0.5)
    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3]); ax.set_aspect("equal")
    st.map_axes(ax)
    ax.set_title(title, loc="left", fontsize=9)
    cax = ax.inset_axes([0.05, -0.07, 0.6, 0.025])
    st.colorbar(fig, im, cax, "Mean capacity factor, 2013", fmt="%.2f")

# sixth panel: how much better is the best site than the average one
ax = axes.flat[5]
labels = [p[1].replace(", facing north", "").replace(", fixed foundation", "") for p in panels]
mean = [np.nanmean(stats[p[0]]) for p in panels]
top = [np.nanmean(np.sort(stats[p[0]][np.isfinite(stats[p[0]])])[-max(1, int(0.05 * np.isfinite(stats[p[0]]).sum())):])
       for p in panels]
pos = np.arange(len(panels))
w = 0.36
st.bars(ax, pos - w / 2, mean, color=st.NEUTRAL, width=w, fmt="{:.2f}")
st.bars(ax, pos + w / 2, top, color=[p[3] for p in panels], width=w, fmt="{:.2f}")
ax.set_xticks(pos, ["Onshore\nwind", "PV\nfixed", "PV\ntracking", "Offshore\nfixed", "Offshore\nfloating"], fontsize=7.5)
ax.set_title("Capacity factor: all cells vs. best 5 %", loc="left", fontsize=9)
st.legend_squares(ax, [(st.NEUTRAL, "Average of all cells"), ("#888888", "Average of best 5 % of cells")],
                  loc="upper right", fontsize=7.5)
ax.set_ylim(0, 0.8)

fig.suptitle("Capacity factors of wind and solar in Brazil, weather year 2013 (ERA5)", x=0.02, ha="left",
             fontweight="bold", fontsize=11)
out = Path("results/brazil-potential")
fig.savefig(out / "capacity_factors.png", dpi=300)
fig.savefig(out / "capacity_factors.pdf")
for p, m, t in zip(panels, mean, top):
    print(f"{p[0]:15s} mean {m:.3f}  best5% {t:.3f}  max {np.nanmax(stats[p[0]]):.3f}")

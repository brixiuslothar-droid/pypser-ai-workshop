# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""Compare the eligible share of sample cells from eligibility.py with atlite's availabilitymatrix.

atlite reads a whole raster and reprojects it, so the 100 m land cover would not fit into the 10 GB workspace.
Both methods therefore run on a clip of each raster around the sample cells (a box of the cell plus 0.1 degree);
the clips are written to /tmp. Same layers and rules: land cover classes, WDPA (all categories), inside Brazil.
atlite works on a 300 m grid in the Albers CRS (RES), eligibility.py on the native 100 m pixels.
"""
import sys
import warnings
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from atlite.gis import ExclusionContainer
from rasterio.windows import from_bounds
import atlite

warnings.filterwarnings("ignore")
OUT = "results/brazil-potential/"
L = "data-brazil/layers/"
TMP = "/tmp/brazil-scratch/"
CRS, RES, HALF, PAD = "ESRI:102033", int(sys.argv[1]) if len(sys.argv) > 1 else 300, 0.15, 0.1
LC = {"onwind": [20, 30, 40, 60, 100], "solar": [20, 30, 40, 50, 60, 90, 100]}

pot = pd.read_csv(OUT + "potential_per_cell.csv").query("tech in ['onwind','solar'] and lat >= -7")
el = pd.read_csv(OUT + "eligibility_onshore.csv").merge(pot[pot.tech == "onwind"][["lat", "lon"]], on=["lat", "lon"])
el["share"] = el.onwind
rng = np.random.default_rng(0)
# sample: the best wind cells plus cells over the whole range of eligible shares
best = el.merge(pot[pot.tech == "onwind"][["lat", "lon", "cf"]], on=["lat", "lon"]).nlargest(6, "cf")
rest = el.drop(best.index, errors="ignore")
pick = pd.concat([best, rest[rest.share == 0].sample(2, random_state=0), rest[(rest.share > 0) & (rest.share < 0.3)].sample(4, random_state=0),
                  rest[(rest.share >= 0.3) & (rest.share < 0.7)].sample(4, random_state=0), rest[rest.share >= 0.7].sample(4, random_state=0)])
pick = pick.drop_duplicates(["lat", "lon"]).reset_index(drop=True)
print(len(pick), "sample cells")

strip = gpd.read_file(OUT + "coastal_zone.gpkg").set_index("zone").geometry["land"]  # the same 100 km land strip as eligibility.py
wdpa = gpd.read_file(L + "wdpa_brazil.gpkg"); wdpa = gpd.GeoDataFrame(geometry=wdpa.geometry.make_valid(), crs=4326)
cutout = atlite.Cutout("data-brazil/weather/brazil-2013-era5.nc", chunks={"time": 744})
grid = cutout.grid
rows = []
for r in pick.itertuples():
    b = (r.lon - HALF - PAD, r.lat - HALF - PAD, r.lon + HALF + PAD, r.lat + HALF + PAD)
    clip = TMP + "lc_clip.tif"
    with rasterio.open(L + "copernicus_lc100.tif") as src:
        win = from_bounds(*b, src.transform).round_offsets().round_lengths()
        a = src.read(1, window=win, boundless=True, fill_value=255)
        prof = src.profile | dict(height=a.shape[0], width=a.shape[1], transform=src.window_transform(win), compress="deflate")
    with rasterio.open(clip, "w", **prof) as dst:
        dst.write(a, 1)
    out = {}
    cell = grid[(abs(grid.x - r.lon) < 1e-6) & (abs(grid.y - r.lat) < 1e-6)].geometry.iloc[0]
    inside = gpd.GeoSeries([cell.intersection(strip)], crs=4326)
    # atlite returns about 0.89 even for a cell that is entirely eligible (edge effect of its reprojection to the
    # cutout grid): the same shape without any exclusion layer is the reference that the values are divided by
    A0 = cutout.availabilitymatrix(inside, ExclusionContainer(crs=CRS, res=RES))
    ref = float(A0.isel({A0.dims[0]: 0}).sel(x=r.lon, y=r.lat, method="nearest"))
    for tech in ("onwind", "solar"):
        ex = ExclusionContainer(crs=CRS, res=RES)
        ex.add_raster(clip, codes=LC[tech], invert=True, crs=4326, nodata=255)
        ex.add_geometry(wdpa.to_crs(CRS).geometry)
        cell = grid[(abs(grid.x - r.lon) < 1e-6) & (abs(grid.y - r.lat) < 1e-6)].geometry.iloc[0]
        inside = gpd.GeoSeries([cell.intersection(strip)], crs=4326)
        A = cutout.availabilitymatrix(inside, ex)
        a_ = float(A.isel({A.dims[0]: 0}).sel(x=r.lon, y=r.lat, method="nearest"))  # share of the whole cell
        out[tech] = a_ / ref if ref > 0 else np.nan
        out[tech + '_raw'] = a_
        out['ref'] = ref
    in_strip = cell.intersection(strip).area / cell.area
    rows.append(dict(lat=r.lat, lon=r.lon, cf=getattr(r, "cf", np.nan), mine_onwind=r.onwind, atlite_onwind=out["onwind"], atlite_raw=out["onwind_raw"], atlite_noexcl=out["ref"],
                     in_strip=in_strip))
d = pd.DataFrame(rows)
# both are the eligible share of the whole cell (land strip, land cover, outside protected areas)
mine_solar = pd.read_csv(OUT + "eligibility_onshore.csv").set_index(["lat", "lon"]).solar
d["mine_solar"] = [mine_solar.get((a, b), np.nan) for a, b in zip(d.lat, d.lon)]
# normalised atlite value is the share of the shape inside the cell; both then refer to the whole cell
d["atlite_onwind_of_cell"] = d.atlite_onwind * d.in_strip
d["diff"] = d.mine_onwind - d.atlite_onwind_of_cell
d.to_csv(OUT + "eligibility_check_atlite.csv", index=False)
pd.set_option("display.width", 200)
print(d.round(3).to_string(index=False))
print("\nmean abs difference (share of cell): %.3f, max %.3f, correlation %.3f" % (d["diff"].abs().mean(), d["diff"].abs().max(), d.mine_onwind.corr(d.atlite_onwind_of_cell)))
big = d[d.mine_onwind > 0.05]
print("total eligible area, sample, relative difference: %.1f %%; cells with > 5 %% eligible (%d): %.1f %%, mean abs diff %.3f" % (
    100 * (d.mine_onwind.sum() / d.atlite_onwind_of_cell.sum() - 1), len(big), 100 * (big.mine_onwind.sum() / big.atlite_onwind_of_cell.sum() - 1), (big.mine_onwind - big.atlite_onwind_of_cell).abs().mean()))
print("atlite value without exclusion layers (should be 1): %.3f to %.3f" % (d.atlite_noexcl.min(), d.atlite_noexcl.max()))

# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""Eligible area of every ERA5 cell in Brazil's coastal zone (cells of coastal_cells_annual_energy.csv).

Follows PyPSA-Eur's determine_availability_matrix, evaluated per cell on the native rasters
and read window by window (the full 100 m land cover does not fit into the 10 GB workspace).

Onshore wind, PV: Copernicus LC100 classes of determine_availability_matrix_MD_UA.py
  (onwind 20,30,40,60,100; solar 20,30,40,50,60,90,100), inside Brazil, outside WDPA areas.
  Not done: PyPSA-Eur's 1 km buffer around urban land for onshore wind.
Offshore: inside the EEZ and outside land, outside WDPA, ship density below 400*8760*6,
  fixed: depth <= 60 m (AC: <= 30 km from the coast, DC: > 30 km), floating: 60 to 1000 m.
Both strips from coastal_zone.py. Result: eligible fraction and km2 per cell, p_nom_max = km2 x capacity_per_sqkm (config.default.yaml).
"""
import warnings
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import xarray as xr
from rasterio import features
from rasterio.transform import from_origin
from rasterio.windows import from_bounds
from shapely import box

warnings.filterwarnings("ignore", category=DeprecationWarning)
L = "data-brazil/layers/"
HALF = 0.15  # ERA5 cell is 0.3 deg
R_EARTH = 6371.0
SHIP_MAX = 400 * 8760 * 6
LC = {"onwind": [20, 30, 40, 60, 100], "solar": [20, 30, 40, 50, 60, 90, 100]}
LC["solar-hsat"] = LC["solar"]
DENSITY = {"onwind": 3.0, "solar": 5.1, "solar-hsat": 4.43,   # MW per km2, config.default.yaml
           "offwind-ac": 2.0, "offwind-dc": 2.0, "offwind-float": 2.0}

zone = pd.read_csv("results/brazil-potential/coastal_zone_cells.csv")
land_cells = zone[zone.land_km2 > 0][["lat", "lon"]].reset_index(drop=True)
sea_cells = zone[zone.sea_km2 > 0][["lat", "lon"]].reset_index(drop=True)
strips = gpd.read_file("results/brazil-potential/coastal_zone.gpkg").set_index("zone").geometry
land_strip, sea_strip = strips["land"], strips["sea"]  # land <= 100 km from the coast, EEZ <= 200 km from it

simp = 0.0005  # ~50 m, below the 100 m raster
land = gpd.read_file("zip://data-brazil/raw/gadm/gadm41_BRA_1.json.zip")
land = gpd.GeoSeries([land.geometry.make_valid().buffer(0).union_all()], crs=4326).simplify(simp)
eez = gpd.GeoSeries([gpd.read_file(L + "eez_brazil.gpkg").geometry.make_valid().union_all()], crs=4326).simplify(simp)
wdpa = gpd.read_file(L + "wdpa_brazil.gpkg")
wdpa = gpd.GeoSeries(wdpa.geometry.make_valid().simplify(simp), crs=4326)
wsi = wdpa.sindex
# land buffered by 30 km (equal-area CRS), for the AC / DC split
land30 = land.to_crs("ESRI:102033").buffer(30_000).simplify(500).to_crs(4326)


def rasterize(geoms, shape, transform):
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return np.zeros(shape, bool)
    return features.rasterize(geoms, out_shape=shape, transform=transform, fill=0, default_value=1,
                              dtype="uint8").astype(bool)


def protected(cellbox, shape, tf):
    return rasterize(wdpa.iloc[wsi.query(cellbox)].values, shape, tf)


def cell_area_km2(lat):
    a, b = np.radians(lat - HALF), np.radians(lat + HALF)
    return R_EARTH ** 2 * np.radians(2 * HALF) * (np.sin(b) - np.sin(a))


def row_weights(tf, n_rows):
    lat = tf.f + tf.e * (np.arange(n_rows) + 0.5)
    w = np.cos(np.radians(lat)); return (w / w.sum())[:, None]  # pixel rows are not equal-area


# ---- onshore -----------------------------------------------------------------
out = []
with rasterio.open(L + "copernicus_lc100.tif") as src:
    for r in land_cells.itertuples():
        b = (r.lon - HALF, r.lat - HALF, r.lon + HALF, r.lat + HALF)
        win = from_bounds(*b, src.transform).round_offsets().round_lengths()
        a = src.read(1, window=win, boundless=True, fill_value=255)
        tf = src.window_transform(win)
        cb = box(*b)
        inside = rasterize([land_strip.intersection(cb)], a.shape, tf)
        prot = protected(cb, a.shape, tf)
        w = row_weights(tf, a.shape[0]) * np.ones(a.shape[1])[None, :] / a.shape[1]
        row = dict(lat=r.lat, lon=r.lon, area_km2=cell_area_km2(r.lat), in_brazil=(w * inside).sum(),
                   protected=(w * (inside & prot)).sum())
        for t, codes in LC.items():
            ok = np.isin(a, codes) & inside
            row[t + "_lc"] = (w * ok).sum()
            row[t] = (w * (ok & ~prot)).sum()
        out.append(row)
on = pd.DataFrame(out)

# ---- offshore ----------------------------------------------------------------
gebco = xr.open_dataset(L + "gebco_brazil.nc").elevation
lat0, lon0, d = float(gebco.lat[0]), float(gebco.lon[0]), 15 / 3600
assert float(gebco.lat[1]) > lat0  # south to north
ship = rasterio.open(L + "shipdensity_brazil.tif")
ship_a = ship.read(1)
out = []
for r in sea_cells.itertuples():
    i0, i1 = int(round((r.lat - HALF - lat0) / d)), int(round((r.lat + HALF - lat0) / d))
    j0, j1 = int(round((r.lon - HALF - lon0) / d)), int(round((r.lon + HALF - lon0) / d))
    z = gebco.isel(lat=slice(i0, i1), lon=slice(j0, j1)).values.astype(np.float32)[::-1]  # north-up
    la = lat0 + d * (np.arange(i0, i1)[::-1])
    tf = from_origin(lon0 + d * (j0 - 0.5), la[0] + d / 2, d, d)
    ln = lon0 + d * np.arange(j0, j1)
    cb = box(r.lon - HALF, r.lat - HALF, r.lon + HALF, r.lat + HALF)
    inside = rasterize([sea_strip.intersection(cb)], z.shape, tf)  # EEZ without land, <= 200 km
    near = rasterize([land30.iloc[0].intersection(cb)], z.shape, tf)
    prot = protected(cb, z.shape, tf)
    inv = ~ship.transform
    cols = np.floor(inv.a * ln + inv.c).astype(int)[None, :] * np.ones((len(la), 1), int)
    rows = np.floor(inv.e * la + inv.f).astype(int)[:, None] * np.ones((1, len(ln)), int)
    s = ship_a[np.clip(rows, 0, ship_a.shape[0] - 1), np.clip(cols, 0, ship_a.shape[1] - 1)]
    s = np.where(s == ship.nodata, 0, s)
    busy = s > SHIP_MAX
    w = row_weights(tf, z.shape[0]) * np.ones(z.shape[1])[None, :] / z.shape[1]
    base = inside & ~prot & ~busy
    fixed = base & (z <= 0) & (z >= -60)
    row = dict(lat=r.lat, lon=r.lon, area_km2=cell_area_km2(r.lat), in_eez=(w * inside).sum(),
               protected=(w * (inside & prot)).sum(), busy_shipping=(w * (inside & busy)).sum(),
               **{"offwind-ac": (w * (fixed & near)).sum(), "offwind-dc": (w * (fixed & ~near)).sum(),
                  "offwind-float": (w * (base & (z < -60) & (z >= -1000))).sum()})
    out.append(row)
off = pd.DataFrame(out)

on.to_csv("results/brazil-potential/eligibility_onshore.csv", index=False)
off.to_csv("results/brazil-potential/eligibility_offshore.csv", index=False)

# ---- summary -----------------------------------------------------------------
pd.set_option("display.width", 200)
print(f"ONSHORE ({len(land_cells)} cells touching the 100 km land strip), km2")
for lbl, col in [("inside Brazil", "in_brazil")] + [(t + " land cover ok", t + "_lc") for t in LC] + \
                [(t + " after protected areas", t) for t in LC]:
    print(f"  {lbl:32s} {(on[col] * on.area_km2).sum():10.0f}")
print(f"  {'protected area (of Brazil land)':32s} {(on.protected * on.area_km2).sum():10.0f}")
print("OFFSHORE, km2")
for col in ["in_eez", "protected", "busy_shipping", "offwind-ac", "offwind-dc", "offwind-float"]:
    print(f"  {col:32s} {(off[col] * off.area_km2).sum():10.0f}")
print("ship density max in raster:", int(ship_a.max()), "threshold:", SHIP_MAX)
pot = {t: (on[t] * on.area_km2 * DENSITY[t]).sum() / 1e3 for t in LC}
pot |= {t: (off[t] * off.area_km2 * DENSITY[t]).sum() / 1e3 for t in ["offwind-ac", "offwind-dc", "offwind-float"]}
print("p_nom_max in the coastal zone, GW:", {k: round(v) for k, v in pot.items()})

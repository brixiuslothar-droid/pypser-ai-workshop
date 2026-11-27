# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""Coastal zone of Brazil as polygons, and the ERA5 cells that touch it.

Land strip: Brazilian land within LAND_KM of the coast. Sea strip: EEZ without land within SEA_KM
of the coast. A cell belongs to the zone if its box overlaps a strip (not only if its centre lies in it).
Coast = national outline where it touches the EEZ (no land borders). Equal-area CRS for distances.
Writes coastal_zone.gpkg (strips) and coastal_zone_cells.csv (lat, lon, land/sea overlap in km2).
"""
import warnings
import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from shapely import box

warnings.filterwarnings("ignore")
LAND_KM, SEA_KM, HALF, CRS = 100, 200, 0.15, "ESRI:102033"
OUT = "results/brazil-potential/"

land = gpd.read_file("zip://data-brazil/raw/gadm/gadm41_BRA_1.json.zip")
land = gpd.GeoSeries([land.geometry.make_valid().buffer(0).union_all()], crs=4326).to_crs(CRS).simplify(200).iloc[0]
eez = gpd.GeoSeries([gpd.read_file("data-brazil/layers/eez_brazil.gpkg").geometry.make_valid().union_all()],
                    crs=4326).to_crs(CRS).iloc[0]
coast = land.boundary.intersection(eez.buffer(5_000))
land_strip = land.intersection(coast.buffer(LAND_KM * 1e3))
sea_strip = eez.difference(land).intersection(coast.buffer(SEA_KM * 1e3))
strips = gpd.GeoDataFrame({"zone": ["land", "sea"]}, geometry=[land_strip, sea_strip], crs=CRS).to_crs(4326)
strips.to_file(OUT + "coastal_zone.gpkg", driver="GPKG")

cut = xr.open_dataarray(OUT + "coast_distance_km.nc")  # only for the ERA5 grid
rows = []
for y in cut.y.values:
    for x in cut.x.values:
        b = box(x - HALF, y - HALF, x + HALF, y + HALF)
        bm = gpd.GeoSeries([b], crs=4326).to_crs(CRS).iloc[0]
        la, se = bm.intersection(land_strip).area / 1e6, bm.intersection(sea_strip).area / 1e6
        if la > 0 or se > 0:
            rows.append((round(float(y), 2), round(float(x), 2), la, se, bm.area / 1e6))
z = pd.DataFrame(rows, columns=["lat", "lon", "land_km2", "sea_km2", "cell_km2"])
z.to_csv(OUT + "coastal_zone_cells.csv", index=False)
print("land cells:", int((z.land_km2 > 0).sum()), " sea cells:", int((z.sea_km2 > 0).sum()))
print("land strip km2: %.0f  sea strip km2: %.0f" % (land_strip.area / 1e6, sea_strip.area / 1e6))

# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""Distance of every ERA5 cell centre in Brazil to the Brazilian coast, in km.

Coast = the part of the national outline (GADM states) that touches the EEZ, so land
borders with neighbouring countries do not count. Distances in an equal-area CRS.
Negative on land, positive at sea.
"""
import geopandas as gpd
import numpy as np
import shapely
import xarray as xr
import atlite

CRS = "ESRI:102033"  # South America Albers
cutout = atlite.Cutout("data-brazil/weather/brazil-2013-era5.nc", chunks={"time": 744})
x, y = cutout.coords["x"].values, cutout.coords["y"].values
X, Y = np.meshgrid(x, y)

land = gpd.read_file("zip://data-brazil/raw/gadm/gadm41_BRA_1.json.zip")
land = gpd.GeoSeries([land.geometry.make_valid().buffer(0).union_all()], crs=4326).to_crs(CRS).iloc[0]
eez = gpd.read_file("data-brazil/layers/eez_brazil.gpkg")
eez = gpd.GeoSeries([eez.geometry.make_valid().union_all()], crs=4326).to_crs(CRS).iloc[0]

coast = land.boundary.intersection(eez.buffer(5_000))  # shore only, no land borders
print("coastline length km:", round(coast.length / 1e3))

pts = gpd.GeoSeries(gpd.points_from_xy(X.ravel(), Y.ravel()), crs=4326).to_crs(CRS)
d = shapely.distance(coast, pts.values).reshape(X.shape) / 1e3
on_land = shapely.contains_xy(land, pts.x.values, pts.y.values).reshape(X.shape)
d = np.where(on_land, -d, d)
xr.DataArray(d, coords={"y": y, "x": x}, name="coast_distance_km").to_netcdf(
    "results/brazil-potential/coast_distance_km.nc")
print("land cells within 50/100/200 km of coast:",
      [int(((-d > 0) & (-d <= k)).sum()) for k in (50, 100, 200)], "of", int(on_land.sum()))

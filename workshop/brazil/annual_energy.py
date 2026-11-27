# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""Annual energy per MW installed, for every ERA5 cell in the Brazilian coastal zone.

E [MWh/MW/a] = CF x 8760 h. Offshore wind is scaled by the config's correction_factor 0.8855.
Cells of the coastal zone (coastal_zone.py): every cell that overlaps the land strip (<= 100 km from
the coast) or the sea strip (EEZ within 200 km of the coast). Depth and protection are filtered later.
"""
import numpy as np
import pandas as pd
import xarray as xr

H, OFFSHORE_CORR = 8760, 0.8855
cf = xr.open_dataset("results/brazil-potential/capacity_factors.nc")
d = xr.open_dataarray("results/brazil-potential/coast_distance_km.nc")
X, Y = np.meshgrid(cf.x.values, cf.y.values)

z = pd.read_csv("results/brazil-potential/coastal_zone_cells.csv")
inzone_land = set(zip(z[z.land_km2 > 0].lat, z[z.land_km2 > 0].lon))
inzone_sea = set(zip(z[z.sea_km2 > 0].lat, z[z.sea_km2 > 0].lon))
Yr, Xr = np.round(Y, 2), np.round(X, 2)
land = np.array([(a, b) in inzone_land for a, b in zip(Yr.ravel(), Xr.ravel())]).reshape(X.shape)
sea = np.array([(a, b) in inzone_sea for a, b in zip(Yr.ravel(), Xr.ravel())]).reshape(X.shape)

tech = {"onwind": (land, 1.0), "solar": (land, 1.0), "solar-hsat": (land, 1.0),
        "offwind": (sea, OFFSHORE_CORR), "offwind-float": (sea, OFFSHORE_CORR)}
rows = []
for t, (mask, corr) in tech.items():
    e = cf[t].values * corr * H
    iy, ix = np.where(mask)
    rows.append(pd.DataFrame(dict(tech=t, lat=Y[iy, ix].round(2), lon=X[iy, ix].round(2),
                                  coast_km=d.values[iy, ix].round(0), cf=(cf[t].values * corr)[iy, ix],
                                  mwh_per_mw=e[iy, ix])))
df = pd.concat(rows, ignore_index=True)
df.to_csv("results/brazil-potential/coastal_cells_annual_energy.csv", index=False)

pd.set_option("display.width", 200)
g = df.groupby("tech").mwh_per_mw
s = pd.DataFrame({"cells": g.size(), "mean": g.mean(), "median": g.median(),
                  "best 10 %": g.quantile(0.9), "max": g.max()}).loc[list(tech)]
print(s.round(0).to_string())
print()
for t in tech:
    print(t); print(df[df.tech == t].nlargest(5, "mwh_per_mw")[["lat", "lon", "coast_km", "cf", "mwh_per_mw"]]
                    .round(3).to_string(index=False))

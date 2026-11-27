# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""Annual-mean capacity factor of every ERA5 cell in Brazil (weather year 2013).

Same turbines and panels as config.default.yaml, except that fixed PV faces north
(latitude_optimal) because Brazil lies in the southern hemisphere.
Computed lazily in monthly chunks, so the 5.8 GB cutout never sits in memory.
"""
import atlite
import xarray as xr

OUT = "results/brazil-potential/capacity_factors.nc"
c = atlite.Cutout("data-brazil/weather/brazil-2013-era5.nc", chunks={"time": 744})

cf = {}
wind = dict(smooth=False, add_cutout_windspeed=True, capacity_factor=True)
cf["onwind"] = c.wind("Vestas_V112_3MW", **wind)
cf["offwind"] = c.wind("NREL_ReferenceTurbine_2020ATB_5.5MW", **wind)  # offwind-ac/dc
cf["offwind-float"] = c.wind("NREL_ReferenceTurbine_5MW_offshore", **wind)
cf["solar"] = c.pv("CSi", "latitude_optimal", capacity_factor=True)
cf["solar-hsat"] = c.pv("CSi", "latitude_optimal", tracking="horizontal", capacity_factor=True)

ds = xr.Dataset(cf).compute()
ds.to_netcdf(OUT)
print(ds.to_dataframe().describe().T)

# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""Hourly availability profiles of the northern coast of Brazil, weather year 2013 (UTC), for the model.

Per technology, the cells with >= MIN_MW installable capacity north of lat -7 (lcoe_cells.csv, same cells as the
ranking) are sorted by capacity factor and cut into N_CLASSES classes of equal installable capacity, as the
baseline does for Germany (three site qualities). Each class profile is the mean of its cells' hourly capacity
factors, weighted by installable capacity (eligible area x power density), like PyPSA-Eur's layout weighting.
Same turbines/panels as capacity_factors.py; offshore wind x correction_factor 0.8855; values below
clip_p_max_pu = 0.01 set to 0 (config.default.yaml). Fixed PV faces north (latitude_optimal).
Writes profiles_north_1h.nc, profiles_north_2h.nc (2 h mean, clustering.temporal.averaging), profile_classes.csv.
"""
import numpy as np
import pandas as pd
import xarray as xr
import atlite

OUT = "results/brazil-potential/"
MIN_MW, N_CLASSES, CORR, CLIP = 100, 3, 0.8855, 0.01
cells = pd.read_csv(OUT + "lcoe_cells.csv").query("year == 2030 and rate == 'wacc' and north and p_nom_max_mw >= @MIN_MW")
cutout = atlite.Cutout("data-brazil/weather/brazil-2013-era5.nc", chunks={"time": 744})
x0, x1, y0, y1 = cells.lon.min() - 0.2, cells.lon.max() + 0.2, cells.lat.min() - 0.2, cells.lat.max() + 0.2
sub = cutout.sel(x=slice(x0, x1), y=slice(y0, y1))

SOURCE = {  # carrier -> (resource function, offshore)
    "onwind": (lambda c: c.wind("Vestas_V112_3MW", smooth=False, add_cutout_windspeed=True, aggregate_time=None), False),
    "solar": (lambda c: c.pv("CSi", "latitude_optimal", aggregate_time=None), False),
    "solar-hsat": (lambda c: c.pv("CSi", "latitude_optimal", tracking="horizontal", aggregate_time=None), False),
    "offwind-ac": (lambda c: c.wind("NREL_ReferenceTurbine_2020ATB_5.5MW", smooth=False, add_cutout_windspeed=True, aggregate_time=None), True),
    "offwind-dc": (lambda c: c.wind("NREL_ReferenceTurbine_2020ATB_5.5MW", smooth=False, add_cutout_windspeed=True, aggregate_time=None), True),
    "offwind-float": (lambda c: c.wind("NREL_ReferenceTurbine_5MW_offshore", smooth=False, add_cutout_windspeed=True, aggregate_time=None), True),
}
cache, profiles, classes = {}, {}, []
for car, (fn, offshore) in SOURCE.items():
    tag = "offwind-fixed" if car in ("offwind-ac", "offwind-dc") else car
    if tag not in cache:
        cache[tag] = fn(sub).compute()  # (time, y, x); a few hundred MB
    res = cache[tag]
    d = cells[cells.carrier == car].sort_values("cf").reset_index(drop=True)
    if d.empty:
        continue
    ts = res.sel(x=xr.DataArray(d.lon.values, dims="cell"), y=xr.DataArray(d.lat.values, dims="cell"),
                 method="nearest").transpose("time", "cell").values  # (time, cell)
    if offshore:
        ts = ts * CORR
    ts = np.where(ts < CLIP, 0.0, ts)
    w = d.p_nom_max_mw.values
    cum = (w.cumsum() - w / 2) / w.sum()  # capacity-weighted position of each cell
    cls = np.minimum((cum * N_CLASSES).astype(int), N_CLASSES - 1)
    for k in range(N_CLASSES):
        m = cls == k
        if not m.any():
            continue
        name = f"{car}-class{k}"
        profiles[name] = (ts[:, m] * w[m]).sum(1) / w[m].sum()
        classes.append(dict(profile=name, carrier=car, cls=k, cells=int(m.sum()), p_nom_max_mw=w[m].sum(),
                            cf_mean=profiles[name].mean(), cf_cells_min=d.cf[m].min(), cf_cells_max=d.cf[m].max(),
                            energy_gwh=(d.energy_gwh[m]).sum(), lat_mean=float(np.average(d.lat[m], weights=w[m])),
                            lon_mean=float(np.average(d.lon[m], weights=w[m])), full_load_h=profiles[name].sum()))
    print(f"{car:14s} {len(d):4d} cells, {w.sum()/1e3:7.1f} GW", flush=True)

time = pd.date_range("2013-01-01", periods=8760, freq="h")
assert len(time) == len(res.time) and (res.time.values == time.values).all(), "time axis"
ds = xr.Dataset({k: ("time", v.astype("float32")) for k, v in profiles.items()}, coords={"time": time})
ds.attrs = dict(description="availability (p_max_pu) of the northern coast of Brazil, weather year 2013, UTC",
                min_mw=MIN_MW, correction_factor_offshore=CORR, clip_p_max_pu=CLIP)
ds.to_netcdf(OUT + "profiles_north_1h.nc")
ds.resample(time="2h").mean().to_netcdf(OUT + "profiles_north_2h.nc")
cl = pd.DataFrame(classes)
cl.to_csv(OUT + "profile_classes.csv", index=False)
pd.set_option("display.width", 220)
print(cl[["profile", "cells", "p_nom_max_mw", "cf_mean", "cf_cells_min", "cf_cells_max", "full_load_h", "lat_mean", "lon_mean"]].round(3).to_string(index=False))

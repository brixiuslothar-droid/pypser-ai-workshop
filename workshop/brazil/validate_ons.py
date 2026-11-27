# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""Check the ERA5 wind profiles against the wind generation measured by the grid operator (ONS, 2013).

Plant level: ONS hourly generation of each wind farm in operation the whole year (>= 8000 hours), its capacity from
the ONS plant register (units in operation on 2013-01-01, matched by the CEG code without unit number), its location
from the WRI power plant database (matched by name). ERA5 hourly capacity factor (Vestas V112, as in the model) of the
cell holding the plant, weighted by capacity, against the measured capacity factor.
Time: ONS is Brasilia local time with daylight saving; converted to UTC without filling or wrapping: the hour that
does not exist on 2013-10-20, the empty day 2013-12-01 and the first hours of the UTC year are NaN and left out of every statistic.
Writes ons_validation_plants.csv and ons_validation_hourly.csv.
"""
import io
import warnings
import zipfile
import numpy as np
import pandas as pd
import xarray as xr
import atlite

warnings.filterwarnings("ignore")
OUT = "results/brazil-potential/"
ONS = "data-brazil/raw/ons/"


def to_utc(df, year=2013):
    """Hourly frame with naive ONS local index -> UTC year, NaN where ONS has no value (no filling)."""
    idx = df.index.tz_localize("America/Sao_Paulo", ambiguous=True, nonexistent="shift_forward")
    df = df.set_axis(idx.tz_convert("UTC").tz_localize(None))
    df = df[~df.index.duplicated()]
    full = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    return df.reindex(full)  # the first 2 UTC hours (local Dec 31 2012) and the last hours of local Dec 31 are missing


g = pd.read_parquet(ONS + "GERACAO_USINA-2_2013.parquet",
                    columns=["din_instante", "id_estado", "nom_tipousina", "nom_usina", "ceg", "val_geracao"])
g = g[g.nom_tipousina == "EOLIELÉTRICA"].copy()
g["mw"] = g.val_geracao.astype(float)
g["cegp"] = g.ceg.str.rsplit(".", n=1).str[0]
rows = g.groupby("nom_usina").size()
full_year = rows[rows >= 8000].index
g = g[g.nom_usina.isin(full_year)]
hourly = g.pivot_table(index="din_instante", columns="nom_usina", values="mw", aggfunc="sum")  # MW = MWh per hour
hourly = to_utc(hourly)

reg = pd.read_csv(ONS + "CAPACIDADE_GERACAO.csv", sep=";")
for c in ["ceg", "id_estado", "nom_usina"]:
    reg[c] = reg[c].str.strip()
reg = reg[reg.nom_tipousina.str.contains("EOL", na=False)].copy()
reg["cegp"] = reg.ceg.str.rsplit(".", n=1).str[0]
on = pd.to_datetime(reg.dat_entradaoperacao); off = pd.to_datetime(reg.dat_desativacao)
reg["active"] = (on <= "2013-01-01") & (off.isna() | (off >= "2013-01-01"))
cap_active = reg[reg.active].groupby("cegp").val_potenciaefetiva.sum()
cap_all = reg.groupby("cegp").val_potenciaefetiva.sum()

meta = g.groupby("nom_usina").agg(state=("id_estado", "first"), cegp=("cegp", "first")).reset_index()
meta["cap_active_mw"] = meta.cegp.map(cap_active)
meta["cap_all_mw"] = meta.cegp.map(cap_all)
meta["gen_mean_mw"] = meta.nom_usina.map(hourly.mean())
meta["gen_max_mw"] = meta.nom_usina.map(hourly.max())
meta["cf_active"] = meta.gen_mean_mw / meta.cap_active_mw
meta["cf_all"] = meta.gen_mean_mw / meta.cap_all_mw

z = zipfile.ZipFile("data-brazil/raw/wri/global_power_plant_database_v_1_3.zip")
wri = pd.read_csv(z.open("global_power_plant_database.csv"), low_memory=False)
wri = wri[(wri.country == "BRA") & (wri.primary_fuel == "Wind")].copy()
wri["key"] = wri.name.str.lower().str.strip()
meta["key"] = meta.nom_usina.str.lower().str.strip()
meta = meta.merge(wri[["key", "latitude", "longitude", "capacity_mw"]].drop_duplicates("key"), on="key", how="left")
meta.to_csv(OUT + "ons_validation_plants_raw.csv", index=False)

# ---- ERA5 at the plants ------------------------------------------------------------------------------
m = meta.dropna(subset=["latitude", "cap_active_mw"]).reset_index(drop=True)
cutout = atlite.Cutout("data-brazil/weather/brazil-2013-era5.nc", chunks={"time": 744})
x0, x1, y0, y1 = m.longitude.min() - 0.4, m.longitude.max() + 0.4, m.latitude.min() - 0.4, m.latitude.max() + 0.4
sub = cutout.sel(x=slice(x0, x1), y=slice(y0, y1))
era = sub.wind("Vestas_V112_3MW", smooth=False, add_cutout_windspeed=True, aggregate_time=None).compute()
e = era.sel(x=xr.DataArray(m.longitude.values, dims="p"), y=xr.DataArray(m.latitude.values, dims="p"),
            method="nearest").transpose("time", "p").values
e = np.where(e < 0.01, 0.0, e)
E = pd.DataFrame(e, index=era.time.values, columns=m.nom_usina)
M = (hourly[m.nom_usina] / m.set_index("nom_usina").cap_active_mw).clip(upper=1.2)  # measured capacity factor
ok = M.notna()
m["cf_measured"] = [M[c][ok[c]].mean() for c in m.nom_usina]
m["cf_era5"] = [E[c][ok[c]].mean() for c in m.nom_usina]
m["corr_hourly"] = [M[c].corr(E[c]) for c in m.nom_usina]
m["corr_daily"] = [M[c].resample("D").mean().corr(E[c].where(ok[c]).resample("D").mean()) for c in m.nom_usina]
m["corr_monthly"] = [M[c].resample("MS").mean().corr(E[c].where(ok[c]).resample("MS").mean()) for c in m.nom_usina]
m["bias"] = m.cf_era5 - m.cf_measured
m["ratio"] = m.cf_era5 / m.cf_measured
m.drop(columns=["key"]).to_csv(OUT + "ons_validation_plants.csv", index=False)

pd.set_option("display.width", 220)
print(f"{len(m)} wind farms with capacity, coordinates and a full year; hours without ONS value: {int((~ok).all(axis=1).sum())}")
print(m[["nom_usina", "state", "cap_active_mw", "cf_measured", "cf_era5", "bias", "corr_hourly", "corr_daily", "corr_monthly"]].round(3).to_string(index=False))
ne = m[m.state.isin(["CE", "RN", "BA"])]
w = ne.cap_active_mw
print("\nNortheast (CE, RN, BA), %d farms, %.0f MW:" % (len(ne), w.sum()))
print("  capacity-weighted CF measured %.3f, ERA5 %.3f, bias %+.3f (ERA5 / measured %.2f)" %
      (np.average(ne.cf_measured, weights=w), np.average(ne.cf_era5, weights=w), np.average(ne.bias, weights=w),
       np.average(ne.cf_era5, weights=w) / np.average(ne.cf_measured, weights=w)))
for st_, d in m.groupby("state"):
    print(f"  {st_}: measured {np.average(d.cf_measured, weights=d.cap_active_mw):.3f}  ERA5 {np.average(d.cf_era5, weights=d.cap_active_mw):.3f}  mean hourly corr {d.corr_hourly.mean():.2f}")
# aggregated series of the northeast (this is what the model sees)
cols = list(ne.nom_usina)
Mn = (M[cols] * w.values).sum(1, min_count=1) / np.where(M[cols].notna().all(axis=1), w.sum(), np.nan)
En = (E[cols] * w.values).sum(1) / w.sum()
Mn = Mn.dropna(); En = En.loc[Mn.index]
print("\nAggregated northeast series (%d hours): hourly corr %.2f, daily %.2f, monthly %.2f" % (
    len(Mn), Mn.corr(En), Mn.resample("D").mean().corr(En.resample("D").mean()), Mn.resample("MS").mean().corr(En.resample("MS").mean())))
dm, de = Mn.groupby(Mn.index.hour).mean(), En.groupby(En.index.hour).mean()
print("  diurnal shape correlation %.2f; hour of maximum UTC measured %d, ERA5 %d; amplitude measured %.2f, ERA5 %.2f" % (dm.corr(de), dm.idxmax(), de.idxmax(), dm.max() - dm.min(), de.max() - de.min()))
mm, me = Mn.resample("MS").mean(), En.resample("MS").mean()
print("  monthly CF measured:", mm.round(2).values.tolist()); print("  monthly CF ERA5:    ", me.round(2).values.tolist())
pd.DataFrame({"measured": Mn, "era5": En}).to_csv(OUT + "ons_validation_hourly.csv")
# bias-corrected CF: what would ERA5 need to be scaled by
print("\nscale factor measured / ERA5 (capacity weighted, northeast): %.3f" % (np.average(ne.cf_measured, weights=w) / np.average(ne.cf_era5, weights=w)))

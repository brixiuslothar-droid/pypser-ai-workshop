# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""
Check modelled wind generation against ONS measurements, 2013 (role 2 guardrail).

For ONS-dispatched wind plants in CE, RN and BA that ran all year, the model
(ERA5 cutout, same turbine as brazil_import.turbine) is evaluated at the plants'
coordinates (WRI Global Power Plant Database, matched by name) and compared with
measured generation: capacity factor, hourly correlation, mean diurnal and
monthly shape. The ratio of measured to modelled CF is the correction factor
for brazil_import.correction_factor.onwind.

    pixi run python workshop/brazil/validate_wind.py --out results/brazil-validation
"""

import argparse
import sys
import unicodedata
import zipfile
from pathlib import Path

import atlite
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plotstyle"))
import studystyle as st  # noqa: E402
from ons_wind import measured_wind  # noqa: E402

WRI = Path("data-brazil/raw/wri/global_power_plant_database_v_1_3.zip")
CUTOUT = Path("data-brazil/weather/brazil-2013-era5.nc")


def norm(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper().strip()


def wri_wind():
    z = zipfile.ZipFile(WRI)
    f = next(n for n in z.namelist() if n.endswith(".csv") and "database" in n.lower())
    d = pd.read_csv(z.open(f), low_memory=False,
                    usecols=["country", "primary_fuel", "name", "latitude", "longitude", "capacity_mw"])
    d = d[(d.country == "BRA") & (d.primary_fuel == "Wind")].copy()
    d["N"] = d.name.map(norm).str.replace(r"^EOLICA\s+", "", regex=True)
    return d


def match_coords(tab):
    d = wri_wind()
    rows = {}
    for ceg, r in tab.iterrows():
        exact = d[d.N == norm(r["name"])]
        if len(exact) == 1:
            rows[ceg] = exact.iloc[0][["latitude", "longitude"]]
    return pd.DataFrame(rows).T.astype(float)


def modelled(plants, turbine):
    """Hourly modelled generation (MW) per state at plant cells, plant capacity as layout."""
    cutout = atlite.Cutout(CUTOUT)
    out = {}
    for state, grp in plants.groupby("state"):
        site = cutout.sel(x=slice(grp.longitude.min() - 0.5, grp.longitude.max() + 0.5),
                          y=slice(grp.latitude.min() - 0.5, grp.latitude.max() + 0.5))
        layout = xr.zeros_like(site.data["height"]).load()
        for _, p in grp.iterrows():
            cell = dict(x=layout.x.sel(x=p.longitude, method="nearest"),
                        y=layout.y.sel(y=p.latitude, method="nearest"))
            layout.loc[cell] += p.capacity_mw
        gen = site.wind(turbine=turbine, add_cutout_windspeed=True, layout=layout,
                        aggregate_time=None)
        out[state] = gen.squeeze(drop=True).to_pandas()
    return pd.DataFrame(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--turbine", default="Vestas_V112_3MW")
    ap.add_argument("--out", type=Path, default=Path("results/brazil-validation"))
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    tab, _ = measured_wind()
    ok = tab[tab.full_year & tab.capacity_ok & tab.capacity_mw.gt(0)]
    coords = match_coords(ok)
    plants = ok.join(coords, how="inner")
    print(f"{len(plants)} of {len(ok)} usable plants matched to WRI coordinates")

    from ons_wind import plant_generation
    gen, _ = plant_generation()
    meas = pd.DataFrame({s: gen[g.index].sum(axis=1) for s, g in plants.groupby("state")})
    cap = plants.groupby("state").capacity_mw.sum()
    mod = modelled(plants, a.turbine)
    mod.index = pd.DatetimeIndex(mod.index)
    meas, mod = meas.align(mod, join="inner", axis=0)

    res = pd.DataFrame({
        "plants": plants.groupby("state").size(),
        "capacity_mw": cap,
        "cf_measured": meas.mean() / cap,
        "cf_modelled": mod.mean() / cap,
        "corr_hourly": [meas[s].corr(mod[s]) for s in cap.index],
        "corr_daily": [meas[s].resample("D").mean().corr(mod[s].resample("D").mean()) for s in cap.index],
    })
    res["correction_factor"] = res.cf_measured / res.cf_modelled
    allp = pd.Series({"plants": res.plants.sum(), "capacity_mw": cap.sum(),
                      "cf_measured": meas.sum(axis=1).mean() / cap.sum(),
                      "cf_modelled": mod.sum(axis=1).mean() / cap.sum(),
                      "corr_hourly": meas.sum(axis=1).corr(mod.sum(axis=1)),
                      "corr_daily": meas.sum(axis=1).resample("D").mean().corr(mod.sum(axis=1).resample("D").mean())})
    allp["correction_factor"] = allp.cf_measured / allp.cf_modelled
    res.loc["all"] = allp
    res.round(3).to_csv(a.out / "wind_validation.csv")
    print(res.round(3).to_string())

    # figure: mean diurnal (UTC) and monthly capacity factor, measured vs modelled, all plants
    st.use()
    m_all, s_all = meas.sum(axis=1) / cap.sum(), mod.sum(axis=1) / cap.sum()
    fig, axes = plt.subplots(1, 2, figsize=(5.6, 3.0))
    for ax, key, title in [(axes[0], m_all.index.hour, "Hour of day (UTC)"),
                           (axes[1], m_all.index.month, "Month")]:
        x = np.unique(key)
        st.line(ax, x, m_all.groupby(key).mean().values, st.GROUPS["Onshore wind"], label="ONS")
        st.line(ax, x, s_all.groupby(key).mean().values, st.NEUTRAL, label="model")
        ax.set_xlabel(title)
        ax.set_xticks(x[::3] if len(x) > 12 else x[::2])
        ax.set_ylim(0, None)
    fig.suptitle("Wind capacity factor in north-east Brazil, 2013, measured and modelled",
                 x=0.02, ha="left", fontweight="bold", fontsize=9)
    for ext in ("pdf", "png"):
        fig.savefig(a.out / f"wind_validation.{ext}", dpi=300)

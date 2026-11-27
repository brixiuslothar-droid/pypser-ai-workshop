# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""
Screen candidate export regions in north-east Brazil for the cable (role 2).

For each box: wind and solar capacity factors of the best land cells (ERA5
cutout, same turbine and panel as the model), the wind share that minimises
the LCOE of the site, wind-solar correlation, and a screening cost per MWh
delivered in Germany: site LCOE plus the cable (cost table, length = great
circle x 1.25, losses as sector.transmission_efficiency.DC), with the cable
sized to the site so that its utilisation equals the site's capacity factor.
All annualised at the E2 WACC of 10 % real.

Screening only: no land eligibility beyond land/sea, no grid to the coast.

    pixi run python workshop/brazil/scan_regions.py --year 2035 --out results/brazil-validation
"""

import argparse
import sys
from pathlib import Path

import atlite
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "workshop/plotstyle"))
import studystyle as st  # noqa: E402
from scripts.add_brazil_import import annualised, haversine_km  # noqa: E402

CUTOUT = Path("data-brazil/weather/brazil-2013-era5.nc")
# lon range, lat range, coastal landing point (lon, lat); public place names
REGIONS = {
    "CE Pecem":          ([-39.5, -38.0], [-4.5, -3.0], (-38.80, -3.53)),
    "CE east (Aracati)": ([-38.3, -36.9], [-5.2, -4.0], (-37.77, -4.56)),
    "CE west (Camocim)": ([-41.2, -39.8], [-3.5, -2.6], (-40.84, -2.90)),
    "PI coast":          ([-42.3, -41.0], [-3.6, -2.7], (-41.78, -2.90)),
    "RN north":          ([-36.5, -35.1], [-6.0, -4.9], (-35.25, -5.20)),
    "RN Mossoro":        ([-37.8, -36.5], [-5.6, -4.8], (-37.10, -4.95)),
    "BA interior":       ([-43.0, -41.5], [-15.0, -13.5], (-38.50, -12.97)),  # lands at Salvador
}
DE_BUS = (8.21, 52.52)  # DE0 7, the bus the model connects to


def region_profiles(cutout, xs, ys, turbine, panel, best):
    site = cutout.sel(x=slice(*sorted(xs)), y=slice(*sorted(ys)))
    land = (site.data["height"] > 1.0).load()
    wcf = site.wind(turbine=turbine, add_cutout_windspeed=True, capacity_factor=True)
    wcf = wcf.where(land)
    thr = float(wcf.quantile(1 - best))
    layout = ((wcf >= thr) & land).astype(float)
    kw = dict(layout=layout, per_unit=True, aggregate_time=None)
    w = site.wind(turbine=turbine, add_cutout_windspeed=True, **kw).squeeze(drop=True).to_pandas()
    s = site.pv(panel=panel, orientation="latitude_optimal", **kw).squeeze(drop=True).to_pandas()
    return pd.DataFrame({"onwind": w, "solar": s}).clip(0, 1), int(layout.sum())


WACC = 0.10  # decisions.md E2, Brazilian generation and cable


def site_lcoe(cf, share, costs):
    annual = share * annualised(costs, "onwind", WACC) + (1 - share) * annualised(costs, "solar-utility", WACC)
    mix = share * cf.onwind + (1 - share) * cf.solar
    vom = share * cf.onwind.mean() * costs.at["onwind", "marginal_cost"] + \
        (1 - share) * cf.solar.mean() * costs.at["solar-utility", "marginal_cost"]
    return (annual + 8760 * vom) / (8760 * mix.mean()), mix


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2035)
    ap.add_argument("--costs", type=Path, default=Path("resources/de10-br-import"))
    ap.add_argument("--best", type=float, default=0.25, help="share of best land cells")
    ap.add_argument("--wind-correction", type=float, default=1.0)
    ap.add_argument("--turbine", default="Vestas_V112_3MW")
    ap.add_argument("--panel", default="CSi")
    ap.add_argument("--out", type=Path, default=Path("results/brazil-validation"))
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    costs = pd.read_csv(a.costs / f"costs_{a.year}_processed.csv", index_col=0)
    cutout = atlite.Cutout(CUTOUT)
    rows = {}
    for name, (xs, ys, landing) in REGIONS.items():
        cf, cells = region_profiles(cutout, xs, ys, a.turbine, a.panel, a.best)
        cf["onwind"] = (cf.onwind * a.wind_correction).clip(upper=1)
        lcoe_w, _ = site_lcoe(cf, 1.0, costs)
        lcoe_s, _ = site_lcoe(cf, 0.0, costs)
        length = 1.25 * float(haversine_km(*landing, *DE_BUS))
        eff = 0.98 * 0.977 ** (length / 1e3)
        cable = annualised(costs, "HVDC submarine", WACC) * length + annualised(costs, "HVDC inverter pair", WACC)

        def delivered_cost(share):
            lcoe, mix = site_lcoe(cf, share, costs)
            delivered = 8760 * mix.mean() * eff      # MWh per MW of cable at the German end
            return (lcoe * 8760 * mix.mean() + cable) / delivered

        # the wind share that minimises the cost delivered in Germany, not the site LCOE:
        # the cable dominates, so its utilisation matters more than the cheapest MWh
        shares = np.round(np.arange(0, 1.01, 0.05), 2)
        best_share = shares[int(np.argmin([delivered_cost(sh) for sh in shares]))]
        lcoe, mix = site_lcoe(cf, best_share, costs)
        delivered = 8760 * mix.mean() * eff
        rows[name] = dict(
            cells=cells, cf_onwind=cf.onwind.mean(), cf_solar=cf.solar.mean(),
            lcoe_onwind=lcoe_w, lcoe_solar=lcoe_s,
            wind_share_opt=best_share, cf_mix=mix.mean(), corr_wind_solar=cf.onwind.corr(cf.solar),
            lcoe_site=lcoe, length_km=length, efficiency=eff,
            cost_delivered=(lcoe * 8760 * mix.mean() + cable) / delivered,
        )
        print(name, {k: round(v, 3) for k, v in rows[name].items()}, flush=True)
    res = pd.DataFrame(rows).T.astype(float).sort_values("cost_delivered")
    res.round(3).to_csv(a.out / f"region_scan_{a.year}.csv")
    pd.set_option("display.width", 200)
    print(res.round(3).to_string())

    st.use()
    fig, axes = plt.subplots(1, 2, figsize=(5.6, 3.2), sharey=True)
    y = np.arange(len(res))
    axes[0].barh(y, res.lcoe_site, color=st.GROUPS["Onshore wind"], height=0.62, zorder=2)
    axes[1].barh(y, res.cost_delivered, color=st.color("Brazil cable"), height=0.62, zorder=2)
    for ax, col, title in [(axes[0], "lcoe_site", "Site LCOE"), (axes[1], "cost_delivered", "Delivered in Germany")]:
        for yi, v in zip(y, res[col]):
            ax.annotate(f"{v:,.0f}", (v, yi), xytext=(3, 0), textcoords="offset points",
                        va="center", fontsize=7.5, color="#222222")
        ax.set_title(title, loc="left", fontsize=8)
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(y, res.index)
    axes[0].invert_yaxis()
    fig.suptitle(f"Cost of Brazilian export power by region, {a.year}, EUR/MWh",
                 x=0.02, ha="left", fontweight="bold", fontsize=9)
    for ext in ("pdf", "png"):
        fig.savefig(a.out / f"region_scan_{a.year}.{ext}", dpi=300)

# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""Rank the offered sites of workshop/inputs/site_shortlist.csv by cost and suitability.

Per site: eligibility of the point (protected area, land cover, eligible share of its ERA5 cell),
levelised cost from the offered CAPEX/OPEX/lease (BRL -> EUR, constant over the years: the offers carry no
price year) and from the cost tables of all horizons, at 7 % and at the WACC of the Brazilian generation tranche
(7.62 %, financing_term_sheet.md), each at the measured capacity factor.
The shortlist holds personal contact data: only site ids and technical/cost columns are written out.
"""
import warnings
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import Point

warnings.filterwarnings("ignore")
BRL_PER_EUR = 6.2385      # financing_term_sheet.md, Brazilian tranche, price base 2025
g_, b_, m_, t_, e_ = 0.62, 0.02635, 0.0312, 0.34, 0.1385
RATES = {"r07": 0.07, "wacc": g_ * (b_ + m_) * (1 - t_) + (1 - g_) * e_}  # 7 % as for Germany; WACC 7.62 %
YEARS = [2025, 2030, 2035, 2040, 2045, 2050]
H = 8760
LC_OK = {"onwind": [20, 30, 40, 60, 100], "solar": [20, 30, 40, 50, 60, 90, 100]}
COST_TECH = {"onwind": "onwind", "solar": "solar-utility", "offwind": "offwind"}


def annuity(n, r):
    return r / (1 - (1 + r) ** -n)


s = pd.read_csv("workshop/inputs/site_shortlist.csv")
wdpa = gpd.read_file("data-brazil/layers/wdpa_brazil.gpkg")
wdpa = gpd.GeoSeries(wdpa.geometry.make_valid(), crs=4326)
elig = pd.concat([pd.read_csv("results/brazil-potential/eligibility_onshore.csv"),
                  pd.read_csv("results/brazil-potential/eligibility_offshore.csv")])
lc = rasterio.open("data-brazil/layers/copernicus_lc100.tif")

rows = []
for r in s.itertuples():
    pt = Point(r.lon, r.lat)
    prot = wdpa.iloc[wdpa.sindex.query(pt, predicate="within")]
    lc_class = next(lc.sample([(r.lon, r.lat)]))[0] if r.technology != "offwind" else None
    lc_ok = None if lc_class is None else int(lc_class in LC_OK[r.technology])
    rows.append((prot.shape[0], lc_class, lc_ok))
s[["n_protected", "landcover", "landcover_ok"]] = rows

# eligible share of the ERA5 cell holding the site
cells = pd.read_csv("results/brazil-potential/potential_per_cell.csv")
share = []
for r in s.itertuples():
    t = {"onwind": "onwind", "solar": "solar", "offwind": "offwind"}[r.technology]
    d = cells[cells.tech == t]
    dist = np.maximum((d.lat - r.lat).abs(), (d.lon - r.lon).abs())
    i = dist.idxmin()
    # the eligibility was computed only for the coastal zone: no value if the site lies outside it
    share.append((d.loc[i, "eligible_km2"], d.loc[i, "p_nom_max_mw"]) if dist.min() <= 0.15 else (np.nan, np.nan))
s[["cell_eligible_km2", "cell_p_nom_max_mw"]] = share

# levelised cost, EUR/MWh -------------------------------------------------------
cf = s.capacity_factor_measured
lease_eur_mw = s.lease_brl_per_ha_year.fillna(0) * s.area_km2 * 100 / s.buildable_mw / BRL_PER_EUR  # EUR/MW/a
for rn, r in RATES.items():
    life = s.technology.map({"onwind": 30, "solar": 40, "offwind": 30})
    s[f"lcoe_offer_{rn}"] = ((s.capex_offer_brl_per_kw * 1e3 * life.map(lambda n: annuity(n, r)) + s.opex_offer_brl_per_kw_year * 1e3)
                             / BRL_PER_EUR + lease_eur_mw) / (H * cf)
    for y in YEARS:
        c = pd.read_csv(f"resources/de10-myopic/costs_{y}_processed.csv", index_col=0)
        vals = []
        for t in s.technology:
            k = COST_TECH[t]
            inv = c.at[k, "investment"]  # EUR/MW in the processed table (EUR/kW x 1000)
            vals.append((annuity(c.at[k, "lifetime"], r) + c.at[k, "FOM"] / 100) * inv)
        s[f"lcoe_table_{rn}_{y}"] = np.array(vals) / (H * cf) + s.technology.map(lambda t: c.at[COST_TECH[t], "marginal_cost"])
s["offer_vs_table_2030_wacc_pct"] = 100 * (s.lcoe_offer_wacc / s.lcoe_table_wacc_2030 - 1)
s["capex_offer_eur_kw"] = s.capex_offer_brl_per_kw / BRL_PER_EUR
c30 = pd.read_csv("resources/de10-myopic/costs_2030_processed.csv", index_col=0)
s["capex_table_2030_eur_kw"] = s.technology.map(lambda t: c30.at[COST_TECH[t], "investment"] / 1e3)  # EUR/MW -> EUR/kW
s["suitable"] = (s.n_protected == 0) & (s.landcover_ok.fillna(1) == 1) & ~(s.cell_eligible_km2 == 0)  # NaN: cell not computed
s["energy_gwh"] = s.buildable_mw * H * cf / 1e3

tabcols = [f"lcoe_table_{rn}_{y}" for rn in RATES for y in YEARS]
out = s[["site_id", "state", "technology", "buildable_mw", "area_km2", "capacity_factor_measured", "coast_km",
         "grid_connection_km", "n_protected", "landcover", "landcover_ok", "cell_eligible_km2", "suitable",
         "capex_offer_eur_kw", "capex_table_2030_eur_kw", "lcoe_offer_r07", "lcoe_offer_wacc"] + tabcols +
        ["offer_vs_table_2030_wacc_pct", "energy_gwh", "exclusivity_until"]].sort_values("lcoe_table_wacc_2030")
out.to_csv("results/brazil-potential/shortlist_ranking.csv", index=False)
pd.set_option("display.width", 250)
print(f"WACC {100 * RATES['wacc']:.2f} %")
print(out[["site_id", "technology", "capacity_factor_measured", "suitable", "lcoe_offer_wacc", "lcoe_table_wacc_2025",
           "lcoe_table_wacc_2030", "lcoe_table_wacc_2050", "lcoe_table_r07_2030", "offer_vs_table_2030_wacc_pct"]].round(1).to_string(index=False))

# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""Which point on the northern coast of Brazil can collect the most and cheapest renewable energy?

Candidates: points every STEP_KM along the mainland coast north of lat -7 (outline touching the EEZ, no islands).
Sites: for each ERA5 cell and domain (land / sea) the cheapest option of lcoe_cells.csv (2030, WACC 7.62 %,
cells >= 100 MW); a land and a sea site of the same cell do not share an area.
Delivered cost at a candidate = site LCOE + transmission to the point, straight line x 1.25 (line length_factor):
  land sites up to 150 km: HVAC overhead; beyond: HVDC overhead + inverter pair; sea sites: only the way beyond the
  point where their own connection already reaches the coast (max(0, distance - distance to coast)), HVAC overhead.
  Lines are not shared between sites (conservative); costs from costs_2030_processed.csv at the WACC.
Metrics per candidate, within RADIUS_KM: GW and TWh delivered below 30 / 40 / 50 EUR/MWh; average and marginal
cost of the cheapest CABLE_TWH (9.25 TWh a year, the offtake in the term sheet) from all technologies and from wind only.
Cable length: great circle to Wilhelmshaven, shown apart (rough, role 1 owns the route): cost per km from
cable_system_design.yaml (deep class, 2 cables, 16 % owner's cost, 2000 MW, 40 years, 6.93 % cable WACC).
"""
import warnings
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

warnings.filterwarnings("ignore")
OUT = "results/brazil-potential/"
CRS, STEP_KM, RADIUS_KM, LF, H = "ESRI:102033", 25, 500, 1.25, 8760
CABLE_TWH, AC_MAX_KM = 9.25, 150
g, base, margin, tax, eq = 0.62, 0.02635, 0.0312, 0.34, 0.1385
WACC = g * (base + margin) * (1 - tax) + (1 - g) * eq
ann = lambda n, r: r / (1 - (1 + r) ** -n)

c = pd.read_csv("resources/de10-myopic/costs_2030_processed.csv", index_col=0)
cap = lambda k: (ann(c.at[k, "lifetime"], WACC) + c.at[k, "FOM"] / 100) * c.at[k, "investment"]
AC, DC, INV = cap("HVAC overhead"), cap("HVDC overhead"), cap("HVDC inverter pair")  # EUR/MW/km/a, EUR/MW/a

# ---- sites -------------------------------------------------------------------------------------------
d = pd.read_csv(OUT + "lcoe_cells.csv").query("year == 2030 and rate == 'wacc' and north and p_nom_max_mw >= 100")
d["domain"] = np.where(d.carrier.str.startswith("offwind"), "sea", "land")
s = d.sort_values("lcoe_eur_mwh").drop_duplicates(["lat", "lon", "domain"]).reset_index(drop=True)
s["wind"] = s.carrier.isin(["onwind", "offwind-ac", "offwind-dc", "offwind-float"])
s["coast_d"] = s.distance_km.where(s.domain == "sea", 0.0)  # sea: connection to the coast already in the LCOE
xy = gpd.GeoSeries(gpd.points_from_xy(s.lon, s.lat), crs=4326).to_crs(CRS)
sx, sy = xy.x.values / 1e3, xy.y.values / 1e3

# ---- candidates along the coast ----------------------------------------------------------------------
land = gpd.read_file("zip://data-brazil/raw/gadm/gadm41_BRA_1.json.zip")
land = gpd.GeoSeries([land.geometry.make_valid().buffer(0).union_all()], crs=4326).to_crs(CRS).simplify(200).iloc[0]
mainland = max(shapely.get_parts(land), key=lambda p: p.area)  # no islands (Fernando de Noronha, Trindade ...)
eez = gpd.GeoSeries([gpd.read_file("data-brazil/layers/eez_brazil.gpkg").geometry.make_valid().union_all()], crs=4326).to_crs(CRS).iloc[0]
coast = mainland.boundary.intersection(eez.buffer(5_000))
lines = [coast] if coast.geom_type == "LineString" else list(shapely.get_parts(coast))
pts = []
for ln in lines:
    for dist in np.arange(0, ln.length, STEP_KM * 1e3):
        pts.append(ln.interpolate(dist))
cand = gpd.GeoSeries(pts, crs=CRS).to_crs(4326)
cand = pd.DataFrame({"lon": cand.x, "lat": cand.y}).query("lat >= -7.0").round(3).drop_duplicates().reset_index(drop=True)
cxy = gpd.GeoSeries(gpd.points_from_xy(cand.lon, cand.lat), crs=4326).to_crs(CRS)
print(len(cand), "candidate points,", len(s), "sites")

# ---- great circle to Wilhelmshaven -------------------------------------------------------------------
def gc(lat, lon, lat0=53.52, lon0=8.10):
    p1, p2 = np.radians(lat), np.radians(lat0)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon0 - lon) / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(a))
cand["cable_km"] = gc(cand.lat, cand.lon)
cab_cost_m = 2 * 3094.65 + 468200 / 5.5 / 1000  # EUR per m of route: supply of two cables + lay spread (deep class)
cab_a = (ann(40, 0.0693) + 0.0035) * cab_cost_m * 1e3 * 1.16  # EUR/km/a, whole link
cable_eur_mwh_km = cab_a / (CABLE_TWH * 1e6)

# ---- metrics --------------------------------------------------------------------------------------------
def cheapest(tab, twh):
    t = tab.sort_values("deliv").copy(); t["cum"] = t.energy_gwh.cumsum() / 1e3
    if t.empty or t.cum.iloc[-1] < twh:  # not enough energy in the radius
        return np.nan, np.nan, (t.cum.iloc[-1] if len(t) else 0.0)
    k = t[t.cum >= twh].index[0]; u = t.loc[:k].copy()
    u.iloc[-1, u.columns.get_loc("energy_gwh")] -= (u.cum.iloc[-1] - twh) * 1e3  # only what is needed
    return np.average(u.deliv, weights=u.energy_gwh), t.loc[k, "deliv"], t.cum.iloc[-1]

rows = []
for i, (cx, cy) in enumerate(zip(cxy.x.values / 1e3, cxy.y.values / 1e3)):
    dist = np.hypot(sx - cx, sy - cy)
    m = dist <= RADIUS_KM
    t = s[m].copy(); dd = dist[m] * LF
    extra = np.where(t.domain == "sea", np.maximum(0, dd - t.coast_d.values), dd)
    tx = np.where(extra <= AC_MAX_KM, extra * AC, extra * DC + INV)  # EUR/MW/a
    t["deliv"] = t.lcoe_eur_mwh + tx / (H * t.cf)
    r = dict(cand[["lat", "lon", "cable_km"]].iloc[i])
    r["cells_in_radius"] = len(t)
    for thr in (30, 40, 50):
        x = t[t.deliv < thr]; r[f"GW<{thr}"] = x.p_nom_max_mw.sum() / 1e3; r[f"TWh<{thr}"] = x.energy_gwh.sum() / 1e3
    r["avg_all"], r["marg_all"], r["TWh_total"] = cheapest(t, CABLE_TWH)
    r["avg_wind"], r["marg_wind"], r["TWh_wind"] = cheapest(t[t.wind], CABLE_TWH)
    r["avg_all_cable_incl"] = r["avg_all"] + cable_eur_mwh_km * r["cable_km"]
    r["avg_wind_cable_incl"] = r["avg_wind"] + cable_eur_mwh_km * r["cable_km"]
    rows.append(r)
res = pd.DataFrame(rows)
res.to_csv(OUT + "landing_point_candidates.csv", index=False)
pd.set_option("display.width", 250)
print(f"cable cost: {cab_a/1e6:.3f} M EUR/km/a, {cable_eur_mwh_km:.4f} EUR/MWh per km (rough); HVAC {AC:.1f}, HVDC {DC:.1f} EUR/MW/km/a, inverter {INV:.0f} EUR/MW/a")
cols = ["lat", "lon", "cable_km", "TWh<30", "TWh<40", "GW<40", "avg_all", "marg_all", "avg_wind", "TWh_wind"]
print("\nCheapest 9.25 TWh, all technologies (delivered at the point)"); print(res.sort_values("avg_all")[cols].head(8).round(2).to_string(index=False))
print("\nCheapest 9.25 TWh, wind only"); print(res.sort_values("avg_wind")[cols].head(8).round(2).to_string(index=False))
print("\nMost energy below 40 EUR/MWh"); print(res.sort_values("TWh<40", ascending=False)[cols].head(6).round(2).to_string(index=False))
c2 = ["lat", "lon", "cable_km", "avg_all", "avg_all_cable_incl", "avg_wind", "avg_wind_cable_incl"]
print("\nWith the cable length to Wilhelmshaven added (rough): all technologies"); print(res.sort_values("avg_all_cable_incl")[c2].head(5).round(1).to_string(index=False))
print("wind only"); print(res.sort_values("avg_wind_cable_incl")[c2].head(5).round(1).to_string(index=False))
print(f"\ncable_km range: {res.cable_km.min():.0f} to {res.cable_km.max():.0f} -> cable cost difference {cable_eur_mwh_km * (res.cable_km.max() - res.cable_km.min()):.1f} EUR/MWh;",
      f"the whole link on {CABLE_TWH} TWh: about {cable_eur_mwh_km * res.cable_km.min():.0f} EUR/MWh (rough, supply and laying of two cables only)")

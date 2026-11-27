# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""Restrict the coastal potential to the northern coast, the part of Brazil closest to Europe.

North = latitude >= LAT_MIN (about Natal, Rio Grande do Norte, northwards to the border with
French Guiana). The cut is a latitude, not a state border, so it is easy to move.
Reads potential_per_cell.csv (potential.py), writes potential_north.csv and prints a summary.
"""
import pandas as pd

LAT_MIN = -7.0
df = pd.read_csv("results/brazil-potential/potential_per_cell.csv")
n = df[df.lat >= LAT_MIN].copy()
n.to_csv("results/brazil-potential/potential_north.csv", index=False)

order = ["onwind", "solar", "solar-hsat", "offwind", "offwind-float"]
g = n.groupby("tech")
s = pd.DataFrame({
    "cells": g.size(),
    "with_area": g.p_nom_max_mw.apply(lambda x: int((x > 0).sum())),
    "gw": g.p_nom_max_mw.sum() / 1e3,
    "twh": g.energy_gwh.sum() / 1e3,
}).loc[order]
s["mwh_per_mw"] = s.twh * 1e6 / (s.gw * 1e3)
a = df.groupby("tech").p_nom_max_mw.sum().loc[order] / 1e3
s["share_of_all_coast_gw_%"] = 100 * s.gw / a
pd.set_option("display.width", 200)
print(f"lat >= {LAT_MIN}: lat {n.lat.min():.1f} to {n.lat.max():.1f}, lon {n.lon.min():.1f} to {n.lon.max():.1f}")
print(s.round(1).to_string())
for t in order:
    print(t); print(n[(n.tech == t) & (n.p_nom_max_mw > 0)].nlargest(4, "mwh_per_mw")
                    [["lat", "lon", "coast_km", "cf", "mwh_per_mw", "p_nom_max_mw", "energy_gwh"]].round(2).to_string(index=False))

# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""
Brazilian generation costs per technology and planning year (role 2 deliverable, E2).

Derived like the European ones: the model's cost table of each planning year
(data/costs/archive/v0.15.0, so the same learning curve), scaled by a Brazil
factor on investment. Price basis and units are those of the cost table
(currency_year column, mostly 2025). FOM, VOM and lifetime as in the table.

Factor on investment (Brazil relative to the table):
- central: IRENA, Renewable Power Generation Costs in 2023, Brazil vs global
  weighted average total installed cost, same source and year (USD/kW):
  onwind 1079 / 1154 = 0.935, utility PV 727 / 758 = 0.959
- high:    1.0, the European table without a Brazilian advantage
- low:     central minus the same distance (assumption, symmetric range)

LCOE uses the E2 WACC for Brazilian generation (10 % real) and a capacity
factor (default: best land cells of CE east from scan_regions.py).

    pixi run python workshop/brazil/brazil_costs.py --out results/brazil-validation
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.add_electricity import calculate_annuity  # noqa: E402

TABLES = Path("data/costs/archive/v0.15.0")
YEARS = [2025, 2030, 2035, 2040, 2045, 2050]
CENTRAL = {"onwind": 1079 / 1154, "solar-utility": 727 / 758}
CASES = {"low": {t: 2 * f - 1 for t, f in CENTRAL.items()}, "central": CENTRAL,
         "high": {t: 1.0 for t in CENTRAL}}


def table(year):
    d = pd.read_csv(TABLES / f"costs_{year}.csv")
    return d.set_index(["technology", "parameter"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--wacc", type=float, default=0.10)
    ap.add_argument("--cf-onwind", type=float, default=0.591)
    ap.add_argument("--cf-solar", type=float, default=0.203)
    ap.add_argument("--out", type=Path, default=Path("results/brazil-validation"))
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    cf = {"onwind": a.cf_onwind, "solar-utility": a.cf_solar}

    rows = []
    for year in YEARS:
        t = table(year)
        for tech in CENTRAL:
            inv = float(t.loc[(tech, "investment"), "value"])     # EUR/kW
            fom = float(t.loc[(tech, "FOM"), "value"])            # %/a
            vom = float(t.loc[(tech, "VOM"), "value"]) if (tech, "VOM") in t.index else 0.0
            life = float(t.loc[(tech, "lifetime"), "value"])
            cyear = t.loc[(tech, "investment"), "currency_year"]
            for case, fac in CASES.items():
                capex = inv * fac[tech]
                annual = (calculate_annuity(life, a.wacc) + fom / 100) * capex * 1e3   # EUR/MW/a
                rows.append(dict(
                    year=year, technology=tech, case=case, factor=round(fac[tech], 3),
                    investment_eur_per_kw=round(capex, 1), FOM_pct_per_a=fom, VOM_eur_per_mwh=vom,
                    lifetime_a=life, currency_year=cyear, wacc=a.wacc,
                    lcoe_eur_per_mwh=round(annual / (8760 * cf[tech]) + vom, 2),
                ))
    df = pd.DataFrame(rows)
    df.to_csv(a.out / "brazil_costs.csv", index=False)
    pd.set_option("display.width", 200)
    print(df[df.case == "central"].to_string(index=False))
    print(df.pivot_table(index=["technology", "year"], columns="case", values="lcoe_eur_per_mwh"))

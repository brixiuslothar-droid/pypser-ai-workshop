# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""Brazilian cost tables in the format of data/costs/archive/v0.15.0/costs_<year>.csv, for all planning horizons.

Derivation, kept identical to the European one so that a difference is not an artefact of the method:
  investment, FOM, VOM, lifetime: unchanged from the European table of the same year (same source, same currency year);
  discount rate: the WACC of the Brazilian generation tranche in workshop/inputs/financing_term_sheet.md instead of 7 %:
    62 % debt at 2.635 % + 312 bps, 34 % tax shield, 38 % equity at 13.85 % (country risk premium of 4.25 % included) = 7.62 %.
The model computes capital_cost = (annuity(lifetime, discount rate) + FOM) x investment from these columns
(process_cost_data.py). Technologies carry the prefix "Brazil " so they cannot overwrite a European entry.
The grid and converter items (offshore station and cable, HVAC/HVDC lines) get the same rate: they belong to the
Brazilian side up to the landing point. Not included: interest during construction, exchange rate cover, grid connection
onshore (the model has none); these are not in the European table either.
Writes costs/costs_brazil_<year>.csv (long format, raw layout) and costs/costs_brazil_summary.csv.
"""
import pandas as pd

g, base, margin, tax, eq = 0.62, 0.02635, 0.0312, 0.34, 0.1385
WACC = g * (base + margin) * (1 - tax) + (1 - g) * eq
TECH = ["onwind", "solar-utility", "solar-utility single-axis tracking", "offwind", "offwind-float",
        "offwind-ac-station", "offwind-dc-station", "offwind-float-station",
        "offwind-ac-connection-submarine", "offwind-ac-connection-underground",
        "offwind-dc-connection-submarine", "offwind-dc-connection-underground",
        "offwind-float-connection-submarine", "offwind-float-connection-underground",
        "HVAC overhead", "HVDC overhead", "HVDC inverter pair"]
NAME = {"solar-utility single-axis tracking": "Brazil solar-hsat", "solar-utility": "Brazil solar"}
ann = lambda n, r: r / (1 - (1 + r) ** -n)
summary = []
for year in [2025, 2030, 2035, 2040, 2045, 2050]:
    raw = pd.read_csv(f"data/costs/archive/v0.15.0/costs_{year}.csv")
    out = raw[raw.technology.isin(TECH)].copy()
    out = out[out.parameter.isin(["investment", "FOM", "VOM", "lifetime"])]
    out["technology"] = out.technology.map(lambda t: NAME.get(t, "Brazil " + t))
    out["source"] = "European value of the same year (" + out.source.astype(str).str.slice(0, 80) + "), unchanged"
    rate = pd.DataFrame({"technology": sorted(out.technology.unique()), "parameter": "discount rate", "value": round(WACC, 5),
                         "unit": "per unit", "source": "WACC of the Brazilian generation tranche, financing_term_sheet.md (draft 4)",
                         "further description": "62 % debt 2.635 % + 312 bps, 34 % tax, 38 % equity 13.85 % incl. 4.25 % country risk premium",
                         "currency_year": ""})
    out = pd.concat([out, rate], ignore_index=True)
    out.to_csv(f"workshop/brazil/costs/costs_brazil_{year}.csv", index=False)
    p = out.pivot(index="technology", columns="parameter", values="value")
    for t in p.index:
        inv = p.at[t, "investment"]
        unit = out[(out.technology == t) & (out.parameter == "investment")].unit.iloc[0]
        mult = 1000 if "kW" in unit else 1  # EUR/kW -> EUR/MW; per km items are already EUR/MW/km
        cap = (ann(p.at[t, "lifetime"], WACC) + p.at[t, "FOM"] / 100) * inv * mult
        cap7 = (ann(p.at[t, "lifetime"], 0.07) + p.at[t, "FOM"] / 100) * inv * mult
        summary.append(dict(year=year, technology=t, investment=inv, unit=unit, FOM_pct=p.at[t, "FOM"],
                            VOM=p.at[t, "VOM"] if "VOM" in p.columns else float("nan"), lifetime=p.at[t, "lifetime"],
                            capital_cost_wacc_eur_mw_a=cap, capital_cost_7pct_eur_mw_a=cap7, increase_pct=100 * (cap / cap7 - 1)))
s = pd.DataFrame(summary)
s.to_csv("workshop/brazil/costs/costs_brazil_summary.csv", index=False)
pd.set_option("display.width", 200)
print(f"WACC {100 * WACC:.3f} %")
print(s[s.year.isin([2030, 2050]) & s.technology.isin(["Brazil onwind", "Brazil solar", "Brazil solar-hsat", "Brazil offwind", "Brazil offwind-float"])]
      .round(1).to_string(index=False))
# consistency with the LCOE calculation of lcoe.py (annualised cost of onwind 2030)
c = pd.read_csv("resources/de10-myopic/costs_2030_processed.csv", index_col=0)
w = (ann(30, WACC) + c.at["onwind", "FOM"] / 100) * c.at["onwind", "investment"]
print("check onwind 2030 capital cost at the WACC: table %.0f, lcoe.py basis %.0f EUR/MW/a" % (
      s[(s.year == 2030) & (s.technology == "Brazil onwind")].capital_cost_wacc_eur_mw_a.iloc[0], w))

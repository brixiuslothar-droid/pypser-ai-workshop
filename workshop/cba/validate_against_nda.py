# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""
Check the model's public cable assumptions against confidential (NDA) data.

The NDA documents in ``workshop/inputs/`` may be used for validation, not as
model input. This script reads them at runtime, compares them with the public
numbers the model uses (cost table, discount rate) and prints only coarse
ratio bands, never a confidential value or an exact ratio: an exact ratio
times the public number would reveal the confidential one.

Nothing here is written to disk. Do not paste its inputs into code, config,
commits, figures or chats with outside services.

    pixi run python workshop/cba/validate_against_nda.py --horizon 2035
"""

import argparse
import re
from pathlib import Path

import pandas as pd
import yaml

BANDS = [(0.0, 0.5, "NDA < 0.5x public"), (0.5, 0.8, "NDA 0.5-0.8x public"),
         (0.8, 1.25, "NDA within 0.8-1.25x public"), (1.25, 2.0, "NDA 1.25-2x public"),
         (2.0, 3.0, "NDA 2-3x public"), (3.0, float("inf"), "NDA > 3x public")]


def band(ratio: float) -> str:
    return next(label for lo, hi, label in BANDS if lo <= ratio < hi)


def cable_cost_per_mw_km(design: dict) -> dict:
    """Investment per MW and km of route for each depth class, EUR."""
    sysd, inst = design["system"], design["installation"]
    p_mw = float(sysd["rated_power_mw"])
    out = {}
    for cls, d in design["depth_classes"].items():
        lay_days_per_km = (1.0 / d["lay_rate_km_per_day"]) * (1 + inst["weather_downtime_share"])
        joints_per_km = 1.0 / inst["field_joint_every_km"]
        per_km = (
            2 * d["supply_cost_eur_per_m"] * 1e3                       # two power cables
            + d["burial_and_protection_eur_per_m"] * 1e3
            + lay_days_per_km * d["lay_spread_eur_per_day"]
            + joints_per_km * (inst["field_joint_cost_eur"]
                               + inst["field_joint_days"] * d["lay_spread_eur_per_day"])
        )
        per_km *= 1 + inst["owners_cost_and_contingency"][cls]
        out[cls] = per_km / p_mw
    return out


def cable_wacc(term_sheet: str) -> float:
    """After-tax WACC of the cable company from the term sheet table."""
    row = next(line for line in term_sheet.splitlines() if line.startswith("| Subsea cable"))
    cells = [c.strip().rstrip("%") for c in row.strip("|").split("|")]
    gearing, base, margin_bps, equity = (float(cells[1]) / 100, float(cells[2]) / 100,
                                         float(cells[3]) / 1e4, float(cells[6]) / 100)
    tax = re.search(r"Tax rate[^:]*:\s*([\d.]+)%\s*in Germany and for the cable company", term_sheet)
    if tax is None:
        raise ValueError("cable company tax rate not found in term sheet")
    tax = float(tax.group(1)) / 100
    return gearing * (base + margin_bps) * (1 - tax) + (1 - gearing) * equity


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--inputs", type=Path, default=Path("workshop/inputs"))
    ap.add_argument("--costs", type=Path, default=Path("resources/de10-br-import"))
    ap.add_argument("--horizon", type=int, default=2035)
    ap.add_argument("--rate", type=float, default=0.10,
                    help="public WACC to compare with (decisions.md E2: cable 10%%)")
    a = ap.parse_args()

    costs = pd.read_csv(a.costs / f"costs_{a.horizon}_processed.csv", index_col=0)
    design = yaml.safe_load((a.inputs / "cable_system_design.yaml").read_text())
    terms = (a.inputs / "financing_term_sheet.md").read_text()

    pub_cable = costs.at["HVDC submarine", "investment"]          # EUR/MW/km
    pub_conv = costs.at["HVDC inverter pair", "investment"]       # EUR/MW, both ends
    pub_rate = a.rate

    print(f"Public reference: cost table {a.horizon} (DEA), WACC {a.rate:.0%} (E2)\n")
    print("Cable investment per MW and km, by depth class:")
    for cls, v in cable_cost_per_mw_km(design).items():
        print(f"  {cls:8s} {band(v / pub_cable)}")

    conv = 2 * design["converter_stations"]["cost_eur_per_station"] / design["system"]["rated_power_mw"]
    print(f"Converter pair per MW:   {band(conv / pub_conv)}")
    print(f"Cable company WACC:      {band(cable_wacc(terms) / pub_rate)}")

    life = design["system"]["design_life_years"]
    pub_life = costs.at["HVDC submarine", "lifetime"]
    print(f"Lifetime:                {'same as' if life == pub_life else 'differs from'} cost table")
    print("\nOnly bands are shown. Use them to set sensitivity ranges (brazil_import.cost_factor,"
          " discount rate), not to copy values.")

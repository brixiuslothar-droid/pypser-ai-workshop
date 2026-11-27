# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""Role 3: side-by-side German key figures of several runs.

Usage: pixi run python workshop/role3/compare_runs.py de10-nb9 de10-nb9-ref
Needs neighbours_check.py to have written results/<run>/role3/de_years.csv;
runs it for runs where the file is missing. Baseline figures come from
results/de10-myopic/role3/years.csv (baseline_check.py).
"""

import subprocess
import sys
from pathlib import Path

import pandas as pd

runs = sys.argv[1:] or ["de10-nb9", "de10-nb9-ref"]
ROWS = {
    "de_price_loadweighted": "Preis DE (€/MWh)",
    "de_hours_price_gt_300": "Stunden > 300 €/MWh",
    "de_hours_price_lt_1": "Stunden < 1 €/MWh",
    "de_net_import_TWh": "Nettoimport DE (TWh)",
    "de_max_import_GW": "Max. Import (GW)",
    "de_co2_Mt": "CO2 DE (Mt)",
    "co2_cap_shadow_EUR_t": "Schattenpreis CO2 (€/t)",
    "de_battery_GWh": "Batterie DE (GWh)",
    "de_H2_store_GWh": "H2-Speicher DE (GWh)",
    "de_cap_solar_GW": "PV fest DE (GW)",
    "de_cap_onwind_GW": "Wind an Land DE (GW)",
    "de_cap_OCGT_GW": "OCGT DE (GW)",
    "load_shed_all_TWh": "Lastabwurf alle (TWh)",
}
BASE = {
    "price_loadweighted": "de_price_loadweighted",
    "hours_price_gt_300": "de_hours_price_gt_300",
    "hours_price_lt_1": "de_hours_price_lt_1",
    "co2_Mt": "de_co2_Mt",
    "co2_cap_shadow_EUR_t": "co2_cap_shadow_EUR_t",
    "store_battery_GWh": "de_battery_GWh",
    "store_H2_GWh": "de_H2_store_GWh",
    "cap_solar_GW": "de_cap_solar_GW",
    "cap_onwind_GW": "de_cap_onwind_GW",
    "cap_OCGT_GW": "de_cap_OCGT_GW",
}
frames = {}
b = Path("results/de10-myopic/role3/years.csv")
if b.exists():
    frames["baseline"] = pd.read_csv(b, index_col=0).rename(index=BASE)
for r in runs:
    f = Path(f"results/{r}/role3/de_years.csv")
    if not f.exists():
        subprocess.run([sys.executable, "workshop/role3/neighbours_check.py", r], check=True,
                       stdout=subprocess.DEVNULL)
    frames[r] = pd.read_csv(f, index_col=0)
for key, label in ROWS.items():
    t = pd.DataFrame({k: v.loc[key].astype(float) for k, v in frames.items() if key in v.index}).T
    print(f"\n{label}")
    print(t.round(1).to_string())

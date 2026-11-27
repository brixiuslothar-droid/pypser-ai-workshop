# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""Role 3: compare German key figures of baseline, neighbours and reference.

Usage: pixi run python workshop/role3/plot_compare.py
Reads results/<run>/role3/*.csv (written by baseline_check.py and
neighbours_check.py) and writes workshop/role3/figures/compare_*.{pdf,png}.
Results are aggregated (Germany, per year); no unit-level data.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "workshop/plotstyle").is_dir())
sys.path.insert(0, str(ROOT / "workshop/plotstyle"))
import studystyle as st  # noqa: E402

OUT = ROOT / "workshop/role3/figures"
OUT.mkdir(parents=True, exist_ok=True)

RUNS = {  # run -> (label, colour)
    "de10-myopic": ("Baseline (island)", st.NEUTRAL),
    "de10-nb9": ("Neighbours, free trade", "#56B4E9"),
    "de10-nb9-ref": ("Neighbours, NTC limits", "#0072B2"),
}
BASE_MAP = {
    "price_loadweighted": "de_price_loadweighted",
    "hours_price_gt_300": "de_hours_price_gt_300",
    "store_battery_GWh": "de_battery_GWh",
    "co2_cap_shadow_EUR_t": "co2_cap_shadow_EUR_t",
}


def load(run):
    if run == "de10-myopic":
        f = ROOT / "results/de10-myopic/role3/years.csv"
        df = pd.read_csv(f, index_col=0).rename(index=BASE_MAP)
        df.loc["de_net_import_TWh"] = 0.0
    else:
        f = ROOT / f"results/{run}/role3/de_years.csv"
        df = pd.read_csv(f, index_col=0)
    df.columns = df.columns.astype(int)
    return df.apply(pd.to_numeric, errors="coerce")


st.use()
data = {r: load(r) for r in RUNS if (ROOT / "results" / r / "role3").exists()}

panels = [
    ("de_price_loadweighted", "Average electricity price in Germany, EUR/MWh"),
    ("de_net_import_TWh", "Net imports into Germany, TWh"),
    ("de_hours_price_gt_300", "Hours with prices above 300 EUR/MWh in Germany"),
    ("de_battery_GWh", "Battery storage in Germany, GWh"),
]
for key, title in panels:
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    for run, df in data.items():
        if key not in df.index:
            continue
        label, colour = RUNS[run]
        s = df.loc[key].dropna()
        st.line(ax, s.index, s.values, colour, label=label)
    ax.set_xticks([2025, 2030, 2035, 2040, 2045, 2050])
    ax.set_ylim(bottom=0)
    ax.set_title(title, loc="left")
    name = key.replace("de_", "")
    fig.savefig(OUT / f"compare_{name}.pdf")
    fig.savefig(OUT / f"compare_{name}.png", dpi=300)
    plt.close(fig)
    print("wrote", OUT / f"compare_{name}.png")

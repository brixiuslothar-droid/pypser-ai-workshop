# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""
Cost-benefit analysis of the Brazil import cable: a cable run against its reference.

Both runs must differ in ``brazil_import`` only. Per planning horizon:

- annual system cost (capex + opex from ``n.statistics``) of both runs,
  split into German assets, the cable and the import payments to Brazil;
- net benefit = reference cost - cable-run cost (positive: the cable pays off
  for the system as a whole);
- delivered imports, cable utilisation, the German load-weighted price and the
  cable's merchant revenue (German price x delivered energy - import payments).

Each horizon stands for the five years from its own year. The NPV discounts
them to ``--base-year``, with and without ``--exclude`` (default 2050, whose
zero CO2 cap inflates every clean MWh; see workshop/README.md).

    pixi run python workshop/cba/cba_brazil_import.py \\
        --reference results/de10-myopic --case results/de10-br-import \\
        --out results/de10-br-import/cba
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pypsa

ROOT = next(p for p in [Path(__file__).resolve(), *Path(__file__).resolve().parents]
            if (p / "workshop/plotstyle").is_dir())
sys.path.insert(0, str(ROOT / "workshop/plotstyle"))
import studystyle as st  # noqa: E402

BRAZIL = {"Brazil import", "Brazil HVDC"}
LINK, GEN = "BR0 Brazil HVDC", "BR0 Brazil import"


def annual_cost_by_carrier(n: pypsa.Network) -> pd.Series:
    """EUR/a by carrier, all components."""
    cost = pd.concat([n.statistics.capex(groupby="carrier", nice_names=False),
                      n.statistics.opex(groupby="carrier", nice_names=False)])
    return cost.groupby(level="carrier").sum()


def german_price(n: pypsa.Network) -> float:
    """Load-weighted average electricity price in Germany, EUR/MWh."""
    loads = n.loads[n.loads.bus.map(n.buses.country) == "DE"]
    p = n.loads_t.p[loads.index]
    lam = n.buses_t.marginal_price[loads.bus].set_axis(loads.index, axis=1)
    w = n.snapshot_weightings.generators
    return float((p * lam).mul(w, axis=0).sum().sum() / p.mul(w, axis=0).sum().sum())


def cable_flows(n: pypsa.Network) -> dict:
    if LINK not in n.links.index:
        return dict(imports_twh=0.0, utilisation=np.nan, merchant_revenue=0.0,
                    import_payment=0.0, import_price=np.nan, p_nom=0.0)
    w = n.snapshot_weightings.generators
    p0 = n.links_t.p0[LINK]
    delivered = -n.links_t.p1[LINK]
    lam_de = n.buses_t.marginal_price[n.links.at[LINK, "bus1"]]
    payment = (n.generators_t.p[GEN] * n.get_switchable_as_dense("Generator", "marginal_cost")[GEN]).mul(w).sum()
    p_nom = n.links.at[LINK, "p_nom_opt"]
    return dict(
        imports_twh=float(delivered.mul(w).sum() / 1e6),
        utilisation=float(p0.mul(w).sum() / (p_nom * w.sum())) if p_nom else np.nan,
        merchant_revenue=float((delivered * lam_de).mul(w).sum()),
        import_payment=float(payment),
        import_price=float(payment / p0.mul(w).sum()) if p0.sum() else np.nan,
        p_nom=float(p_nom),
    )


def horizon_table(ref_dir: Path, case_dir: Path):
    rows, deltas = [], {}
    files = sorted((case_dir / "networks").glob("solved_*.nc"))
    if not files:
        raise FileNotFoundError(f"no solved networks in {case_dir / 'networks'}")
    for f in files:
        year = int(f.stem.split("_")[1])
        ref_f = ref_dir / "networks" / f.name
        if not ref_f.exists():
            print(f"skip {year}: no reference network", file=sys.stderr)
            continue
        n_ref, n = pypsa.Network(ref_f), pypsa.Network(f)
        c_ref, c = annual_cost_by_carrier(n_ref), annual_cost_by_carrier(n)
        cable = c.reindex(["Brazil HVDC"]).fillna(0).sum()
        imports = c.reindex(["Brazil import"]).fillna(0).sum()
        de = c.drop(BRAZIL, errors="ignore")
        delta = de.sub(c_ref, fill_value=0.0)  # + = German assets cost more with the cable
        deltas[year] = delta
        fl = cable_flows(n)
        rows.append(dict(
            horizon=year,
            reference_cost_bn=c_ref.sum() / 1e9,
            case_cost_bn=c.sum() / 1e9,
            german_saving_bn=-delta.sum() / 1e9,
            cable_cost_bn=cable / 1e9,
            import_cost_bn=imports / 1e9,
            net_benefit_bn=(c_ref.sum() - c.sum()) / 1e9,
            imports_twh=fl["imports_twh"],
            cable_utilisation=fl["utilisation"],
            cable_gw=fl["p_nom"] / 1e3,
            import_price_eur_mwh=fl["import_price"],
            price_de_reference=german_price(n_ref),
            price_de_case=german_price(n),
            merchant_rent_bn=(fl["merchant_revenue"] - fl["import_payment"]) / 1e9,
        ))
    tab = pd.DataFrame(rows).set_index("horizon")
    return tab, pd.DataFrame(deltas).T.fillna(0.0)


def npv(series: pd.Series, rate: float, base_year: int, step: int = 5) -> float:
    total = 0.0
    for year, value in series.items():
        t = np.arange(year, year + step) - base_year
        total += value * ((1 + rate) ** -t).sum()
    return float(total)


def plot(tab: pd.DataFrame, deltas: pd.DataFrame, out: Path) -> None:
    st.use()
    # change in annual cost vs the reference, billion EUR/a: German assets by group,
    # the cable and the import payments; negative = saving
    parts = st.by_group(deltas / 1e9, axis=1)
    parts["Brazil cable"] = tab["cable_cost_bn"].reindex(parts.index).fillna(0.0)
    parts = parts.loc[:, parts.abs().max() > 0.01]
    x = np.arange(len(parts))
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    pos = np.zeros(len(x)); neg = np.zeros(len(x))
    for col in parts.columns:
        v = parts[col].values
        bottom = np.where(v >= 0, pos, neg)
        ax.bar(x, v, 0.62, bottom=bottom, color=st.color(col), edgecolor="white",
               linewidth=0.6, zorder=2)
        pos += np.clip(v, 0, None); neg += np.clip(v, None, 0)
    imp = tab["import_cost_bn"].reindex(parts.index).fillna(0.0).values
    ax.bar(x, imp, 0.62, bottom=pos, color=st.color("Brazil cable"), alpha=st.TINT,
           edgecolor="white", linewidth=0.6, zorder=2)
    net = -tab["net_benefit_bn"].reindex(parts.index).values
    ax.scatter(x, net, s=18, color="#222222", zorder=3)
    for xi, v in zip(x, net):
        ax.annotate(f"{v:+,.1f}", (xi, v), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=7.5, color="#222222")
    ax.axhline(0, color="#222222", linewidth=0.8)
    ax.set_xticks(x, parts.index)
    ax.set_title("Change in annual system cost with the Brazil cable, billion EUR", loc="left")
    items = [(st.color(c), c) for c in parts.columns]
    items.append((st.color("Brazil cable"), "Brazil imports", st.TINT))
    st.legend_squares(ax, items, loc="upper left", bbox_to_anchor=(1.0, 1.0), fontsize=7.5)
    ax.annotate("dot: net change (+ = cable costs the system more)", (0, -0.16),
                xycoords="axes fraction", fontsize=7, color="#aaaaaa")
    for ext in ("pdf", "png"):
        fig.savefig(out / f"cba_cost_change.{ext}", dpi=300)
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--reference", type=Path, default=Path("results/de10-myopic"))
    ap.add_argument("--case", type=Path, default=Path("results/de10-br-import"))
    ap.add_argument("--out", type=Path)
    ap.add_argument("--rate", type=float, default=0.07, help="discount rate (cost tables use 7%%)")
    ap.add_argument("--base-year", type=int, default=2025)
    ap.add_argument("--exclude", type=int, nargs="*", default=[2050])
    a = ap.parse_args()
    out = a.out or a.case / "cba"
    out.mkdir(parents=True, exist_ok=True)

    tab, deltas = horizon_table(a.reference, a.case)
    tab.round(3).to_csv(out / "cba_by_horizon.csv")
    (deltas / 1e9).round(4).to_csv(out / "cost_change_by_carrier_bn.csv")
    plot(tab, deltas, out)

    kept = tab.drop(a.exclude, errors="ignore")
    summary = pd.Series({
        f"NPV net benefit, all horizons, bn EUR ({a.rate:.0%}, {a.base_year})":
            npv(tab.net_benefit_bn, a.rate, a.base_year),
        f"NPV net benefit, without {a.exclude}, bn EUR":
            npv(kept.net_benefit_bn, a.rate, a.base_year),
    })
    summary.to_csv(out / "cba_summary.csv", header=["value"])
    pd.set_option("display.width", 200)
    print(tab.round(2).T)
    print(summary.round(2))
    print(f"written to {out}")

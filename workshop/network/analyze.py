# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""
Role 6 (grid analysis): one command-line script.

Rebuild a solved 10-node market result on the full German grid, pick stress
weeks, compute line loading and the redispatch to clear the overloads, and - if
a reference run is given - compare the two (e.g. with and without the cable).

Usage
-----
    pixi run python workshop/network/analyze.py RUN HORIZON [REFERENCE]

    RUN        solved run name, e.g. de10-br-import
               (reads results/RUN/networks/solved_HORIZON.nc)
    HORIZON    planning year, e.g. 2040
    REFERENCE  optional second run to compare against, e.g. de10-myopic

Examples
--------
    # one run
    pixi run python workshop/network/analyze.py de10-br-ext 2040

    # with / without the cable
    pixi run python workshop/network/analyze.py de10-br-import 2050 de10-myopic

Outputs go to ``results/network/<run>_<horizon>/`` (CSV, PNG, PDF); with a
reference also ``results/network/compare_<run>_vs_<reference>_<horizon>.png``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plotstyle"))
import studystyle as st  # noqa: E402

import workshop.network.full_grid as fg  # noqa: E402

OUT = Path("results/network")
WEEK_LABEL = {
    "max_wind": "max wind",
    "max_import": "max Brazil import",
    "max_load": "max load",
}
logger = logging.getLogger("network.analyze")


def loading_summary(loading: pd.DataFrame, weeks: dict[str, pd.DatetimeIndex]) -> pd.DataFrame:
    rows = []
    for label, snaps in weeks.items():
        ld = loading.reindex(snaps)
        rows.append(
            {
                "week": label,
                "max_loading": float(ld.max().max()),
                "lines_over_1": int(ld.max().gt(1).sum()),
                "lines_over_1.5": int(ld.max().gt(1.5).sum()),
                "lines_over_2": int(ld.max().gt(2).sum()),
                "line_snap_share_over_1": float(ld.gt(1).to_numpy().mean()),
            }
        )
    return pd.DataFrame(rows).set_index("week")


def analyze(run: str, horizon: int) -> dict:
    """Reconstruct, run the DC load flow and the redispatch, write results."""
    outdir = OUT / f"{run}_{horizon}"
    outdir.mkdir(parents=True, exist_ok=True)

    b2c = fg.read_cluster_map(run)
    grid = fg.base_grid(run)
    pop = fg.population_weights(grid, run)
    area = fg.area_weights(grid, run, b2c)
    plant = fg.plant_weights(grid, run, b2c)
    inj = fg.reconstruct_injections(run, horizon, b2c, pop, area, plant)
    n = fg.build_network(run, inj)

    weeks = fg.select_weeks(inj)
    snaps = pd.DatetimeIndex(sorted(set().union(*weeks.values())))
    logger.info("%s %s: weeks %s, %d snapshots", run, horizon, list(weeks), len(snaps))

    loading = fg.line_loading(n, snaps)
    loading.to_csv(outdir / "line_loading.csv")
    summary = loading_summary(loading, weeks)
    summary.to_csv(outdir / "loading_summary.csv")

    redispatch = fg.redispatch(n, inj, snaps)
    redispatch.to_csv(outdir / "redispatch.csv")

    loading.abs().max(axis=0).sort_values(ascending=False).rename("max_loading").to_csv(
        outdir / "line_worst.csv"
    )
    try:
        import workshop.network.plot_map as pm

        pm.plot_map(run, horizon, 5)
    except Exception as exc:  # map is a bonus, never fail the analysis
        logger.warning("map skipped: %s", exc)

    rd_week = pd.DataFrame(
        {
            label: {
                "up": redispatch.reindex(w)["up"].sum() * 2 / 1e3,
                "down": redispatch.reindex(w)["down"].sum() * 2 / 1e3,
            }
            for label, w in weeks.items()
        }
    ).T
    rd_week.to_csv(outdir / "redispatch_weeks.csv")

    _figure_share(summary, run, horizon, outdir)
    _figure_redispatch(rd_week, run, horizon, outdir)

    return {
        "run": run,
        "horizon": horizon,
        "summary": summary,
        "rd_week": rd_week,
        "import_twh": float(inj["import"].sum() * 2 / 1e6),
        "weeks": weeks,
    }


def compare(res: dict, ref: dict) -> None:
    """Figure and table with / without the cable, over the common weeks."""
    run, refrun, horizon = res["run"], ref["run"], res["horizon"]
    outdir = OUT / f"{run}_{horizon}"
    weeks = [w for w in WEEK_LABEL if w in res["summary"].index and w in ref["summary"].index]
    color = st.color("Brazil cable")

    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.4))
    x = np.arange(len(weeks))
    w = 0.38
    for j, (label, d, c) in enumerate(
        [
            (refrun, ref["summary"]["line_snap_share_over_1"].reindex(weeks) * 100, st.NEUTRAL),
            (run, res["summary"]["line_snap_share_over_1"].reindex(weeks) * 100, color),
        ]
    ):
        axes[0].bar(x + (j - 0.5) * w, d, w, color=c, label=label)
    for j, (label, d, c) in enumerate(
        [
            (refrun, ref["rd_week"].reindex(weeks)["down"], st.NEUTRAL),
            (run, res["rd_week"].reindex(weeks)["down"], color),
        ]
    ):
        axes[1].bar(x + (j - 0.5) * w, d, w, color=c, label=label)

    for ax, title, unit in [
        (axes[0], "Overloaded line-hours", "% of line-hours above limit"),
        (axes[1], "Redispatch", "GWh per week"),
    ]:
        ax.set_xticks(x, [WEEK_LABEL[wk] for wk in weeks])
        ax.set_title(f"{title}, {horizon}\n{unit}", loc="left")
        ax.set_ylim(bottom=0)
    st.legend_squares(axes[1], [(st.NEUTRAL, refrun), (color, run)])

    path = OUT / f"compare_{run}_vs_{refrun}_{horizon}"
    fig.savefig(path.with_suffix(".png"), dpi=300)
    fig.savefig(path.with_suffix(".pdf"))
    logger.info("wrote %s.png", path)

    table = pd.concat(
        {
            f"{refrun} (ref)": ref["summary"]["line_snap_share_over_1"].reindex(weeks) * 100,
            f"{run} (cable)": res["summary"]["line_snap_share_over_1"].reindex(weeks) * 100,
        },
        axis=1,
    )
    table.index = [WEEK_LABEL[wk] for wk in weeks]
    table.to_csv(OUT / f"compare_{run}_vs_{refrun}_{horizon}.csv")
    print(f"\nOverloaded line-hours (%), {refrun} vs {run}:")
    print(table.round(2).to_string())


def _figure_share(summary: pd.DataFrame, run: str, horizon: int, outdir: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    x = np.arange(len(summary))
    st.bars(ax, x, summary["line_snap_share_over_1"] * 100, color=st.NEUTRAL)
    ax.set_xticks(x, [WEEK_LABEL.get(i, i) for i in summary.index])
    ax.set_ylim(bottom=0)
    ax.set_title(
        f"Overloaded line-hours in the stress weeks\n{run} {horizon}, % of line-hours above limit",
        loc="left",
    )
    fig.savefig(outdir / "loading_share.png", dpi=300)
    fig.savefig(outdir / "loading_share.pdf")


def _figure_redispatch(rd_week: pd.DataFrame, run: str, horizon: int, outdir: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    x = np.arange(len(rd_week))
    w = 0.38
    ax.bar(x - w / 2, rd_week["down"], w, color=st.NEUTRAL, label="down")
    ax.bar(x + w / 2, rd_week["up"], w, color=st.color("Brazil cable"), label="up")
    ax.set_xticks(x, [WEEK_LABEL.get(i, i) for i in rd_week.index])
    ax.set_ylim(bottom=0)
    ax.set_title(
        f"Redispatch to clear the overloads\n{run} {horizon}, GWh per week", loc="left"
    )
    st.legend_squares(ax, [(st.NEUTRAL, "down"), (st.color("Brazil cable"), "up")])
    fig.savefig(outdir / "redispatch_weeks.png", dpi=300)
    fig.savefig(outdir / "redispatch_weeks.pdf")


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="Role 6 grid analysis: full-grid loading and redispatch of a solved run.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("run", help="solved run name, e.g. de10-br-import")
    p.add_argument("horizon", type=int, help="planning year, e.g. 2050")
    p.add_argument(
        "reference",
        nargs="?",
        default=None,
        help="optional second run to compare against, e.g. de10-myopic",
    )
    return p.parse_args(argv)


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    st.use()
    args = parse_args(argv if argv is not None else sys.argv[1:])

    res = analyze(args.run, args.horizon)
    print(f"\n{args.run} {args.horizon} (Brazil import {res['import_twh']:.2f} TWh):")
    print(res["summary"].round(3).to_string())
    print("\nRedispatch (GWh/week):")
    print(res["rd_week"].round(1).to_string())

    if args.reference:
        ref = analyze(args.reference, args.horizon)
        print(f"\n{args.reference} {args.horizon} (Brazil import {ref['import_twh']:.2f} TWh):")
        print(ref["summary"].round(3).to_string())
        compare(res, ref)


if __name__ == "__main__":
    main()

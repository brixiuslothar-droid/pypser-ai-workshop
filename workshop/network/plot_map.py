# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""
Role 6 (grid analysis): PyPSA map of the most overloaded corridors.

Reads the worst line loading written by ``analyze.py`` and draws the grid on a
map with the top-N overloaded lines highlighted.

    pixi run python workshop/network/plot_map.py RUN HORIZON [N]

Default N = 5. Writes ``results/network/<run>_<horizon>/map_top{N}.png/pdf``.
"""

from __future__ import annotations

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


def plot_map(run: str, horizon: int, top_n: int = 5) -> Path:
    worst = pd.read_csv(OUT / f"{run}_{horizon}" / "line_worst.csv", index_col=0)[
        "max_loading"
    ]
    grid = fg.base_grid(run)
    xy = grid.buses[["x", "y"]]
    lines = grid.lines

    st.use()
    fig, ax = plt.subplots(figsize=(5.6, 6.2))

    # all lines: thin, grey when within limits, faint orange when overloaded
    for name, row in lines.iterrows():
        p0, p1 = xy.loc[row.bus0], xy.loc[row.bus1]
        over = worst.get(name, 0.0) > 1.0
        ax.plot(
            [p0.x, p1.x],
            [p0.y, p1.y],
            color="#e8a26a" if over else "#dcdcdc",
            lw=1.4 if over else 0.4,
            zorder=1 if over else 0,
            solid_capstyle="round",
        )

    # buses
    ax.scatter(xy.x, xy.y, s=3, color="#9e9e9e", zorder=2)

    # top-N corridors
    top = worst.sort_values(ascending=False).head(top_n)
    color = st.color("Brazil cable")
    labels = []
    for i, (name, load) in enumerate(top.items(), start=1):
        row = lines.loc[name]
        p0, p1 = xy.loc[row.bus0], xy.loc[row.bus1]
        ax.plot(
            [p0.x, p1.x],
            [p0.y, p1.y],
            color=color,
            lw=3.2,
            zorder=3,
            solid_capstyle="round",
        )
        mx, my = (p0.x + p1.x) / 2, (p0.y + p1.y) / 2
        ax.annotate(
            f"{i}",
            (mx, my),
            color="white",
            fontsize=8,
            fontweight="bold",
            ha="center",
            va="center",
            zorder=4,
            bbox=dict(boxstyle="circle,pad=0.18", fc=color, ec="none"),
        )
        labels.append(
            f"{i}. {load:.1f}x  {row.length:.0f} km  "
            f"({p0.x:.1f},{p0.y:.1f})-({p1.x:.1f},{p1.y:.1f})"
        )

    st.map_axes(ax)
    ax.set_title(
        f"Top {top_n} überlastete Korridore, {run} {horizon}\n"
        "maximale Leitungsauslastung in den Stresswochen",
        loc="left",
    )
    fig.text(
        0.01,
        0.005,
        "\n".join(labels),
        fontsize=7,
        color="#666666",
        va="bottom",
        family="monospace",
    )
    path = OUT / f"{run}_{horizon}" / f"map_top{top_n}"
    fig.savefig(path.with_suffix(".png"), dpi=300, bbox_inches="tight")
    fig.savefig(path.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    return path.with_suffix(".png")


def main():
    run = sys.argv[1] if len(sys.argv) > 1 else "de10-br-import"
    horizon = int(sys.argv[2]) if len(sys.argv) > 2 else 2040
    top_n = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    print("wrote", plot_map(run, horizon, top_n))


if __name__ == "__main__":
    main()

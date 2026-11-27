<!--
SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>

SPDX-License-Identifier: CC-BY-4.0
-->

# Role 6: grid analysis (full German grid, loading and redispatch)

The market model runs on 10 nodes, so its transmission limits are aggregated
per cluster and internal congestion inside a cluster is invisible. This role
rebuilds a solved market result on the **full German transmission grid** and
answers three questions:

1. How loaded is the internal grid, with and without the Brazil cable?
2. Which lines overload in the market dispatch?
3. How much redispatch would clear those overloads?

The market result is treated as a **copper plate** (the model's nodal prices and
dispatch), and the generation is spread onto the real grid by technology; the DC
power flow then shows where the physical grid cannot carry it.

## Usage

One command-line script, two or three arguments:

```bash
# one run: writes results/network/<run>_<horizon>/ (CSV, PNG, PDF)
pixi run python workshop/network/analyze.py de10-br-ext 2040

# with / without the cable: additionally a comparison figure
pixi run python workshop/network/analyze.py de10-br-import 2040 de10-myopic
```

| Argument | Meaning |
|---|---|
| `RUN` | solved run name, reads `results/RUN/networks/solved_HORIZON.nc` |
| `HORIZON` | planning year, e.g. `2040` |
| `REFERENCE` (optional) | second run to compare against, e.g. `de10-myopic` |

| File | Role |
|---|---|
| `analyze.py` | the command-line script: reconstruction, load flow, redispatch, figures |
| `full_grid.py` | the library: cluster map, spatial weights, reconstruction, DC flow, PTDF redispatch |

Outputs go to `results/network/` (git-ignored, like the rest of `results/`):
`line_loading.csv`, `loading_summary.csv`, `redispatch.csv`,
`redispatch_weeks.csv`, `line_worst.csv`, `loading_share.{png,pdf}`,
`redispatch_weeks.{png,pdf}` and, with a reference,
`compare_<run>_vs_<reference>_<horizon>.{png,pdf,csv}`.

## Method

**Grid.** The raw `resources/<run>/networks/base.nc` (780 AC buses) is
fragmented into 28 islands (an OSM extraction artefact) and cannot carry a load
flow. The connected **simplified** network is used instead: **470 AC buses,
831 AC lines**, today's capacities (`s_nom * s_max_pu`).

**Reconstructing the market dispatch on the full grid**, per technology:

* variable renewables (on/offshore wind, solar, solar-hsat) - distributed within
  each cluster by the available land/sea cells of the availability matrices
  (`availability_matrix_<carrier>.nc`), a proxy for the spatial `p_max_pu`
  (the profiles themselves exist only at cluster resolution);
* conventional plants, run-of-river, hydro and PHS - by the location and
  capacity of the existing plants (`powerplants.csv`);
* demand - by population (`pop_layout_total.nc`);
* store/battery/H2 links - their net AC-side injection, by population;
* the Brazil cable - a fixed injection at the German landing bus.

Every cluster total is preserved and every snapshot is balanced by a small
population-proportional correction, so the DC flow is well posed.

**DC power flow** via PyPSA's `n.lpf` (lossless, no N-1). Line loading is
`|p0| / (s_nom * s_max_pu)`.

**Stress weeks.** Three weeks (Monday-Sunday) with the highest wind feed-in,
highest Brazil import and highest load; 2-hour snapshots.

**Redispatch.** Per snapshot, the minimum total nodal adjustment (up and down,
bounded by local market generation) that removes all overloads, formulated on
the DC power-transfer distribution factors (PTDF, `full_grid.ptdf`) and solved
with HiGHS (`scipy.optimize.linprog`). A costly slack per line keeps the program
feasible and reports overload that cannot be relieved (always zero here).

## Inputs (all public, E7 untouched)

`solved_<horizon>.nc` and `resources/<run>/networks/{base,simplified}.nc`,
`busmap_*_network.csv`, `availability_matrix_*.nc`, `pop_layout_total.nc`,
`powerplants.csv`. Nothing from `workshop/inputs/` is read (NDA, E7).

## Results at a glance (horizon 2040)

The newest solved network, `de10-br-ext` 2040, optimises the cable to **~0 GW**
(the model does not build it on the island baseline); for "with the cable" see
`de10-br-import` (fixed 2 GW, 7.6 TWh in 2040).

| Week | overloaded line-hours, no cable | with 2 GW cable |
|---|---|---|
| max wind | 9.4 % | 9.3 % |
| max load | 8.3 % | 8.4 % |
| max Brazil import | - | 3.0 % |

30-41 lines are over 2x the limit in the stress weeks; the congestion sits on
the **north-south corridor**. The redispatch to clear it is 2.5-2.8 TWh per week
without and 1.5-2.8 TWh with the cable. A 2 GW cable changes the internal
loading by **less than 1 %**: it feeds in where the wind already is.

## Caveats

* The spatial allocation is a **reconstruction**; the absolute overload and
  redispatch magnitudes are order-of-magnitude, not a forecast. The
  with/without-cable **comparison** is the robust part.
* Today's line capacities (no grid expansion); the market used the aggregated
  10-node grid.
* DC, lossless, no N-1; redispatch is a theoretical minimum.
* Horizon 2040 (the newest solved network); 2050 is cap-driven (E3).

## Where this sits in the workshop

This is a new, exploratory role, not in `workshop/README.md` (roles 1-5). It
changes no model code and no config; it reads solved networks only. It is not
part of the results pipeline (`workshop/analysis/evaluate.py`, role 4); see
`workshop/network/HANDOFF.md` for how the main analysis and the presentation can
pick it up. Memory: one run's reconstruction and load flow stay well under the
workspace limit; never run it during a solve (O7).

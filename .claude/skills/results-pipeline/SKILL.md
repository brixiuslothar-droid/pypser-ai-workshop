---
name: results-pipeline
description: Role 4 (economics) - evaluates all solved runs of the study (system cost, prices, emissions, trade, the Brazil cable, winners and losers) and writes the structured report workshop/results/RESULTS.md with tables, CSVs and figures. Load it when the person wants to evaluate runs, compare scenarios, update the results or make figures for the final presentation.
---

<!--
SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>

SPDX-License-Identifier: CC-BY-4.0
-->

# Results pipeline (role 4)

One pipeline over all runs, as fixed in E6 of `workshop/decisions.md`.

| File | Role |
|---|---|
| `workshop/analysis/runs.yaml` | which runs exist (label, run name, configs, parent) and which pairs are compared (E4) |
| `workshop/analysis/evaluate.py` | reads `results/<run>/networks/solved_<year>.nc`, computes the metrics, writes everything below |
| `workshop/results/RESULTS.md` | **the report**, generated: status, findings, checks, comparisons, per-run tables and figures, definitions |
| `workshop/results/notes.md` | findings and interpretation, written by hand, included in section 2 of the report |
| `workshop/results/metrics.csv` | long table: run, horizon, section, metric, unit, value |
| `workshop/results/comparisons.csv` | differences run − reference |
| `workshop/results/status.csv` | solver status, solve time, peak memory per run and year |
| `workshop/results/figures/` | PNG (300 dpi) and PDF, workshop plot style |

## Use

```bash
pixi run python workshop/analysis/evaluate.py                 # all runs that have results
pixi run python workshop/analysis/evaluate.py --runs BASE REF CABLE
```

Six horizons of one run take about a minute. Runs without results are listed
as "planned"; comparisons appear once both runs exist.

**Never evaluate while a solve runs.** The workspace's memory limit is shared:
a solve needs up to ~7 GB, loading networks another 1–2 GB. On 2026-11-27 an
evaluation during a solve got the solve killed (out of memory). `evaluate.py`
therefore refuses to start while `solve_network.py` runs; `--force` overrides
it at your own risk. Check first: `pgrep -af solve_network`.

**Grid analysis (role 6) on request only:** `--grid LABEL:YEAR ...`, e.g.
`--grid REF:2040 CABLE:2040`. About 4 minutes per run and year, and it pushed the
workspace to its 10 GB limit in the test: never next to a solve, never for
all years. Results go to `workshop/results/grid.csv` and stay there until
recomputed; comparisons show grid metrics only where both runs have them.
`--runs` evaluates only some runs and keeps the others from the last full run.

**A run is evaluated when it is complete**, i.e. all horizons solved. A run
whose last solve failed is listed as "teilweise"; do not report its numbers.

## Steps

1. A new or renamed run: add or update it in `runs.yaml` first. The run name
   must match the one role 3 uses in `config/scenarios.yaml`; set
   `scenario:` (and `scenario_file:` if not `config/scenarios.yaml`) so the
   pipeline reads the run's CO2 price from its config.
2. Run `evaluate.py`.
3. Read section 3 "Auffälligkeiten" of `RESULTS.md`. Every flagged point is
   either explained in `notes.md` or reported to role 3.
4. Write or update the findings in `workshop/results/notes.md`, then run
   `evaluate.py` again so they appear in the report. Never edit `RESULTS.md`
   by hand.
5. For a figure that is not in the pipeline, add a function to `evaluate.py`
   rather than a one-off script, so it reruns with every result.

## Rules

- **Plot style:** read `.claude/skills/plot-style/SKILL.md` before changing a
  figure. The cable is the only vermilion element; reference runs are grey.
- **One change per comparison** (E4): only add comparison pairs whose runs
  differ in one thing.
- **2050 and the cap:** the pipeline flags any year whose cap shadow price is
  above 1,000 EUR/t. Do not report a cable value that rests on such a year
  without saying so.
- **Confidential data (E7):** the pipeline reads no file from
  `workshop/inputs/`. Never add one, and never put a value from there into
  `notes.md`, a figure or a table.
- **Model code** is not changed here. If a metric needs something the network
  does not hold, ask role 3.

## Metrics and definitions

Defined in section 6 of `RESULTS.md` (written by `evaluate.py`). Points to know:

- System cost = all annualised capital cost of active assets (existing ones
  included) + operating cost. The solver objective is smaller in myopic runs;
  in differences between runs the existing assets cancel.
- Actors: revenue − capital cost − operating cost. CO2 payments (price and cap
  shadow price) go to the state. Sum of actors = −(system cost − CO2 price
  payments), checked automatically.
- The cable is the link whose carrier contains "Brazil HVDC" (`CABLE_TAG` in
  `evaluate.py`). Break-even gap per MW = congestion rent per MW − annuity per
  MW (E5).
- Net import counts cross-border lines and links into Germany, without the cable.

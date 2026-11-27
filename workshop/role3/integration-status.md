<!--
SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>

SPDX-License-Identifier: CC-BY-4.0
-->

# Role 3: integration with roles 2 and 4, status

Working document. Last updated: 2026-11-27, after the cleanup of `workshop/role3`.
Nothing here is agreed with roles 2 or 4 yet. "Checked" means I read the code
or ran a query; "proposal" means it is my suggestion.

## What was asked

- Define how role 3 hands over to role 4: a folder of results that role 4 can
  wrap for analysis and the presentation (talked through with role 4, folder
  not yet defined).
- Define how role 2 (Brazil) plugs into the model that role 3 maintains.

## State of the work

| Item | State |
|---|---|
| Baseline `de10-myopic` | Solved, six years. Check tables in `baseline-check.md`. |
| `de10-nb9` (free trade) | Solved for all six years, 4 h steps. Results in `neighbours.md`. |
| `de10-nb9-ref` (NTC limits, 2050 CO2 price) | Config and code exist (`config/config.role3-reference.yaml`, `data/role3_constraints.py`). Only 2025 and 2030 solved so far (`results/de10-nb9-ref/networks/`). |
| Handover to the group | `handover.md`. |
| Handoff folder for role 4 | Not written. |
| Group repo | Remote `group`. Nothing committed or pushed by me. |

Memory: the workspace limit is 10 GB and a solve peaks at about 7 GB. Run one
solve at a time.

## Facts that shape the interface (checked in code)

1. **Cost definition differs by 2.8x.** For 2030, `statistics.capex + opex` =
   67.5 bn EUR (the `total costs` row in `csvs/metrics.csv`), but the solver
   objective is 24.5 bn EUR. The objective only contains extendable assets;
   the statistics also charge existing plants. Role 4 has to pick one
   definition and use it for every scenario. For a with/without-cable
   difference the two can give different answers.
2. **Myopic carry-over drops assets with infinite lifetime** and recreates them
   each horizon (`add_brownfield.add_brownfield`). New assets are renamed
   `<name>-<year>`. A cable and Brazilian plants must either have a finite
   lifetime and build year, or be re-added in every horizon with
   `p_nom_min` taken from the previous solve. Not tested.
3. **Costs enter through `data/custom_costs.csv`** (long format: planning
   horizon, technology, parameter, value, unit, source) and are annualised in
   `process_cost_data` from lifetime and `discount rate`. Role 2's CAPEX,
   FOM, VOM can be expressed there. A discount rate per technology exists
   (`costs.fill_values.discount rate`: 0.07), so a Brazil-specific rate is
   possible but is a role 4 decision.
4. **Components in `compose_network.py`** can be added after
   `add_electricity_components` and before `prepare_network_for_solving`
   (so costs and the transmission limit apply), or after
   `apply_brownfield`. The `lv_limit` (grid volume +25%) counts DC links by
   carrier `"DC"`: a cable with that carrier would count against the German
   grid limit, so it needs its own carrier.
5. **A scenario run name needs its own inputs.** A dry run with a new run name
   and `shared_resources: base` still failed on missing
   `resources/costs_2025_processed.csv`. With the neighbours config it plans 37
   jobs. So role 4's scenarios cannot just change the run name; sharing inputs
   with the reference run is not solved yet.
6. **Mismatch in the Brazil data README**: it assumes Germany with 4 nodes and
   3-hour steps. The baseline has 10 nodes and 2-hour steps. Role 2 should
   build hourly profiles that can be averaged to 2 h.

## Proposal: what role 3 hands to role 4

One folder per run: `results/<run>/handoff/`, written by one script
(`workshop/role3/export_handoff.py <run>`) so every run has the same shape.

| File | Content |
|---|---|
| `manifest.yaml` | run name, config files used, git commit, cost definition, horizons, solver status per year, peak memory, run time |
| `system_costs.csv` | per horizon, per component and carrier: capex, opex (both from `n.statistics`), plus the objective value |
| `prices_nodal.csv`, `prices_summary.csv` | nodal mean price, load-weighted price, hours above 300 and below 1 EUR/MWh |
| `energy_balance.csv` | generation, storage, trade, demand per carrier and horizon |
| `capacities.csv` | optimal capacity per carrier and node |
| `co2.csv` | emissions, cap shadow price, CO2 price used |
| `trade.csv` | net flow per neighbour and horizon (once neighbours exist) |
| `cable.csv` | cable capacity, hourly flow, utilisation, price at both ends (once the cable exists) |

Caveats: the networks are 159 MB and `results/` is git-ignored, so how the
folder reaches role 4 (shared drive, group repo, copy) is **open**. The CSVs
are small and could go in the group repo, but only after the confidential
check: no unit-level efficiencies. The export reads solved networks only and
does not use the confidential file.

## Proposal: what role 2 plugs into

- Role 2 delivers (a) a `custom_costs`-style table: CAPEX, FOM, VOM, lifetime,
  source, currency year; (b) hourly capacity-factor profiles at the landing
  point, weather year 2013, with the potential in MW per technology.
- Role 3 provides a single function in `compose_network.py` (for example
  `add_brazil_export_site(n, ...)`) that role 2's tables feed, in a separate
  block, so merge conflicts with roles 1 and 3 stay small. Role 1 adds the
  cable block next to it.
- Brazil is an export site only (the role file's default): one bus, new
  generators with their potentials, no demand.

## Open questions

1. Which cost definition does role 4 want as the main number (objective or
   statistics)?
2. Does 2050 stay in the study? This decides whether the CO2-price work matters.
3. How does the handoff folder travel between workspaces?
4. Who owns which block in `compose_network.py`, and which carrier name does the
   cable get? Needs roles 1 and 2.
5. `de10-nb9-ref`: solve 2035-2050 (memory peak 2045: about 6.9 GB in `de10-nb9`).

## Update log

- 2026-11-27: first version, from the code and data survey. No model run was
  started by me.
- 2026-11-27: cleanup. Neighbours run is solved, `handover.md` exists, dropped stale rows.

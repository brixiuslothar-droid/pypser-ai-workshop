<!--
SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>

SPDX-License-Identifier: CC-BY-4.0
-->

# Hand-off of solved runs (role 3 to role 4)

One folder per run, written by `workshop/role3/export_handoff.py RUN`, always the
same files. About 170 KB per run; the solved networks (30 MB each) stay in
`results/<run>/networks/` of the workspace and are not in git.

| Run | What it is | Use it for |
|---|---|---|
| `de10-ref` | **REF of decisions.md E4/E3**: neighbours with NTC limits, net import of DE at most 25 TWh/a, cap 2050 = 0.05 and 750 EUR/t | the comparison case for every cable run |
| `de10-cable` | **CABLE of E4** on `de10-ref`: Brazil cable 0-20 GW from 2035, Brazilian wind and solar by investment, 10 % WACC. **Pipeline test, not an assessment**: cable cost is the European cost-table entry (placeholder for role 1), profile is the built-in Pecem profile, no potential caps | the first CABLE-minus-REF comparison; result: no cable built |
| `de10-nb9-ref` | the reference before E3: NTC limits only, no annual import limit, 2050 at 2,600 EUR/t without cap | showing what the import limit does (E3 sensitivity) |
| `de10-cable` | **CABLE of E4**: `de10-ref` plus the Brazil cable (0-20 GW from 2035, Brazilian generation by investment, WACC 10 %). Solved 2025-2050. The model builds **no cable** in any year (capacity ~1e-7 MW, i.e. zero). **2050 solver status is `Imprecise`**, not `Optimal`: treat 2050 with care. 2025 and 2030 have no solver log (`n/a`) because they are the reference's years. | the main run against `de10-ref` |

Files per run: `manifest.yaml` (git commit, configs, solver status, run time, peak
memory, definitions), `system_costs.csv`, `objective.csv`, `energy_balance.csv`,
`capacities.csv`, `prices_de.csv`, `prices_nodes.csv`, `trade.csv`, `co2.csv`, and
`cable.csv` when the run has the Brazil cable.

Definitions (also in each manifest): system cost = capex + opex of all active assets
(the solver objective counts extendable assets only and is smaller); trade = net flow
at the sending end, the quantity the import limit constrains; Germany = AC buses with
country DE; 4 h steps, weather year 2013.

Content: aggregates by country and carrier, and prices per node. Nothing per power
plant unit; the model inputs are public data, the NDA files in `workshop/inputs/` are
not read. If a run ever needs unit-level data, it does not belong in this folder.

Run `evaluate.py` and the exporter only when no solve is running (decisions.md O7).

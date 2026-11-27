<!--
SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>

SPDX-License-Identifier: CC-BY-4.0
-->

# Review checklists (E8)

Concrete items for the three reviews. Tick each; anything not ticked becomes a
finding in `results/review/report-<date>.md` with a severity, an owner and
`path:line` evidence. `[ ]` = to check, `[x]` = confirmed. Keep no confidential
value in this file.

The how is in `.claude/skills/review/SKILL.md`. The what is `decisions.md` E8.

## R3 - NDA (E7) — do this first

- [ ] `workshop/inputs/` is listed in `.git/info/exclude`.
- [ ] `git status` shows no tracked file under `workshop/inputs/`.
- [ ] `git log --all -- workshop/inputs` and `git log --all --diff-filter=A` show
      no input file ever committed.
- [ ] No run config, model script or rule reads `workshop/inputs/`. Only
      `cba/validate_against_nda.py` does, at runtime, for validation.
- [ ] No confidential value appears in code, config, comments, commits, file
      names, logs, results, figures, slides or docs. (Grep the deal code, the
      offtake price and the guarantee terms — do not record the matches.)
- [ ] Only coarse bands leave the validation step; no exact value, ratio or
      difference that reveals one.
- [ ] The report itself holds no confidential value, deal code or guarantee
      term; scanned before saving.
- [ ] Slides and report mention the NDA only qualitatively; every number rests on
      a public source (E2).
- [ ] Nothing from `workshop/inputs/` was passed to an outside service or chat.

## R1 - workflow (E1, E4)

- [ ] Each run differs from its parent in exactly one thing (diff the two config
      layers, not each against `config.default.yaml`).
- [ ] Comparison pairs match E4 and `workshop/analysis/runs.yaml`:
      `CABLE–REF`, `MV–REF`, `CAPEX50–REF`, `WACC7–REF`, `CABLE-ISL–REF-ISL`,
      `REF–BASE`.
- [ ] Every run has its own `run: {name: ...}`; no run name is reused for a
      different definition.
- [ ] Runs with their own name have their own inputs (`run.shared_resources` set
      where required; see BASELINE.md "Rebuilding the inputs").
- [ ] The baseline `de10-myopic` still reproduces BASELINE.md's "Results at a
      glance".
- [ ] E1: cable `p_nom_extendable: true`, `p_nom_max` 20 GW, `p_nom_max = 0` in
      2025/2030, buildable from 2035.
- [ ] E3: soft 2050 cap (`co2_budget.upper.2050: 0.05`), trade allowed in all
      years, net-import limit applied; CO₂ price path as decided.
- [ ] E2: cable and Brazil carriers carry the agreed WACC; carrier name contains
      "Brazil".
- [ ] Role hand-offs are in E2 form: EUR_2020, CAPEX/FOM/VOM, life, a
      low/central/high range, no annualised costs.
- [ ] Every changed assumption has a source and a year.
- [ ] Runs fit the memory limit (≤ ~7 GB) and the time budget; recorded in
      `results/scenario-runs.md`.
- [ ] Each result's producing command is recorded; inputs are newer than the
      config that changed them.
- [ ] Plausibility against BASELINE.md: prices outside 2050, capacity at
      `p_nom_max`, solver status "imprecise" only where BASELINE.md allows it.
- [ ] Refinements live in config files, not hard-coded, so role 4 can vary them.

## R2 - evaluation (E2, E3, E5, E6)

- [ ] The pipeline was built and tested on the baseline before any cable run
      existed.
- [ ] Every E6 metric is present per run and horizon: system cost, cable
      capacity/flows, prices, emissions and CO₂ shadow price, trade, generation
      mix, winners/losers.
- [ ] Costs are annuities + opex from `n.statistics`; cost year EUR_2020 and
      currency EUR, one set (E2).
- [ ] Two subtracted runs differ in one thing only; the compare split
      (`CABLE–REF` changes cable + Brazil/cable WACC together, per E4) is stated.
- [ ] E5: `MV` gives the shadow price of `p_nom_min` against the cable annuity,
      with the price-difference × flow cross-check; if unavailable (O5), flagged
      as such.
- [ ] `CAPEX50` confirms the break-even; the break-even cost (EUR/MW, EUR/MW/km)
      is shown against role 1's range.
- [ ] E3: 2050 is marked separately in every figure; the summary exists with and
      without 2050.
- [ ] Winner/loser table uses the E6 groups and the `CABLE − REF` difference.
- [ ] Sample recomputation (≥2 numbers) from the `.nc` files matches the
      pipeline output.
- [ ] Every figure follows `.claude/skills/plot-style/SKILL.md`: fixed group
      colours; Brazil cable in `#D55E00`; no-cable series neutral grey; one y
      axis; titles give quantity/place/year/unit; legends frameless.
- [ ] Each figure agrees with its CSV (regenerate a figure and compare).
- [ ] Every number in the report and slides traces to an existing run directory
      or a public source; none exists only in a slide.
- [ ] Units everywhere: GW/TWh for the system, EUR/MWh prices, EUR/t CO₂, Mt
      emissions, bn EUR costs.

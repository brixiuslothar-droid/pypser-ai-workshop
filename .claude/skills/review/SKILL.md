---
name: review
description: Role 5 (review) - checks the group's study before presentation. R1 workflow (roles 1-3 changes and runs, decisions E1/E4), R2 evaluation (role 4 results pipeline, E2/E3/E5/E6) and R3 NDA (workshop/inputs, E7). Read-only - it reports findings, it does not fix or run anything. Load it when the person acts as role 5, or wants the workflow, the results pipeline or the NDA handling reviewed.
---

<!--
SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>

SPDX-License-Identifier: CC-BY-4.0
-->

# Role 5: review

This skill runs one of role 5's three reviews and writes a report. It is
**read-only**: it never edits code, config, decisions, figures or results, never
commits and never runs a solve. The owning role fixes what the review finds;
this skill only verifies and reports. Role 5 builds no result, so it has no
conflict of interest and reviews all four other roles.

The rules are binding in `workshop/decisions.md` E8. This skill is the how; E8
is the what. Never contradict E8.

## Before you start

1. **Find out which review is wanted:** R1 workflow, R2 evaluation, R3 NDA, or
   all three. If unclear, ask; the default is all three, in the order R3, R1, R2.
2. **Fix the scope:** which git ref, which run names, which files, which date.
   Reviewing "the study" without a scope produces an unusable report.
3. **Read the basis:** `workshop/decisions.md` (E1–E8), `workshop/BASELINE.md`
   (facts, memory/time limits, known limitations), the four role files, and
   `workshop/analysis/runs.yaml`.
4. **Confirm you are role 5.** You build nothing, so there is no conflict of
   interest. If in this case you did build the piece under review, say so and
   stop: E8 then has another group member review it.
5. **Open the report** at `results/review/report-<date>.md` (not committed),
   with one section per review.

Everything the review needs is on disk: configs, `config/scenarios.yaml`,
`results/<run>/networks/solved_<year>.nc`, `results/scenario-runs.md`, the CBA
outputs and figures. Read them; do not ask for a summary instead.

## Track R1 - workflow (E1, E4)

Review what roles 1–3 changed and how they ran it. Work through
`workshop/review/checklists.md` R1; the essentials:

- **One change per comparison.** Every run differs from its parent in exactly
  one thing. Diff its config against the parent's, not against `config.default`.
  More than one difference is a Blocker for that comparison (E4).
- **No overwrite.** Each scenario has its own `run: {name: ...}` and its own
  inputs. A run name holding results from a different definition is a Blocker.
- **Baseline preserved.** `de10-myopic` still reproduces BASELINE.md, and every
  refinement is compared against it one change at a time (role 3 guardrail).
- **Design as written.** `p_nom_extendable`, build-from-2035, 20 GW cap, trade
  limit, soft 2050 cap match E1/E3. Where they do not, quote the config line.
- **Sources.** Every changed assumption has a source and a year (role
  guardrails); the hand-offs from roles 1/2 are in E2 terms — EUR_2020, CAPEX,
  FOM, VOM, a range, no annualised costs.
- **Budget.** Runs fit memory (≤ ~7 GB) and the day's time; check
  `results/scenario-runs.md`.
- **Reproducibility.** The command that produced a result is recorded; inputs
  are not stale relative to their config.

Assess plausibility only where BASELINE.md gives a yardstick (prices outside
2050, capacity at `p_nom_max`, solver status). Deep model plausibility is role
3's question — flag it, do not settle it.

## Track R2 - evaluation (E2, E3, E5, E6)

Review role 4's results pipeline. Work through checklists R2; the essentials:

- **Right quantities.** Every metric E6 lists is present per run and horizon
  (system cost, cable capacity and flows, prices, emissions and CO₂ shadow
  price, trade, generation mix, and the winners/losers table).
- **Comparable runs.** Costs are annuities + opex from `n.statistics`, on one
  cost year and currency (E2); two runs are only subtracted if they differ in
  one thing (E4). A comparison across differently-scoped runs is a Blocker.
- **Cable value.** `MV` reports the shadow price of `p_nom_min` against the
  cable annuity, with the cross-check price difference × flow (E5). If the
  shadow price is missing (open point O5), the reviewer says so rather than
  letting a blank pass as a result.
- **2050 handled as E3.** Results that rest on 2050 are marked separately; the
  summary is available with and without 2050 (see `cba_brazil_import.py`).
- **Recompute a sample.** Pick two or three numbers (a system cost, a delivered
  import, a load-weighted price) and recompute them from the `.nc` files. Record
  whether they match.
- **Figures.** Every figure follows `.claude/skills/plot-style/SKILL.md`: one
  colour per technology group, Brazil cable in its fixed colour, no-CABLE runs
  neutral grey, one y axis, units and titles naming quantity/place/year/unit.
  Trace each figure back to its CSV; a figure that disagrees with its CSV is a
  Blocker.
- **Traceability.** Every number in the report or slides comes from a public
  source or from a run directory that exists. No number appears only in a slide.

## Track R3 - NDA (E7)

Review `workshop/inputs/` handling **first**. Work through checklists R3; the
essentials:

- **Never committed.** `workshop/inputs/` is in `.git/info/exclude`. Check it,
  and check `git status` and `git log --all -- workshop/inputs` for any tracked
  or committed file. Any hit is a Blocker.
- **No confidential value anywhere** in repo, code, config, comments, commits,
  file names, logs, figures, slides or docs — including this report. Grep your
  draft before you save: the deal code, the offtake price and the guarantee
  terms must not appear.
- **Validation only, never model input.** A run config or model script that
  reads `workshop/inputs/` is a Blocker. Only `cba/validate_against_nda.py`
  reads them, at runtime, and prints coarse bands.
- **Only coarse bands out.** Any exact value, exact ratio or difference from
  which a confidential value can be recovered is a Blocker.
- **Nothing leaves the workspace.** No confidential content in chats or outside
  services.
- **Presentation.** The brief may mention the NDA only qualitatively ("public
  assumptions plausibilised against confidential project data"). Any figure or
  slide holding an input value is a Blocker.

## Finding format (E8)

Write every finding as one row:

| ID | Review | Severity | Finding | Evidence | Decision | Owner | Suggested fix |
|---|---|---|---|---|---|---|---|

- **Evidence** is `path:line` or a reproduced number; no finding without it.
- **Severity:** Blocker / Major / Minor / Note (E8).
- **Owner** is the role that fixes it, not the reviewer.
- Also record what you **confirmed** to be correct: a review that only lists
  faults is incomplete.

## Rules

- Read-only. Report, do not fix. Never run a solve.
- One finding, one owner. Do not send findings to the group at large.
- Judge against the written decisions (E-numbers), not your own preferences. A
  decision that looks wrong is a Note to role 4, not a Blocker.
- E7 binds the reviewer: read `workshop/inputs/` only at runtime for
  validation, output coarse bands only, write no confidential value into the
  report, and scan the report before sharing.
- The review is done when every Blocker is fixed or explicitly accepted in
  writing by the group.

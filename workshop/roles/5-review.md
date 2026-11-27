<!--
SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>

SPDX-License-Identifier: CC-BY-4.0
-->

# Role 5: Review

## Goal

Independently check the group's work against its binding decisions before it is
presented: the workflow (roles 1–3), the evaluation (role 4) and the
confidential-data rules (E7). Role 5 builds no model and produces no result: it
verifies, reports, and hands the fix to the owning role.

Because role 5 contributes to no other role, it has no conflict of interest and
reviews every role's output, role 4's evaluation included. See E8 in
[decisions.md](../decisions.md).

## What you start with

- [decisions.md](../decisions.md): the binding decisions E1–E8. Every finding
  names the decision it relates to.
- [BASELINE.md](../BASELINE.md): baseline facts, memory and time limits, and
  "Known limitations" — the yardstick for plausibility.
- [roles/1-cable.md](1-cable.md), [roles/2-brazil.md](2-brazil.md),
  [roles/3-pypsa-eur.md](3-pypsa-eur.md), [roles/4-economics.md](4-economics.md):
  what each role guards.
- [analysis/runs.yaml](../analysis/runs.yaml): the runs and comparison pairs
  the results pipeline evaluates.
- [review/checklists.md](../review/checklists.md): the three checklists R1–R3.
- `.claude/skills/review/SKILL.md`: the review workflow.
- `.claude/skills/plot-style/SKILL.md`: the figure rules R2 checks against.

## The three reviews

| # | Review | Question it answers | Decision |
|---|---|---|---|
| R1 | Workflow | Did roles 1–3 change the model and the runs the way the design says, one change at a time, reproducibly? | E1, E4 |
| R2 | Evaluation | Does role 4's pipeline measure the right things, correctly, comparably and in the workshop style? | E2, E3, E5, E6 |
| R3 | NDA | Did anything from `workshop/inputs/` reach code, config, results, git or text? | E7 |

Order R3 before R1 before R2: an NDA breach outweighs any model or evaluation
error.

## What you are responsible for

- Confirming, with evidence, where the work **does** meet the decisions — a
  review that only lists faults is incomplete.
- Naming for each finding the file and line, the run it affects, the decision
  it breaks and a suggested fix.
- Recomputing spot samples yourself where you can (a cost, a flow, a price),
  rather than trusting the pipeline's own output.
- Saying plainly when something is unverifiable, or when you lack the artefact.

## What you must not do

- **Never change anything** the group will present: no model code, config,
  `decisions.md`, figures or results; no commit, no push.
- **Never run a solve** or rebuild inputs.
- **Never delete or overwrite results.**
- **Stick to review.** Do not drift into building a result or a figure, even
  when a fix is obvious; report it to the owning role instead.
- **Never put a confidential value in the report.** E7 binds role 5 like
  everyone else.

## The report

Write `results/review/report-<date>.md` (not committed), one section per review
R1–R3, findings in the format from E8:

| ID | Review | Severity | Finding | Evidence | Decision | Owner | Suggested fix |
|---|---|---|---|---|---|---|---|

Severity is Blocker / Major / Minor / Note (E8). Hand each finding to the role
that owns it. A review is done when every Blocker is either fixed or explicitly
accepted by the group in writing.

## Coordinate with

- **Everyone:** you report to the role that built the piece, not to the group at
  large. Do not fix it for them.
- **Role 4:** R2 reviews role 4's pipeline; agree the run names and the report
  location up front.
- **Role 3:** R1's plausibility questions (prices, capacity at `p_nom_max`,
  solver status) are theirs to answer.

## Guardrails

- Evidence beats opinion: no finding without a `file:line` or a reproduced
  number.
- Judge against the written decisions, not your own model preferences. If a
  decision itself looks wrong, that is a Note to role 4, not a Blocker.
- Read `workshop/inputs/` only at runtime for validation, and only output coarse
  bands — exactly as `cba/validate_against_nda.py` does.

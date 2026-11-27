<!--
SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>

SPDX-License-Identifier: CC-BY-4.0
-->

# PyPSA x AI workshop: a Brazilian–German interconnector

Every group works on the same study with one shared model: an HVDC cable between
Brazil and Germany. The brief is to show that it is an amazing solution to the
energy transition. Whether your results support that, and under which
conditions, is what your group presents at the end of the day.

You start with two things:

- A solved baseline of the German power system from 2025 to 2050. How it is
  built, how to run it and what it assumes is in [BASELINE.md](BASELINE.md).
- A prepared dataset for Brazil in `data-brazil/`, described in its own
  `README.md`. Nothing in it is a model yet.

Everything else is yours to build: Brazil, the cable, a better picture of
Germany's surroundings, the scenarios and the analysis.

## Roles

Each person in a group takes one role.

| Role | Question it answers | Works mostly in | Instructions |
|---|---|---|---|
| 1 Cable techno-economics | Where is the cable laid, at what cost, under which constraints? | the network composition step | [roles/1-cable.md](roles/1-cable.md) |
| 2 Brazil renewable potential | Where in Brazil, and with which renewables, is power for the cable best produced? | the network composition step | [roles/2-brazil.md](roles/2-brazil.md) |
| 3 PyPSA-Eur setup | Is the German system the cable connects to modelled well enough to judge it? | the whole workflow | [roles/3-pypsa-eur.md](roles/3-pypsa-eur.md) |
| 4 Economic analysis | How is the study designed, and what is the cable worth? | config and postprocessing | [roles/4-economics.md](roles/4-economics.md) |
| 5 Review | Does the study hold up against its binding decisions — workflow, evaluation, NDA? | the whole workflow, read-only | [roles/5-review.md](roles/5-review.md) |

Roles 1, 2 and 3 change the model in one shared place, the step that composes
the network (`scripts/compose_network.py`). Role 4 does not change model code:
it sets the study design in config files and compares the solved runs. Role 5
changes nothing: it checks the work of roles 1–4 against the binding decisions
and reports, before the group presents.

The role files set guardrails, not a plan. They say what each role is
responsible for and whom it depends on. How you get there is up to you.

Role 5 runs three reviews — workflow (R1), evaluation (R2) and NDA (R3). Their
rules are E8 in [decisions.md](decisions.md); the checklists are in
[review/checklists.md](review/checklists.md); the agent workflow is
`.claude/skills/review/SKILL.md`. Because role 5 builds no result, it has no
conflict of interest and reviews every role's output, role 4's included.

## General instructions

_Placeholder: the organisers add these before the workshop._

## Working together

Each of you works in your own workspace with your own AI agent, and all four
roles contribute to one workflow. How your group shares code is yours to
organise: branches, who changes which file, how pieces are merged and tested.
Nothing here prescribes it.

## One thing every group has to deal with: 2050

In the baseline, the CO₂ cap falls to zero in 2050. Germany alone can only meet
it at extreme cost:

| | 2040 | 2045 | 2050 |
|---|---|---|---|
| Price the cap adds on top of the CO₂ price (€/t) | 43 | 488 | 24,341 |
| Highest electricity price (€/MWh) | 1,427 | 430 | 2,957 |

Any new source of clean power looks enormously valuable against this, the cable
included. A result that rests on 2050 says more about the cap than about the
cable. Roles 3 and 4 decide together how the study handles it.

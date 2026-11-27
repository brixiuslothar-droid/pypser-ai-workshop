---
name: scenario-runs
description: Role 4 (economics) - runs the study's scenario set from workshop/decisions.md (E4) one after another, in the right order, without overwriting runs, and hands each finished run to the results pipeline. Controls only the outer loop over scenarios; how a single run is configured, built and solved comes from role 3's skill `run-model`. Load it when the person wants to run, rerun or check the status of the scenarios.
---

<!--
SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>

SPDX-License-Identifier: CC-BY-4.0
-->

# Scenario runs (role 4)

This skill steers the **outer loop**: which scenarios run, in which order, when
a run counts as done and what happens with its results. It does **not** say how
a single run is solved. That belongs to role 3, who optimises the model and
its run procedure.

## Split of responsibility

| | Role 3: skill `run-model` | Role 4: this skill |
|---|---|---|
| Owns | one run: config layering, input builds, `--allowed-rules`, solver, memory, unlock and rerun after a crash | the set of runs: list, order, status, comparisons, results |
| Source of truth | `.claude/skills/run-model/SKILL.md` | `workshop/decisions.md` (E4, E5, E6) |
| Changes when | role 3 improves the model or the run procedure | the study design changes |

Never copy commands or settings from `run-model` into this skill. Read
`run-model` again before every round of runs: role 3 may have changed it.

### Interface expected from `run-model`

This skill relies on `run-model` to say, for one scenario:

1. how to start a run, given a run name and its config files (or an entry in
   `config/scenarios.yaml`);
2. where its solved networks are written (`results/<run>/networks/solved_<year>.nc`);
3. how to tell success from failure (exit status, solver status, files);
4. the expected memory and run time;
5. how to recover from a crash (unlock, rerun incomplete).

If `run-model` does not exist yet or does not answer one of these points, stop
and tell the person: role 3 has to provide it. Until then, the only fallback is
the procedure in `workshop/BASELINE.md`, and only for runs that need no model
change by role 3. Say clearly that the fallback was used.

## The loop

1. **Read the plan.** Take the scenario list, the "derived from" column and the
   comparison pairs from E4 in `workshop/decisions.md`. Do not invent
   scenarios. Do not change a scenario's definition here; change E4 first.
2. **Check that each scenario differs from its parent in one thing only.**
   Compare its config with the parent's. If it differs in more, stop and report.
3. **Check the status of each run.**
   - *done:* all `solved_<year>.nc` exist for the planning horizons and are
     newer than its config files
   - *open:* files are missing or older than the config
   - *failed:* the last attempt failed (see `run-model`, point 3)
4. **Order the open runs.** Parents before children, references before the runs
   compared with them:
   `REF` → `CABLE` → `MV` → `CAPEX50` → `WACC7` → `REF-ISL` → `CABLE-ISL`.
   If time is short, the priority is `REF`, `CABLE`, `MV`; the rest follow in
   the order above.
5. **Check the time budget and the workspace.** Multiply the open runs by the
   run time from `run-model`, and tell the person before starting. Runs go one
   at a time: a solve needs up to about 7 GB, and the workspace limit (10 GB
   measured in `/sys/fs/cgroup/memory.max`) is shared with every editor,
   agent and script in it. Before starting, check `pgrep -af solve_network`:
   another role may already be solving in the same workspace. Nothing else
   memory-heavy (the results pipeline included) runs during a solve.
6. **Run one scenario** exactly as `run-model` says.
7. **Check the result.** Every planning year is solved and the solver status is
   accepted by `run-model`. Plausibility of the system is role 3's question;
   flag what looks odd (for example prices in the thousands of EUR/MWh outside
   2050, or cable capacity at `p_nom_max`) and pass it on.
8. **Hand the run to the results pipeline** (E6) and update the comparison of
   each pair whose two runs are done.
9. **Log the run** (see below), then continue with the next open run.
10. **On failure:** recover once as `run-model` says. If it fails again, stop the
    loop, log it and report to the person and role 3. Do not change the model
    to make it pass.

## Rules

- **No run overwrites another.** Each scenario has its own run name. Never
  start a run whose name already holds results from another definition.
- **Never touch model code** (`scripts/`, `rules/`, `data/custom_extra_functionality.py`).
  That is role 1, 2 and 3's area.
- **Never delete results** without the person's explicit go.
- **Runs started by others** are logged, not restarted. Restarting a failed run
  of another role is that role's call.
- **Confidential data (E7):** no run takes input from `workshop/inputs/`. Logs
  and summaries hold no confidential value.

## Run log

Keep a log in `results/scenario-runs.md` (not committed), one line per attempt:

| Date and time | Run | Horizons | Status | Wall time | Peak memory | Notes |
|---|---|---|---|---|---|---|

Report from it when the person asks what has run.

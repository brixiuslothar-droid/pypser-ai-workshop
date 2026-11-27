---
name: presentation
description: Role 4 (economics) - builds the group's final PowerPoint presentation from the study (decisions E1-E8, role deliveries, results pipeline, register of data/assumptions/decisions). Asks only the settings that are open, documents every decision with its intermediate step and effect, uses only finished runs, and names NDA data only as a source before processing. Load it when the person wants slides, the final presentation or a status deck.
---

<!--
SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>

SPDX-License-Identifier: CC-BY-4.0
-->

# Final presentation (role 4)

Builds `results/presentation/praesentation-<date>.pptx` from the state of the
study. The reference for structure, rules and design is
`workshop/presentation/README.md`; read it once per session. This skill is
the how; never contradict the README or `workshop/decisions.md`.

| File | Role |
|---|---|
| `workshop/presentation/deck.yaml` | slide outline with placeholders |
| `workshop/presentation/register.yaml` | data, assumptions, decisions with intermediate step and effect |
| `workshop/presentation/settings.yaml` | fixed settings and the question catalogue |
| `workshop/presentation/build_deck.py` | builder, checks (pending, TODO, NDA, review) |
| `results/presentation/answers.yaml` | stored answers of this workspace |

Command prefix used below:

```bash
B="uv run --no-project --with python-pptx --with pandas --with pyyaml --with matplotlib python workshop/presentation/build_deck.py"
```

## Steps

1. **Role.** The deck is role 4's. If the person has another role, they own
   only their slides in `deck.yaml` (part A) and their entries in
   `register.yaml`; help with those and leave the rest.
2. **Handovers up to date?** Pull or merge the group's work first if the
   person wants that (never force). Then look for new or changed role
   handovers: the builder lists every registered handover whose checksum
   changed ("Übergaben geändert"); also check for new files in the roles'
   folders (e.g. `workshop/role3/`, `workshop/brazil/`, `workshop/cable/`,
   `config/config.role*-*.yaml`). Work each one in as README "Übergaben der
   Rollen einarbeiten" says, then update its `sha` in `register.yaml`.
3. **Results up to date?** Compare `workshop/results/status.csv` with
   `results/<run>/networks/`. If a run finished since the last evaluation,
   evaluate it first with the skill `results-pipeline` – but **never while a
   solve runs** (`pgrep -af solve_network`; O7). If a solve runs, build from the
   existing results and say so.
4. **Ask only open questions.** Run `$B --questions`. It prints only the
   questions whose condition holds and that have no valid stored answer
   (a stored answer goes stale only where `neu_fragen_wenn` says so, e.g. when
   the set of finished runs changed). If it prints "keine offenen Fragen",
   ask nothing. Otherwise ask exactly those, in one `question` call, with the
   options from the catalogue (first option = default, marked recommended),
   including the context that makes them relevant (e.g. which runs are
   missing). Never ask the fixed settings (`fest:` in `settings.yaml`) or
   anything already answered. If the person states a setting unprompted, store
   it.
5. **Build.** `$B --set key=value ...` with the answers (stores them and
   builds), or `$B` if nothing was asked.
6. **Read the report** the builder prints and tell the person, briefly:
   - slides with placeholders (`▢`, state "Platzhalter") and which runs or
     files they wait for; with `ausstehend=platzhalter` every slide keeps its
     full layout and missing values show where they belong;
   - `TODO`s grouped by owning role (column "Rolle"), so each role knows its gap;
   - "Layout" warnings (table too long: split it or shorten text);
   - NDA scan hits (see below), review blockers.
7. **Fill gaps the right way** (only if asked to):
   - a number: a placeholder in `deck.yaml` or `register.yaml`, never typed;
   - an interpretation: first into `workshop/results/notes.md`, then onto the
     slide; result slide titles are statements taken from `notes.md`;
   - a decision: a new entry in `register.yaml` with phase, who, why, the
     intermediate step (run, file or finding) and its effect as a placeholder;
   - a data source or assumption: a `D…`/`A…` entry with source and year;
   - a number from a role's handover: `{{md|…}}` on its Markdown table,
     `{{cfg|…}}` on its config, `{{src|…}}` for a quoted key sentence – never
     copy the number;
   - a missing figure: a function in `evaluate.py` (skill `results-pipeline`),
     in the plot style – no one-off script for a slide.
   Content of roles 1–3 comes from their deliveries; do not invent it. Leave a
   `TODO Rolle n:` instead.
8. **Final.** Only when the person wants the final deck: `$B --final`. It
   writes nothing while slides are pending, `TODO`s remain, the NDA scan hits
   or the newest review report has blockers. Remind them that role 5 reviews
   the draft first (E8).

## Sharing the deck in the repo

Only when the person asks: build with
`$B --out workshop/presentation/praesentation.pptx`, then before committing
(1) no open NDA scan hit, (2) every embedded image matches a public figure of
the pipeline or a role by checksum (none of unknown origin, none based on GADM
or WDPA), (3) `python workshop/hooks/check_confidential.py staged` is clean.
Commit the `.pptx` together with its `.license` file. Never edit it by hand.

## Rules

- **Decisions with effect.** The deck shows every decision with the step in
  which it acted and what it did there (slides "Entscheidungspfad" and
  "Zwischenschritte", from `register.yaml`). Intermediate runs of a role
  (e.g. role 3's `de10-nb9`, `de10-nb9-ref`) are steps, not E4 results.
- **Contradictions stay visible.** If a handover, a config and `decisions.md`
  disagree, write a `TODO Rolle n:` naming both; do not pick one silently. Test runs (BRIMP) are
  intermediate steps, marked as tests, never study results.
- **Finished runs only.** A run counts when all horizons are solved. Slides of
  missing runs are pending or dropped (answer `ausstehend`); never fill them
  with numbers from another run.
- **E3, E4.** Summaries are 2035–2045, 2050 separate; every comparison names
  its pair and the one change.
- **Design** follows the plot style as set in the builder (README "Design").
  Do not restyle slides by hand; change the builder so it reruns.
- **No hand-edited numbers in the .pptx.** Edit the YAML and rebuild.

## Confidential data (E7)

- An entry based on `workshop/inputs/` has `nda: true` and names **only** the
  source before processing ("vertrauliche Projektdaten (NDA), vor der
  Verarbeitung"), the processing script and its use. No value, result, effect,
  year, placeholder, file name from `workshop/inputs/`, partner or deal. The
  builder refuses anything else; do not work around it.
- Never read `workshop/inputs/` for slide content. The builder reads it only to
  scan the finished text at runtime and prints only slide ids and hit counts.
- On a scan hit: find which placeholder produced it and whether the same
  number stands in a public handover or pipeline file (count and file names
  only, never the number). If it does and the source is public, acknowledge
  with `--nda-ok SLIDE`; otherwise remove it. Never print or quote the
  suspected confidential value, and never compare it with the input in the chat.
- The NDA may be mentioned only qualitatively, only with
  `nda_hinweis=qualitativ`, and only if `validate_against_nda.py` has run.
- Do not send the deck or its text to outside services before the scan is clean.

## Done when

The deck is built, the person knows what is pending and who owns each gap,
the NDA scan is clean (or every hit checked), and for a final deck `--final`
passed.

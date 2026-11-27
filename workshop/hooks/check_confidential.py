# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""
Block commits that would publish confidential unit-level plant efficiencies.

The efficiencies in workshop/inputs/thermal_unit_efficiencies.csv are under NDA:
no single unit's value may reach the public repository, with or without name.

Modes
-----
staged            check files and added lines in the index (pre-commit hook)
message FILE      check a commit message (commit-msg hook)
range REV..REV    check the added lines of a commit range (pre-push / manual)

Hits are reported by file and line only, never with the value itself.
Install the hooks with ``bash workshop/hooks/install.sh``.
"""

import csv
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    ).stdout.strip()
    or "."
)
CONFIDENTIAL_DIR = "workshop/inputs/"
CONFIDENTIAL_FILE = ROOT / "workshop/inputs/thermal_unit_efficiencies.csv"
# Files allowed to mention the confidential path (they explain the rule).
SELF = {"workshop/hooks/check_confidential.py"}

NEAR = 3  # lines



def load_patterns():
    """Return (strong, weak) from the confidential CSV.

    strong: set of efficiency strings precise enough to be unlikely by chance
            (fraction with >= 4 decimals, percent with >= 3 decimals);
            blocked anywhere.
    weak:   {rounded efficiency string: set of identifiers of that unit}
            (fraction with 3 decimals, percent with 1-2 decimals; identifiers
            are capacity and plant id). Blocked only within NEAR lines of an
            identifier of the same unit.
    """
    if not CONFIDENTIAL_FILE.exists():
        return set(), {}
    strong, weak = set(), {}
    with open(CONFIDENTIAL_FILE, newline="") as f:
        for row in csv.DictReader(f):
            eff = float(row["net_efficiency"])
            cap = float(row["capacity_mw"])
            ids = {f"{cap:.1f}", row["plant_id"].strip()}
            if cap.is_integer():
                ids.add(str(int(cap)))
            for d in range(4, 7):
                strong.add(f"{eff:.{d}f}")
            for d in range(3, 5):
                strong.add(f"{eff * 100:.{d}f}")
            for s in (f"{eff:.3f}", f"{eff * 100:.1f}", f"{eff * 100:.2f}"):
                weak.setdefault(s, set()).update(ids)
    return strong, weak


TOKEN = re.compile(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])")


def scan_lines(lines_by_file, patterns):
    """lines_by_file: {name: [(lineno, text), ...]}. Returns list of hits."""
    strong, weak = patterns
    hits = []
    for name, lines in lines_by_file.items():
        if name in SELF:
            continue
        tokens = {lineno: set(TOKEN.findall(text)) for lineno, text in lines}
        for lineno, toks in tokens.items():
            if toks & strong:
                hits.append(f"{name}:{lineno}: matches a unit efficiency")
                continue
            for s in toks & weak.keys():
                near = set().union(
                    *(tokens.get(i, set()) for i in range(lineno - NEAR, lineno + NEAR + 1))
                )
                if near & weak[s]:
                    hits.append(
                        f"{name}:{lineno}: rounded efficiency next to the capacity "
                        "or id of the same unit"
                    )
                    break
    return hits


def parse_diff(diff):
    """Collect added lines per file from a unified diff with -U0."""
    out, name, lineno = {}, None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            name = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            lineno = int(m.group(1)) if m else 0
        elif line.startswith("+") and name:
            out.setdefault(name, []).append((lineno, line[1:]))
            lineno += 1
    return out


def git(*args):
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=ROOT, check=True
    ).stdout


def check_paths(names):
    return [
        f"{n}: file from {CONFIDENTIAL_DIR} or a copy of the confidential CSV"
        for n in names
        if n.startswith(CONFIDENTIAL_DIR) or "thermal_unit_efficiencies" in n
    ]


def main(argv):
    mode = argv[1] if len(argv) > 1 else "staged"
    patterns = load_patterns()
    if mode == "staged":
        names = git("diff", "--cached", "--name-only", "--diff-filter=ACMR").split()
        hits = check_paths(names)
        hits += scan_lines(parse_diff(git("diff", "--cached", "-U0", "--no-color")), patterns)
    elif mode == "message":
        text = Path(argv[2]).read_text()
        lines = [(i + 1, t) for i, t in enumerate(text.splitlines()) if not t.startswith("#")]
        hits = scan_lines({"commit message": lines}, patterns)
    elif mode == "range":
        rng = argv[2]
        names = git("diff", "--name-only", "--diff-filter=ACMR", rng).split()
        hits = check_paths(names)
        hits += scan_lines(parse_diff(git("diff", "-U0", "--no-color", rng)), patterns)
        msgs = git("log", "--format=%B", rng)
        hits += scan_lines(
            {f"commit messages in {rng}": list(enumerate(msgs.splitlines(), 1))}, patterns
        )
    else:
        print(__doc__)
        return 2

    if not patterns[0]:
        print(
            f"check_confidential: {CONFIDENTIAL_FILE.name} not found, only file paths were checked.",
            file=sys.stderr,
        )
    if hits:
        print("BLOCKED: possible confidential unit-level plant efficiencies (NDA).", file=sys.stderr)
        for h in hits:
            print("  " + h, file=sys.stderr)
        print(
            "See .claude/skills/confidential-inputs/SKILL.md. Remove the data; "
            "bypass (--no-verify) only after checking it is a false positive.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

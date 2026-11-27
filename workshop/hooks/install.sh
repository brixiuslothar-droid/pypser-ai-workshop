#!/usr/bin/env bash
# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
#
# Install git hooks that block confidential unit-level plant efficiencies
# (workshop/inputs/thermal_unit_efficiencies.csv, under NDA) from commits and pushes.
# Run once per clone: bash workshop/hooks/install.sh
set -euo pipefail

root=$(git rev-parse --show-toplevel)
hooks=$(git rev-parse --git-path hooks)
check="$root/workshop/hooks/check_confidential.py"

install_hook() {
    local name=$1 body=$2 target="$hooks/$1"
    if [ -e "$target" ] && ! grep -q "check_confidential" "$target"; then
        mv "$target" "$target.local"
        echo "Kept existing $name hook as $name.local; it still runs first."
    fi
    {
        echo '#!/usr/bin/env bash'
        echo 'set -e'
        echo "[ -x \"\$(dirname \"\$0\")/$name.local\" ] && \"\$(dirname \"\$0\")/$name.local\" \"\$@\""
        echo "$body"
    } > "$target"
    chmod +x "$target"
    echo "Installed $name hook."
}

install_hook pre-commit "python3 \"$check\" staged"
install_hook commit-msg "python3 \"$check\" message \"\$1\""
install_hook pre-push 'z=0000000000000000000000000000000000000000
while read -r lref lsha rref rsha; do
    [ "$lsha" = "$z" ] && continue
    if [ "$rsha" = "$z" ]; then range="$(git merge-base "$lsha" origin/HEAD 2>/dev/null || git rev-list --max-parents=0 "$lsha" | tail -1)..$lsha"; else range="$rsha..$lsha"; fi
    python3 "'"$check"'" range "$range"
done'

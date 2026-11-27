# SPDX-FileCopyrightText: : 2023- The PyPSA-Eur Authors
#
# SPDX-License-Identifier: MIT

"""
Workshop hook, run after the model is built and before it is solved.

Both changes keep the optimisation problem the same; they only cut the memory
the solve needs, so it fits on laptops with 8 GB:

1. PyPSA writes the limits of every fixed-capacity component as two
   one-variable constraints per snapshot (``<Component>-fix-<attr>-lower/upper``).
   Here they become bounds on the variable itself, which removes about half of
   the rows the solver has to load. The shadow prices of these limits
   (``mu_lower``/``mu_upper`` of fixed components) are no longer reported.
2. The LP file handed to the solver goes next to the results instead of /tmp,
   which on many Linux systems lives in RAM.
"""

from pathlib import Path

import numpy as np
import xarray as xr


def fix_constraints_to_bounds(m):
    """Turn single-variable '-fix-' constraints into variable bounds; return rows moved."""
    moved = 0
    for name in [k for k in m.constraints if "-fix-" in k]:
        comp, rest = name.split("-fix-", 1)
        attr, side = rest.rsplit("-", 1)
        vname = f"{comp}-{attr}"
        d = m.constraints[name].data
        if vname not in m.variables or d.sizes.get("_term", 1) != 1:
            continue  # e.g. lines with losses (p - loss): keep as constraints
        if not bool(((d.coeffs == 1) | (d.labels == -1)).all()):
            continue
        var = m.variables[vname]
        rhs = d.rhs.where(d.labels != -1)  # NaN where the constraint is masked
        if side == "lower":
            cur = var.lower
            rhs = rhs.reindex_like(cur)
            var.lower = xr.where(rhs.isnull(), cur, np.maximum(cur, rhs)).transpose(
                *cur.dims
            )
        else:
            cur = var.upper
            rhs = rhs.reindex_like(cur)
            var.upper = xr.where(rhs.isnull(), cur, np.minimum(cur, rhs)).transpose(
                *cur.dims
            )
        moved += int((d.labels != -1).sum())
        m.remove_constraints(name)
    return moved


def custom_extra_functionality(n, snapshots, snakemake):
    """Keep the memory steps below; add your own constraints after them."""
    m = n.model
    rows = m.constraints.ncons
    moved = fix_constraints_to_bounds(m)
    print(f"Moved {moved:,} of {rows:,} rows to variable bounds", flush=True)

    if snakemake is not None:
        solver_dir = Path(snakemake.output[0]).parent.parent / "solver_tmp"
        solver_dir.mkdir(parents=True, exist_ok=True)
        m._solver_dir = solver_dir

    # Your own constraints go here, e.g. m.add_constraints(...).

    # Role 3: trade limits for the run with neighbours (config block `role3:`,
    # see data/role3_constraints.py). Does nothing without that block.
    role3 = (snakemake.config.get("role3") if snakemake is not None else None) or {}
    if role3:
        from role3_constraints import add_role3_constraints

        add_role3_constraints(n, role3, snakemake.wildcards.get("horizon"))

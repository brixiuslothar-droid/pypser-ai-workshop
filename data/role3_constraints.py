# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""
Role 3: limits on trade between Germany and its neighbours.

Called from ``data/custom_extra_functionality.py`` when the config has a
``role3:`` block (see ``config/config.role3-neighbours.yaml``). Each part has
its own switch, so role 4 can vary them in scenarios.

- ``crossborder.freeze_expansion``: cross-border AC lines and DC links keep
  today's capacity (no expansion between countries).
- ``crossborder.ntc``: the sum of flows over each border of Germany is limited
  to a commercial exchange capacity (NTC) in GW, given as
  ``[export from DE, import into DE]`` per neighbour, times ``scale`` (a number
  or a mapping year -> number). Physical line limits still apply on top.
- ``min_self_generation``: each country generates on average at least
  ``level`` of its own annual demand (logic of PyPSA-Eur's ``EQ<level>c``).
  Note: its shadow price acts like a production subsidy and lowers nodal
  prices; use system costs rather than prices when it is on.

Changes to this file or to the ``role3`` config are not tracked by Snakemake:
rerun with ``--forcerun solve_network``.
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def _say(msg):
    print(f"role3: {msg}", flush=True)
    logger.info(msg)


def freeze_crossborder_expansion(n):
    m = n.model
    c = n.buses.country
    for comp, var, cap in [("lines", "Line-s_nom", "s_nom"), ("links", "Link-p_nom", "p_nom")]:
        if var not in m.variables:
            continue
        df = getattr(n, comp)
        ext = df[df[f"{cap}_extendable"]]
        if comp == "links":
            ext = ext[ext.carrier == "DC"]
        xb = ext.index[ext.bus0.map(c) != ext.bus1.map(c)]
        if xb.empty:
            continue
        v = m.variables[var]
        dim = v.dims[0]
        upper = v.upper.copy()
        upper.loc[{dim: list(xb)}] = df.loc[xb, cap].values
        v.upper = upper
        _say(f"froze {len(xb)} cross-border {comp} at today's capacity")


def _border_flow(n, a, b):
    """Linear expression: net flow from country a to country b, per snapshot."""
    m = n.model
    c = n.buses.country
    expr = None
    for comp, var in [("lines", "Line-s"), ("links", "Link-p")]:
        df = getattr(n, comp)
        if comp == "links":
            df = df[df.carrier == "DC"]
        c0, c1 = df.bus0.map(c), df.bus1.map(c)
        for sel, sign in [(df.index[(c0 == a) & (c1 == b)], 1), (df.index[(c0 == b) & (c1 == a)], -1)]:
            if sel.empty:
                continue
            v = m.variables[var]
            term = sign * v.sel({v.dims[1]: list(sel)}).sum(v.dims[1])
            expr = term if expr is None else expr + term
    return expr


def _for_year(value, horizon, default=1.0):
    if value is None:
        return default
    if isinstance(value, dict):
        if horizon is None:
            raise ValueError("role3: a per-year value needs the planning horizon")
        v = value.get(int(horizon), value.get(str(horizon)))
        return default if v is None else float(v)
    return float(value)


def add_ntc_limits(n, cfg, horizon=None):
    m = n.model
    scale = _for_year(cfg.get("scale"), horizon)
    home = cfg.get("country", "DE")
    done = []
    for nb, gw in cfg["values"].items():
        if nb not in set(n.buses.country):
            continue
        flow = _border_flow(n, home, nb)
        if flow is None:
            continue
        exp, imp = (gw, gw) if not isinstance(gw, (list, tuple)) else gw
        m.add_constraints(flow <= float(exp) * 1e3 * scale, name=f"role3-ntc-{home}-{nb}-export")
        m.add_constraints(flow >= -float(imp) * 1e3 * scale, name=f"role3-ntc-{home}-{nb}-import")
        done.append(nb)
    _say(f"NTC limits on borders {home}-{','.join(done)}, scale {scale}")


def add_min_self_generation(n, cfg):
    m = n.model
    level = float(cfg["level"])
    sc = 1e-1
    c = n.buses.country
    countries = cfg.get("countries") or sorted(set(n.loads.bus.map(c)))
    w = n.snapshot_weightings.generators
    load = n.loads_t.p_set.mul(w, axis=0).sum().groupby(n.loads.bus.map(c)).sum()
    inflow = (
        n.storage_units_t.inflow.mul(n.snapshot_weightings.stores, axis=0)
        .sum()
        .groupby(n.storage_units.bus.map(c))
        .sum()
        .reindex(load.index, fill_value=0.0)
    )
    p = m["Generator-p"]
    g = n.generators.bus.map(c).rename("country").to_xarray()
    lhs = (p * (w.to_xarray() * sc)).groupby(g).sum().sum("snapshot")
    if not n.storage_units_t.inflow.empty and "StorageUnit-spill" in m.variables:
        sg = n.storage_units.bus.map(c).rename("country").to_xarray()
        spill = m["StorageUnit-spill"] * (-n.snapshot_weightings.stores.to_xarray() * sc)
        lhs = lhs + spill.groupby(sg).sum().sum("snapshot")
    rhs = (sc * (level * load - inflow)).reindex(countries)
    rhs.index.name = "country"
    m.add_constraints(lhs.sel(country=countries) >= rhs.to_xarray(), name="role3-min-self-generation")
    _say(f"min self-generation {level:.0%} for {', '.join(countries)}")


def add_role3_constraints(n, cfg, horizon=None):
    xb = cfg.get("crossborder", {})
    if xb.get("freeze_expansion", False):
        freeze_crossborder_expansion(n)
    if xb.get("ntc", {}).get("enable", False):
        add_ntc_limits(n, xb["ntc"], horizon)
    if cfg.get("min_self_generation", {}).get("enable", False):
        add_min_self_generation(n, cfg["min_self_generation"])

# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""
Add imports from a dedicated Brazilian export site over an HVDC cable.

Brazil is not modelled as a system. It is one bus ``BR0`` with one import
generator ``BR0 Brazil import`` whose hourly price follows the capacity factor
of the export site (``build_brazil_import_profile.py``)::

    price_t = p_max - (p_max - p_min) * CF_t + adder

If ``p_min`` and ``p_max`` are not set, they are derived so that the mean
price equals the levelised cost of the wind/solar mix, computed from the
horizon's cost table (annualised at ``discount_rate.generation``), and
``p_max - p_min = spread * LCOE``.

The cable ``BR0 Brazil HVDC`` is a one-way link from ``BR0`` to the German AC
bus nearest to ``landing_de``. Its cost is ``cable_cost`` per MW and km plus
``converter_cost`` per MW from the cost table; its losses follow
``sector.transmission_efficiency.DC``. All components get an infinite lifetime
so that ``add_brownfield`` does not copy them; they are added afresh in every
horizon from ``build_year`` on.

With ``generation: investment`` (role 3) the price-based import generator is
replaced by one extendable generator per technology in ``mix`` (e.g.
``BR0 Brazil onwind``) with the hourly capacity factor of the export site as
``p_max_pu``; the model optimises their capacity together with the cable.
Investment comes from the horizon's cost table (``COST_TECH``), scaled by
``capex_factor`` and annualised at ``discount_rate.generation``; capacity built
in an earlier horizon is kept as a lower bound. The profile is the CSV of
``build_brazil_import_profile.py`` or, if set, ``profile_file`` (hourly, one
column per technology in ``mix``, values 0-1), e.g. delivered by role 2.

Called from ``compose_network.py`` after the brownfield step.
"""

import logging

import numpy as np
import pandas as pd
import pypsa

from scripts.add_electricity import calculate_annuity

logger = logging.getLogger(__name__)

BUS = "BR0"
GEN = "BR0 Brazil import"
LINK = "BR0 Brazil HVDC"
COLOR = "#D55E00"  # workshop plot style: Brazil cable
# cost-table entry per site technology; PyPSA-Eur's solar generators are costed
# as solar-utility (the "solar" row's investment blends in rooftop)
COST_TECH = {"onwind": "onwind", "solar": "solar-utility"}


def haversine_km(lon0, lat0, lon1, lat1):
    lon0, lat0, lon1, lat1 = map(np.radians, (lon0, lat0, lon1, lat1))
    a = (
        np.sin((lat1 - lat0) / 2) ** 2
        + np.cos(lat0) * np.cos(lat1) * np.sin((lon1 - lon0) / 2) ** 2
    )
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def to_snapshots(hourly: pd.Series, snapshots: pd.DatetimeIndex) -> pd.Series:
    """Average an hourly series over each snapshot's window (snapshot to next)."""
    hourly = hourly.copy()
    hourly.index = pd.DatetimeIndex(hourly.index)
    years = snapshots.year.unique()
    if len(years) != 1 or not (hourly.index.year == years[0]).all():
        # profile from another weather year than the network: align by hour of year
        hourly.index = hourly.index.map(lambda t: t.replace(year=int(years[0])))
    pos = snapshots.searchsorted(hourly.index, side="right") - 1
    valid = pos >= 0
    out = hourly[valid].groupby(pos[valid]).mean()
    out.index = snapshots[out.index]
    return out.reindex(snapshots).interpolate(limit_direction="both")


def annualised(costs: pd.DataFrame, tech: str, rate: float | None) -> float:
    """
    Annual fixed cost (EUR/MW/a or EUR/MW/km/a) of a cost-table entry: annuity
    of the investment plus FOM, as in the cost processing. With ``rate`` empty,
    the cost table's own ``capital_cost`` (its discount rate) is used.
    """
    if rate is None:
        return float(costs.at[tech, "capital_cost"])
    annuity = calculate_annuity(float(costs.at[tech, "lifetime"]), float(rate))
    return float((annuity + costs.at[tech, "FOM"] / 100.0) * costs.at[tech, "investment"])


def mix_lcoe(
    costs: pd.DataFrame,
    cf: pd.DataFrame,
    mix: dict,
    capex_factor: dict | None = None,
    rate: float | None = None,
) -> float:
    """
    LCOE (EUR/MWh) of the export site from cost-table entries, annualised at ``rate``.

    ``capex_factor`` scales investment (and with it FOM, a share of investment)
    per technology, for Brazilian costs relative to the cost table.
    """
    shares = pd.Series(mix, dtype=float)
    shares = shares / shares.sum()
    factor = capex_factor or {}
    tech = {t: COST_TECH.get(t, t) for t in shares.index}
    annual = sum(
        shares[t] * factor.get(t, 1.0) * annualised(costs, tech[t], rate)
        for t in shares.index
    )
    vom = sum(
        shares[t] * cf[t].mean() * costs.at[tech[t], "marginal_cost"]
        for t in shares.index
    )
    energy = 8760.0 * cf["mix"].mean()  # MWh per MW of site capacity
    return (annual + 8760.0 * vom) / energy


def import_price(cf_mix: pd.Series, weights: pd.Series, lcoe: float, cfg: dict):
    pc = cfg["price"]
    p_min, p_max = pc.get("p_min"), pc.get("p_max")
    if (p_min is None) != (p_max is None):
        raise ValueError("brazil_import.price: set both p_min and p_max, or neither")
    if p_min is None:
        delta = pc["spread"] * lcoe
        mean_cf = np.average(cf_mix, weights=weights)
        p_max = lcoe + delta * mean_cf
        p_min = p_max - delta
    price = p_max - (p_max - p_min) * cf_mix + pc.get("adder", 0.0)
    return price.clip(lower=0.0), float(p_min), float(p_max)


def add_brazil_generation(
    n: pypsa.Network,
    cf: pd.DataFrame,
    cfg: dict,
    costs: pd.DataFrame,
    rate: float | None,
    nyears: float,
    horizon: int,
    n_previous: pypsa.Network | None = None,
) -> None:
    """Extendable wind/solar generators at the Brazilian bus (generation: investment)."""
    factor = cfg.get("capex_factor") or {}
    p_max = cfg.get("generation_p_nom_max") or {}
    for tech in cfg["mix"]:
        if tech not in cf.columns:
            raise ValueError(f"brazil_import: profile has no column '{tech}'")
        name = f"{BUS} Brazil {tech}"
        carrier = f"Brazil {tech}"
        if carrier not in n.carriers.index:
            n.add("Carrier", carrier, co2_emissions=0.0, nice_name=carrier, color=COLOR)
        cost_tech = COST_TECH.get(tech, tech)
        capital_cost = (
            factor.get(tech, 1.0) * annualised(costs, cost_tech, rate) * nyears
        )
        p_min = 0.0
        if n_previous is not None and name in n_previous.generators.index:
            p_min = float(n_previous.generators.at[name, "p_nom_opt"])
        n.add(
            "Generator",
            name,
            bus=BUS,
            carrier=carrier,
            p_nom=p_min,
            p_nom_min=p_min,
            p_nom_max=float(p_max.get(tech, np.inf)),
            p_nom_extendable=True,
            p_max_pu=cf[tech].clip(0.0, 1.0),
            capital_cost=capital_cost,
            marginal_cost=float(costs.at[cost_tech, "marginal_cost"]),
            lifetime=np.inf,
            build_year=horizon,
        )
        logger.info(
            f"Brazil {tech}: capital cost {capital_cost:,.0f} EUR/MW per period, "
            f"mean CF {np.average(cf[tech], weights=n.snapshot_weightings.generators):.3f}, "
            f"existing {p_min:,.0f} MW"
        )


def add_brazil_import(
    n: pypsa.Network,
    profile_path: str,
    cfg: dict,
    costs: pd.DataFrame,
    dc_efficiency: dict,
    horizon: int,
    n_previous: pypsa.Network | None = None,
) -> None:
    if horizon < cfg["build_year"]:
        logger.info(f"Brazil import: not built before {cfg['build_year']}")
        return

    hourly = pd.read_csv(profile_path, index_col=0, parse_dates=True)
    cf = hourly.apply(to_snapshots, snapshots=n.snapshots)
    weights = n.snapshot_weightings.generators

    # German landing bus
    ac = n.buses[(n.buses.carrier == "AC") & (n.buses.country == "DE")]
    lon_de, lat_de = cfg["landing_de"]
    lon_br, lat_br = cfg["landing_br"]
    bus_de = haversine_km(ac.x, ac.y, lon_de, lat_de).idxmin()

    length = cfg.get("length_km")
    if not length:
        length = cfg["length_factor"] * float(
            haversine_km(lon_br, lat_br, n.buses.at[bus_de, "x"], n.buses.at[bus_de, "y"])
        )

    eff = dc_efficiency.get("efficiency_static", 1.0) * dc_efficiency.get(
        "efficiency_per_1000km", 1.0
    ) ** (length / 1e3)

    nyears = n.snapshot_weightings.objective.sum() / 8760.0
    rates = cfg.get("discount_rate") or {}
    capital_cost = cfg["cost_factor"] * nyears * (
        annualised(costs, cfg["cable_cost"], rates.get("cable")) * length
        + annualised(costs, cfg["converter_cost"], rates.get("cable"))
    )

    mode = cfg.get("generation", "import")
    if mode not in ("import", "investment"):
        raise ValueError("brazil_import.generation must be 'import' or 'investment'")

    p_nom = float(cfg["p_nom"])
    extendable = bool(cfg["extendable"])
    p_nom_min = p_nom
    if extendable and n_previous is not None and LINK in n_previous.links.index:
        p_nom_min = max(p_nom_min, float(n_previous.links.at[LINK, "p_nom_opt"]))

    for carrier, nice in [("Brazil import", "Brazil import"), ("Brazil HVDC", "Brazil cable")]:
        if carrier not in n.carriers.index:
            n.add("Carrier", carrier, co2_emissions=0.0, nice_name=nice, color=COLOR)

    n.add("Bus", BUS, carrier="AC", x=lon_br, y=lat_br, country="BR")

    if mode == "import":
        lcoe = mix_lcoe(
            costs, hourly, cfg["mix"], cfg.get("capex_factor"), rates.get("generation")
        )
        price, p_min, p_max = import_price(cf["mix"], weights, lcoe, cfg)
        n.add(
            "Generator",
            GEN,
            bus=BUS,
            carrier="Brazil import",
            p_nom=float(cfg["p_nom_max"]) if extendable else p_nom,
            marginal_cost=price,
            lifetime=np.inf,
            build_year=horizon,
        )
    else:
        lcoe = p_min = p_max = float("nan")
        add_brazil_generation(n, cf, cfg, costs, rates.get("generation"), nyears, horizon, n_previous)
    n.add(
        "Link",
        LINK,
        bus0=BUS,
        bus1=bus_de,
        carrier="Brazil HVDC",
        p_nom=p_nom_min,
        p_nom_min=p_nom_min,
        p_nom_max=float(cfg["p_nom_max"]) if extendable else p_nom,
        p_nom_extendable=extendable,
        p_min_pu=0.0,
        efficiency=eff,
        length=length,
        capital_cost=capital_cost,
        lifetime=np.inf,
        build_year=cfg["build_year"],
    )

    n.meta["brazil_import"] = dict(
        bus_de=bus_de,
        length_km=round(float(length), 1),
        efficiency=round(float(eff), 4),
        capital_cost_eur_per_mw_a=round(float(capital_cost), 1),
        lcoe_eur_per_mwh=round(float(lcoe), 2),
        p_min=round(p_min, 2),
        p_max=round(p_max, 2),
        cf_mix_mean=round(float(np.average(cf["mix"], weights=weights)), 4),
    )
    logger.info(f"Brazil import added: {n.meta['brazil_import']}")

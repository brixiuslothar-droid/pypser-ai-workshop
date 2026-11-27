# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""
Hourly capacity factors of the Brazilian export site for the cable import.

Computes onshore wind and solar capacity factors from the ERA5 cutout in
``data-brazil/`` for the land cells of the box ``brazil_import.region``, with
the same turbine and panel models as PyPSA-Eur's European profiles, and their
mix by capacity share (``brazil_import.mix``).

Output: CSV indexed by hour (UTC, weather year of the cutout) with columns
``onwind``, ``solar`` and ``mix`` in per unit.
"""

import logging

import atlite
import pandas as pd
import xarray as xr

from scripts._helpers import configure_logging, set_scenario_config

logger = logging.getLogger(__name__)


def site_profiles(cutout_path, region, turbine, panel, mix, best_share=1.0):
    cutout = atlite.Cutout(cutout_path)
    x0, x1 = sorted(region["x"])
    y0, y1 = sorted(region["y"])
    site = cutout.sel(x=slice(x0, x1), y=slice(y0, y1))
    if site.grid.empty:
        raise ValueError(f"brazil_import.region {region} holds no cutout cells")

    # ERA5 surface height is 0 over the sea: keep land cells only
    land = (site.data["height"] > 1.0).astype(float)
    if land.sum() == 0:
        raise ValueError(f"brazil_import.region {region} holds no land cells")
    if best_share < 1.0:
        wcf = site.wind(turbine=turbine, add_cutout_windspeed=True, capacity_factor=True)
        wcf = wcf.where(land > 0)
        land = (land > 0) & (wcf >= float(wcf.quantile(1 - best_share)))
        land = land.astype(float)
    logger.info(f"Export site: {int(land.sum())} land cells of {land.size}")

    kw = dict(layout=land, per_unit=True, aggregate_time=None)
    wind = site.wind(turbine=turbine, add_cutout_windspeed=True, **kw)
    solar = site.pv(panel=panel, orientation="latitude_optimal", **kw)

    df = pd.DataFrame(
        {
            "onwind": wind.squeeze(drop=True).to_pandas(),
            "solar": solar.squeeze(drop=True).to_pandas(),
        }
    ).clip(0.0, 1.0)
    shares = pd.Series(mix, dtype=float)
    shares = shares / shares.sum()
    df["mix"] = df[shares.index].mul(shares).sum(axis=1)
    df.index.name = "time"
    return df


if __name__ == "__main__":
    if "snakemake" not in globals():
        from scripts._helpers import mock_snakemake

        snakemake = mock_snakemake("build_brazil_import_profile")
    configure_logging(snakemake)
    set_scenario_config(snakemake)

    cfg = snakemake.params.brazil_import
    df = site_profiles(
        snakemake.input.cutout,
        cfg["region"],
        cfg["turbine"],
        cfg["panel"],
        cfg["mix"],
        cfg.get("best_share", 1.0),
    )
    logger.info(f"Mean capacity factors:\n{df.mean().round(3)}")
    df.to_csv(snakemake.output[0])

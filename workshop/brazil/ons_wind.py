# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""Measured 2013 wind generation and capacity factors from ONS (role 2 validation)."""

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ONS = Path("data-brazil/raw/ons")


def ons_to_utc(df, year=2013):
    """ONS local time (with DST) -> complete hourly UTC year; from data-brazil/README.md."""
    idx = df.index.tz_localize("America/Sao_Paulo", ambiguous=True, nonexistent="shift_forward")
    df = df.set_axis(idx.tz_convert("UTC").tz_localize(None))
    df = df[~df.index.duplicated()]
    full = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    nxt = df[df.index > full[-1]]
    df = pd.concat([nxt.set_axis(nxt.index - pd.DateOffset(years=1)), df])
    df = df[df.index >= full[0]].reindex(full)
    df = df.interpolate(limit=3, limit_area="inside")
    df = df.fillna(df.shift(168)).fillna(df.shift(-168))
    return df.interpolate(limit_direction="both")


def plant_generation(states=("CE", "RN", "BA")):
    """Hourly generation (MW, UTC) per wind plant, columns = ceg."""
    t = pq.read_table(
        ONS / "GERACAO_USINA-2_2013.parquet",
        columns=["din_instante", "id_estado", "nom_tipousina", "ceg", "val_geracao"],
        filters=[("nom_tipousina", "=", "EOLIELÉTRICA"), ("id_estado", "in", list(states))],
    ).to_pandas()
    t["val_geracao"] = pd.to_numeric(t.val_geracao, errors="coerce")
    t["din_instante"] = pd.to_datetime(t.din_instante)
    state = t.groupby("ceg").id_estado.first()
    wide = t.pivot_table(index="din_instante", columns="ceg", values="val_geracao", aggfunc="sum")
    return ons_to_utc(wide), state


def plant_capacity():
    """Effective capacity (MW) per ceg from the ONS register, all units."""
    reg = pd.read_csv(ONS / "CAPACIDADE_GERACAO.csv", sep=";", dtype=str)
    reg = reg[reg.nom_tipousina.str.strip() == "EOLIELÉTRICA"]
    reg["val_potenciaefetiva"] = pd.to_numeric(reg.val_potenciaefetiva, errors="coerce")
    reg["ceg"] = reg.ceg.str.strip()
    return reg.groupby("ceg").val_potenciaefetiva.sum(), reg.groupby("ceg").nom_usina.first().str.strip()


def measured_wind():
    """Per-plant table and per-state hourly capacity factor of plants running all year."""
    gen, state = plant_generation()
    cap, name = plant_capacity()
    monthly = gen.resample("MS").mean()
    full_year = (monthly > 0.02 * gen.max()).all()          # generated in every month
    tab = pd.DataFrame({
        "state": state, "name": name.reindex(gen.columns), "capacity_mw": cap.reindex(gen.columns),
        "max_gen_mw": gen.max(), "mean_gen_mw": gen.mean(), "full_year": full_year,
    })
    tab["cf"] = tab.mean_gen_mw / tab.capacity_mw
    # capacity check: a plant cannot generate much above its capacity
    tab["capacity_ok"] = tab.max_gen_mw <= 1.1 * tab.capacity_mw
    ok = tab.index[tab.full_year & tab.capacity_ok & tab.capacity_mw.gt(0)]
    cf_state = {
        s: gen[ok[tab.loc[ok, "state"] == s]].sum(axis=1)
        / tab.loc[ok[tab.loc[ok, "state"] == s], "capacity_mw"].sum()
        for s in tab.loc[ok, "state"].unique()
    }
    return tab, pd.DataFrame(cf_state)


if __name__ == "__main__":
    tab, cf = measured_wind()
    pd.set_option("display.width", 200)
    print(tab.sort_values(["state", "cf"]).round(3).to_string())
    print("\nfleet CF of plants running all year with consistent capacity:")
    print(cf.mean().round(3))

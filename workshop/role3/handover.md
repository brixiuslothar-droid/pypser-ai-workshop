<!--
SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>

SPDX-License-Identifier: CC-BY-4.0
-->

# Rolle 3 → Gruppe: was ihr wissen müsst

## Neue Referenz statt Baseline: `de10-nb9-ref`

```bash
pixi run snakemake results/de10-nb9-ref/networks/solved_2050.nc -c4 \
  --configfile config/config.workshop.yaml config/config.role3-neighbours.yaml \
               config/config.role3-reference.yaml \
  --allowed-rules process_cost_data compose_network solve_network
```

- Deutschland (10 Knoten) mit AT, BE, CH, CZ, DK (2), FR, LU, NL, PL (je 1 Knoten).
- Die Zeitauflösung beträgt **4 h**, nicht 2 h. Das ist nötig wegen des Speichers.
- Handel mit den Nachbarn ist auf die heutigen NTC begrenzt (TYNDP 2024), Kuppelleitungen werden nicht ausgebaut.
- 2050: keine CO₂-Grenze, stattdessen ein CO₂-Preis.
- Ein Solve braucht bis etwa 7 GB, ein voller Lauf etwa 25 min. **Nur ein Solve gleichzeitig pro Workspace.**
- Eigene Varianten: als zusätzliche Config **nach** diesen drei Dateien laden und einen eigenen `run.name` setzen.
  - Damit die Eingangsdaten nicht neu gebaut werden müssen, `resources/de10-nb9-ref` kopieren (siehe Kopf von `config/config.role3-co2-750.yaml`).

## Rolle 1 und 2 (Kabel, Brasilien)

- **Die Knotennamen sind neu.** Die deutschen Knoten in `de10-nb9*` haben andere Nummern als in der Baseline:

  | Region | Baseline | `de10-nb9*` |
  |---|---|---|
  | Weser-Ems / Nordsee West (Offshore-Anlandung) | DE0 7 | **DE0 5** |
  | Schleswig-Holstein / Hamburg | DE0 8 | **DE0 9** |
  | Mecklenburg-Vorpommern / Brandenburg | DE0 0 | **DE0 3** |
  | Rhein-Ruhr | DE0 2 | DE0 2 |
  | Baden-Württemberg | DE0 1 | **DE0 0** |
  | Bayern | DE0 4 | DE0 4 |

  Bus-Namen im Code bitte nicht fest eintragen, sondern aus der Config lesen.
- Die Grenzflüsse zählt `data/role3_constraints.py` nur zwischen Ländern (`bus.country`). Wenn ihr Brasilien hinzufügt, gebt den Bussen `country = "BR"`. Für BR–DE gibt es dann **kein** NTC-Limit, nur die Kabelkapazität.
- Mehr Komponenten brauchen mehr Speicher. Messt nach eurer Änderung einmal 2045, das ist das größte Jahr mit etwa 6,9 GB.

## Rolle 4 (Studiendesign)

Diese Stellschrauben sind per Config erreichbar (Block `role3:` in `config/config.role3-reference.yaml`):

| Schalter | Standard | Wirkung |
|---|---|---|
| `role3.crossborder.freeze_expansion` | `true` | Kuppelleitungen auf dem heutigen Stand |
| `role3.crossborder.ntc.enable` | `true` | Grenzflüsse DE ≤ NTC |
| `role3.crossborder.ntc.scale` | `1.0` | Faktor auf die NTC, auch je Jahr möglich, z. B. `{2035: 1.3, 2040: 1.5}` (geplanter Netzausbau) |
| `role3.min_self_generation.enable` / `level` | `false` / `0.9` | Mindesteigenerzeugung je Land. **Verzerrt die Preise nach unten**, nur für Mengen- und Kostenvergleiche nutzen |
| `co2_budget.upper.2050` | `null` | Keine Grenze 2050 (bis 2045 gemeinsame Grenze aller zehn Länder) |
| `costs.emission_prices.co2.2050` | `2600` | Gruppenentscheidung, aber **ohne Quelle**. Literatur 250–1.250 €/t. Vorschlag: 750 €/t (IPCC AR6) zentral, siehe `config/config.role3-co2-750.yaml` |

- Nach Änderungen unter `role3:` `--forcerun solve_network` anhängen, weil Snakemake diesen Block nicht sieht.
- Bei aktiver Mindesteigenerzeugung (`min_self_generation`) das Kabel über Systemkosten bewerten (Zielfunktion mit und ohne Kabel), nicht über Preise.

Details, Zahlen und Quellen: `workshop/role3/neighbours.md`, `workshop/role3/baseline-check.md`.

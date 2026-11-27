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
- Ein Solve braucht bis etwa 7 GB (gemessen max. 6,7 GB in 2045), ein voller Lauf etwa 30 min. **Nur ein Solve gleichzeitig pro Workspace.**
- **Gelöst für alle sechs Jahre.** Nettoimport DE 13–16 % der Nachfrage ab 2030, Preis DE 79–112 €/MWh. Zahlen: `neighbours.md`.
- Ein Hinweis zu `scripts/add_brazil_import.py` (Commit `bad8500`): Der Code verbindet das Kabel mit dem DE-Bus, der `landing_de` am nächsten liegt, also nach Koordinaten. Das funktioniert auch mit den neuen Knotennummern. **Aber:** mit den Koordinaten von Wilhelmshaven ist DE0 5 nur 0,5 km näher als DE0 9 (Schleswig-Holstein). Eine kleine Änderung kippt die Wahl. `landing_de` deshalb ein Stück im Inneren der gewünschten Region setzen (Conneforde: 28 km Abstand), nicht auf die Grenze.
- Eigene Varianten: als zusätzliche Config **nach** diesen drei Dateien laden und einen eigenen `run.name` setzen.
  - Damit die Eingangsdaten nicht neu gebaut werden müssen, `resources/de10-nb9-ref` kopieren (siehe Kopf von `config/config.role3-co2-750.yaml`).

## Referenz nach `decisions.md` E3 (`de10-ref`): gerechnet, alle sechs Jahre optimal

`de10-nb9-ref` bleibt, wie es gelöst wurde (nur NTC-Grenzen, 2050 nur CO₂-Preis). E3 verlangt aber zusätzlich:

| E3 | `de10-nb9-ref` | `de10-ref` (neu) |
|---|---|---|
| Nettoimport DE pro Jahr ≤ heutiges Niveau (ca. 25 TWh/a) | nicht begrenzt, 90–112 TWh/a ab 2030 | `role3.net_import_limit.twh: 25` |
| Weiche CO₂-Grenze 2050 wie 2045 (0,05) und CO₂-Preis 2050 | keine Grenze, Preis 2.600 €/t | `co2_budget.upper.2050: 0.05`, Preis **750 €/t** (E3 geändert, O8 erledigt) |

```bash
mkdir -p resources/de10-ref results/de10-ref/networks
cp -a resources/de10-nb9-ref/. resources/de10-ref/ && rm -f resources/de10-ref/networks/composed_2050.nc
pixi run snakemake results/de10-ref/networks/solved_2050.nc -c4 \
  --configfile config/config.workshop.yaml config/config.role3-neighbours.yaml \
               config/config.role3-reference.yaml config/config.role3-e3.yaml \
  --allowed-rules process_cost_data compose_network solve_network
```

- Neue Config: `config/config.role3-e3.yaml`, neuer Code: `add_net_import_limit` in `data/role3_constraints.py`. Die Grenze zählt Leitungen und DC-Links zwischen DE und den Nachbarn, **nicht** das Brasilien-Kabel (BR-Bus hat `country = "BR"`). Im Spielzeugnetz getestet (Grenze greift, Kabel zählt nicht, Leitungsrichtung egal). Im vollen Modell **gelöst**: unklar, ob 25 TWh in allen Jahren lösbar ist und was es kostet (Lastabwurf ist im Netz zugelassen).
- **Nicht kopieren:** gelöste Netze von `de10-nb9-ref`. Die Grenze ändert jedes Jahr ab 2025. Nur die Eingangsdaten (`resources/`) werden wiederverwendet.
- Kabellauf auf dieser Referenz: `config/config.role3-cable.yaml` plus `config/config.role3-e3-cable.yaml` für den Run-Namen `de10-cable`. Ein Kabellauf auf der NTC-Referenz (`de10-nb9-cable`) ist **explorativ** und nicht der CABLE-Lauf von E4.
- Die 25 TWh: Energy-Charts (Abfrage 27.11.2026, Kreuzflussdaten 2024, Grenzen von DE): Nettoimport insgesamt 28,3 TWh, davon 19,9 TWh aus den neun Modell-Nachbarn (Norwegen und Schweden sind nicht im Modell). 25 TWh liegt in dieser Spanne. Ob ein Jahreswert so gemessen wird, wie E3 ihn meint, entscheidet Rolle 4.

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

## Interconnector Brasilien–Deutschland (`de10-nb9-cable`)

Config `config/config.role3-cable.yaml`, geladen nach den drei Referenz-Configs. Code: `scripts/add_brazil_import.py`, Modus `generation: investment`.

- **Kabel:** `BR0 Brazil HVDC`, Einbahn-Link BR0 → DE-Knoten am nächsten zu `landing_de` (Wilhelmshaven → `DE0 5`).
  - Ausbaubar von 0 bis 20 GW ab 2035 (E1).
  - Kosten aus der Kostentabelle (`HVDC submarine` je MW·km + `HVDC inverter pair`), WACC 10 % (E2).
  - Länge: Großkreis × 1,25 ≈ 9.530 km, bis Rolle 1 eine Route liefert. Verluste gemäß `transmission_efficiency.DC` (≈ 21 %).
- **Erzeugung in Brasilien:** je Technologie ein ausbaubarer Generator (`BR0 Brazil onwind`, `BR0 Brazil solar`) mit dem Standortprofil als `p_max_pu`. Kosten aus der Kostentabelle × `capex_factor`, WACC 10 %. Bereits gebaute Kapazität bleibt als Untergrenze in späteren Jahren.
- **Rolle 2 liefert das Profil:**
  - Format: stündliche CSV mit Index `time` (UTC) und Spalten `onwind`, `solar` (Kapazitätsfaktor 0–1).
  - Pfad in `brazil_import.profile_file` eintragen.
  - Optional: Potenzialgrenzen in `generation_p_nom_max` (MW je Technologie).
  - Ohne eigenes Profil wird es aus dem Brasilien-Cutout für `region` gebaut (Standard: Pecém; Kapazitätsfaktor Wind 0,31, PV 0,19).
- **Erstes Ergebnis 2035 (vor E3-Anpassung): Kabel 0 GW.**
  - Die Annuität des Kabels liegt bei etwa 3,8 Mio. €/MW/a.
  - Selbst bei 100 % Auslastung kostet die Übertragung etwa 555 €/MWh. Mit dem Standortprofil (≈ 27 % Kapazitätsfaktor) sind es etwa 2.000 €/MWh.
  - → E5: Der Lauf `MV` (Kabel auf 0,1 GW erzwungen) misst den Abstand zum Break-even.

## Stand 14:25: E3-Referenz `de10-ref` rechnet

- `de10-ref` (Configs: neighbours + reference + e3) ist gerechnet und setzt E3 um: Nettoimport ≤ 25 TWh/a, CO₂-Grenze 0,05 und 750 €/t in 2050.
- `de10-nb9-ref` und `de10-nb9-cable` (nur 2025–2035) bleiben unverändert als NTC-Variante bestehen.

## Übergabe an Rolle 4: Ergebnisse von `de10-ref`

Ordner `workshop/role3/handoff/<run>/` (im Repo, je Lauf etwa 170 KB, immer dieselben Dateien, erzeugt von `workshop/role3/export_handoff.py`). Beschreibung: `workshop/role3/handoff/README.md`. Enthalten sind `de10-ref` (REF nach E3) und `de10-nb9-ref` (vor E3, für den Effekt der Importgrenze).

- Die gelösten Netze (30 MB je Jahr) liegen **nicht** im Repo, nur in `results/<run>/networks/` dieses Workspaces. `workshop/analysis/evaluate.py` liest Netze, nicht diese CSVs. Rolle 4 braucht daher entweder die Netze in ihrem Workspace oder rechnet `de10-ref` mit der Kette aus `runs.yaml` selbst (etwa 30 min).
- Prüfung: Systemkosten und Strompreis DE aus dem Export stimmen mit `evaluate.py` (Lauf REF) überein; Energiebilanz je Jahr null.
- **2050 mit 750 statt 2.600 €/t:** `de10-ref` 2050 wurde mit der neuen Config neu gelöst. Systemkosten 234,5 Mrd. €/a gegenüber 246,3 Mrd. €/a in `de10-nb9-ref` (2.600 €/t, ohne Cap). Das alte 2050-Netz mit 2.600 €/t liegt als `results/de10-ref-p2600/networks/solved_2050.nc` (nur 2050, nicht im Repo).
- Gegenüber `de10-nb9-ref` ändert die Importgrenze die Systemkosten 2030–2045 um höchstens 0,4 Mrd. €/a (0,2 %) und den DE-Preis um weniger als 2 €/MWh. Der Effekt auf die Kabelbewertung kommt also von den Flüssen, nicht von den Gesamtkosten.
- Offen in `decisions.md`: O9 (Configs für MV, CAPEX50, WACC7, REF-ISL, CABLE-ISL) und O10 (Übertrag des Kabels zwischen den Jahren).

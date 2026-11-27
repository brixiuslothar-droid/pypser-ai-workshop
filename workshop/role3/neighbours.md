<!--
SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>

SPDX-License-Identifier: CC-BY-4.0
-->

# Rolle 3: Deutschland mit Nachbarn (`de10-nb9`)

Config: `config/config.role3-neighbours.yaml`, geladen nach `config/config.workshop.yaml`.

```bash
pixi run snakemake results/de10-nb9/networks/solved_2050.nc -c4 \
  --configfile config/config.workshop.yaml config/config.role3-neighbours.yaml
```

Die Auswertung macht `pixi run python workshop/role3/neighbours_check.py` (CSV-Ausgabe nach
`results/de10-nb9/role3/`).

## Was sich gegenüber der Baseline ändert

| | Baseline `de10-myopic` | `de10-nb9` | Grund |
|---|---|---|---|
| Länder | DE | DE, AT, BE, CH, CZ, DK, FR, LU, NL, PL | Handel statt Insel |
| Knoten | DE 10 | DE 10, DK 2 (Ost/West, getrennte Synchronzonen), die übrigen je 1, insgesamt 20 | Die DE-Knoten liegen fast wie in der Baseline (469 von 470 Ausgangsknoten gleich zugeordnet), **die Nummern unterscheiden sich aber** (s. u.) |
| Zeitauflösung | 2 h | **4 h** | Speicher: bei 2 h wurde 2025, bei 3 h 2030 vom 10-GB-Limit beendet |
| Lastabwurf | – | AC-Knoten, 100.000 €/MWh | 2025 (nur Bestand, kein Zubau) fehlen in DK1 sonst 0,3 GW, das Problem wäre unlösbar. Abgeworfen werden 2025 knapp 1 GWh, ab 2030 nichts |
| CO₂-Grenze | 1990-Emissionen des Stromsektors DE | 1990-Emissionen aller 10 Länder, **gemeinsame Grenze** | Folgt aus `co2_budget.relative`. Länder können untereinander ausgleichen |
| Grenzkuppelleitungen | – | Aus dem OSM-Netz von PyPSA-Eur. Ausbau erlaubt, gemeinsames Limit von +25 % auf das Leitungsvolumen | gleiche Regel wie in der Baseline. Die Werte sind **noch nicht** mit ENTSO-E-NTC abgeglichen |

Alles andere ist unverändert und gilt jetzt für alle zehn Länder: Nachfrage ×1,0–1,5, CO₂-Preis, Lebensdauern, drei Ressourcenklassen.

**Knotennamen:** `DE0 0`–`DE0 9` haben in `de10-nb9*` andere Nummern als in der Baseline. Zuordnung für Rolle 1 in `handover.md`.

## Rechenaufwand (gemessen, Workspace mit 4 CPUs und 10 GB)

| | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
|---|---|---|---|---|---|---|
| Spitzenspeicher Solve (GB) | 4,1 | 6,4 | 6,1 | 6,2 | 6,9 | 6,6 |
| Solverzeit (min) | 1,8 | 3,6 | 3,7 | 3,9 | 4,7 | 4,4 |
| Status | optimal | optimal | optimal | optimal | optimal | optimal |

- Ein voller Lauf 2025–2050 dauert etwa 25 Minuten. Das Neubauen der Eingangsdaten (einmalig) dauerte etwa 15 Minuten.
- **Achtung:** 6,9 GB liegen knapp unter dem Limit. Andere Prozesse im Workspace (Editor, Agenten) brauchen zusammen etwa 2,5 GB. Pro Workspace sollte nur ein Solve gleichzeitig laufen.
- Weitere Komponenten (Brasilien, Kabel) erhöhen den Bedarf. Rolle 1 und 2 sollten nach ihrer Änderung einmal 2045 messen.

Nachbarn ohne Zubau (eingefroren) sparen in 2030 nur 28 % Solverzeit und 3 % Speicher und sind inhaltlich falsch (Kraftwerkspark von 2025 bis 2050). Mögliche Einsparung, falls nötig und nicht umgesetzt: Altanlagen-Jahrgänge in DE zusammenfassen, Nachbarn ohne Ressourcenklassen (geschätzt 15–25 %, nicht gemessen).

## Ergebnisse Deutschland: Baseline vs. Nachbarn

| | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
|---|---|---|---|---|---|---|
| **Preis DE, lastgewichtet (€/MWh)** Baseline → Nachbarn | 96 → 96 | 87 → 71 | 91 → 85 | 93 → 87 | 113 → 100 | 117 → 114 |
| Stunden > 300 €/MWh | 0 → 0 | 0 → 0 | 52 → 40 | 52 → 48 | 2.040 → 468 | 1.498 → 1.116 |
| Stunden < 1 €/MWh | 360 → 0 | 1.980 → 460 | 2.292 → 732 | 3.088 → 992 | 4.486 → 3.304 | 2.882 → 2.308 |
| **Nettoimport DE (TWh)** | 29 | 183 | 221 | 238 | 218 | 286 |
| Anteil Import an Nachfrage DE | 6 % | 33 % | 36 % | 36 % | 31 % | 37 % |
| Max. Import (GW) | 20 | 47 | 50 | 54 | 54 | 63 |
| Export DE brutto (TWh) | 15 | 1 | 0,3 | 0,3 | 1 | 0,7 |
| CO₂ DE (Mt) | 161 → 133 | 64 → 21 | 43 → 20 | 34 → 19 | 17 → 13 | 0 → 0 |
| Schattenpreis CO₂-Grenze (€/t) | 0 → 0 | 0 → 0 | 0 → 0 | 43 → 0 | 488 → 266 | 24.354 → 30.852 |
| Batterie DE (GWh) | 0 → 0 | 20 → 0 | 155 → 48 | 391 → 139 | 607 → 245 | 834 → 329 |
| H₂-Speicher DE (TWh) | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 13 → 0 | 72 → 38 |
| PV DE (GW) | 90 → 90 | 145 → 90 | 197 → 120 | 311 → 183 | 425 → 241 | 499 → 267 |
| Wind an Land DE (GW) | 64 → 64 | 90 → 71 | 79 → 67 | 72 → 66 | 115 → 65 | 141 → 68 |
| OCGT DE (GW) | 6 → 6 | 5 → 5 | 14 → 16 | 23 → 33 | 22 → 32 | 21 → 31 |

Nettoimport nach Nachbarland (TWh, + = Import nach DE):

| | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
|---|---|---|---|---|---|---|
| CH | 36 | 78 | 85 | 97 | 89 | 114 |
| DK | 16 | 101 | 88 | 83 | 68 | 78 |
| AT | −7 | 24 | 31 | 34 | 33 | 41 |
| FR | 15 | 25 | 20 | 18 | 16 | 32 |
| NL | −7 | 2 | 8 | 12 | 13 | 28 |
| PL | −13 | −31 | −11 | −7 | −2 | −10 |
| CZ | −12 | −16 | −4 | −2 | 1 | 0 |

## Bewertung

**Was besser wird (Richtung stimmt):**
- Die Preisspreizung schrumpft deutlich. 2045 gibt es 468 statt 2.040 Stunden über 300 €/MWh und weniger Stunden nahe null.
- Der Bedarf an Speichern in DE sinkt stark (Batterie −60 %, H₂-Speicher 2045 entfällt). Das war das erwartete Symptom der Insellage.
- 2025 passt mit 29 TWh Nettoimport der Größenordnung nach zu den letzten Jahren. Der Wert ist noch nicht belegt, ca. 25 TWh in 2024 laut Energy-Charts.

**Was nicht plausibel ist und den Kabelwert verzerrt:**
1. **Viel zu hohe Importe ab 2030 (33–37 % der Nachfrage).** Deutschland exportiert praktisch nichts mehr und baut kaum noch Wind an Land zu (Bestand 65–71 GW statt 115 GW Ziel 2030). Die Ursachen:
   - **Zubau im Ausland ist billiger.** In DK (Wind), CH/AT (PV mit Nachführung, 30–46 GW in AT/CH 2030) und FR (Kernkraft-Bestand, Wind) sind die Kapazitätsfaktoren besser. Das Modell kennt keine Ausbaugrenzen, keine Akzeptanzgrenzen und keine nationalen Ziele. Der PV-Zubau in CH und AT ist unrealistisch.
   - **Die Kuppelleitungen werden ausgebaut,** v. a. DE–DK von 10 auf 24 GW und DE–CH von 14 auf 20 GW. Das ist billig, weil das +25 %-Limit fürs Leitungsvolumen für alle 10 Länder gemeinsam gilt.
   - **Gemeinsame CO₂-Grenze:** Die Nachbarn tragen die Dekarbonisierung mit.
2. **2050 bleibt extrem:** Der Schattenpreis steigt sogar auf ~31.000 €/t, weil die Nullgrenze jetzt für alle zehn Länder gilt. Der geplante Umstieg auf einen CO₂-Preis 2050 bleibt damit nötig.
3. Die Preisunterschiede innerhalb DE wachsen leicht (2045: 81–100 €/MWh). Der Norden ist billiger, weil dort Importe aus DK ankommen.

**Bedeutung für das Kabel:** Mit dieser Variante würde das Kabel vermutlich **unterbewertet**, weil billige Importe aus den Nachbarländern die Knappheit in DE überdecken. Die Baseline überbewertet es. Die Wahrheit liegt dazwischen. Bevor wir `de10-nb9` zur Referenz machen, sollten die Importe begrenzt werden (siehe nächste Schritte).

## Sensitivitäten und Referenz

- Sensitivität 2030, Kuppelleitungen auf heutigem Stand eingefroren: Nettoimport 146 statt 183 TWh, Preis DE 72 €/MWh. Die Importe kommen also **nur zu etwa 20 % aus dem Leitungsausbau**. Der Hauptgrund ist der billige Zubau im Ausland.
- Sensitivität 2030 mit Mindesteigenerzeugung je Land, 90 % der eigenen Nachfrage im Jahresmittel (Logik wie PyPSA-Eur `EQ0.9c`, Skript-Test außerhalb des Workflows):
  - DE erzeugt jetzt 502 statt 389 TWh. Der Nettoimport sinkt auf rund 58 TWh (10 %).
  - Die Laufzeit bleibt gleich (197 s).
  - **Allerdings fällt der Strompreis in DE auf 57 €/MWh.** Der Schattenpreis der Nebenbedingung wirkt wie eine Erzeugungsprämie und drückt den Knotenpreis. Für eine Bewertung des Kabels über Preise (Rolle 4) ist das eine Verzerrung. Kosten- und Mengenvergleiche (Systemkosten mit/ohne Kabel) sind davon nicht betroffen.
  - Den Effekt habe ich nur in einem Lauf gesehen. Die Erklärung über die Erzeugungsprämie ist meine Deutung, ich habe sie nicht im Detail nachgerechnet.
- **Referenz umgesetzt** – Run `de10-nb9-ref`, Config `config/config.role3-reference.yaml` (nach den beiden anderen Configs laden), Code `data/role3_constraints.py` (wird aus `data/custom_extra_functionality.py` aufgerufen, nur wenn der Config-Block `role3:` existiert; Baseline unberührt):
  - Kuppelleitungen ohne Ausbau (`role3.crossborder.freeze_expansion`).
  - Summe der Flüsse je deutscher Grenze ≤ NTC (`role3.crossborder.ntc`), Werte aus ENTSO-E/ENTSOG TYNDP 2024 Scenarios, *Electricity and Hydrogen Reference Grid & Investment Candidates* (2023-11-03), Blatt „1. Elec Ref Grid“, CC BY 4.0. GW Export/Import: AT 7,5/7,5 · BE 1,0/1,0 · CH 4,4/4,2 · CZ 2,5/2,6 · DK 4,1/4,1 (DKE1+DKW1) · FR 4,8/4,8 · LU 2,4/2,4 · NL 5,0/5,0 · PL 2,0/3,0. Faktor `scale` (Zahl oder je Jahr) für Szenarien von Rolle 4.
  - Mindesteigenerzeugung als Schalter vorhanden, **aus** (Preisverzerrung, s. o.).
  - 2050: CO₂-Grenze aus, CO₂-Preis 2.600 €/t. Bis 2045 bleibt die gemeinsame Grenze aller zehn Länder.
  - Änderungen unter `role3:` sieht Snakemake nicht: `--forcerun solve_network`.
- Quellen zum CO₂-Preis 2050 gesucht. **Keine Quelle stützt 2.600 €/t.** Das ist etwa doppelt so hoch wie der höchste gefundene Wert und wirkt fast wie die Nullgrenze. Gefundene Werte für 2050:
  - IEA NZE, fortgeschrittene Volkswirtschaften: 250 USD₂₀₂₂/t (*Global Energy and Climate Model Documentation 2023*, Tab. 2.4)
  - IPCC AR6 WGIII Kap. 3, Pfade 1,5 °C (C1): Median 630 USD₂₀₁₅/t (IQR 430–990), etwa 750 €₂₀₂₅/t (eigene Umrechnung)
  - UBA Methodenkonvention 4.0, Klimakosten: 485 €₂₀₂₅/t (1 % Zeitpräferenz) bzw. 1.240 €₂₀₂₅/t (0 %)
  - DAC inkl. Speicherung als Obergrenze der Vermeidungskosten: etwa 230–835 USD/t (Sievert et al., *Joule* 2024)

  → Sensitivität mit 750 €/t vorbereitet: `config/config.role3-co2-750.yaml`. Es wird nur 2050 neu gerechnet. **Vorschlag an Rolle 4:** 750 €/t als zentralen Wert, 250 und 1.250 €/t als Bandbreite.

### Referenz `de10-nb9-ref`: erste Ergebnisse

| | 2025 | 2030 |
|---|---|---|
| Preis DE (€/MWh), freier Handel → NTC | 96 → 96 | 71 → 79 |
| Nettoimport DE (TWh) | 29 → 18 | 183 → 90 |
| Max. Import (GW) | 20 → 15 | 47 → 30 |
| Wind an Land DE (GW) | 64 → 64 | 71 → 82 |
| Spitzenspeicher (GB) / Solverzeit (s) | 4,2 / 100 | 6,1 / 203 |

2030 entspricht der Nettoimport 16 % der Nachfrage. Die Grenze AT ist am stärksten belastet, die NTC-Summe der Importe liegt bei 34,6 GW.

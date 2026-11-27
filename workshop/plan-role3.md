<!--
SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>

SPDX-License-Identifier: CC-BY-4.0
-->

# Plan Rolle 3: PyPSA-Eur Setup

Ziel: Das deutsche System soll gut genug sein, um den Wert des Kabels zu beurteilen. Wir
ändern nur, was den Kabelwert am stärksten beeinflusst: den fehlenden Handel und die
CO₂-Grenze 2050.

## Entscheidungen

| Thema | Entscheidung | Offen / zu klären |
|---|---|---|
| Import/Export | 9 direkte Nachbarn (FR, BE, NL, LU, DK, PL, CZ, AT, CH) mit je 1 Knoten, DE bleibt bei 10 Knoten | Speicher und Laufzeit messen; Notfallplan: DE auf 6–8 Knoten oder 3 h |
| 2050 | **Umgesetzt** in `config/config.role3-reference.yaml`: CO₂-Grenze 2050 aus (`co2_budget.upper.2050: null`), CO₂-Preis 2050 = 2.600 €/t (Preis 2045 × 10) | Quelle für den Faktor finden; Rolle 4 entscheidet, ob 2050 in der Studie bleibt |
| Handelsgrenzen | **Umgesetzt** in `config/config.role3-reference.yaml` (Block `role3:`), Code in `data/role3_constraints.py`: Kuppelleitungen ohne Ausbau, NTC je Grenze aus TYNDP 2024 Reference Grid, Faktor `scale` je Jahr; Mindesteigenerzeugung als Schalter (aus) | Ob `scale` > 1 für spätere Jahre (geplanter Netzausbau) – Rolle 4 |
| Vertrauliche Wirkungsgrade | Werden nicht verwendet, nur geschützt (Skill, `.gitignore`, Git-Hooks) | – |
| Code-Zusammenarbeit | Ein gemeinsamer Branch für Rollen 1–3 im Gruppen-Repo <https://github.com/brixiuslothar-droid/pypser-ai-workshop> (öffentlich; lokal als Remote `group`, `origin` bleibt die Workshop-Baseline) | Kurze Absprache, wer welchen Teil von `compose_network.py` ändert; oft pullen |
| Anschlussknoten | Entscheidet Rolle 1 | Rolle 3 liefert Kennzahlen je Knoten (Preis, Netzauslastung) |

## Ablauf

1. **Baseline verstehen und prüfen** (ohne Solve)
   - Die sechs gelösten Netze auswerten: Erzeugungsmix, Preise, Speicher, CO₂, Engpässe.
   - Die Werte gegen öffentliche Zahlen prüfen (z. B. 2025 gegen AGEB/Energy-Charts).
   - Auffälligkeiten notieren, z. B. dass Braunkohle hinter Steinkohle liegt (Brennstoffpreis).
   - Ergebnis: kurze Plausibilitätstabelle pro Jahr und Kennzahlen pro Knoten für Rolle 1.
2. **Nachbarn einbauen**
   - Eigene Config `config/config.role3-neighbours.yaml` anlegen: `countries` erweitern, Clustering so einstellen, dass DE 10 Knoten und jeder Nachbar 1 Knoten bekommt, eigener `run.name`.
   - Die Eingangsdaten neu bauen (Rebuild, ca. 7 min).
   - **Test-Solve nur für 2030**, dabei Spitzenspeicher und Laufzeit messen. Grenze: unter 8 GB, Ziel unter 7 GB.
3. **2050 per CO₂-Preis**
   - Die Grenze für 2050 in der Config abschalten und den Preis für 2050 setzen.
   - Den Faktor als Parameter anlegen, damit Rolle 4 ihn variieren kann (z. B. 500 / 1.000 / 2.600 €/t).
4. **Neue Referenz rechnen**
   - Ein voller Lauf 2025–2050 „Nachbarn + CO₂-Preis 2050“, danach mit der Baseline vergleichen.
   - Diese Referenz geht an die Gruppe. Kabel-Szenarien laufen auf ihr auf.
5. **Kabel-Läufe begleiten**
   - Mit Rollen 1 und 2 im gemeinsamen Branch integrieren.
   - Jedes Ergebnis auf Plausibilität prüfen und den Mechanismus erklären: Was verdrängt das Kabel, und zu welchen Stunden fließt Strom?

## Solve-Budget (gestuft)

| # | Lauf | Zweck |
|---|---|---|
| 1 | Rebuild + nur 2030 mit Nachbarn | Speicher und Laufzeit messen, Go/No-Go |
| 2 | 2025–2050 mit Nachbarn (Grenze bleibt) | Einzeleffekt des Handels |
| 3 | 2025–2050 mit Nachbarn + CO₂-Preis 2050 | Neue Gruppenreferenz |
| 4+ | Kabel-Szenarien (Rolle 4) | Bewertung des Kabels |

Die Baseline-Ergebnisse liegen schon vor und werden nicht neu gerechnet.

## Leitplanken

- Die Baseline bleibt reproduzierbar: Änderungen nur in eigenen Config-Dateien und mit eigenem `run.name`.
- Immer nur eine Änderung gleichzeitig gegen die Baseline vergleichen (Läufe 2 und 3 trennen die Effekte).
- Für jede geänderte Annahme eine Quelle angeben. Offen: Quelle für den Faktor 10 beim CO₂-Preis und für die Kapazitäten der Grenzkuppelstellen (NTC), falls wir sie ändern.
- Vor jedem Git-Befehl den Skill `confidential-inputs` laden. Jede Person installiert einmal die Hooks mit `bash workshop/hooks/install.sh`.
- Abbildungen im Workshop-Stil anlegen (Skill `plot-style`).

## Risiken

- **Speicher über 8 GB:** DE auf weniger Knoten reduzieren oder die Zeitauflösung auf 3 h setzen. Danach erneut messen.
- **Fehler beim Rebuild der Eingangsdaten für die Nachbarn** (fehlende Rohdaten): früh starten (Schritt 2 vor Schritt 1 anstoßen, weil der Rebuild im Hintergrund läuft).
- **Merge-Konflikte in `compose_network.py`:** kleine Commits, oft pullen, Abschnitte vorab absprechen.
- **Der Preis von 2.600 €/t wirkt wie eine Grenze:** Ergebnisse 2050 als Sensitivität berichten. Belastbare Aussagen zum Kabel vor allem für 2035–2045 treffen.

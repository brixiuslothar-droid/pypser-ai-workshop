<!--
SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>

SPDX-License-Identifier: CC-BY-4.0
-->

# Entscheidungen der Gruppe: Studiendesign und ökonomische Parameter

Verbindlich für alle Rollen der Gruppe. Verantwortlich: Rolle 4. Änderungen nur
in Absprache mit Rolle 4; jede Änderung unten im Änderungsprotokoll eintragen.

Ergebnisse der Studie: [`results/RESULTS.md`](results/RESULTS.md) (siehe E6).

Stand: 2026-11-27

## E1 Studientyp

| | Entscheidung |
|---|---|
| Typ | **Kapazitätsausbau**: das Modell entscheidet, ob und wie viel Kabel gebaut wird (`p_nom_extendable: true`) |
| Foresight | myopic, wie die Baseline |
| Planungsjahre | 2025, 2030, 2035, 2040, 2045, 2050 |
| Kabel baubar ab | **2035** (Vorlaufzeit für Planung und Bau eines Projekts ohne Vorbild; 2025 und 2030: `p_nom_max = 0`) |
| Kabel maximal | **20 GW** (`p_nom_max`); Rolle 1 begründet die technische Machbarkeit (mehrere Bipole) |

Begründung: Die Frage "lohnt sich das Kabel?" beantwortet das Modell direkt.
Wählt es 0 GW, misst E5 den Abstand zum Break-even.

## E2 Harmonisierte ökonomische Parameter

Gelten für Deutschland, Brasilien und das Kabel.

| Parameter | Wert | Hinweis |
|---|---|---|
| Währung | EUR | |
| Preisbasis | **EUR_2020** | BRL/USD zum Jahresmittelkurs des Quelljahres in EUR umrechnen, dann mit dem HICP des Euroraums auf 2020 bringen. Quelle und Jahr jeder Zahl angeben. |
| Kostenprojektion | je Planungsjahr aus `data/costs/archive/v0.15.0/costs_<jahr>.csv` | Brasilianische Kosten folgen denselben Lernkurven wie die europäischen Tabellenwerte derselben Technologie |
| Kostenterme | CAPEX (investment), FOM (%/a), VOM (EUR/MWh), lifetime, discount rate | wie in den Kostentabellen |
| Annuisierung | übernimmt das Modell aus lifetime und discount rate | Rolle 1 und 2 liefern **Investitionskosten**, keine Annuitäten |
| WACC Deutschland | **7 % real** | Baseline (`costs.fill_values.discount rate`) |
| WACC Erzeugung Brasilien | **10 % real** | Länderrisiko; Rolle 2 belegt den Wert (z. B. IRENA, IEA) |
| WACC Kabel und Konverter | **10 % real** | Projektrisiko; Rolle 1 belegt den Wert |
| Lebensdauer Kabel und Konverter | **40 Jahre** | DEA (`HVDC submarine`, `HVDC inverter pair`); Abweichung nur mit Beleg |
| Lebensdauer Erzeugung Brasilien | wie in der Kostentabelle für dieselbe Technologie | |
| Carrier-Name des Kabels | muss "Brazil" enthalten | dann bekommt es im Plot-Style seine Farbe |

Rolle 1 und 2 geben Kosten als **Spanne** an (niedrig, zentral, hoch). Die
Modellläufe verwenden den zentralen Wert.

## E3 Umgang mit 2050

Der Nullcap der Baseline macht 2050 unbrauchbar für die Bewertung: Die Obergrenze
legt rund 24.000 €/t auf den CO₂-Preis. Deshalb gilt in allen Szenarien (außer der
Baseline selbst):

| | Entscheidung |
|---|---|
| CO₂-Obergrenze 2050 | **wie 2045: 0,05** relativ zu 1990 (`co2_budget.upper.2050: 0.05`) |
| CO₂-Preis 2050 | **750 €/t** (`costs.emission_prices.co2.2050: 750`), zentraler Wert nach IPCC AR6; Literatur 250–1.250 €/t. Ersetzt den früheren Wert 2.600 €/t (10 × 2045), der keine Quelle hatte |
| CO₂ 2025–2045 | unverändert wie in der Baseline |
| Handel mit Nachbarländern | **in allen Planungsjahren** zugelassen: AT, BE, CH, CZ, DK, FR, LU, NL, PL (`config/config.role3-neighbours.yaml`) |
| Handelsgrenze je Grenze | heutige NTC (ENTSO-E/ENTSOG TYNDP 2024, Reference Grid), Kuppelleitungen nicht ausbaubar (`config/config.role3-reference.yaml`) |
| Handelsgrenze pro Jahr | **Netto-Import DE ≤ 25 TWh/a** aus den neun Nachbarn, ohne Brasilien-Kabel (`role3.net_import_limit`, `config/config.role3-e3.yaml`) |
| Quelle der 25 TWh | Energy-Charts, grenzüberschreitender Handel DE 2024, abgefragt 2026-11-27: Netto-Import 28,3 TWh insgesamt, 19,9 TWh aus den neun Modell-Nachbarn (NO, SE nicht im Modell). 25 TWh liegt in dieser Spanne und gilt als „heutiges Niveau“ (O2 geschlossen) |

Umsetzung im Modell: Rolle 3 (`workshop/role3/handover.md`). In allen Abbildungen
sind die Ergebnisse für 2050 getrennt gekennzeichnet.

Folgen der Umsetzung, die jede Auswertung kennen muss:

- **Zeitauflösung 4 h** statt 2 h in allen Läufen mit Nachbarn (Speicher). Läufe
  mit Nachbarn sind deshalb nicht direkt mit der Baseline (2 h) vergleichbar;
  `REF − BASE` ändert Handel, Cap 2050 **und** Zeitauflösung und ist nur
  Einordnung, kein Vergleich nach E4.
- Die CO₂-Obergrenze bis 2045 gilt **gemeinsam für alle zehn Länder**
  (`co2_budget.relative`); Deutschland kann mit den Nachbarn ausgleichen.
- **Lastabwurf** ist an AC-Knoten zu 100.000 €/MWh zugelassen. Jeder Lauf weist
  ihn aus; mehr als ~0 ist ein Befund.
- **Knotennamen** in Läufen mit Nachbarn haben andere Nummern als in der
  Baseline. Busse nie fest eintragen.

## E4 Szenarien

Jeder Vergleich ändert genau eine Sache. Kein Lauf überschreibt einen anderen.

**Umsetzung (geändert 2026-11-27):** Jeder Lauf ist eine Kette von Config-Dateien,
die letzte setzt einen eigenen `run.name`. Die Eingangsdaten werden von
`resources/de10-nb9-ref` kopiert (etwa 0,9 GB je Lauf), gelöste Netze nie.
`scenarios.yaml` mit `run.shared_resources` fällt weg: Rolle 3 hat gezeigt, dass
ein neuer Run-Name damit an fehlenden Kosten-Dateien scheitert. Die Ketten
stehen in `workshop/analysis/runs.yaml`; dort ist auch festgehalten, welche
Configs Rolle 3 schon geliefert hat und welche fehlen.

| # | Lauf | Abgeleitet von | Einzige Änderung | Zweck |
|---|---|---|---|---|
| 1 | `REF` | Baseline | Handel (E3) und weicher Cap 2050 (E3), kein Kabel | Vergleichsfall |
| 2 | `CABLE` | REF | Kabel ausbaubar (E1), WACC nach E2 | Hauptlauf |
| 3 | `MV` | CABLE | Kabel auf 0,1 GW gezwungen (`p_nom_min = p_nom_max = 0.1 GW`, ab 2035) | Marginalwert des Kabels |
| 4 | `CAPEX50` | CABLE | Investitionskosten des Kabels 50 % | Bestätigung des Break-even |
| 5 | `WACC7` | CABLE | WACC Brasilien und Kabel 7 % | Einfluss der Finanzierung |
| 6 | `REF-ISL` | REF | ohne Handel | Vergleichsfall Insel |
| 7 | `CABLE-ISL` | CABLE | ohne Handel | Einfluss des fehlenden Handels auf den Kabelwert (gegen 6) |

Vergleichspaare: 2–1 (Wert des Kabels), 3–1 (Marginalwert), 4–1, 5–1, 7–6. Für
2–1 gilt: CABLE ändert gegenüber REF das Kabel und die WACC von BR und Kabel
zusammen, beide gehören zur Kabeloption.

`REF-ISL` ist nötig, weil die Baseline den harten Nullcap 2050 hat und sich damit
in zwei Dingen von `CABLE-ISL` unterscheiden würde.

Rechenzeit: 7 Läufe × etwa 30 min (gemessen für `de10-nb9-ref`), zusammen
etwa 3,5 h, plus das Kopieren der Eingangsdaten. Nur ein Solve gleichzeitig je
Workspace (O7).

Nicht gerechnet, weil die Zeit nicht reicht: harter Nullcap 2050, Kabelkosten
150 %, andere Technologien oder Kosten in Brasilien.

## E5 Break-even

- `CABLE` zeigt, ob und wie viel Kabel gebaut wird.
- Baut das Modell 0 GW, zeigt `MV` den Wert eines zusätzlichen MW Kabel: der
  Schattenpreis von `p_nom_min` (EUR/MW/a) gegen die Annuität des Kabels. Die
  Differenz ist der Abstand zum Break-even. Zur Kontrolle: Preisdifferenz an
  beiden Enden × Fluss.
- `CAPEX50` bestätigt die Schwelle unabhängig davon.
- Kernergebnis: **Break-even-Investitionskosten** des Kabels (EUR/MW bzw. EUR/MW/km)
  gegen die Spanne von Rolle 1.

## E6 Auswertung

Eine Pipeline für alle Läufe; aufgebaut und getestet zuerst auf der Baseline
(`results/de10-myopic/networks/solved_<jahr>.nc`).

Kennzahlen je Lauf und Planungsjahr:

- Systemkosten (Annuitäten + Betriebskosten), Differenz zu REF
- Kabelkapazität, Flüsse auf dem Kabel (Jahresmenge, Auslastung, Dauerlinie)
- Strompreise: Mittelwert, lastgewichtet, Dauerlinie, Spitzen
- Emissionen (Mt) und CO₂-Preis inklusive Schattenpreis der Obergrenze
- Handel: Netto-Import, Import und Export (TWh/a)
- Erzeugungsmix und Kapazitäten nach Technologiegruppe

**Gewinner und Verlierer**, Differenz CABLE − REF in Mrd. EUR/a:

| Gruppe | Größe |
|---|---|
| Verbraucher DE | Δ (Last × Knotenpreis) |
| Erzeuger DE, je Technologiegruppe | Δ (Markterlöse − Kosten) |
| Kabelbetreiber | Engpasserlöse (Preisdifferenz × Fluss) − Annuität − FOM |
| Erzeuger BR | Erlöse − Kosten |
| Staat | Δ CO₂-Erlöse |

Abbildungen im Workshop-Stil (`workshop/plotstyle`, siehe
`.claude/skills/plot-style/SKILL.md`). Das Kabel hat die Farbe "Brazil cable",
der Lauf ohne Kabel neutrales Grau.

### Umsetzung

| Datei | Inhalt |
|---|---|
| `workshop/analysis/runs.yaml` | Läufe (Kürzel, Run-Name, Configs, Ausgangslauf) und Vergleichspaare nach E4 |
| `workshop/analysis/evaluate.py` | die Pipeline: liest alle gelösten Netze, schreibt alles unter `workshop/results/` |
| `workshop/results/RESULTS.md` | **der Ergebnisbericht**, generiert: Status, Befunde, Auffälligkeiten, Vergleiche, Tabellen und Abbildungen je Lauf, Definitionen |
| `workshop/results/notes.md` | Befunde und Deutung, von Hand gepflegt, in Abschnitt 2 des Berichts eingebunden |
| `workshop/results/metrics.csv`, `comparisons.csv`, `status.csv` | Kennzahlen, Differenzen, Solverstatus und Speicher |
| `workshop/results/figures/` | Abbildungen als PNG und PDF |
| `workshop/presentation/` | Abschlusspräsentation: Gliederung `deck.yaml`, Register der Daten, Annahmen und Entscheidungen `register.yaml`, Builder; Skill `.claude/skills/presentation/SKILL.md` |

Aufruf: `pixi run python workshop/analysis/evaluate.py`. Ablauf und Regeln:
Skill `.claude/skills/results-pipeline/SKILL.md`. Die Läufe selbst steuert der
Skill `.claude/skills/scenario-runs/SKILL.md`; wie ein einzelner Lauf gerechnet
wird, steht im Skill `run-model` von Rolle 3.

Festlegungen der Auswertung:

- Deutschland = alle AC-Knoten mit `country == DE`.
- Systemkosten = Annuitäten aller aktiven Anlagen (inkl. Bestand) + Betriebskosten.
- Akteure: Erlöse − Kapitalkosten − Betriebskosten. CO₂-Zahlungen (Preis und
  Schattenpreis der Obergrenze) gehen an den Staat. Summe aller Akteure =
  −(Systemkosten − CO₂-Preis-Zahlungen); die Pipeline prüft das.
- Jahre, in denen die CO₂-Obergrenze mehr als 1.000 EUR/t zusätzlich kostet,
  werden als cap-getrieben gekennzeichnet (E3).

## Aufträge an die anderen Rollen

| Rolle | Braucht von Rolle 4 | Liefert an Rolle 4 |
|---|---|---|
| 1 Kabel | E1, E2 | Investitionskosten Kabel und Konverter als Spanne (EUR_2020), Länge, Verluste, Begründung für WACC 10 % und für bis zu 20 GW |
| 2 Brasilien | E2 | CAPEX, FOM und VOM je Technologie und Planungsjahr (EUR_2020), Profile, Potenziale, Begründung für WACC 10 % |
| 3 PyPSA-Eur | E1, E3, E4 | Umsetzung über Config: Nachbarländer mit Grenze für den Netto-Import pro Jahr, weicher Cap 2050, Kabel baubar ab 2035 mit `p_nom_min`/`p_nom_max`/Kostenfaktor, WACC je Carrier; `scenarios.yaml` mit `shared_resources`; Speicher und Laufzeit je Lauf |

## E7 Vertraulichkeit (NDA)

Gilt für Rolle 4 und für jeden, der mit Rolle 4 an Ergebnissen arbeitet,
Menschen wie KI-Agenten.

**Regel:** Jeder einzelne Term des Term Sheets
(`workshop/inputs/financing_term_sheet.md`) fällt unter das NDA. Das gilt vor
allem für

- den **Offtake-Preis** und
- die **Garantiebedingungen**

des Deals, den der Deal-Code im Term Sheet bezeichnet.

| Erlaubt | Nicht erlaubt |
|---|---|
| Das Term Sheet lokal zur Laufzeit lesen, zur **Validierung** öffentlicher Annahmen (wie `workshop/cba/validate_against_nda.py`) | Werte aus dem Term Sheet als **Modellinput** verwenden |
| Grobe Bänder ausgeben (z. B. "NDA 0.8–1.25x public") | Exakte Werte, exakte Verhältnisse, Differenzen oder andere Größen, aus denen sich ein Wert zurückrechnen lässt |
| Sensitivitätsspannen aus den Bändern ableiten | Werte, Deal-Code oder Garantiebedingungen in Code, Config, Kommentare, Commits, Dateinamen, Logs, Abbildungen, Folien oder diese Datei schreiben |
| | Inhalte an externe Dienste oder Chats außerhalb des Workspaces geben |

- `workshop/inputs/` steht in `.git/info/exclude` und wird nie committet oder
  gepusht.
- Ergebnisse, die das Term Sheet benutzt haben, werden vor dem Teilen geprüft:
  Enthält eine Datei einen vertraulichen Wert, wird sie nicht geteilt.
- In Präsentation und Bericht stützt sich jede Zahl auf öffentliche Quellen
  (E2). Das NDA darf höchstens qualitativ erwähnt werden ("öffentliche Annahmen
  gegen vertrauliche Projektdaten plausibilisiert").

## E8 Review

**Rolle 5 (Review)** prüft die Arbeit der Rollen 1–4 vor der Präsentation gegen
die verbindlichen Entscheidungen E1–E7. Rolle 5 baut selbst kein Ergebnis: sie
prüft, berichtet und übergibt die Behebung an die jeweilige Rolle. Dadurch hat
sie keinen Interessenkonflikt und reviewt die Auswertung von Rolle 4 wie jeden
anderen Beitrag. Ihre Rolle steht in
[`roles/5-review.md`](roles/5-review.md).

Drei Prüfungen, jede mit eigener Checkliste in
[`review/checklists.md`](review/checklists.md):

| # | Prüfung | Gegenstand | Regeln |
|---|---|---|---|
| R1 | **Workflow** | was Rollen 1–3 am Modell und am Lauf geändert haben | E1, E4 |
| R2 | **Auswertung** | die Ergebnisse-Pipeline von Rolle 4 | E2, E3, E5, E6 |
| R3 | **NDA** | der Umgang mit `workshop/inputs/` | E7 |

Regeln für Rolle 5:

- **Read-only.** Rolle 5 ändert weder Modellcode, Config noch `decisions.md`,
  committet nichts, löscht und überschreibt keine Ergebnisse und startet keinen
  Solve. Sie berichtet, die jeweilige Rolle behebt.
- **Belege statt Meinung.** Jeder Befund nennt Datei und Zeile
  (`pfad:zeile`), den betroffenen Lauf und die verletzte Entscheidung
  (z. B. E4). Wo möglich, rechnet Rolle 5 Stichproben selbst nach.
- **Befundformat**, Schweregrade:

  | Grad | Bedeutung |
  |---|---|
  | Blocker | verletzt eine verbindliche Entscheidung, gefährdet ein Ergebnis oder das NDA; ohne Behebung nicht präsentieren |
  | Major | Ergebnis oder Vergleich ist irreführend oder nicht reproduzierbar |
  | Minor | Form, Beschriftung, Nachvollziehbarkeit |
  | Note | Hinweis, keine Handlung nötig |

- **Bericht** unter `results/review/report-<datum>.md` (nicht committet),
  gegliedert nach R1, R2, R3. Jeder Befund wird einer Rolle zugeordnet, die ihn
  behebt.
- **Rolle 5 im Konfliktfall.** Rolle 5 baut nichts, also gibt es keinen
  Interessenkonflikt. Arbeitet im Ausnahmefall doch jemand aus Rolle 5 an einem
  Stück mit, reviewt es ein anderes Gruppenmitglied.
- **E7 gilt für den Reviewer mit.** `workshop/inputs/` wird nur zur Laufzeit zur
  Validierung gelesen, nur grobe Bänder ausgegeben, und in den Bericht gelangt
  kein vertraulicher Wert, kein Deal-Code und keine Garantiebedingung. Vor dem
  Teilen des Berichts wird er darauf geprüft.

Die Reihenfolge ist R3 (NDA) zuerst, dann R1 (Workflow), dann R2 (Auswertung):
ein NDA-Verstoß wiegt schwerer als jeder Modell- oder Auswertungsfehler.

## Offene Punkte

| # | Frage | Wer | Status |
|---|---|---|---|
| O1 | Lässt sich die Diskontrate je Carrier allein über die Config setzen? | Rolle 3 | erledigt: `brazil_import.discount_rate.{generation,cable}` (10 % in `config.role3-cable.yaml`); Deutschland bleibt bei 7 % aus der Kostentabelle |
| O2 | Genauer Wert des Netto-Imports 2024 mit Quelle | Rolle 3 | erledigt: Energy-Charts 2024, 19,9–28,3 TWh; 25 TWh/a bestätigt (E3) |
| O3 | Ist ein Kabel bis 20 GW technisch machbar, mit wie vielen Bipolen? | Rolle 1 | offen |
| O4 | Passen Handel mit den Nachbarn und 7 Läufe in Speicher und Rechenzeit des Tages? | Rolle 3 | teilweise: mit 4 h passt ein Solve (max. 6,9 GB 2045, ~30 min je Lauf); Speicher mit Kabel und Netto-Import-Grenze noch nicht gemessen; 7 Läufe ≈ 3,5 h |
| O6 | Die vorhandenen Kabel-Configs (`config.brazil-import*.yaml`, Läufe `de10-br-*`) bauen auf der Baseline auf: Insel, harter Nullcap 2050. Sie erfüllen E3 nicht und taugen nur als Test. | Rolle 3 | erledigt: E3-Ketten `de10-ref` (`config.role3-e3.yaml`) und `de10-cable` (`config.role3-e3-cable.yaml`) geliefert, noch nicht gelöst |
| O7 | Alle Rollen teilen sich einen Workspace mit 10 GB Speichergrenze. Ein Solve und eine Auswertung gleichzeitig haben am 2026-11-27 einen Solve (`de10-br-ext` 2045) abgebrochen (OOM). Regel: während eines Solves läuft nichts Speicherintensives; `evaluate.py` prüft das. | alle | Regel gilt |
| O8 | E3-Configs von Rolle 3 setzen 2050 noch 2.600 €/t (`config.role3-reference.yaml`). Nach der Änderung von E3 muss die E3-Kette 750 €/t setzen, bevor `de10-ref` gelöst wird. | Rolle 3 | erledigt: `config.role3-e3.yaml` setzt 750 €/t; `de10-ref` gelöst, alle Jahre optimal, Netto-Import 24,7–24,9 TWh/a |
| O12 | Gelöste Netze liegen nur im Workspace von Rolle 3. Rolle 4 wertet REF aus der Übergabe (`workshop/role3/handoff/`) aus; ohne Netze fehlen Akteure, Abregelung und Brutto-Handel. Für CABLE − REF braucht Rolle 4 entweder beide Netze oder beide Übergaben mit `cable.csv`. | Rolle 3, Rolle 4 | offen |
| O9 | Configs für MV, CAPEX50, WACC7, REF-ISL, CABLE-ISL auf der E3-Kette fehlen. Vorschlag je eine kleine Datei nach `config.role3-e3-cable.yaml`, siehe `workshop/analysis/runs.yaml`. | Rolle 3 | offen |
| O10 | Kabel und brasilianische Anlagen haben unendliche Lebensdauer; `add_brownfield` entfernt sie zwischen den Jahren, die Kapazität wird jedes Jahr neu optimiert (Rolle 3, `integration-status.md`). Die volle Annuität fällt jedes Jahr an, was für den Jahresvergleich konsistent ist, aber kein Bauplan. Beim ersten Kabellauf 2040 prüfen. | Rolle 3, Rolle 4 | offen |
| O11 | Landepunkt DE: Wilhelmshaven liegt nur 0,5 km näher an DE0 5 als an DE0 9; `de10-cable` setzt Conneforde (eindeutig DE0 5). Rolle 1 entscheidet den Standort. | Rolle 1 | offen |
| O5 | Schattenpreis von `p_nom_min` im MV-Lauf verfügbar? `data/custom_extra_functionality.py` macht Grenzen fester Kapazitäten zu Variablengrenzen; das Kabel ist ausbaubar und deshalb nicht betroffen. Prüfen. | Rolle 4 | offen |

## Änderungsprotokoll

| Datum | Änderung | Wer |
|---|---|---|
| 2026-11-27 | Erste Fassung, Entscheidungen E1–E6 | Rolle 4 |
| 2026-11-27 | E7 Vertraulichkeit (NDA) ergänzt | Rolle 4 |
| 2026-11-27 | E8 Review eingeführt: Rolle 5 prüft R1 Workflow, R2 Auswertung, R3 NDA | Rolle 4 |
| 2026-11-27 | Datei von `decisions-role4.md` in `decisions.md` umbenannt; E6 Umsetzung (Pipeline, Ergebnisbericht, Skills) ergänzt; erste Auswertung der Baseline | Rolle 4 |
| 2026-11-27 | Testauswertung `de10-br-import` (BRIMP − BASE); offene Punkte O6, O7 | Rolle 4 |
| 2026-11-27 | Abschlusspräsentation: `workshop/presentation/` (Aufbau, Register, Builder) und Skill `presentation` | Rolle 4 |
| 2026-11-27 | Übergabe Rolle 3 (`workshop/role3/handover.md`) übernommen: E3 CO₂-Preis 2050 auf 750 €/t (IPCC AR6), 25 TWh/a mit Quelle, NTC-Grenzen und Folgen (4 h, gemeinsame Grenze, Lastabwurf); E4 Config-Ketten statt `scenarios.yaml`; O1, O2, O6 erledigt, O8–O11 neu | Rolle 4 |
| 2026-11-27 | Ergebnis-Übergabe Rolle 3 (`workshop/role3/handoff/`, `de10-ref`, `de10-nb9-ref`) in die Pipeline übernommen; O8 erledigt, O12 neu | Rolle 4 |

<!--
SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>

SPDX-License-Identifier: CC-BY-4.0
-->

# Abschlusspräsentation der Studie

## Einleitung

Am Ende des Workshops stellt jede Gruppe ihre Studie zum Kabel Brasilien–Deutschland
vor. Diese Präsentation wird hier nicht von Hand gebaut, sondern **aus dem
Stand der Studie erzeugt**: aus den Entscheidungen der Gruppe
(`workshop/decisions.md`), den Lieferungen der Rollen 1–3, den Ergebnissen
der Pipeline von Rolle 4 (`workshop/results/`) und einem Register aller
Daten, Annahmen und Entscheidungen (`register.yaml`).

Der Aufbau folgt den Rollen und ihren Entscheidungen:

- **Entscheidungen und ihre Wirkung.** Jede Entscheidung steht mit dem
  Zwischenschritt, in dem sie gewirkt hat, und mit dem, was sie dort bewirkt
  hat: von der Baseline über das Studiendesign (E1–E7) und die Lieferungen der
  Rollen bis zu den Testläufen.
- **Ergebnisse** nur aus fertigen Läufen. Was noch fehlt, erscheint als
  "ausstehend" mit Grund oder wird weggelassen.
- **Daten und Annahmen** mit Quelle, Jahr, Verarbeitung und Wirkung auf den
  Kabelwert.
- **Vertrauliche Daten (NDA, E7)** erscheinen nur als *Quelle vor der
  Verarbeitung* ("vertrauliche Projektdaten (NDA)"), nie mit Werten, Dateinamen,
  Partnern oder dem Deal; das Werkzeug lässt nichts anderes zu.

Verantwortlich ist Rolle 4. Für Agenten ist der Ablauf im Skill
`.claude/skills/presentation/SKILL.md` festgelegt; diese Datei ist die
Referenz für Menschen und Agenten.

| Datei | Inhalt | gepflegt von |
|---|---|---|
| `README.md` | diese Datei: Einleitung, User Guide, Aufbau, Regeln, Design | Rolle 4 |
| `deck.yaml` | Gliederung: jede Folie mit Aussage, Text, Abbildung, Tabelle, Quelle, Platzhaltern | Rolle 4; Folien der Teile A je Rolle |
| `register.yaml` | Daten, Annahmen, Entscheidungen mit Zwischenschritt und Wirkung | jede Rolle ihre Einträge |
| `settings.yaml` | feste Einstellungen und die Fragen, die im Chat gestellt werden | Rolle 4 |
| `build_deck.py` | baut die `.pptx`, füllt Zahlen, prüft Vollständigkeit, NDA und Review | Rolle 4 |
| `results/presentation/answers.yaml` | gespeicherte Antworten dieses Workspaces (nicht committet) | automatisch |
| `results/presentation/praesentation-<datum>.pptx` | die erzeugte Präsentation (nicht committet) | automatisch |

## User Guide

### Kurz: mit dem Agenten

Sage deinem Agenten "Bereite die Präsentation vor" (oder lade den Skill
`presentation`). Er

1. prüft, ob neue Läufe fertig sind, und wertet sie bei Bedarf aus
   (Skill `results-pipeline`; nie während eines Solves);
2. fragt **nur die Einstellungen, die gerade offen sind** (siehe unten);
3. baut die Präsentation und meldet ausstehende Folien, `TODO`s, NDA-Treffer
   und offene Review-Blocker;
4. sagt dir, welche Rolle welche Lücke füllen muss.

### Welche Einstellungen gefragt werden

Feste Dinge werden nie gefragt: Sprache (Deutsch), Zusammenfassungsjahre
2035–2045 und 2050 getrennt (E3), Szenarien (E4), Farben und Design
(Plot-Style), Zahlen nur über Platzhalter, NDA-Regeln (E7). Sie stehen unter
`fest:` in `settings.yaml`.

Gefragt wird nur, was der Nutzer entscheiden muss, und nur wenn es gerade
relevant ist:

| Einstellung | gefragt wenn | erneut gefragt wenn | Default |
|---|---|---|---|
| `gruppe` – Name auf der Titelfolie | noch nie beantwortet | – | leer |
| `umfang` – voll (≈ 20 min) oder kurz (≈ 10 min, ohne optionale Folien) | noch nie beantwortet | – | voll |
| `ausstehend` – Folien fehlender Läufe zeigen oder weglassen | ein benötigter Lauf ist nicht fertig | sich die Menge fertiger Läufe ändert | zeigen |
| `testlaeufe` – Testläufe (z. B. BRIMP) im Anhang | ein fertiger Lauf gehört nicht zu E4 | sich die Menge fertiger Läufe ändert | anhang |
| `nda_hinweis` – qualitativer NDA-Satz | `workshop/inputs/` existiert | – | weglassen |
| `schrift` – Libre Franklin oder Arial | noch nie beantwortet | – | Libre Franklin |

Antworten werden in `results/presentation/answers.yaml` gespeichert. Beim
nächsten Aufruf fragt der Agent nur, was neu oder durch neue Läufe überholt
ist. Wer eine Antwort ändern will, sagt es dem Agenten oder setzt sie direkt
(`--set`).

### Von Hand

```bash
B="uv run --no-project --with python-pptx --with pandas --with pyyaml --with matplotlib \
   python workshop/presentation/build_deck.py"
$B --questions                       # welche Fragen gerade offen sind (YAML)
$B --set umfang=kurz gruppe="Gruppe 3"   # Antworten speichern und bauen
$B                                   # Entwurf mit gespeicherten Antworten
$B --final                           # schreibt nur, wenn nichts offen ist
```

`python-pptx` ist nicht Teil der pixi-Umgebung; `uv run --no-project` holt es
in eine Wegwerf-Umgebung, ohne `pixi.lock` zu ändern. `build_deck.py` liest
nur CSVs und Bilder, keine Netzwerke; es braucht wenig Speicher, darf also auch
neben einem Solve laufen. `evaluate.py` darf das nicht (O7).

### In einem frischen Clone

Skill und Werkzeug liegen im Repo (`.claude/skills/presentation/`,
`workshop/presentation/`). Die Inhalte kommen aus Dateien, die nicht immer
mitkommen:

| Braucht | im Repo? | sonst |
|---|---|---|
| `workshop/analysis/runs.yaml` | ja | – |
| `workshop/results/*.csv`, `figures/` | sobald Rolle 4 sie committet | `evaluate.py` ausführen (Skill `results-pipeline`) |
| `results/cable-route/`, `results/brazil-validation/` | nein (`/results` ist ignoriert) | Skripte von Rolle 1/2 ausführen |
| `workshop/inputs/` | nie (NDA) | NDA-Scan und `nda_hinweis` entfallen |

Fehlt eine Datei, baut der Builder trotzdem; betroffene Folien erscheinen als
"ausstehend" mit dem Namen der fehlenden Datei. `uv` muss installiert sein.

### Was der Builder ausgibt

Eine Zeile je Folie: Rolle, Stand (`ok`, `ausstehend`, `Layout`), Zahl der
`TODO`s und der Grund. Darunter:

- **NDA-Scan**: vergleicht Folientext und Notizen zur Laufzeit mit
  `workshop/inputs/`; meldet nur Folie und Anzahl möglicher Treffer, nie den
  Wert. Jeder Treffer wird von Hand geprüft.
- **Review**: Zahl der Blocker im neuesten `results/review/report-*.md` (E8).
- `--final` bricht ab bei ausstehenden Folien, `TODO`, NDA-Treffern oder
  Blockern.

### Von Entwurf zur fertigen Präsentation

1. Läufe auswerten (`results-pipeline`), Befunde in `workshop/results/notes.md`.
2. Jede Rolle trägt ihre Daten, Annahmen und Entscheidungen in `register.yaml`
   ein und füllt die `TODO`s ihrer Folien in `deck.yaml` (Teil A: Rolle 1
   Folien Route/Kosten, Rolle 2 Standort/Profile, Rolle 3 deutsches System).
3. Rolle 4 schreibt die Aussagen der Ergebnisfolien (Titel als Aussage) aus
   `notes.md` und ergänzt in `register.yaml` die Wirkung der Studienentscheidungen.
4. Entwurf bauen, ausstehende Folien und Warnungen lesen.
5. Rolle 5 prüft (R3, R1, R2) gegen den Entwurf; Blocker beheben.
6. `--final` bauen; dann teilen.

## Aufbau der Präsentation

### Leitgedanke

Der Auftrag lautet, zu zeigen, dass das Kabel eine "amazing solution" ist. Die
Präsentation zeigt, **ob und unter welchen Bedingungen** das gilt (Rolle 4:
"Report what the result depends on, also where it does not hold"; Rolle 1: ein
unbezahlbares Kabel ist ein gültiges Ergebnis). Drei Grundsätze:

1. **Antwort zuerst.** Folie 2 gibt das Ergebnis. Jeder Folientitel ist eine
   Aussage ("Das Modell baut kein Kabel"), kein Thema.
2. **Jede Zahl ist rückverfolgbar** auf einen gelösten Lauf, eine Lieferung
   unter `results/` oder eine öffentliche Quelle mit Jahr (Review R2). Zahlen
   werden nicht abgetippt, sondern über Platzhalter eingesetzt.
3. **Ein Vergleich, eine Änderung** (E4). Jede Ergebnisfolie nennt das
   Vergleichspaar und was sich zwischen den Läufen ändert.

### Folienplan

| Teil | Folie (Aussage) | Inhalt | Quelle | Rolle |
|---|---|---|---|---|
| – | Titel | Frage, Gruppe, Stand der Läufe | `runs.yaml`, Antworten | 4 |
| – | **Kernaussage** | baut das Modell das Kabel, Abstand zum Break-even, wovon es abhängt, wer gewinnt/verliert | `notes.md`, CSVs | 4 |
| – | Die Falle 2050 | Nullcap macht jede saubere Quelle wertvoll | BASE, README Workshop | 4 |
| – | **Entscheidungspfad** | Ausgangslage und Studiendesign: Entscheidung → Zwischenschritt → Wirkung | `register.yaml` Phasen 1–2 | 4 |
| A Inputs | Route und Tiefe | Varianten, Länge, Tiefe, Abschnitt jenseits 3.000 m | `results/cable-route/` | 1 |
| A | Kabelkosten als Spanne | niedrig/zentral/hoch, WACC, Lebensdauer, Verluste | Kostentabelle (DEA), Rolle 1 | 1 |
| A | Exportstandort Brasilien | Region, Mix, CF, LCOE | `results/brazil-validation/` | 2 |
| A | Profile gegen Messung (optional) | Windvalidierung ONS | `wind_validation*` | 2 |
| A | Das deutsche System | Annahmen, Handel, Netto-Importgrenze, Anschlussknoten | `BASELINE.md`, Rolle 3 | 3 |
| A | **Zwischenschritte** | Entscheidungen der Rollen und Testläufe mit Wirkung | `register.yaml` Phasen 3–4 | alle |
| B Methodik | E1 Studientyp, E2 Parameter, E3 2050, E4 Szenarien, E5/E6 Messung | je eine Folie | `decisions.md` | 4 |
| C Ergebnisse | Baut das Modell das Kabel? | Kapazität je Jahr | CABLE | 4 |
| C | Systemkosten | Δ CABLE − REF, Mittel 2035–2045, 2050 getrennt | `comparisons.csv` | 4 |
| C | **Abstand zum Break-even** | Engpasserlös vs. Annuität (MV), CAPEX50 | MV, CAPEX50, Rolle 1 | 4 |
| C | Was das Ergebnis bewegt | CAPEX50, WACC7, ohne Handel | `comparisons.csv` | 4 |
| C | Gewinner und Verlierer | Akteure nach E6 | `comparisons.csv` | 4 |
| C | Verdrängung (optional) | Erzeugung CABLE | Abbildung | 4 |
| D Einordnung | Wovon es abhängt | Grenzen mit Richtung | `BASELINE.md`, Rollen | alle |
| D | Fazit | was sich ändern müsste | Folien C | 4 |
| Anhang | Status der Läufe, Baseline, Testlauf, **Daten**, **Annahmen**, (NDA-Hinweis), Definitionen, Quellen | | `status.csv`, `register.yaml` | alle |

Reihenfolge: zuerst die Antwort und warum die naheliegende Antwort (2050)
falsch wäre, dann der Weg der Entscheidungen, dann was eingeht (dem Weg des
Stroms entlang: Kabel → Brasilien → Deutschland), wie gerechnet wird, was
herauskommt und wie belastbar es ist.

## Regeln

### Register: Daten, Annahmen, Entscheidungen

`register.yaml` ist die eine Stelle, an der dokumentiert wird, was in die
Studie eingeht und warum. Es erzeugt die Folien "Entscheidungspfad",
"Zwischenschritte", "Daten" und "Annahmen".

- **Daten** (`D…`): Name, Quelle, Jahr, Verarbeitung (Skript), Ergebnis (Datei).
- **Annahmen** (`A…`): Wert, Quelle, Rolle und die vermutete Richtung für den
  Kabelwert.
- **Entscheidungen**: Phase (1 Ausgangslage, 2 Studiendesign, 3 Inputs,
  4 Zwischenschritt), wer, was, warum, der **Zwischenschritt** (Lauf, Datei,
  Befund), in dem sie gewirkt hat, und die **Wirkung** dort, als Platzhalter auf
  das Ergebnis. Eine Wirkung, deren Läufe fehlen, erscheint als "ausstehend".
- Testläufe (`test: true`) erscheinen als Zwischenschritt, nie als
  Studienergebnis.

### NDA (E7)

- Einträge aus oder auf Basis von `workshop/inputs/` tragen `nda: true` und
  nennen **nur** die Quelle vor der Verarbeitung (`vertrauliche Projektdaten
  (NDA), vor der Verarbeitung`), das verarbeitende Skript und die Verwendung.
  Kein Wert, kein Ergebnis, keine Wirkung, kein Jahr, kein Platzhalter, kein
  Dateiname aus `workshop/inputs/`. `build_deck.py` bricht sonst ab.
- Platzhalter und Abbildungen dürfen nicht aus `workshop/inputs/` lesen; der
  Builder sperrt das.
- Eine Größe, die aus vertraulichen Daten berechnet wurde (z. B. Bänder aus
  `validate_against_nda.py`), wird nicht gezeigt; genannt wird nur die Quelle.
- Der NDA-Hinweis erscheint nur mit `nda_hinweis=qualitativ`, und nur wenn die
  Validierung gelaufen ist (Review R3-03).
- Deck, Register, Notizen und Dateinamen enthalten keinen Wert, kein
  Verhältnis, keinen Deal-Code und keine Garantiebedingung.
- Bilder lassen sich nicht scannen: sie kommen nur aus der Pipeline oder
  Rollenskripten, die `workshop/inputs/` nicht lesen.

### Inputs (Teil A)

- Nur öffentliche Inputs: Lieferungen unter `results/`, `data-brazil/` (Quelle
  laut `raw/sources.csv`), Kostentabellen, Configs.
- Quelle und Jahr in der Fußzeile; wo extrapoliert wird, sagt es die Folie.
- Kosten als Spanne; die Läufe nutzen zentral (E2).
- Preisbasis nennen; Abweichung von EUR_2020 an Rolle 4 melden.
- Weicht die Lieferung vom Modellstand ab (Routenlänge vs. Großkreis × 1,25),
  zeigt die Folie den Modellwert und nennt die Abweichung.
- GADM und WDPA dürfen nicht weitergegeben werden: Karten auf dieser Basis
  bleiben im Workshop.

### Methodik (Teil B)

- Die Folien geben `decisions.md` wieder, mit E-Nummer im Untertitel. Weicht
  die Umsetzung ab, gilt die Umsetzung, und die Folie nennt die Abweichung.
- Offene Punkte (O1–O7), die ein Ergebnis berühren, stehen auf der Folie.

### Ergebnisse (Teil C)

- Zahlen und Abbildungen nur aus der Pipeline; fehlende Abbildungen als
  Funktion in `evaluate.py`, nicht als Einzelskript.
- Nur fertige Läufe; 2050 getrennt; cap-getriebene Jahre nicht als Kabelwert.
- Deutung aus `notes.md`; was auf einer Folie steht, steht zuerst dort.

### Einordnung (Teil D)

- Grenzen aus `BASELINE.md` und den Rollen, jede mit Richtung.
- Offene Review-Blocker: nicht präsentieren (E8).

## Platzhalter

| Platzhalter | Wert |
|---|---|
| `{{m\|RUN\|JAHRE\|Sektion/Kennzahl\|DEZ}}` | Kennzahl aus `metrics.csv` |
| `{{c\|RUN\|REF\|JAHRE\|Sektion/Kennzahl\|DEZ}}` | Differenz aus `comparisons.csv`, mit Vorzeichen |
| `{{csv\|PFAD\|ZEILE\|SPALTE\|DEZ}}` | Zelle einer Lieferung; `ZEILE` = Wert der ersten Spalte oder `spalte=wert;spalte=wert` |
| `{{date}}`, `{{status}}` | Datum, Kurzstatus der Läufe |

`JAHRE`: `2040` oder `2035-2045` (Mittel der vorhandenen Jahre). Deutsches
Zahlenformat. Ein Platzhalter ohne Wert macht die Folie "ausstehend". `TODO` im
Text markiert, was eine Rolle noch liefern muss.

Automatische Tabellen: `table: {auto: status | daten | annahmen | entscheidungen}`,
bei Entscheidungen optional `phasen: ["3", "4"]`.

## Design

Die Folien übertragen den Workshop-Plot-Style (`workshop/plotstyle/`, Skill
`plot-style`) auf PowerPoint, damit Abbildungen und Folien eine Fläche bilden.

| Element | Regel | Plot-Style |
|---|---|---|
| Format | 16:9, weißer Grund, keine Bilder im Hintergrund, keine Verläufe, keine Schatten | flache Flächen, kein Rahmen |
| Schrift | Libre Franklin (oder Arial nach Antwort `schrift`) | Regel 1 |
| Titel | oben links, fett, 26 pt, `#222222`, als Aussage | Regel 7 |
| Untertitel | 13 pt `#666666`: Frage, E-Nummer oder Vergleichspaar | Tick-Farbe |
| Teil-Marke | 9 pt Versalien `#666666` über dem Titel | – |
| Text | 16 pt `#222222`, Aufzählung mit flachen grauen Quadraten; `TODO` kursiv grau | `legend_squares` |
| Fußzeile | 9 pt `#aaaaaa`, Quelle links, Seitenzahl rechts, über Linie `#dcdcdc` 0,5 pt | faint notes, Gitter |
| Tabellen | keine Füllung, keine senkrechten Linien, Kopf fett über Linie `#222222` 0,8 pt, Zeilen `#dcdcdc` 0,5 pt, Zahlen rechtsbündig | Regel 2 |
| Kennzahlen | 44 pt fett, Beschriftung `#666666`, Quadrat in Gruppenfarbe | Regel 4, 6 |
| Farben | nur `st.GROUPS`; Vermilion `#D55E00` nur für das Kabel; Referenz grau `#c4c4c4` | Regel 4 |
| Abbildungen | PNG 300 dpi aus der Pipeline, unverzerrt, Titel der Abbildung bleibt | Regel 10 |
| Ausstehend | Fläche `#eeeeee`, Grund in `#666666` | `LAND` |

Fonts: PowerPoint bettet Libre Franklin nicht ein. Auf dem
Präsentationsrechner die TTFs aus `workshop/plotstyle/fonts/` installieren oder
`schrift=Arial` wählen.

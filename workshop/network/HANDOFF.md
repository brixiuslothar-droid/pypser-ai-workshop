<!--
SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>

SPDX-License-Identifier: CC-BY-4.0
-->

# Handoff: Rolle 6 Netzanalyse

Für den **Hauptanalyse-Chat** (Rolle 4 / `evaluate.py`) und den
**Präsentations-Chat** (Rolle 4, `deck.yaml`/`register.yaml`). Stand vom
2026-11-27. Methode und Vorbehalte: [`README.md`](README.md).

## Was fertig ist

- Ein CLI-Skript: `pixi run python workshop/network/analyze.py RUN HORIZON [REFERENCE]`.
- Bibliothek `workshop/network/full_grid.py`; Doku `README.md`.
- Ergebnisse (git-ignoriert) unter `results/network/<run>_<horizon>/`
  (CSV + PNG/PDF) und `results/network/compare_<run>_vs_<ref>_<horizon>.png`.
- Getestet mit dem neuesten gelösten Netz `de10-br-ext` 2040 und den
  Vergleichspaaren `de10-myopic` / `de10-br-import` 2040.

## Kernbefunde (2040, Vorbehalte beachten)

- `de10-br-ext` 2040 baut **kein Kabel** (`p_nom_opt ≈ 0 GW`); für „mit Kabel"
  dient `de10-br-import` (fest 2 GW, 7,6 TWh 2040).
- In den Stresswochen sind **8–9 % aller Linien-Stunden** über der Grenze
  (max Wind / max Last), 30–41 Leitungen über 2x; Engpass ist der
  **Nord–Süd-Korridor**.
- Redispatch zum Freiräumen: **2,5–2,8 TWh/Woche** ohne Kabel, 1,5–2,8 mit Kabel.
- Ein 2-GW-Kabel ändert die innere Belastung um **< 1 %**.

## An den Hauptanalyse-Chat (Rolle 4)

1. **Einordnung.** Die Netzanalyse ist kein E4-Lauf und keine
   Kabelbewertung; sie nutzt die gelösten Netze nur lesend. Sie beantwortet eine
   andere Frage (innere Netzbelastung/Redispatch), die die 10-Knoten-Bilanz
   nicht sieht.
2. **Regel der Präsentation beachten.** Der Präsentations-README verlangt:
   „Zahlen und Abbildungen nur aus der Pipeline; fehlende Abbildungen als
   Funktion in `evaluate.py`, nicht als Einzelskript." Soll die Netzanalyse in
   die Präsentation, **portiere die zwei Funktionen aus `analyze.py`
   (`analyze`, `compare`) als Pipeline-Schritt in `workshop/analysis/evaluate.py`**,
   der die Metriken nach `workshop/results/metrics.csv` schreibt und die
   Abbildungen nach `workshop/results/figures/`. Der aktuelle Einzelskript-Pfad
   ist nur für Exploration.
3. **Nicht während eines Solves** ausführen (O7); Speicherbedarf ist klein, aber
   der Lastfluss über drei Wochen braucht etwas Zeit.
4. **Abgrenzung der Zahlen.** Absolute Überlast/Redispatch sind eine
   Rekonstruktion (Groessenordnung); der Vergleich mit/ohne Kabel ist robust.
   Das im Bericht/Vortrag so kennzeichnen; Rolle 5 (R1/R2) muss die Methode
   prüfen, bevor sie präsentiert wird.

## An den Präsentations-Chat (Rolle 4)

### Wo einordnen

Teil **D „Wovon das Ergebnis abhängt"** (eine Grenze/Ergänzung des
Kabelwerts), optional als eigene C-Folie. Aussage der Folie ist eine
**Einordnung**, keine Kabelbewertung: „Das 2-GW-Kabel bewegt die innere
Netzbelastung nicht; der Engpass ist der Nord–Süd-Transport."

### Vorgeschlagene register.yaml-Einträge

`daten`:

```yaml
- id: D10
  name: Volles deutsches Übertragungsnetz (rekonstruiert)
  quelle: PyPSA-Eur Workflow (OSM-Netz, simplified)
  jahr: 2013
  verarbeitung: workshop/network/analyze.py
  ergebnis: results/network/<run>_<horizon>/   # bzw. nach evaluate.py-Portierung
  rolle: 6
- id: D11
  name: Verfügbarkeits- und Bevölkerungsraster (789/470-Knoten-Verteilung)
  quelle: PyPSA-Eur (Availability-Matrizen), Pop-Layout
  jahr: 2013
  verarbeitung: workshop/network/full_grid.py
  ergebnis: results/network/<run>_<horizon>/
  rolle: 6
```

`annahmen`:

```yaml
- id: A10
  name: Räumliche Verteilung der Markteinspeisung
  wert: VRE nach Verfügbarkeitszellen, konventionell nach Kraftwerksstandorten, Last nach Bevölkerung
  quelle: Methode Rolle 6 (full_grid.py)
  rolle: 6
  wirkung: absolute Netzbelastung/-redispatch größenordnungsabhängig; Vergleich mit/ohne Kabel robust
```

### Vorgeschlagene Folie (Teil D), Entwurf

```yaml
- id: netzanalyse
  layout: figure
  part: D
  owner: 4
  title: "Ohne Netzausbau überlastet der Nord-Süd-Korridor"
  subtitle: "Netzanalyse auf dem vollen Netz (470 Knoten); Stresswochen 2040"
  figure: workshop/results/figures/netz_<run>.png   # erst nach evaluate.py-Portierung
  bullets:
    - "{{…}} % der Linien-Stunden über der Grenze (max Wind/max Last)"
    - "Redispatch ~{{…}} TWh/Woche; ein 2-GW-Kabel ändert < 1 %"
    - "Rekonstruktion: Größenordnung, nicht Prognose"
  source: "workshop/network/README.md; results/network/; E3 (2040 statt 2050)"
```

Die Platzhalter `{{…}}` müssen aus `metrics.csv`/`comparisons.csv` kommen
(README „Platzhalter"). Das setzt die Portierung nach `evaluate.py` voraus;
sonst bleibt die Folie „ausstehend".

### NDA (E7)

Es wurde **nichts** aus `workshop/inputs/` gelesen oder verwendet. Einträge ohne
`nda: true`; keine Prüfung nötig, aber der übliche R3-Scan läuft mit.

## Nächste Schritte (offen)

1. Rolle 4 entscheidet, ob die Netzanalyse in die Pipeline/Präsentation kommt
   (Portierung) oder Appendix bleibt.
2. Optional auf **2050** rechnen: `analyze.py de10-br-import 2050 de10-myopic`
   (2050 in der Präsentation getrennt, E3).
3. Optional Allokation verfeinern (Resourcengüte je Zelle statt Zellfläche) und
   Karte der überlasteten Leitungen ergänzen.
4. Rolle 5: Methode und Zahlen prüfen (R1/R2), bevor präsentiert wird.

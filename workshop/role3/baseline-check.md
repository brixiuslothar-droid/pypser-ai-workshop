<!--
SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>

SPDX-License-Identifier: CC-BY-4.0
-->

# Rolle 3: Plausibilitätsprüfung der Baseline (`de10-myopic`)

Erzeugt mit `pixi run python workshop/role3/baseline_check.py`, das CSVs nach
`results/de10-myopic/role3/` schreibt. Es ist kein Solve nötig. Nutzt keine vertraulichen Daten.

## Kennzahlen je Jahr

| | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
|---|---|---|---|---|---|---|
| Nachfrage (TWh) | 509 | 560 | 611 | 662 | 713 | 764 |
| Preis, lastgewichtet (€/MWh) | 96 | 87 | 91 | 93 | 113 | 117 |
| Preis max. (€/MWh) | 124 | 177 | 1.040 | 1.427 | 430 | 2.959 |
| Stunden > 300 €/MWh | 0 | 0 | 52 | 52 | 2.040 | 1.498 |
| Stunden < 1 €/MWh | 360 | 1.980 | 2.292 | 3.088 | 4.486 | 2.882 |
| Schattenpreis CO₂-Grenze (€/t) | 0 | 0 | 0 | 43 | 488 | 24.354 |
| CO₂ (Mt) | 161 | 64 | 43 | 34 | 17 | 0 |
| Abregelung Wind+PV (TWh / Anteil) | 3 / 1 % | 34 / 9 % | 42 / 9 % | 78 / 13 % | 159 / 19 % | 107 / 11 % |
| Steinkohle / Braunkohle (TWh) | 131 / 32 | 26 / 1 | 0 / 1 | 0 / 0 | – | – |
| Gas CCGT+OCGT (TWh) | 21 | 108 | 114 | 93 | 47 | 0 |
| Biomasse (TWh) | 65 | 50 | 45 | 27 | 8 | 7 |
| Wind an Land (GW) | 64 | 90 | 79 | 72 | 115 | 141 |
| Wind auf See AC+DC (GW) | 9 | 10 | 19 | 24 | 28 | 26 |
| PV fest + Tracking (GW) | 90 + 0 | 91 + 54 | 113 + 84 | 227 + 84 | 337 + 88 | 411 + 88 |
| OCGT (GW) | 6 | 5 | 14 | 23 | 22 | 21 |
| Batterie (GWh) | 0 | 20 | 155 | 391 | 607 | 834 |
| H₂-Speicher (TWh) / Brennstoffzelle (GW) | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 13 / 10 | 72 / 109 |
| HVDC innerhalb DE (GW) | 0 | 0 | 0 | 0 | 0 | 7 |
| Ø Leitungsauslastung / Anteil Stunden mit Engpass | 18 % / 0 % | 29 % / 0 % | 36 % / 1 % | 37 % / 1 % | 41 % / 2 % | 41 % / 2 % |

## 2025 im Vergleich zur Realität

Ungefähre Ist-Werte für 2024, aus dem Gedächtnis (Energy-Charts/AGEB). **Vor
Verwendung mit Quelle prüfen.**

| | Modell 2025 | Ist ca. 2024 | Bewertung |
|---|---|---|---|
| Wind an Land | 108 TWh / 64 GW | ~110 TWh / ~63 GW | passt |
| Wind auf See | 38 TWh / 9,2 GW | ~26 TWh / ~9 GW | zu hoch (Volllaststunden, Wetterjahr 2013) |
| PV | 86 TWh / 90 GW | ~70 TWh / ~100 GW | plausibel |
| Braunkohle | 32 TWh | ~70 TWh | **viel zu niedrig** (bekannt: Brennstoffpreis) |
| Steinkohle | 131 TWh | ~25 TWh | **viel zu hoch** |
| Erdgas | 21 TWh | ~75 TWh | **viel zu niedrig** (ohne KWK-Pflichtlauf, ohne Handel) |
| Biomasse | 65 TWh | ~45 TWh | zu hoch |
| Großhandelspreis | 96 €/MWh | ~80 €/MWh | etwas hoch |
| Nettoexport | 0 (Insel) | ~25 TWh Nettoimport | fehlt |

## Auffälligkeiten mit Bedeutung für das Kabel

1. **Ohne Handel entstehen die Preisspitzen.** Ab 2035 gibt es einzelne Spitzen über 1.000 €/MWh. 2045 liegen 2.040 Stunden über 300 €/MWh, und gleichzeitig liegen 4.486 Stunden unter 1 €/MWh. Diese Spreizung macht jede steuerbare Einspeisung, auch das Kabel, im Modell sehr wertvoll. Mit Nachbarn sollte sie deutlich kleiner werden. → **Priorität 1 bestätigt.**
2. **Schon 2045 ist die CO₂-Grenze teuer** (488 €/t Schattenpreis, 17 Mt Rest). Nicht nur 2050 ist betroffen. Wenn wir 2050 auf einen CO₂-Preis umstellen, sollten wir 2045 im Blick behalten.
3. **Die geplanten HVDC-Korridore fehlen** (SuedLink, SuedOstLink, A-Nord, Ultranet). Im Modell sind die DC-Links bis 2045 mit 0 GW angelegt. Real sollen sie um 2028 in Betrieb gehen. Trotzdem sind die Engpässe gering (2 % der Stunden), und die Knotenpreise unterscheiden sich kaum (2045: 101–109 €/MWh im Mittel). Für den Anschlussknoten spielt das Netz innerhalb Deutschlands deshalb kaum eine Rolle. Das kann auch an der groben Aggregation auf 10 Knoten liegen. → Prüfen, warum die Projekte nicht gebaut werden (`transmission_projects`).
4. **Wind an Land sinkt 2030–2040 von 90 auf 72 GW.** Altanlagen gehen vom Netz, und die myopische Optimierung ersetzt sie durch PV. Das gesetzliche Ziel liegt bei 115 GW in 2030 (EEG 2023). Dadurch gibt es mehr Mittagsspitzen und weniger Erzeugung im Winter, was den Winterwert des Kabels erhöht.
5. **2050 gleichen Brennstoffzellen aus (109 GW) statt H₂-Turbinen**, mit 72 TWh H₂-Speicher. Das ist eine Folge der Nullgrenze. Mit dem CO₂-Preis wird sich das ändern.

Kohle und Gas 2025 (Vertauschung von Braun- und Steinkohle) und die viele PV mit Nachführung (54–88 GW) sind bekannt, für den Kabelwert ab 2035 aber kaum relevant. Wir ändern sie nicht.

## Kennzahlen je Knoten für Rolle 1 (Anschlussknoten)

Ø-Preis in €/MWh, Nettoexport in TWh (positiv = Überschuss).
**Knotennummern der Baseline.** In `de10-nb9*` sind sie anders vergeben, Zuordnung in `handover.md`.

| Knoten | Lage (ca.) | Ø-Preis 2035 | Ø-Preis 2045 | Nettoexport 2035 | Nettoexport 2045 | Wind auf See 2045 (GW) |
|---|---|---|---|---|---|---|
| DE0 7 | Weser-Ems / Nordsee West | 88,0 | 102,0 | +55 | +66 | 22,3 |
| DE0 8 | Schleswig-Holstein / Hamburg | 87,1 | 101,5 | +45 | +55 | 2,2 |
| DE0 0 | Mecklenburg-Vorpommern / Brandenburg (Ostsee) | 88,0 | 103,8 | +67 | +60 | 3,2 |
| DE0 2 | Rhein-Ruhr | 89,1 | 104,8 | −42 | +14 | 0 |
| DE0 5 | Rhein-Main / Rheinland-Pfalz | 90,5 | 108,6 | −57 | −18 | 0 |
| DE0 1 | Baden-Württemberg | 89,9 | 108,8 | −19 | −11 | 0 |
| DE0 4 | Bayern | 89,4 | 109,4 | +18 | −10 | 0 |

Die Küstenknoten (7, 8, 0) haben schon Überschuss und die niedrigsten Preise.
Ein Kabel aus Brasilien würde dort mit Wind auf See konkurrieren, und der Strom müsste nach Süden.
Wegen der kleinen Preisunterschiede im Modell ist das aber ein schwacher Effekt.
Wenn das Netz nicht genauer abgebildet ist, sollte die Wahl des Knotens das Ergebnis nicht tragen.

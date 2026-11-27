### Baseline (BASE, `de10-myopic`)

Stand 2026-11-27. Befunde von Hand, Zahlen aus den Tabellen unten.

- **Die Baseline taugt nicht als Vergleichsfall für das Kabel.** 2050 legt die
  CO2-Obergrenze 24.354 EUR/t auf den CO2-Preis, der höchste Strompreis liegt bei
  2.959 EUR/MWh (76 h über 1.000 EUR/MWh). Jede saubere Stromquelle sähe dagegen
  wertvoll aus. Deshalb vergleicht die Studie mit REF (E3, E4), nicht mit BASE.
- **Schon 2035 und 2040 gibt es Preisspitzen** über 1.000 EUR/MWh (32 bzw. 42 h).
  Ursache ist die Insellage: Knappheit, die Handel decken würde, fällt auf Speicher
  und Reservekraftwerke. Ein Kabel bekäme hier einen Wert, der mit Handel (REF)
  kleiner ausfallen dürfte.
- **2045 ist die Obergrenze bereits bindend** (488 EUR/t zusätzlich, effektiv 748 EUR/t).
  Das Ergebnis 2045 ist damit ebenfalls teilweise cap-getrieben; E3 entschärft nur 2050.
- **Speicher wachsen stark:** Kapitalkosten der Speicher von 7 (2040) auf
  36 Mrd EUR/a (2050), davon 72 TWh Wasserstoffspeicher 2050. Das ist der Kostenblock,
  den ein Kabel oder Handel am ehesten ersetzt.
- **Abregelung** von Wind, Solar und Laufwasser steigt auf 159 TWh (2045) und
  107 TWh (2050): Ein Kabel nach Deutschland konkurriert mit billigem Überschussstrom
  in vielen Stunden; sein Wert liegt in den knappen Stunden.
- **Verteilung:** Verbraucher zahlen 49 (2025) bis 89 Mrd EUR/a (2050). Die
  Erzeuger fossiler Anlagen verlieren bis 2035 deutlich (Bestand wird nicht mehr
  gedeckt), Wind und Wasser gewinnen ab 2045.
- **Solver:** 2045 endet "imprecise" (laut BASELINE.md nutzbar); Spitzenspeicher
  6,7 GB von 8 GB, also wenig Luft für mehr Nachbarländer (O4).

### Test: fester 2-GW-Kabel auf der Baseline (BRIMP − BASE, `de10-br-import`)

Stand 2026-11-27. Kein Studienergebnis: BRIMP baut auf BASE (Insel, harter
Nullcap 2050) und gehört nicht zu E4. Er testet Pipeline und Regeln.

- **Ein festes 2-GW-Kabel rechnet sich hier in keinem Jahr.** Die Systemkosten
  steigen um 3,9 bis 5,3 Mrd EUR/a (Mittel 2035–2045: +4,8). Das Kabel kostet
  2,6–3,0 Tsd. EUR/kW/a Annuität bei 10 % WACC, verdient aber nur 0,35–0,57 Tsd.
  EUR/kW/a Engpasserlös: Die Erlöse decken 12–21 % der Kosten.
- **Treiber sind die Kosten der Leitung:** rund 9.500 km (Großkreis × 1,25),
  78,5 % Wirkungsgrad. Das Kabel kostet 2035 6,0 Mrd EUR/a; Deutschland spart dafür
  nur 1,2 Mrd EUR/a an eigenen Kosten.
- **Die Auslastung fällt von 65 % (2035) auf 34 % (2045)**, weil Deutschland
  selbst immer mehr billigen Überschussstrom hat (Stunden mit Preis < 1 EUR/MWh).
  Der Engpasserlös pro kW steigt trotzdem, weil die wenigen knappen Stunden teurer
  werden.
- **2050 verzerrt nicht einmal zugunsten des Kabels:** Der Schattenpreis der
  Obergrenze sinkt nur um 243 von 24.354 EUR/t; die 2 GW bewegen den Nullcap kaum.
  Das Jahr ist trotzdem gekennzeichnet und in der Zusammenfassung ausgelassen.
- **Gewinner und Verlierer** (Mittel 2035–2045): Verbraucher DE +0,5 Mrd EUR/a
  durch etwas niedrigere Preise; der Kabelbetreiber −4,9; der Staat −0,4 (weniger
  CO2-Erlöse). Die Erzeuger in BR stehen bei 0, weil der Importpreis im Modell
  gleich ihren Kosten ist (LCOE, `brazil_import.price`).
- **Abgleich:** Systemkosten, Kabelannuität, Engpasserlös, Lieferung, Auslastung
  und Preis stimmen in allen Jahren mit `workshop/cba/cba_brazil_import.py`
  überein (Abweichung < 0,001); Kabelannuität, Lieferung und Engpasserlös 2040
  direkt aus dem Netz nachgerechnet.
- **Was das für die Studie heißt:** Für die Kapazitätsausbau-Läufe (E1) ist zu
  erwarten, dass das Modell das Kabel nicht baut. Der Abstand zum Break-even
  liegt hier bei rund 2,1–2,7 Tsd. EUR/kW/a; MV und CAPEX50 (E5) messen ihn mit
  Handel genauer.

### Netzanalyse (Rolle 6) im Test: BRIMP − BASE, 2040

Stand 2026-11-27. Mit `evaluate.py --grid BASE:2040 BRIMP:2040` gerechnet.
Rekonstruktion: absolute Werte sind eine Größenordnung; belastbar ist nur der
Vergleich mit/ohne Kabel. Von Rolle 5 noch nicht geprüft.

- **Ein 2-GW-Kabel ändert die innere Netzbelastung kaum.** In der Woche mit dem
  meisten Wind sind 20,1 % der Leitungsstunden überlastet, mit Kabel 20,1 %;
  Redispatch 2,8 TWh/Woche ohne, 2,7 mit Kabel. Engpass ist der Nord-Süd-Transport.
- **Abweichung zur Übergabe von Rolle 6:** Dort stehen 8–9 % überlastete
  Leitungsstunden, hier 18–20 %. `analyze.py` zählt nur Überlast in
  Leitungsrichtung (`loading.gt(1)` ohne Betrag); die Pipeline zählt beide
  Richtungen. Der Redispatch (≈ 2,8 TWh/Woche) stimmt überein. Rolle 6
  informieren.
- **Speicher:** Die Netzanalyse brachte den Workspace auf 10,0 von 10 GB.
  Nur ohne laufenden Solve und nur auf Anforderung rechnen (O7).

### Referenz nach E3 (REF, `de10-ref`), aus der Übergabe von Rolle 3

Stand 2026-11-27. Gelesen aus `workshop/role3/handoff/de10-ref/` (die gelösten
Netze liegen nicht in diesem Workspace). Systemkosten und DE-Preis hat Rolle 3
gegen `evaluate.py` geprüft; die Energiebilanz DE geht je Jahr auf (Rest < 0,001 TWh).

- **Die Importgrenze von E3 hält:** Netto-Import DE 24,7–24,9 TWh/a ab 2030
  (2025: 18 TWh). Ohne Grenze (NB9REF) wären es 90–112 TWh/a. Lastabwurf in
  keinem Jahr. Alle sechs Jahre optimal, Spitzenspeicher 6,5 GB.
- **Die Grenze kostet wenig:** Systemkosten 2030–2045 nur +0,03 bis +0,35 Mrd
  EUR/a gegenüber NB9REF, DE-Preis ±2 EUR/MWh. Die Grenze verschiebt Flüsse,
  nicht Kosten. Für das Kabel heißt das: Es konkurriert mit ~25 TWh Import aus
  den Nachbarn, nicht mit ~100 TWh.
- **2050 ist nicht mehr cap-getrieben:** CO2-Preis 750 EUR/t, Schattenpreis der
  Obergrenze 0. DE-Preis 107 EUR/MWh, höchster Preis 1.600 EUR/MWh,
  1.040 Stunden über 300 EUR/MWh, 11,7 Mt CO2 in DE. 2050 kann damit in die
  Kernaussage, bleibt aber in Abbildungen gekennzeichnet (E3).
- **2045 bleibt bindend:** Die gemeinsame Obergrenze der zehn Länder kostet
  343 EUR/t zusätzlich (effektiv 603 EUR/t). Unter der Schwelle von 1.000 EUR/t,
  aber spürbar.
- **Preisspitzen bleiben:** 980 h (2045) und 1.040 h (2050) über 300 EUR/MWh.
  Das sind die Stunden, in denen ein Kabel Wert schaffen kann.
- **Vergleichbarkeit:** REF rechnet mit 4-h-Schritten und zehn Ländern;
  Systemkosten (~215–235 Mrd EUR/a) gelten für alle zehn Länder. Nur
  Differenzen zwischen Läufen mit derselben Kette sind aussagekräftig
  (CABLE − REF). REF − BASE wird deshalb nicht gezeigt.

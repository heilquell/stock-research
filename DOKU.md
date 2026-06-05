# Stock Crossover Database – Dokumentation

## Überblick

Streamlit-Anwendung zur Analyse, Verwaltung und Filterung von Aktien auf Basis einer lokalen SQLite-Datenbank. Kursdaten und Fundamentaldaten werden über `yfinance` bezogen.

---

## Dateistruktur

| Datei | Zweck |
|---|---|
| `main.py` | Einstiegspunkt, Sidebar, Hauptanalyse, Kauf-/Verkaufssignale |
| `stock_db_ops.py` | Alle Datenbankoperationen (SQLite), Datenimport via yfinance |
| `stock_show.py` | Chart-Rendering (Plotly), Fundamental-Info-Anzeige |
| `stock_screener.py` | Aktien-Screener mit 5 Tabs |

---

## main.py – Hauptbereich

### Sidebar
- **Aktien hinzufügen:** Symbol(e) kommagetrennt eingeben → Kurs- und Infodaten werden geladen und gespeichert
- **Aktien löschen:** Zweistufige Bestätigung vor dem Löschen
- **Kurse / Infos updaten:** Batch-Update aller Aktien in der Datenbank

### Hauptanalyse
1. **Prognose-Slider** – Anzahl Jahre für die Prophet-Prognose (1–10)
2. **Crossover-Faktor-Slider** – Steuert die MA-Länge: `Faktor × 9` / `Faktor × 21`
3. **Aktien-Selectbox** – Auswahl aus allen Aktien in der Datenbank
4. **Favoriten** – Aktie einer Favoritenliste hinzufügen oder entfernen
5. **Chart** – Kurshistorie, Moving Averages, Prophet-Prognose
6. **Fundamental-Info** – Kennzahlen-Karten unterhalb des Charts

### Kauf-/Verkaufssignale
- Slider für Lookback-Tage (1–100) und Crossover-Faktor
- Filter: MA-Trend-Filter, Nur Favoriten
- **Signale berechnen** → Liste der Kauf- und Verkaufssignale
- Klick auf ein Signal → Chart + Info erscheint direkt darunter

---

## stock_screener.py – Aktien-Screener

Aufruf aus `main.py`: `show_screener(_conn, forecast_years, crossover_fak)`

Die übergebenen Werte für `forecast_years` und `crossover_fak` gelten als Standardwert für den Chart-Slider innerhalb des Screeners.

### Gemeinsames Feature: Klick-auf-Zeile → Chart

In allen 5 Tabs gilt: Eine Tabellenzeile anklicken öffnet direkt darunter:
- Einen **Crossover-Faktor-Slider** (vorbelegt mit dem Wert aus der Hauptansicht)
- Den **Kurs-Chart** mit MA-Linien und Prognose
- Die **Fundamental-Kennzahlen**

---

### Tab 1 – Fundamentalscreener

Filtert die `company_info`-Tabelle nach frei wählbaren Kriterien.

| Filter | Beschreibung |
|---|---|
| Sektor | Dropdown, alle Sektoren oder ein bestimmter |
| KGV max | Trailing P/E-Obergrenze (0 = kein Filter) |
| Dividende min % | Mindest-Dividendenrendite |
| Beta-Range | Slider für Volatilitätsbereich |
| ROE min % | Mindesteigenkapitalrendite |
| Gewinnmarge min % | Mindest-Profitmarge |
| Market Cap min | Mindestmarktkapitalisierung in Mrd. |
| Short Ratio max | Maximales Short-Ratio (0 = kein Filter) |
| Nur Analyst-Buy | Analyst-Empfehlung ≤ 2,5 |

**Angezeigte Spalten:** Symbol, Name, Sektor, Kurs, Market Cap, KGV, Div %, Beta, ROE %, Marge %, Short Ratio, Empfehlung

---

### Tab 2 – Technischer Screener

Berechnet MA50 und MA200 aus den letzten 320 Tagen Kursdaten.

| Filter | Beschreibung |
|---|---|
| Kurs > MA50 | Nur Aktien im kurzfristigen Aufwärtstrend |
| Kurs > MA200 | Nur Aktien im langfristigen Aufwärtstrend |
| Kurs < MA50 | Reversal-Kandidaten (überverkauft) |
| MA50 > MA200 | Golden-Cross-Zone (bullisches Umfeld) |
| Abstand MA50 % | Slider: wie weit ist der Kurs vom MA50 entfernt |
| Abstand MA200 % | Slider: wie weit ist der Kurs vom MA200 entfernt |
| 52W-Position min % | Mindestposition innerhalb der 52-Wochen-Spanne |

**Angezeigte Spalten:** Symbol, Name, Sektor, Kurs, MA50, MA200, > MA50, > MA200, Abst. MA50 %, Abst. MA200 %, 52W-Pos %

---

### Tab 3 – Performance-Ranking

Berechnet rollierende Performance aus den letzten 370 Tagen Kursdaten.

| Einstellung | Beschreibung |
|---|---|
| Sortieren nach | 1M %, 3M %, 6M %, 12M % |
| Anzahl anzeigen | 10–200 |
| Nur positive Performance | Filtert Verlustaktien heraus |
| Sektor-Filter | Multiselect für Sektoren |

**Farbgebung:** Grün–Gelb–Rot Gradient (RdYlGn, −20 % bis +20 %)

**Erweiterung:** Sektor-Durchschnitt als aufklappbarer Expander

---

### Tab 4 – Scoring-Modell

Gewichtetes Perzentil-Ranking aller Aktien. Score 0–100.

| Kriterium | Gewichtungs-Slider |
|---|---|
| Momentum (3M %) | 0–10 |
| Dividende | 0–10 |
| Value (KGV, invertiert) | 0–10 |
| Qualität (ROE) | 0–10 |

Jedes Kriterium wird als Perzentil-Rang (0–100) berechnet und gewichtet zusammengefasst. **Höherer Score = besser**.

---

### Tab 5 – Empfehlungen

Kombiniertes Signal aus Trend, Momentum und Fundamentaldaten. Keine manuelle Filterauswahl nötig – der Score ergibt sich automatisch.

#### Kauf-Score (0–7 Punkte)

| Kriterium | Punkte |
|---|---|
| Kurs > MA50 | +1 |
| Kurs > MA200 | +1 |
| MA50 > MA200 (Golden-Cross-Zone) | +1 |
| Abstand MA50 zwischen 0 % und +15 % (nicht überkauft) | +1 |
| 1-Monats-Momentum positiv | +1 |
| 3-Monats-Momentum positiv | +1 |
| Analyst-Empfehlung ≤ 2,5 (Strong Buy / Buy) | +1 |

**Farbgebung:** Grüner Gradient (0–7)

#### Short-Score (0–6 Punkte)

| Kriterium | Punkte |
|---|---|
| Kurs < MA50 | +1 |
| Kurs < MA200 | +1 |
| MA50 < MA200 (Death-Cross-Zone) | +1 |
| Abstand MA50 zwischen −5 % und −20 % (nicht überverkauft) | +1 |
| 1-Monats-Momentum negativ | +1 |
| 3-Monats-Momentum negativ | +1 |

**Farbgebung:** Roter Gradient (0–6)

Einstellbar: Mindestscore und Anzahl der angezeigten Kandidaten jeweils per Slider.

---

## Datenbankstruktur (SQLite)

### Tabelle `stock_data`
| Spalte | Typ | Beschreibung |
|---|---|---|
| symbol | TEXT | Ticker-Symbol |
| date | TEXT | Handelsdatum |
| adj_close | REAL | Bereinigter Schlusskurs |

### Tabelle `company_info`
Enthält alle Fundamental-Felder, die über `yfinance` bezogen werden, u. a.:
`currentprice`, `marketcap`, `trailingpe`, `forwardpe`, `dividend_yield`, `beta`, `returnonequity`, `returnonassets`, `profitmargins`, `shortratio`, `shortpercentoffloat`, `debttoequity`, `recommendationmean`, `recommendationkey`, `pegratio`, `pricetobook`, `sector`, `industry`, `company_name`, `fiftytwoweeklow`, `fiftytwoweekhigh`

---

## Technologie-Stack

| Komponente | Bibliothek |
|---|---|
| Web-UI | Streamlit |
| Charting | Plotly |
| Daten | yfinance |
| Prognose | Prophet |
| Datenbank | SQLite3 (via pandas + sqlite3) |
| Datenverarbeitung | pandas, numpy |

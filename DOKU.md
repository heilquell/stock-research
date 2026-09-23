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

## put_screener.py – Put-Schreiber-Liste (Seite 🛡️ Puts)

Beantwortet eine einzige Frage: Auf welche fundamental soliden Titel kann man
einen weit aus dem Geld liegenden Put verkaufen, ohne dass das historisch oft
schiefgegangen wäre — und was bleibt nach Steuer?

**Ablauf in vier Schritten** (Kommandozeile, nicht in der Seite):

```
python put_screener.py --universum     # Indexmitglieder von Wikipedia
python put_screener.py --fundamental   # Cashflow/Verschuldung je Titel (~15 min)
python put_screener.py --historie      # Kurse 2005–2010 der Kandidaten (einmalig)
python put_screener.py --rechnen       # Backtest, rein lokal
python put_screener.py --selbsttest    # 5 Fälle, ohne Netz
```

Die Seite rechnet nichts selbst, sie liest `put_ergebnis`. Vierhundert
Kursreihen bei jedem Seitenaufruf durchzugehen wäre verschwendete Zeit für ein
Ergebnis, das sich nur einmal täglich ändert.

**Auswahl.** Universum S&P 500 (zum Nasdaq 100 gibt es auf Wikipedia keine
maschinenlesbare Mitgliederliste mehr) **plus die eigene Options-Merkliste**
aus `option_watchlist`. Letztere ist kein Luxus: Der S&P 500 nimmt keine
ausländischen Emittenten auf, ASML, Novo Nordisk oder AstraZeneca können dort
nicht stehen. Die Merkliste steht in der Datenbank und nicht im Code — das
Repository ist öffentlich, die gehandelten Basiswerte sind es nicht. Wer aus
der Merkliste trotzdem nicht in der Tabelle steht, wird auf der Seite mit
Grund aufgeführt. Ausschluss bei negativem freiem
Cashflow oder Nettoverschuldung über dem Vierfachen des EBITDA. Fehlende Werte
schließen ebenfalls aus — ein Filter, der bei Datenlücken durchwinkt, ist
keiner.

**Backtest.** Jede Woche eine gedachte Position, Ausübungspreis 5, 7, 10, 15
oder 20 % unter dem damaligen Kurs, Vergleich mit dem Kurs 5, 10, 21, 63 oder
126 Handelstage später (Handelstage, nicht Kalendertage — die Kursreihe kennt
nur Handelstage; eine Woche sind dort fünf Zeilen). Das volle Kreuz sind 25
Kombinationen je Titel. Erfasst werden Trefferquote, mittlerer und
schlimmster Rückgang im Fehlerfall.

**Warum das Vertrauensintervall auf einer kleineren Zahl steht.**
Wöchentliche Startpunkte bei drei Monaten Laufzeit überlappen sich zu zwölf
Dreizehnteln. Benachbarte Fälle teilen sich den größten Teil ihres
Kursverlaufs und sind keine unabhängigen Versuche. Das Intervall wird deshalb
auf `Fälle × Startabstand ÷ Laufzeit` gerechnet. Bei einer Woche Laufzeit und
wöchentlichem Start überlappt nichts — dort sind beide Zahlen gleich, und das
Intervall ist entsprechend eng (gut 1.000 eigenständige Fälle über 20 Jahre).
Wilson statt Normalnäherung: bei Quoten nahe 100 % ragt letztere über 1
hinaus.

**Rendite und Steuer.** Bezugsgröße ist `Ausübungspreis × 100` — so viel muss
bereitliegen, wenn der Put bar besichert ist. Geschriebene Puts sind
unverbriefte Derivate (§ 27a Abs 2 Z 7 EStG) und damit tarifsteuerpflichtig,
nicht mit 27,5 % endbesteuert; die Seite zeigt beide Renditen.

**Optionskette** nur auf Knopfdruck für einen einzelnen Titel. An derselben
Bibliothek und IP hängt `cron_update.py` für 3.200 Titel; sechzig Kettenabrufe
am Stück wären genau die Last, die zur Drosselung führt.

### Eigene Tabellen

| Tabelle | Inhalt |
|---|---|
| `put_universum` | Indexmitglieder, geschnitten mit `stock_list` |
| `put_fundamental` | freier Cashflow, Nettoverschuldung, EBITDA, Quote |
| `put_hist` | Schlusskurse 2005–2010 — `stock_data` beginnt erst 2009-10-21, ohne diese Jahre fehlt der Crash 2008/09 |
| `put_ergebnis` | fertiger Backtest je Titel und Kombination |

Bewusst getrennt von `stock_data`: Der nächtliche Kurslauf bestimmt seinen
Startpunkt aus dem letzten Eintrag und darf von dieser Seite nichts merken.

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

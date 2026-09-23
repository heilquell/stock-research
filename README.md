# Stock Crossover Research-Tool

Streamlit-Tool für technische Analyse von (~3.500 des Autors) Wertpapieren — 9/21-MA-Crossover-Signale, Prophet-Forecast, Fundamental-Screener, Favoritenlisten. Dazu ein Optionsrechner (Binomialmodell, amerikanische Ausübung) für Rollen, Preis, Kette und implizite Volatilität.

**Live:** https://research.georgshost.eu

## Stack

- **Streamlit 1.61.1** (Python 3.11) — Multipage-App, Google-Anmeldung über `st.login`
- **Plotly 6.9** — Candlestick-, Forecast- und Optionscharts
- **Prophet 1.1.5** + **cmdstanpy 1.3** — Zeitreihen-Forecast (cmdstan 2.33.1 wird im Build installiert)
- **yfinance** — Kurs- und Fundamentaldaten
- **SQLite** — lokaler Datenbestand (`stocks.db`, persistent im Docker-Volume)

## Features

| Page | Funktion |
|---|---|
| 📊 Crossover | Aktien-Chart mit Candlesticks, MA-9/MA-21 (oder Vielfache), Prophet-Forecast 1-10 Jahre, Buy/Sell-Signal-Scanner mit Filtern (MA-Trend, Favoriten), Fundamental-Screener |
| 🧮 Optionen | Rollen (Credit je Verfallstermin, Ertrag pro Tag), Preis & Griechen, Optionskette, implizite Volatilität — samt Andienungswahrscheinlichkeit |
| 🛡️ Puts | S&P-500-Titel plus eigene Basiswerte, Backtest aus dem Geld liegender Puts über das Kreuz aus fünf Abständen (−5 … −20 %) und fünf Laufzeiten (1 Woche … 6 Monate) mit Vertrauensintervall, Prämie je Kontrakt und Rendite p. a. **vor und nach Tarifsteuer** |

### Put-Schreiber-Liste

Gerechnet in `put_screener.py` (streamlit-frei, Selbsttest über
`python put_screener.py --selbsttest`). Universum ist der S&P 500 **plus die
eigene Options-Merkliste** aus der Datenbank — der Index nimmt keine
ausländischen Emittenten auf, ASML oder Novo Nordisk können dort nicht stehen,
obwohl auf sie Optionen gehandelt werden. Es fliegt
raus, wer negativen freien Cashflow hat oder dessen Nettoverschuldung mehr als
das Vierfache des EBITDA beträgt. Für die übrigen wird an jedem Monatsanfang
eine gedachte Position eröffnet und mit dem Kurs 3 bzw. 6 Monate später
verglichen.

Gerechnet wird das volle Kreuz aus fünf Abständen (5, 7, 10, 15, 20 %) und
fünf Laufzeiten (1 Woche, 2 Wochen, 1 Monat, 3 und 6 Monate) — 25
Kombinationen je Titel, knapp 10.000 Backtests in 14 Sekunden (vektorisiert).
Startpunkte liegen **wöchentlich**, nicht monatlich: Bei einer Woche Laufzeit
wären monatliche Starts eine Stichprobe von einem Fünftel der möglichen Fälle,
und gerade die kurzen Laufzeiten sind die interessanten.

Drei Dinge, die kommerzielle Varianten dieser Liste weglassen:

- **Das Vertrauensintervall wird auf der effektiven Fallzahl gerechnet.**
  Monatliche Startpunkte bei drei Monaten Laufzeit überlappen sich zu zwei
  Dritteln; aus 200 Beobachtungen werden rund 67 eigenständige Zeiträume. Wer
  das Intervall auf der rohen Zahl rechnet, verkauft Genauigkeit, die er nicht
  hat. Verwendet wird Wilson, nicht die Normalnäherung — bei Quoten nahe 100 %
  ragt letztere über 1 hinaus.
- **Die Rendite steht neben der Prämie.** 57,50 $ Prämie auf einen bar
  besicherten Put mit Ausübungspreis 75 sind 0,77 % über 87 Tage, also 3,2 %
  im Jahr. Erst diese Zahl macht die Liste zur Entscheidungsgrundlage.
- **Die Steuer ist eingebaut.** Geschriebene Puts sind unverbriefte Derivate
  (§ 27a Abs 2 Z 7 EStG): Tarif statt 27,5 %, kein Ausgleich mit dem
  Aktien-Topf. Aus 3,2 % p. a. werden bei 42 % Grenzsteuer 1,9 %.

Eigene Tabellen (`put_hist`, `put_fundamental`, `put_universum`,
`put_ergebnis`), damit der nächtliche Kurslauf unberührt bleibt. `put_hist`
ist nötig, weil `stock_data` erst 2009 beginnt — ohne die Jahre davor fehlt
der Crash 2008/09 und jede Quote fiele zu schön aus.

Die Optionskette wird einzeln und nur auf Knopfdruck geholt: An derselben
Bibliothek und IP hängt der Kurslauf für 3.200 Titel.

### Optionsrechner

Gerechnet wird mit `Option_api.py`: Cox-Ross-Rubinstein-Binomialbaum mit
amerikanischer Ausübung, Griechen über numerische Ableitung, implizite Vola per
Bisektion. Black-Scholes ist als Vergleichswert enthalten; `norm.cdf` kommt über
`math.erf` statt über scipy, damit für eine einzige Funktion keine 40 MB im
Image liegen.

Drei Entwurfsentscheidungen, die das Ergebnis prägen:

- **Strikes und Verfallstermine werden gelesen, nicht erzeugt.** Ein Raster nach
  Kurshöhe („unter 200 → 5er-Schritte") trifft die Wirklichkeit nicht: das
  Raster hängt am Titel, ist am Geld feiner als in den Flügeln und je Verfall
  verschieden. Ebenso die Termine — Wochenverfälle enden irgendwann und springen
  auf Monatstermine, und manche Werte haben Montags- und Mittwochsverfälle. Die
  Optionskette listet beides; sie wird auf Knopfdruck geholt und der gemessene
  Strike-Abstand je Titel in `strike_raster` gemerkt. Ohne Netz gibt es eine
  berechnete Leiter, sichtbar als solche beschriftet.
- **Die Tageszählung ist einstellbar.** Ob der Verfalltag mitzählt, ist keine
  Kosmetik: bei vier Tagen Restlaufzeit sind das rund drei Vola-Punkte — mehr
  als der Unterschied zwischen amerikanischer und europäischer Ausübung. Yahoos
  implizite Vola trifft die eigene Rechnung erst, wenn beide gleich zählen.
- **Delta ist nicht die Andienungswahrscheinlichkeit.** In Delta steckt d1, in
  der Wahrscheinlichkeit d2; beim Call liegt Delta darüber, beim Put darunter.
  Die Seite zeigt beide Zahlen samt Differenz. Vorzeitige Ausübung wird über den
  verbliebenen Zeitwert erkannt, nicht über ein Dividendendatum.

Marktdaten von Yahoo werden nie beim Seitenaufbau geholt, sondern nur auf
ausdrücklichen Knopfdruck und dann eine Stunde zwischengespeichert: am selben
Zugang hängt der nächtliche Kurs-Cron für alle Titel.

## Lokal starten

```bash
git clone https://github.com/heilquell/stock-research.git
cd stock-research
docker compose up -d --build
# → http://localhost:8501
```

Die DB (`data/stocks.db`) wird beim ersten Start automatisch mit leerer Tabellenstruktur angelegt. Aktien per Sidebar hinzufügen — yfinance lädt Kurse und Stammdaten.

## Server-Deployment (mit Traefik)

`docker-compose.yml` enthält Traefik-Labels für HTTPS + Sticky-Sessions. Anpassen:

```yaml
labels:
  - traefik.http.routers.research.rule=Host(`research.deine-domain.tld`)
```

Externes Traefik-Netzwerk muss `traefik-proxy` heißen (anpassen in `docker-compose.yml` falls anders).

## Daten

- **DB nicht im Repo** — `data/`-Volume bleibt beim Container.
- `stock_db_ops.init_db()` legt die Grundtabellen an (`stock_list`, `stock_data`, `company_info`, `fav_names`, `fav_list`, `sentences`).
- Die Optionen-Seite legt bei Bedarf zwei weitere an: `option_watchlist` (Merkliste je angemeldeter Adresse) und `strike_raster` (gemessener Strike-Abstand je Titel). Beide stehen bewusst in der Datenbank und nicht im Code — dieses Repository ist öffentlich, die beobachteten Basiswerte sind es nicht.
- yfinance-Updates via Sidebar-Buttons („alle Aktien Kurse updaten" / „alle Aktien-Infos updaten").

## Architektur-Doku

Siehe [DOKU.md](DOKU.md) für detailliertere Beschreibung von Modulen und Pipeline. Achtung: DOKU.md stammt aus der Zeit vor der Multipage-Aufteilung und beschreibt `main.py` noch als Hauptanalyse; die Modulbeschreibungen dort stimmen, die Navigation nicht mehr.

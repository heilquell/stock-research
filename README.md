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

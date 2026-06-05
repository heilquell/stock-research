# Stock Crossover Research-Tool

Streamlit-Tool für technische Analyse von ~3.500 Wertpapieren — 9/21-MA-Crossover-Signale, Prophet-Forecast, Fundamental-Screener, Favoritenlisten.

**Live:** https://research.georgshost.eu

## Stack

- **Streamlit 1.58** (Python 3.11) — Multipage-App
- **Plotly 6.8** — Candlestick + Forecast-Charts
- **Prophet 1.1.5** + **cmdstanpy 1.3** — Zeitreihen-Forecast (cmdstan 2.33.1 wird im Build installiert)
- **yfinance** — Kurs- und Fundamentaldaten
- **SQLite** — lokaler Datenbestand (`stocks.db`, persistent im Docker-Volume)

## Features

| Page | Funktion |
|---|---|
| 📊 Crossover | Aktien-Chart mit Candlesticks, MA-9/MA-21 (oder Vielfache), Prophet-Forecast 1-10 Jahre, Buy/Sell-Signal-Scanner mit Filtern (MA-Trend, Favoriten), Fundamental-Screener |

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
- `stock_db_ops.init_db()` legt 5 Tabellen an (`stock_list`, `stock_data`, `company_info`, `fav_names`, `fav_list`, `sentences`).
- yfinance-Updates via Sidebar-Buttons („alle Aktien Kurse updaten" / „alle Aktien-Infos updaten").

## Architektur-Doku

Siehe [DOKU.md](DOKU.md) für detailliertere Beschreibung von Modulen und Pipeline.

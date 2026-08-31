"""Datenschicht der Optionen-Seite.

Trennt bewusst drei Quellen, die auf der Seite nebeneinander stehen:

* **Kursdatenbank** (``stocks.db``, taeglich vom Cron gefuellt) — Kurs und
  historische Volatilitaet. Vergangenheit, kostenlos, immer da.
* **Yahoo-Optionskette** — Marktpreise und Yahoos eigene implizite Vola.
  Zukunft, aber nur auf ausdruecklichen Knopfdruck: der naechtliche Kurs-Cron
  haengt an derselben IP und an derselben Bibliothek. Zoege die Seite bei jedem
  Klick eine Kette, riskierte man die Drosselung genau der Verbindung, die die
  3.200 Titel aktualisiert.
* **Eigene Rechnung** (``Option_api``) — Binomialbaum, amerikanische Ausuebung.

Die Merkliste steht in der Datenbank und nicht im Code: das Repository ist
oeffentlich, die gehandelten Basiswerte sind es nicht.
"""
from __future__ import annotations

import math
import os
import sqlite3
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

DB_PATH = os.environ.get("STOCKS_DB", "/data/stocks.db")

# Handelstage pro Jahr. Die Volatilitaet wird aus Tagesschlusskursen
# hochskaliert, und Kurse gibt es nur an Handelstagen — mit 365 statt 252
# waere jede Vola um gut 20 % zu hoch.
HANDELSTAGE = 252


def verbindung() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH, timeout=5)


# --------------------------------------------------------------------------
# Merkliste
# --------------------------------------------------------------------------
def watchlist_anlegen() -> None:
    with verbindung() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS option_watchlist (
                       symbol     TEXT NOT NULL,
                       user_email TEXT NOT NULL DEFAULT '',
                       created_at TEXT NOT NULL DEFAULT (datetime('now')),
                       PRIMARY KEY (symbol, user_email))""")


def watchlist(user: str | None) -> list[str]:
    """Merkliste des Nutzers; ohne Anmeldung die geteilte Liste (user_email '')."""
    watchlist_anlegen()
    with verbindung() as c:
        rows = c.execute(
            "SELECT symbol FROM option_watchlist WHERE user_email IN (?, '') "
            "ORDER BY symbol", (user or "",)).fetchall()
    return sorted({r[0] for r in rows})


def watchlist_add(symbol: str, user: str | None) -> None:
    watchlist_anlegen()
    with verbindung() as c:
        c.execute("INSERT OR IGNORE INTO option_watchlist (symbol, user_email) "
                  "VALUES (?, ?)", (symbol.upper().strip(), user or ""))


def watchlist_del(symbol: str, user: str | None) -> None:
    with verbindung() as c:
        c.execute("DELETE FROM option_watchlist WHERE symbol = ? AND user_email = ?",
                  (symbol, user or ""))


# --------------------------------------------------------------------------
# Kurse und historische Vola aus der eigenen Datenbank
# --------------------------------------------------------------------------
@st.cache_data(ttl=900)
def kursreihe(symbol: str, n: int = 300) -> pd.DataFrame:
    """Letzte ``n`` Schlusskurse.

    ``close IS NOT NULL AND close > 0`` ist kein Zierrat: in ``stock_data``
    stehen einige tausend Zeilen ohne Schlusskurs. Ohne den Filter faellt die
    Log-Return-Rechnung darueber.
    """
    with verbindung() as c:
        df = pd.read_sql_query(
            "SELECT date, close FROM stock_data "
            " WHERE symbol = ? AND close IS NOT NULL AND close > 0 "
            " ORDER BY date DESC LIMIT ?", c, params=(symbol, n))
    return df.iloc[::-1].reset_index(drop=True)


@st.cache_data(ttl=900)
def letzter_kurs(symbol: str) -> tuple[str, float] | None:
    df = kursreihe(symbol, 5)
    if df.empty:
        return None
    return df.iloc[-1]["date"], float(df.iloc[-1]["close"])


@st.cache_data(ttl=900)
def hist_vola(symbol: str, fenster: tuple[int, ...] = (30, 60, 252)) -> dict[int, float]:
    """Annualisierte Standardabweichung der Log-Renditen je Fenster."""
    df = kursreihe(symbol, max(fenster) + 5)
    kurse = df["close"].tolist()
    out: dict[int, float] = {}
    for f in fenster:
        if len(kurse) < f + 1:
            continue
        teil = kurse[-(f + 1):]
        lr = [math.log(teil[i + 1] / teil[i]) for i in range(len(teil) - 1)]
        if len(lr) < 2:
            continue
        m = sum(lr) / len(lr)
        var = sum((x - m) ** 2 for x in lr) / len(lr)
        out[f] = math.sqrt(var) * math.sqrt(HANDELSTAGE)
    return out


@st.cache_data(ttl=3600)
def firmeninfo(symbol: str) -> dict:
    with verbindung() as c:
        try:
            row = c.execute(
                "SELECT shortname, currency, beta, sector FROM company_info "
                " WHERE symbol = ?", (symbol,)).fetchone()
        except sqlite3.OperationalError:
            return {}
    if not row:
        return {}
    return {"name": row[0], "waehrung": row[1], "beta": row[2], "sektor": row[3]}


@st.cache_data(ttl=900)
def symbol_liste() -> list[str]:
    with verbindung() as c:
        return [r[0] for r in c.execute("SELECT symbol FROM stock_list ORDER BY symbol")]


# --------------------------------------------------------------------------
# Yahoo-Optionskette — nur auf Knopfdruck, Ergebnis eine Stunde gehalten
# --------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def yahoo_verfallsdaten(symbol: str) -> list[str]:
    import yfinance as yf
    try:
        return list(yf.Ticker(symbol).options)
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def _yahoo_kette_roh(symbol: str, verfall: str) -> dict[str, pd.DataFrame]:
    """Ein Abruf liefert Puts UND Calls — also auch nur einmal anfragen.

    Ohne diese Zwischenstufe holte jede Seite des Buches ihre eigene Kette und
    verdoppelte die Anfragen an Yahoo, obwohl beide in derselben Antwort
    stehen.
    """
    import yfinance as yf
    ch = yf.Ticker(symbol).option_chain(verfall)
    return {"put": ch.puts.copy(), "call": ch.calls.copy()}


def yahoo_kette(symbol: str, verfall: str, typ: str) -> pd.DataFrame:
    """Optionskette eines Verfalltags.

    ``mid`` ist die Mitte aus bid/ask und die einzige Preisspalte, auf die man
    eine implizite Vola rechnen darf. ``lastPrice`` ist der letzte *Handel* —
    bei duennen Kontrakten Wochen alt, ohne dass die Zahl das verriete.
    """
    df = _yahoo_kette_roh(symbol, verfall)[typ].copy()
    spalten = ["strike", "bid", "ask", "lastPrice", "impliedVolatility",
               "volume", "openInterest", "lastTradeDate"]
    df = df[[s for s in spalten if s in df.columns]]
    df["mid"] = [(b + a) / 2 if (b and a and b > 0 and a > 0) else float("nan")
                 for b, a in zip(df["bid"], df["ask"])]
    return df


def tage_bis(verfall: str | date, heute: date | None = None,
             verfalltag_mitzaehlen: bool = True) -> int:
    """Restlaufzeit in Tagen.

    ``verfalltag_mitzaehlen`` ist kein Detail: Yahoos implizite Vola stimmt mit
    unserer erst ueberein, wenn der Verfalltag mitgezaehlt wird. Bei vier Tagen
    Restlaufzeit macht der eine Tag rund drei Vola-Punkte aus — mehr, als
    zwischen amerikanischer und europaeischer Ausuebung liegt. Wer die beiden
    Zahlen nebeneinanderstellt, muss dieselbe Zaehlung benutzen.
    """
    if isinstance(verfall, str):
        verfall = date.fromisoformat(verfall)
    if isinstance(verfall, datetime):
        verfall = verfall.date()
    heute = heute or date.today()
    return (verfall - heute).days + (1 if verfalltag_mitzaehlen else 0)


def naechste_freitage(anzahl: int = 8, ab: date | None = None) -> list[date]:
    ab = ab or date.today()
    tage = (4 - ab.weekday()) % 7 or 7
    erster = ab + timedelta(days=tage)
    return [erster + timedelta(weeks=i) for i in range(anzahl)]

# --------------------------------------------------------------------------
# Strike-Raster
# --------------------------------------------------------------------------
# Ein Wert je Kurshoehe — "unter 50 → 2,5, unter 200 → 5, darueber 10" — ist
# das falsche Modell. Am 31.08.2026 nachgemessen: ASML steht bei 1.696 und hat
# 5er-Schritte (am Geld 2,50), INTC steht bei 90 und hat 1er-Schritte. Das
# Raster haengt am Titel, nicht an der Kurshoehe; es ist am Geld fein und in
# den Fluegeln grob; und es unterscheidet sich je Verfall (ADBE woechentlich
# 2,50, monatlich 5,00).
#
# Deshalb die Rangfolge: echte Strikes aus der Kette schlagen jede Schaetzung.
# Wo keine Kette vorliegt, zaehlt der zuletzt gemessene Abstand, dann der aus
# der eigenen Handelshistorie abgeleitete, und erst zuletzt die Kurs-Staffel.
def strike_raster_anlegen() -> None:
    with verbindung() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS strike_raster (
                       symbol      TEXT PRIMARY KEY,
                       schritt     REAL NOT NULL,
                       quelle      TEXT NOT NULL,
                       gemessen_am TEXT NOT NULL DEFAULT (datetime('now')))""")


def staffel_nach_kurs(kurs: float) -> float:
    """Letzter Ausweg, wenn ueber den Titel nichts bekannt ist."""
    return 2.5 if kurs < 50 else 5.0 if kurs < 200 else 10.0


def strike_schritt(symbol: str, kurs: float) -> tuple[float, str]:
    """Abstand zwischen zwei Strikes samt Herkunft der Angabe."""
    strike_raster_anlegen()
    with verbindung() as c:
        row = c.execute("SELECT schritt, quelle, gemessen_am FROM strike_raster "
                        " WHERE symbol = ?", (symbol,)).fetchone()
    if row:
        return float(row[0]), f"{row[1]}, {row[2][:10]}"
    return staffel_nach_kurs(kurs), "geschätzt nach Kurshöhe"


def strike_schritt_merken(symbol: str, schritt: float, quelle: str) -> None:
    strike_raster_anlegen()
    with verbindung() as c:
        c.execute("INSERT OR REPLACE INTO strike_raster (symbol, schritt, quelle, "
                  "gemessen_am) VALUES (?, ?, ?, datetime('now'))",
                  (symbol, float(schritt), quelle))


def raster_aus_strikes(strikes: list[float], kurs: float) -> float | None:
    """Haeufigster Abstand am Geld — das ist der Wert, der zaehlt.

    Gemessen wird bewusst nur innerhalb von fuenf Prozent um den Kurs: in den
    Fluegeln sind die Abstaende ein Vielfaches davon, und dort wird ohnehin
    nicht gehandelt.
    """
    strikes = sorted(set(float(k) for k in strikes))
    if len(strikes) < 3:
        return None
    nah = [round(b - a, 4) for a, b in zip(strikes, strikes[1:])
           if abs(a - kurs) <= kurs * 0.05]
    if not nah:
        nah = [round(b - a, 4) for a, b in zip(strikes, strikes[1:])]
    if not nah:
        return None
    from collections import Counter
    return float(Counter(nah).most_common(1)[0][0])


def naechster_strike(kurs: float, abstand_pct: float, symbol: str) -> float:
    """Strike in der Naehe von ``kurs * (1 + abstand_pct/100)``, auf dem Raster."""
    schritt, _ = strike_schritt(symbol, kurs)
    ziel = kurs * (1 + abstand_pct / 100)
    return round(round(ziel / schritt) * schritt, 4)

"""Nächtlicher Kurs-Update fuer alle Aktien in der DB.

Streamlit-frei (im Gegensatz zu update_stock_data in stock_db_ops.py).
Aufruf: docker exec research-tool python cron_update.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timedelta
from time import sleep, time

from stock_db_ops import (
    get_all_stocks,
    get_last_entry_date,
    get_stock_data,
    save_to_db,
)

# Kapitalmassnahmen, an denen sich der Massstab der Reihe aendert.
# Yahoo rechnet die Historie nach einem Split zurueck -- diese Tabelle nicht,
# denn sie waechst nur nach vorn. Ohne Gegenmassnahme steht mitten in der
# Reihe ein Sprung, den es nie gab: Amphenol fiel am 03.09.2026 von 160,08
# auf 82,07, weil dort ein 2:1-Split lag. Ein Scan ueber alle Kurse ueber
# 5 $ fand 126 betroffene Titel -- jeder davon verfaelscht MA-Signale,
# Forecast und jeden Backtest, der ueber die Stelle laeuft.
SPLIT_JAHRE = 15          # so weit reicht der Bestand zurueck
SPLIT_SCHWELLE = 0.35     # Tagesbewegung, ab der genauer hingesehen wird
SPLIT_VERHAELTNISSE = (0.5, 1/3, 0.25, 0.2, 0.1, 2, 3, 4, 5, 10, 20)


def _ist_split_verhaeltnis(faktor: float, toleranz: float = 0.03) -> str | None:
    """Liegt der Sprung nahe an einem uebliches Split-Verhaeltnis?

    Preisbewegungen von 40 % gibt es wirklich (AMD nach Zahlen 2016, APA im
    Oelcrash 2020). Ein 2:1-Split trifft dagegen fast exakt den Faktor 0,5.
    Die Naehe zum glatten Verhaeltnis unterscheidet beides -- nicht perfekt,
    aber gut genug, um den Verdacht zu pruefen statt blind neu zu laden.
    """
    for ziel in SPLIT_VERHAELTNISSE:
        if abs(faktor / ziel - 1) < toleranz:
            return f"{ziel:g}"
    return None


def voll_neu_laden(conn: sqlite3.Connection, symbol: str) -> int:
    """Die gesamte Reihe eines Titels verwerfen und frisch holen.

    Nur so wird der Massstab wieder einheitlich: Yahoo liefert die Historie
    auf den heutigen Stand zurueckgerechnet, und genau die kommt in die
    Tabelle -- nicht ein weiterer Anbau an eine veraltete Basis.
    """
    ende = datetime.today().date()
    beginn = ende - timedelta(days=SPLIT_JAHRE * 365)
    # Nicht kuerzer werden als das, was schon da ist: Der Bestand reicht bei
    # vielen Titeln bis 2009 zurueck, ein pauschales 15-Jahre-Fenster wuerde
    # beim Neuladen zwei Jahre Historie stillschweigend wegwerfen.
    vorhanden = conn.execute(
        "SELECT min(date) FROM stock_data WHERE symbol = ?",
        (symbol.upper(),)).fetchone()
    if vorhanden and vorhanden[0]:
        try:
            alt_datum = datetime.strptime(vorhanden[0][:10], "%Y-%m-%d").date()
            beginn = min(beginn, alt_datum)
        except ValueError:
            pass
    frisch = get_stock_data(symbol, beginn, ende)
    if frisch is None or frisch.empty:
        return 0
    conn.execute("DELETE FROM stock_data WHERE symbol = ?", (symbol.upper(),))
    conn.commit()
    save_to_db(conn, symbol, frisch)
    return len(frisch)


def split_im_zeitraum(data) -> bool:
    """Hat Yahoo im gerade geholten Fenster einen Split gemeldet?

    ``history()`` fuehrt die Spalte "Stock Splits" mit; sie ist an
    Split-Tagen ungleich null. Das ist die verlaessliche Quelle -- die
    Sprungerkennung weiter unten ist nur das Netz darunter, fuer Faelle, in
    denen der Split vor dem geholten Fenster lag.
    """
    spalte = data.get("Stock Splits") if hasattr(data, "get") else None
    try:
        return bool(spalte is not None and (spalte.fillna(0) != 0).any())
    except Exception:
        return False


def verdaechtiger_sprung(conn: sqlite3.Connection, symbol: str, data):
    """Passt der erste neue Kurs nicht zum letzten gespeicherten?

    Faengt den Fall ab, dass der Split zwischen zwei Laeufen lag und im
    geholten Fenster nicht mehr als Ereignis auftaucht.
    """
    letzte = conn.execute(
        "SELECT close FROM stock_data WHERE symbol = ? ORDER BY date DESC LIMIT 1",
        (symbol.upper(),)).fetchone()
    if not letzte or not letzte[0] or data.empty:
        return None
    erster_neuer = float(data["Close"].iloc[0])
    faktor = erster_neuer / float(letzte[0])
    if abs(faktor - 1) < SPLIT_SCHWELLE:
        return None
    return _ist_split_verhaeltnis(faktor)


def altlasten_reparieren(conn: sqlite3.Connection, min_kurs: float = 1.0,
                         probe: int | None = None) -> dict:
    """Einmalig: Titel finden, deren Reihe bereits einen Split-Sprung enthaelt.

    Die Erkennung oben verhindert neue Faelle. Die alten stehen weiterhin in
    der Tabelle -- der Sprung liegt ja mitten in der Reihe, nicht am Rand.
    Diese Funktion sucht sie und laedt die Betroffenen einmal komplett neu.

    ``min_kurs`` haelt Pennystocks draussen: Bei Kursen um 0,004 ist jedes
    Verhaeltnis zufaellig nahe an 2:1, und die Titel interessieren hier
    niemanden.
    """
    kandidaten = conn.execute(
        """WITH x AS (
               SELECT symbol, date, close,
                      LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS vor
               FROM stock_data
           )
           SELECT DISTINCT symbol FROM x
            WHERE vor > ? AND close > ? AND (close/vor > 1.6 OR close/vor < 0.625)
            ORDER BY symbol""", (min_kurs * 5, min_kurs)).fetchall()

    betroffen = []
    for (sym,) in kandidaten:
        reihe = conn.execute(
            "SELECT date, close FROM stock_data WHERE symbol = ? ORDER BY date",
            (sym,)).fetchall()
        for (d1, c1), (d2, c2) in zip(reihe, reihe[1:]):
            if not c1 or not c2 or c1 <= min_kurs * 5:
                continue
            art = _ist_split_verhaeltnis(c2 / c1)
            if art:
                betroffen.append((sym, d2, art))
                break

    if probe:
        betroffen = betroffen[:probe]
    geladen = 0
    for sym, tag, art in betroffen:
        try:
            zeilen = voll_neu_laden(conn, sym)
            geladen += 1
            print(f"  {sym:6s} Sprung {tag} ({art}) — {zeilen} Zeilen neu")
        except Exception as exc:
            print(f"  {sym:6s} FEHLER: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
        sleep(0.4)
    return {"gefunden": len(betroffen), "neu_geladen": geladen}


def main() -> int:
    if "--reparieren" in sys.argv:
        db_path = os.environ.get("STOCKS_DB", "/data/stocks.db")
        conn = sqlite3.connect(db_path)
        probe = None
        if "--probe" in sys.argv:
            probe = int(sys.argv[sys.argv.index("--probe") + 1])
        print(f"[{datetime.now():%F %T}] Suche Reihen mit Split-Sprung …")
        print(altlasten_reparieren(conn, probe=probe))
        conn.close()
        return 0

    db_path = os.environ.get("STOCKS_DB", "/data/stocks.db")
    conn = sqlite3.connect(db_path)

    stocks, _, _ = get_all_stocks(conn)
    today = datetime.today().date()
    fifteen_years_ago = today - timedelta(days=15 * 365)

    t_start = time()
    n_ok = n_skipped = n_empty = n_failed = n_split = 0
    batch_size = 100
    batch_pause = 5  # Sek. nach jeder 100er-Charge — wie im UI-Pfad

    print(f"[{datetime.now():%F %T}] Start — {len(stocks)} Aktien")

    for i, symbol in enumerate(stocks, start=1):
        symbol = symbol.upper()

        if i > 1 and i % batch_size == 1:
            sleep(batch_pause)

        last_date = get_last_entry_date(conn, symbol)
        start_date = (
            datetime.strptime(last_date, "%Y-%m-%d").date() + timedelta(days=1)
            if last_date
            else fifteen_years_ago
        )

        if start_date >= today:
            n_skipped += 1
            continue

        try:
            data = get_stock_data(symbol, start_date, today)
            if data.empty:
                n_empty += 1
            else:
                grund = ("Split gemeldet" if split_im_zeitraum(data)
                         else None)
                if grund is None:
                    verhaeltnis = verdaechtiger_sprung(conn, symbol, data)
                    if verhaeltnis:
                        grund = f"Kurssprung im Verhaeltnis {verhaeltnis}"
                if grund:
                    # Anhaengen wuerde den Sprung festschreiben -- also die
                    # ganze Reihe neu, auf einheitlichem Massstab.
                    zeilen = voll_neu_laden(conn, symbol)
                    n_split += 1
                    print(f"  SPLIT {symbol}: {grund} — Reihe neu geladen "
                          f"({zeilen} Zeilen)")
                else:
                    save_to_db(conn, symbol, data)
                n_ok += 1
        except Exception as e:
            n_failed += 1
            print(f"  FAIL {symbol}: {e}", file=sys.stderr)

    dur = round(time() - t_start, 1)
    print(
        f"[{datetime.now():%F %T}] Ende — ok={n_ok} skipped={n_skipped} "
        f"empty={n_empty} failed={n_failed} splits={n_split} dauer={dur}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

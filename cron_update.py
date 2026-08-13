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


def main() -> int:
    db_path = os.environ.get("STOCKS_DB", "/data/stocks.db")
    conn = sqlite3.connect(db_path)

    stocks, _, _ = get_all_stocks(conn)
    today = datetime.today().date()
    fifteen_years_ago = today - timedelta(days=15 * 365)

    t_start = time()
    n_ok = n_skipped = n_empty = n_failed = 0
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
                save_to_db(conn, symbol, data)
                n_ok += 1
        except Exception as e:
            n_failed += 1
            print(f"  FAIL {symbol}: {e}", file=sys.stderr)

    dur = round(time() - t_start, 1)
    print(
        f"[{datetime.now():%F %T}] Ende — ok={n_ok} skipped={n_skipped} "
        f"empty={n_empty} failed={n_failed} dauer={dur}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

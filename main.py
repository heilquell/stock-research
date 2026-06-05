import streamlit as st
import sqlite3
import os
from datetime import datetime

st.set_page_config(
    page_title="Stock Crossover Database",
    page_icon="📊",
    layout="wide",
)

DB_PATH = os.environ.get("STOCKS_DB", "/data/stocks.db")


@st.cache_data(ttl=300)
def overview_stats():
    """Liest grundlegende Status-Werte aus der DB. Defensiv: falls DB
    fehlt/leer/Tabellen nicht da → leeres Dict zurück."""
    if not os.path.exists(DB_PATH):
        return None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        cur = conn.cursor()

        def safe_count(query):
            try:
                return cur.execute(query).fetchone()[0]
            except Exception:
                return None

        stats = {
            "n_stocks": safe_count("SELECT COUNT(DISTINCT symbol) FROM stock_list"),
            "n_data_rows": safe_count("SELECT COUNT(*) FROM stock_data"),
            "n_favs": safe_count("SELECT COUNT(*) FROM fav_list"),
            "last_date": None,
            "db_size_mb": round(os.path.getsize(DB_PATH) / (1024 * 1024), 1),
        }
        try:
            row = cur.execute("SELECT MAX(date) FROM stock_data").fetchone()
            stats["last_date"] = row[0] if row else None
        except Exception:
            pass
        conn.close()
        return stats
    except Exception as exc:
        return {"error": str(exc)}


st.title("📊 Stock Crossover Database")
st.write("Technische Analyse mit 9/21-Crossover, Prophet-Forecasts und Fundamental-Screener.")

stats = overview_stats()

if stats is None:
    st.error(
        f"❌ Datenbank nicht gefunden unter `{DB_PATH}`. "
        f"Setze die Umgebungsvariable `STOCKS_DB` auf den korrekten Pfad oder mounte das Volume."
    )
elif "error" in stats:
    st.warning(f"⚠ DB-Verbindung fehlgeschlagen: {stats['error']}")
else:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Aktien", f"{stats['n_stocks']:,}" if stats["n_stocks"] is not None else "—")
    col2.metric("Kurs-Datensätze", f"{stats['n_data_rows']:,}" if stats["n_data_rows"] is not None else "—")
    col3.metric("Favoriten", stats["n_favs"] if stats["n_favs"] is not None else "—")
    col4.metric("DB-Größe", f"{stats['db_size_mb']} MB")

    if stats["last_date"]:
        st.caption(f"Letzter Kurs in DB: **{stats['last_date']}**")

st.divider()

st.subheader("Tools")
st.page_link(
    "pages/1_📊_Crossover.py",
    label="Crossover — Charts, Signale, Screener",
    icon="📊",
)

st.caption("Weitere Tools folgen.")

with st.expander("Dokumentation"):
    doku_path = os.path.join(os.path.dirname(__file__), "DOKU.md")
    if os.path.exists(doku_path):
        with open(doku_path, "r", encoding="utf-8") as f:
            st.markdown(f.read())
    else:
        st.info("Keine `DOKU.md` gefunden.")

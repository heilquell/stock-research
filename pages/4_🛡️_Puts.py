"""Puts schreiben — fundamental solide Titel, weit aus dem Geld.

Die Seite beantwortet eine einzige Frage: Auf welche Aktien kann man einen
deutlich aus dem Geld liegenden Put verkaufen, ohne dass das in der
Vergangenheit oft schiefgegangen waere — und was bleibt nach Steuer davon?

Gerechnet wird in ``put_screener`` (streamlit-frei, mit Selbsttest). Hier
steht nur die Darstellung.

Drei Entscheidungen, die die Seite von kommerziellen Vorbildern unterscheiden:

* Neben jeder Quote steht ihr **Vertrauensintervall**. "100 % gehalten" auf
  25 eigenstaendigen Zeitraeumen ist etwas anderes als dieselbe Zahl auf 67.
* Die **Rendite auf das gebundene Kapital** steht gleichberechtigt neben der
  Praemie. Sie ist die Zahl, die entscheidet, und sie ist meist ernuechternd.
* Die **Steuer** ist eingebaut, nicht angehaengt: Geschriebene Puts sind
  unverbriefte Derivate und damit tarifsteuerpflichtig.
"""
from datetime import date

import pandas as pd
import streamlit as st

import put_screener as ps
from auth import sidebar_login

st.set_page_config(page_title="Puts", page_icon="🛡️", layout="wide")
sidebar_login()

st.title("🛡️ Puts schreiben")

KOMBI_NAMEN = {
    "15/3": "15 % unter Kurs, 3 Monate",
    "15/6": "15 % unter Kurs, 6 Monate",
    "20/6": "20 % unter Kurs, 6 Monate",
}


@st.cache_data(ttl=900, show_spinner=False)
def _rangliste(kombi: str) -> pd.DataFrame:
    conn = ps.verbindung()
    try:
        return ps.rangliste(conn, kombi)
    finally:
        conn.close()


@st.cache_data(ttl=900, show_spinner=False)
def _stand() -> tuple[str | None, int]:
    conn = ps.verbindung()
    try:
        r = conn.execute("SELECT max(stand), count(DISTINCT symbol) "
                         "FROM put_ergebnis").fetchone()
        return (r[0], r[1] or 0)
    except Exception:
        return (None, 0)
    finally:
        conn.close()


stand, n_titel = _stand()
if not stand:
    st.info(
        "Noch nichts gerechnet. Der Rechenkern wird ausserhalb der Seite "
        "angestossen: `docker exec research-tool python -c "
        "\"import put_screener as p; p.universum_laden(); "
        "p.alles_rechnen()\"`"
    )
    st.stop()

links, rechts = st.columns([3, 2])
with links:
    kombi = st.radio("Kombination", list(KOMBI_NAMEN),
                     format_func=KOMBI_NAMEN.get, horizontal=True)
with rechts:
    grenzsteuer = st.slider(
        "Grenzsteuersatz für die Nettorechnung (%)", 0, 55, 42, step=1,
        help="Geschriebene Puts sind unverbriefte Derivate (§ 27a Abs 2 Z 7 "
             "EStG): Tarifsteuer statt 27,5 %, kein Ausgleich mit dem "
             "Aktien-Topf.")

df = _rangliste(kombi)
if df.empty:
    st.warning("Für diese Kombination liegt noch kein Ergebnis vor.")
    st.stop()

nur_belastbar = st.checkbox(
    f"Nur Titel mit mindestens {ps.MIN_EIGENSTAENDIG} eigenständigen Zeiträumen",
    value=True,
    help="Sonst stehen Titel oben, deren Quote auf einer Handvoll Fälle beruht.")
if nur_belastbar:
    df = df[df["eigenstaendig"] >= ps.MIN_EIGENSTAENDIG]

anzeige = pd.DataFrame({
    "Symbol": df["symbol"],
    "Name": df["name"],
    "Sektor": df["sektor"],
    "Kurs": df["kurs"].round(2),
    "gehalten": (100 * (1 - df["p_ausuebung"])).round(1),
    "davon sicher ab": (100 * df["ci_lo"]).round(1),
    "Ø Rückgang wenn nicht": df["mittl_rueckgang"].round(1),
    "schlimmster Fall": df["max_rueckgang"].round(1),
    "Zeiträume": df["eigenstaendig"],
    "Schulden/EBITDA": df["schulden_ebitda"].round(1),
    "Historie ab": df["historie_ab"],
})
st.dataframe(
    anzeige, use_container_width=True, hide_index=True, height=430,
    column_config={
        "gehalten": st.column_config.NumberColumn(
            "gehalten %", help="Anteil der Fälle, in denen der Kurs bei "
                               "Verfall über dem Ausübungspreis blieb."),
        "davon sicher ab": st.column_config.NumberColumn(
            "Untergrenze %", help="Untere Grenze des 95-%-Vertrauens"
                                  "intervalls, gerechnet auf den sich nicht "
                                  "überlappenden Zeiträumen."),
        "Ø Rückgang wenn nicht": st.column_config.NumberColumn(
            "Ø Rückgang %", help="Wie weit der Kurs unter dem Ausübungspreis "
                                 "lag, wenn er darunter lag."),
        "schlimmster Fall": st.column_config.NumberColumn("max. %"),
    })

st.caption(
    f"Stand {stand} · {n_titel} Titel · Universum S&P 500, gefiltert auf "
    "positiven freien Cashflow und Nettoverschuldung ≤ 4× EBITDA."
)

# --------------------------------------------------------------------------
# Praemie und Rendite fuer einen Titel
# --------------------------------------------------------------------------
st.divider()
st.subheader("Prämie und Rendite")
st.caption(
    "Die Optionskette wird einzeln und nur auf Knopfdruck geholt: An derselben "
    "Verbindung hängt der nächtliche Kurslauf für 3.200 Titel."
)

sp1, sp2 = st.columns([1, 3])
with sp1:
    symbol = st.selectbox("Titel", list(df["symbol"]))
    holen = st.button("Prämie holen", type="primary")

if holen and symbol:
    zeile = df[df["symbol"] == symbol].iloc[0]
    abstand, monate = (int(x) for x in kombi.split("/"))
    with st.spinner(f"Optionskette {symbol} …"):
        pr = ps.praemie_fuer(symbol, abstand, monate, kurs=float(zeile["kurs"]))
    if not pr or pr["mid"] != pr["mid"]:
        st.warning(
            "Keine brauchbare Notierung: Entweder gibt es zu diesem Verfall "
            "keine Kette, oder Geld- und Briefkurs fehlen. Ohne beide Seiten "
            "lässt sich keine Mitte bilden — `lastPrice` wäre womöglich "
            "wochenalt.")
    else:
        r = ps.rendite(pr["mid"], pr["strike"], pr["tage"], grenzsteuer)
        with sp2:
            a, b, c, d = st.columns(4)
            a.metric("Ausübungspreis", f"{pr['strike']:.2f} $",
                     f"Ziel {pr['ziel_strike']:.2f}")
            b.metric("Prämie je Kontrakt", f"{r['praemie_kontrakt']:.0f} $",
                     f"{pr['bid']:.2f} / {pr['ask']:.2f} Geld/Brief")
            c.metric("Rendite p. a.", f"{100 * r['rendite_pa']:.2f} %",
                     f"{100 * r['rendite_periode']:.2f} % über {pr['tage']} Tage")
            d.metric(f"nach {grenzsteuer} % Steuer",
                     f"{100 * r['rendite_pa_netto']:.2f} %",
                     f"−{100 * (r['rendite_pa'] - r['rendite_pa_netto']):.2f} Pp",
                     delta_color="inverse")
            st.caption(
                f"Verfall {pr['verfall']} · gebundenes Kapital "
                f"{r['kapital']:,.0f} $ bei barer Besicherung · "
                f"offene Kontrakte {pr['offen'] or '—'} · "
                f"implizite Vola {100 * (pr['iv'] or 0):.0f} %"
                .replace(",", ".")
            )

# --------------------------------------------------------------------------
st.divider()
with st.expander("Wie diese Liste entsteht — und was sie nicht kann"):
    st.markdown(f"""
**Die Auswahl.** Universum ist der S&P 500. Es fliegt raus, wer negativen
freien Cashflow hat oder dessen Nettoverschuldung mehr als das Vierfache des
EBITDA beträgt. Übrig bleiben Namen, die man notfalls auch halten würde.

**Der Backtest.** An jedem Monatsanfang der verfügbaren Historie wird eine
gedachte Position eröffnet: Ausübungspreis 15 bzw. 20 % unter dem damaligen
Kurs, Vergleich mit dem Kurs 3 bzw. 6 Monate später. Gezählt wird, wie oft
der Kurs darunter lag — und um wie viel.

**Warum die Untergrenze danebensteht.** Monatliche Startpunkte bei drei
Monaten Laufzeit überlappen sich zu zwei Dritteln; benachbarte Fälle sind
keine unabhängigen Versuche. Das Vertrauensintervall wird deshalb auf der
Zahl der sich *nicht* überlappenden Zeiträume gerechnet, nicht auf der
rohen Fallzahl. Es fällt dadurch deutlich breiter aus — und ehrlicher.

**Der Zirkelschluss, den man kennen sollte.** Wer nach der niedrigsten
historischen Ausübungswahrscheinlichkeit sortiert und diese Zahl dann als
Gütesiegel zeigt, wählt zwangsläufig die Titel aus, die zufällig gestiegen
sind. Die Liste sagt, was war, nicht was kommt.

**Die Steuer.** Geschriebene Puts auf IBKR oder CapTrader sind unverbriefte
Derivate (§ 27a Abs 2 Z 7 EStG). Sie unterliegen dem Einkommensteuertarif,
nicht den 27,5 %, und lassen sich nicht mit Aktiengewinnen ausgleichen.
Deshalb die Nettospalte — bei {grenzsteuer} % bleibt weniger als die Hälfte
der Bruttorendite, wenn der Satz über 50 % liegt.

**Keine Anlageberatung.** Prämien sind die Mitte aus Geld und Brief und
können vom handelbaren Kurs abweichen. Wer einen Put schreibt, kann
verpflichtet werden, die Aktie zu kaufen — auch nach einem scharfen Rückgang.
""")

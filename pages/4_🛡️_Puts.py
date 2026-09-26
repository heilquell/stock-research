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

# Vorgabe: zwei Wochen Laufzeit, 7 % unter dem Kurs. Das ist der Zuschnitt,
# der tatsaechlich gehandelt wird -- die Vorlage kennt nur Monate und 15 %.
VORGABE_ABSTAND = 7
VORGABE_TAGE = 10


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

links, mitte, rechts = st.columns([2, 2, 3])
with links:
    abstand = st.radio(
        "Abstand zum Kurs", ps.ABSTAENDE, horizontal=True,
        index=ps.ABSTAENDE.index(VORGABE_ABSTAND),
        format_func=lambda a: f"−{a} %",
        help="Wie weit der Ausübungspreis unter dem heutigen Kurs liegt.")
with mitte:
    tage = st.radio(
        "Laufzeit", [d for d, _ in ps.LAUFZEITEN], horizontal=True,
        index=[d for d, _ in ps.LAUFZEITEN].index(VORGABE_TAGE),
        format_func=lambda d: ps.LAUFZEIT_NAMEN[d],
        help="In Handelstagen gerechnet: eine Woche sind fünf Kurszeilen.")
kombi = ps.kombi_schluessel(abstand, tage)
with rechts:
    grenzsteuer = st.slider(
        "Grenzsteuersatz für die Nettorechnung (%)", 0, 55, 42, step=1,
        help="Geschriebene Puts sind unverbriefte Derivate (§ 27a Abs 2 Z 7 "
             "EStG): Tarifsteuer statt 27,5 %, kein Ausgleich mit dem "
             "Aktien-Topf.")

df = _rangliste(kombi)
if df.empty:
    st.warning(f"Für {ps.kombi_name(abstand, tage)} liegt noch kein Ergebnis vor.")
    st.stop()

nur_belastbar = st.checkbox(
    f"Nur Titel mit mindestens {ps.MIN_EIGENSTAENDIG} eigenständigen Zeiträumen",
    value=True,
    help="Sonst stehen Titel oben, deren Quote auf einer Handvoll Fälle beruht.")
if nur_belastbar:
    df = df[df["eigenstaendig"] >= ps.MIN_EIGENSTAENDIG]

QUELLE_NAMEN = {"SP500": "S&P 500", "MERKLISTE": "Merkliste",
                "GEHANDELT": "selbst gehandelt"}

# Eigene Titel stehen auch dann in der Tabelle, wenn sie den Fundamentalfilter
# nicht bestehen -- wer auf einen Wert schon Optionen geschrieben hat, will
# die Zahlen sehen und nicht, dass ein Filter ihn stillschweigend verschluckt.
# Sichtbar bleibt der Unterschied trotzdem.
eigene = df["quelle"].isin(("MERKLISTE", "GEHANDELT"))
if eigene.any() and st.checkbox(
        f"Nur eigene Titel — Merkliste und schon gehandelt ({int(eigene.sum())})",
        value=False):
    df = df[eigene]
    eigene = df["quelle"].isin(("MERKLISTE", "GEHANDELT"))
schwach = eigene & ~df["fundamental_ok"]
if schwach.any():
    if not st.checkbox(
            f"Eigene Titel mitzeigen, die den Fundamentalfilter nicht bestehen "
            f"({int(schwach.sum())})", value=True,
            help="Meist hohe Verschuldung (REITs, BDCs) oder negativer freier "
                 "Cashflow. Die Backtest-Zahlen stimmen trotzdem."):
        df = df[~schwach]

# Die Bewertung steht vorn, nicht hinter zehn Rohwerten: Sie ist der Grund,
# warum die Zeilen in dieser Reihenfolge stehen. Was in sie eingeht, folgt
# dahinter zum Nachvollziehen.
anzeige = pd.DataFrame({
    "Symbol": df["symbol"],
    "Bewertung": df["vorsichtig_pa"].round(1),
    "erwartet": df["erwartet_pa"].round(1),
    "Name": df["name"],
    "Quelle": df["quelle"].map(QUELLE_NAMEN).fillna("—"),
    "Fundamental": ["✓" if ok else "⚠" for ok in df["fundamental_ok"]],
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
st.caption(
    "Sortiert nach **Bewertung** — erwarteter Verlust pro Jahr in Prozent des "
    "gebundenen Kapitals, klein ist gut. Die Spalten dahinter zeigen, woraus "
    "sie entsteht."
)
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
        "Bewertung": st.column_config.NumberColumn(
            "Bewertung %/J ▲", help="Erwarteter Verlust pro Jahr in Prozent "
                                    "des gebundenen Kapitals — klein ist gut, "
                                    "danach ist sortiert. Gerechnet mit der "
                                    "pessimistischen Kante des "
                                    "Vertrauensintervalls, damit dünne "
                                    "Stichproben nicht nach oben rutschen."),
        "erwartet": st.column_config.NumberColumn(
            "erwartet %/J", help="Dieselbe Größe mit der gemessenen Quote "
                                 "statt der Untergrenze: die beste Schätzung, "
                                 "ohne Sicherheitsabschlag."),
        "Fundamental": st.column_config.TextColumn(
            "Fund.", help="✓ positiver freier Cashflow und Nettoverschuldung "
                          "≤ 4× EBITDA. ⚠ eigener Titel, der das nicht "
                          "erfüllt — bei REITs und BDCs ist hohe Verschuldung "
                          "allerdings der Normalzustand, kein Warnzeichen."),
    })

st.caption(
    f"Stand {stand} · {n_titel} Titel · Universum S&P 500 plus die eigene "
    "Options-Merkliste, gefiltert auf positiven freien Cashflow und "
    "Nettoverschuldung ≤ 4× EBITDA."
)
st.caption(
    "⚠️ Das Universum sind die **heutigen** Indexmitglieder. Titel, die seit "
    "2005 pleitegingen oder aus dem Index flogen, fehlen — ihre schlechten "
    "Verläufe also auch. Alle Quoten oben sind dadurch systematisch zu "
    "freundlich; korrigieren ließe sich das nur mit historischen "
    "Indexlisten, die es nicht kostenlos gibt."
)


@st.cache_data(ttl=900, show_spinner=False)
def _merkliste() -> pd.DataFrame:
    conn = ps.verbindung()
    try:
        return ps.merkliste_status(conn)
    finally:
        conn.close()


merk = _merkliste()
if not merk.empty:
    fehlen = merk[merk["status"] != "in der Liste"]
    titel = ("Eigene Merkliste — "
             + (f"{len(fehlen)} von {len(merk)} Titeln fehlen in der Tabelle"
                if len(fehlen) else "alle Titel sind in der Tabelle"))
    with st.expander(titel):
        st.caption(
            "Der S&P 500 nimmt keine ausländischen Emittenten auf — ASML, "
            "Novo Nordisk oder AstraZeneca können dort nicht stehen, obwohl "
            "auf sie Optionen gehandelt werden. Deshalb kommen die eigene "
            "Merkliste und alle schon gehandelten Basiswerte als zweite "
            "Quelle dazu; sie werden auch dann gerechnet, wenn sie den "
            "Fundamentalfilter nicht bestehen. Wer hier trotzdem fehlt, "
            "fehlt aus einem genannten Grund.")
        st.dataframe(merk, use_container_width=True, hide_index=True)

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
    with st.spinner(f"Optionskette {symbol} …"):
        pr = ps.praemie_fuer(symbol, abstand, tage, kurs=float(zeile["kurs"]))
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
# Erst Praemie minus erwarteter Verlust ergibt eine Empfehlung. Die Praemie
# kostet je Titel einen Yahoo-Abruf, deshalb nur auf Knopfdruck und nur fuer
# die Spitze der Liste.
st.divider()
st.subheader("Lohnt es sich? Prämie gegen erwarteten Verlust")
st.caption(
    "Die Kennzahl oben misst nur das Risiko. Erst wenn die Prämie dagegensteht, "
    "wird daraus eine Empfehlung: **Prämie p. a. − erwarteter Verlust p. a.** "
    "Weil jede Prämie einen Abruf bei Yahoo kostet, holt der Knopf sie nur für "
    "die besten Titel der aktuellen Auswahl."
)

anzahl_top = st.slider("Wie viele Titel prüfen?", 3, 15, 8)
if st.button("Prämien holen und vergleichen", type="primary"):
    zeilen = []
    fortschritt = st.progress(0.0)
    kandidaten_top = df.head(anzahl_top).to_dict("records")
    for i, r in enumerate(kandidaten_top, start=1):
        pr = ps.praemie_fuer(r["symbol"], abstand, tage, kurs=float(r["kurs"]))
        fortschritt.progress(i / len(kandidaten_top))
        if not pr or pr["mid"] != pr["mid"]:
            continue
        rend = ps.rendite(pr["mid"], pr["strike"], pr["tage"], grenzsteuer)
        if not rend:
            continue
        brutto = 100 * rend["rendite_pa"]
        netto = 100 * rend["rendite_pa_netto"]
        zeilen.append({
            "Symbol": r["symbol"],
            "Name": r["name"],
            "Strike": round(pr["strike"], 2),
            "Verfall": pr["verfall"],
            "Prämie €/Kontrakt": round(rend["praemie_kontrakt"], 0),
            "Prämie %/J": round(brutto, 2),
            "nach Steuer %/J": round(netto, 2),
            "erwarteter Verlust %/J": round(r["vorsichtig_pa"], 2),
            "Überschuss %/J": round(netto - r["vorsichtig_pa"], 2),
        })
    fortschritt.empty()
    if not zeilen:
        st.warning("Keine brauchbaren Notierungen — zu diesen Verfallterminen "
                   "gibt es keine Ketten mit Geld- und Briefkurs.")
    else:
        erg = pd.DataFrame(zeilen).sort_values("Überschuss %/J", ascending=False)
        st.dataframe(erg, use_container_width=True, hide_index=True)
        bester = erg.iloc[0]
        if bester["Überschuss %/J"] > 0:
            st.success(
                f"Bestes Verhältnis: **{bester['Symbol']}** — "
                f"{bester['nach Steuer %/J']:.2f} % Prämie nach Steuer gegen "
                f"{bester['erwarteter Verlust %/J']:.2f} % erwarteten Verlust, "
                f"Überschuss {bester['Überschuss %/J']:.2f} Prozentpunkte im Jahr."
            )
        else:
            st.warning(
                "Kein Titel in dieser Auswahl trägt sich: Die Prämien liegen "
                "nach Steuer unter dem erwarteten Verlust. Das ist ein "
                "Ergebnis, kein Fehler — dann ist dieser Zuschnitt gerade "
                "nicht bezahlt."
            )
        st.caption(
            "Der Überschuss ist eine Erwartung, keine Rendite: Er sagt, was "
            "übrig bleibt, wenn sich die Vergangenheit im Mittel wiederholt. "
            "Eine einzelne Position kann trotzdem den schlimmsten Fall aus der "
            "Spalte „max. %\" treffen."
        )

st.divider()
with st.expander("Wie diese Liste entsteht — und was sie nicht kann"):
    st.markdown(f"""
**Die Auswahl.** Universum ist der S&P 500, dazu die eigene Merkliste und
jeder Basiswert, auf den schon einmal Optionen gehandelt wurden. Aus dem
S&P 500 fliegt raus, wer negativen freien Cashflow hat oder dessen
Nettoverschuldung mehr als das Vierfache des EBITDA beträgt — übrig bleiben
Namen, die man notfalls auch halten würde. Eigene Titel werden immer
gerechnet und mit ⚠ gekennzeichnet, wenn sie den Filter reißen.

**Der Backtest.** Jede Woche der verfügbaren Historie wird eine gedachte
Position eröffnet: Ausübungspreis 5 bis 20 % unter dem damaligen Kurs,
Vergleich mit dem Kurs eine Woche bis sechs Monate später. Gezählt wird, wie
oft der Kurs darunter lag — und um wie viel. Gerechnet wird das volle Kreuz
aus fünf Abständen und fünf Laufzeiten, 25 Kombinationen je Titel.

**Warum die Untergrenze danebensteht.** Wöchentliche Startpunkte bei drei
Monaten Laufzeit überlappen sich zu zwölf Dreizehnteln; benachbarte Fälle
sind keine unabhängigen Versuche. Das Vertrauensintervall wird deshalb auf
der Zahl der sich *nicht* überlappenden Zeiträume gerechnet, nicht auf der
rohen Fallzahl. Bei einer Woche Laufzeit überlappt nichts — dort sind beide
Zahlen gleich, und das Intervall ist entsprechend eng.

**Warum kurze Laufzeiten anders aussehen.** Je näher der Ausübungspreis und
je kürzer die Laufzeit, desto kleiner die Prämie — aber desto öfter im Jahr
einsetzbar. Die Jahresrendite rechnet das hoch; die Trefferquote je Einsatz
ist dabei die Zahl, die man im Auge behalten muss. Wer wöchentlich schreibt,
hat fünfzigmal im Jahr die Gelegenheit, danebenzuliegen.

**Der Zirkelschluss, den man kennen sollte.** Wer nach der niedrigsten
historischen Ausübungswahrscheinlichkeit sortiert und diese Zahl dann als
Gütesiegel zeigt, wählt zwangsläufig die Titel aus, die zufällig gestiegen
sind. Die Liste sagt, was war, nicht was kommt.

**Überlebende unter sich.** Dazu kommt derselbe Effekt eine Ebene höher: Das
Universum besteht aus den heutigen Indexmitgliedern. Wer seit 2005
pleiteging, übernommen wurde oder aus dem Index fiel, ist gar nicht erst
dabei — mit ihm sein Absturz. Der Backtest hat also einen Krieg
nachgerechnet, aus dessen Geschichtsbüchern die Gefallenen entfernt wurden.
Sauber beheben ließe sich das nur mit historischen Indexständen; die gibt es
nicht gratis. Die Zahlen sind deshalb als Obergrenze zu lesen, nicht als
Erwartung.

**Die Kennzahl.** Trefferquote und Fallhöhe gehören multipliziert, nicht
nebeneinandergelegt: 2 % Ausübung mit 20 % Rückgang kostet im Mittel dasselbe
wie 8 % mit 5 %. Das Produkt ist der erwartete Verlust in Prozent des
gebundenen Kapitals, hochgerechnet aufs Jahr. Die Spalte „vorsichtig" nimmt
statt der gemessenen Quote die pessimistische Kante des
Vertrauensintervalls — damit fällt ein Titel mit 99 % auf 40 Zeiträumen
hinter einen mit 98 % auf 1.000 zurück. Der schlimmste Einzelfall geht
bewusst **nicht** ein; ein Ereignis von vor fünfzehn Jahren darf einen
Durchschnitt nicht beherrschen. Er steht daneben.

**Kurse ohne Dividendenbereinigung.** Verglichen wird der reine Kursverlauf,
splitbereinigt, aber ohne Dividenden. Das ist Absicht: Eine
dividendenbereinigte Reihe drückt den früheren Kurs künstlich und lässt jeden
Put besser aussehen, als er war.

**Die Steuer.** Geschriebene Puts auf IBKR oder CapTrader sind unverbriefte
Derivate (§ 27a Abs 2 Z 7 EStG). Sie unterliegen dem Einkommensteuertarif,
nicht den 27,5 %, und lassen sich nicht mit Aktiengewinnen ausgleichen.
Deshalb die Nettospalte — bei {grenzsteuer} % bleibt weniger als die Hälfte
der Bruttorendite, wenn der Satz über 50 % liegt.

**Keine Anlageberatung.** Prämien sind die Mitte aus Geld und Brief und
können vom handelbaren Kurs abweichen. Wer einen Put schreibt, kann
verpflichtet werden, die Aktie zu kaufen — auch nach einem scharfen Rückgang.
""")

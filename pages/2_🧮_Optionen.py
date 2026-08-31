"""Optionen — Rollen, Preis, Kette, implizite Volatilitaet.

Der Zuschnitt folgt dem, was tatsaechlich gehandelt wird: ueberwiegend
verkaufte Puts mit kurzer Laufzeit, die vor dem Verfall weitergerollt werden.
Deshalb steht "Rollen" vorne und nicht der Preisrechner, und deshalb sind die
Vorgabewerte kurzlaufend und knapp aus dem Geld.

Gerechnet wird mit ``Option_api`` — Cox-Ross-Rubinstein, amerikanische
Ausuebung. Das ist fuer Einzelaktien-Optionen das richtige Modell;
Black-Scholes steckt in der Bibliothek nur als Vergleichswert.
"""
import contextlib
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import Option_api as op
import option_data as od
from auth import sidebar_login

st.set_page_config(page_title="Optionen", page_icon="🧮", layout="wide")

# Schritte im Binomialbaum. Gemessen an einem ASML-Put (1380, 30 Tage,
# Vola 0,55): n=200 ergibt 133,134, n=1000 ergibt 133,209 — 0,06 % Unterschied
# bei sechsfacher Rechenzeit. Fuer Tabellen mit hunderten Zellen ist das der
# Unterschied zwischen fuenf und dreissig Sekunden, also bleibt n dort klein.
N_EINZEL = 1000
N_TABELLE = 200

# Vorgabewerte aus der eigenen Handelshistorie: Puts werden im Median gut vier
# Prozent unter dem Kurs verkauft, Calls knapp vier Prozent darueber.
ABSTAND_PUT_PCT = -4.0
ABSTAND_CALL_PCT = 4.0


@st.cache_data(ttl=1800, show_spinner=False)
def preis(S, K, T, r, sigma, n, typ, ausuebung="american"):
    """Optionspreis, gecacht.

    Reine Funktion von Zahlen — der Cache-Schluessel ist damit exakt, und eine
    Kette, die einmal gerechnet wurde, ist beim zweiten Ansehen sofort da.
    """
    p, _ = op.binomial_optionspreis(S, K, T, r, sigma, n, typ, ausuebung)
    return float(p)


@st.cache_data(ttl=1800, show_spinner=False)
def griechen(S, K, T, r, sigma, n, typ, ausuebung="american"):
    return op.calc_griechen(S, K, T, r, sigma, n, typ, ausuebung)[0]


@st.cache_data(ttl=1800, show_spinner=False)
def implizite_vola(marktpreis, S, K, T, r, n, typ, ausuebung="american"):
    return float(op.berechne_implizite_vola(marktpreis, S, K, T, r, n, typ, ausuebung))


def eur(x, nk=2):
    return f"{x:,.{nk}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------------------
# Kopf: Symbol, Kurs, Zins, Volatilitaet — gilt fuer alle Reiter
# ---------------------------------------------------------------------------
st.title("🧮 Optionen")

_user = sidebar_login()
st.sidebar.divider()

merkliste = od.watchlist(_user)
with st.sidebar.expander("Merkliste bearbeiten", expanded=not merkliste):
    neu = st.text_input("Symbol aufnehmen", key="wl_neu", placeholder="z. B. ADBE")
    if st.button("aufnehmen", key="wl_add") and neu.strip():
        od.watchlist_add(neu, _user)
        st.rerun()
    if merkliste:
        weg = st.selectbox("entfernen", ["—"] + merkliste, key="wl_del")
        if st.button("entfernen", key="wl_del_btn") and weg != "—":
            od.watchlist_del(weg, _user)
            st.rerun()

auswahl = merkliste + ["… anderes Symbol"] if merkliste else ["… anderes Symbol"]
k1, k2, k3, k4 = st.columns([2, 2, 1.4, 3])

with k1:
    sym = st.selectbox("Basiswert", auswahl, index=0)
    if sym == "… anderes Symbol":
        sym = st.text_input("Symbol", value="", placeholder="AAPL").upper().strip()

if not sym:
    st.info("Symbol waehlen oder eintragen.")
    st.stop()

kurs_db = od.letzter_kurs(sym)
vola_db = od.hist_vola(sym)
info = od.firmeninfo(sym)

with k2:
    S = st.number_input("Kurs S", min_value=0.01,
                        value=float(kurs_db[1]) if kurs_db else 100.0,
                        step=0.5, format="%.2f")
    if kurs_db:
        st.caption(f"Datenbank: {eur(kurs_db[1])} vom {kurs_db[0]}")
    else:
        st.caption("⚠ nicht in der Kursdatenbank — Kurs von Hand")

with k3:
    r = st.number_input("Zins r %", min_value=-2.0, max_value=20.0,
                        value=3.0, step=0.25) / 100

with k4:
    optionen = {f"σ {f} Tage — {v * 100:.1f} %": v for f, v in vola_db.items()}
    optionen["σ von Hand"] = None
    wahl = st.radio("Volatilität", list(optionen), horizontal=True,
                    index=1 if len(optionen) > 2 else 0,
                    help="Historisch, aus den Schlusskursen der eigenen Datenbank. "
                         "Die implizite Vola des Marktes steht im letzten Reiter.")
    sigma = optionen[wahl]
    if sigma is None:
        sigma = st.number_input("σ %", min_value=1.0, max_value=400.0,
                                value=40.0, step=1.0) / 100

kopf = f"**{sym}**"
if info.get("name"):
    kopf += f" · {info['name']}"
if info.get("beta"):
    kopf += f" · Beta {eur(info['beta'])}"
st.caption(kopf + f" · gerechnet mit σ = {sigma * 100:.1f} %, r = {r * 100:.2f} %")

mitzaehlen = st.checkbox(
    "Verfalltag mitzählen", value=True,
    help="Yahoos implizite Vola stimmt mit der eigenen Rechnung erst überein, wenn "
         "der Verfalltag mitgezählt wird. Bei vier Tagen Restlaufzeit sind das rund "
         "drei Vola-Punkte — mehr, als zwischen amerikanischer und europäischer "
         "Ausübung liegt.")

tab_roll, tab_preis, tab_kette, tab_iv = st.tabs(
    ["🔁 Rollen", "🧮 Preis & Griechen", "📋 Optionskette", "📐 Implizite Vola"])

# ---------------------------------------------------------------------------
# 1) Rollen
# ---------------------------------------------------------------------------
with tab_roll:
    st.subheader("Wie weit muss ich verlängern, damit der Credit stimmt?")

    # Verfallstermine sind keine Regelmaessigkeit, sondern eine Liste.
    # Nachgemessen am 31.08.2026: ADBE hat woechentliche Freitage bis 16.10.,
    # danach springt es auf 20.11. und 18.12. — jeder erzeugte Freitag
    # dazwischen existiert nicht. INTC hat umgekehrt Termine am Montag und
    # Mittwoch, die ein Freitagsraster gar nicht erst anbietet. Deshalb
    # dieselbe Rangfolge wie bei den Strikes: ablesen schlaegt erzeugen.
    modus_v = st.radio("Verfallstermine",
                       ["echte aus der Optionskette", "jeder Freitag (ohne Netz)"],
                       horizontal=True, key="roll_modus")

    r1, r2, r3 = st.columns(3)
    with r1:
        typ = st.radio("Typ", ["put", "call"], horizontal=True, key="roll_typ")
    with r2:
        vorschlag_alt = od.naechster_strike(
            S, ABSTAND_PUT_PCT if typ == "put" else ABSTAND_CALL_PCT, sym)
        k_alt = st.number_input("Strike der offenen Position", value=float(vorschlag_alt),
                                step=1.0, format="%.2f", key=f"roll_kalt_{sym}")
    with r3:
        k_neu = st.number_input("Neuer Strike", value=float(vorschlag_alt),
                                step=1.0, format="%.2f", key=f"roll_kneu_{sym}",
                                help="Gleicher Strike = reines Zeitrollen. Tiefer "
                                     "(Put) heißt defensiver, dafür weniger Prämie.")

    kandidaten: list[date] = []
    verfall_alt = None

    if modus_v.startswith("echte"):
        schluessel_v = f"roll_dates_{sym}"
        if st.button("Verfallstermine laden", key="roll_load"):
            st.session_state[schluessel_v] = od.yahoo_verfallsdaten(sym)
        termine = [date.fromisoformat(t) for t in st.session_state.get(schluessel_v, [])]
        if not termine:
            st.info("Termine laden — dann steht hier die echte Liste des Titels, "
                    "einschließlich der Montags- und Mittwochs-Verfälle, die es "
                    "bei manchen Werten gibt.")
        else:
            v1, v2 = st.columns([2, 1])
            with v1:
                verfall_alt = st.selectbox(
                    "Verfall der offenen Position", termine, key="roll_valt_y",
                    format_func=lambda d: (
                        f"{d:%d.%m.%Y (%a)} · "
                        f"{od.tage_bis(d, date.today(), mitzaehlen)} "
                        + ("Tag" if od.tage_bis(d, date.today(), mitzaehlen) == 1
                           else "Tage")))
            with v2:
                anzahl = st.slider("Termine prüfen", 1, 20, 8, key="roll_anz")
            kandidaten = [t for t in termine if t > verfall_alt][:anzahl]
    else:
        v1, v2 = st.columns([2, 1])
        with v1:
            verfall_alt = st.date_input("Verfall der offenen Position",
                                        value=od.naechste_freitage(1)[0], key="roll_valt")
        with v2:
            wochen = st.slider("Wochen prüfen", 4, 52, 12, key="roll_wochen")
        kandidaten = [f for f in od.naechste_freitage(wochen + 8)
                      if f > verfall_alt][:wochen]
        st.caption("Erzeugte Freitage — nicht jeder davon wird als Kontrakt "
                   "gehandelt. Sicher ist nur die echte Terminliste.")

    min_credit = st.number_input("Mindest-Credit je Kontrakt", value=0.0, step=0.05,
                                 format="%.2f", key="roll_credit")

    # KEIN st.stop() an dieser Stelle: das beendet nicht den Reiter, sondern
    # den ganzen Seitenaufbau — Preis, Kette und implizite Vola blieben leer,
    # solange hier die Termine fehlten.
    rest_alt = od.tage_bis(verfall_alt, date.today(), mitzaehlen) if verfall_alt else 0
    if verfall_alt is None:
        pass
    elif rest_alt <= 0:
        st.warning("Der Verfall liegt nicht in der Zukunft.")
    elif not kandidaten:
        st.warning("Keine Termine nach dem aktuellen Verfall — mehr Termine prüfen.")
    else:
        # Der Rueckkaufpreis und jeder Kandidatenpreis kommen aus derselben
        # Funktion mit derselben Tageszaehlung. Der Credit ist die Differenz —
        # nur so kann zwischen Tabelle und Satz darunter nichts auseinanderlaufen.
        rueckkauf = preis(S, k_alt, rest_alt / 365, r, sigma, N_TABELLE, typ)
        itm = max(k_alt - S, 0) if typ == "put" else max(S - k_alt, 0)

        st.markdown(
            f"**Offene Position:** {typ.upper()} {eur(k_alt)} · Verfall "
            f"**{verfall_alt:%d.%m.%Y (%a)}** · noch "
            f"**{rest_alt} {'Tag' if rest_alt == 1 else 'Tage'}** · "
            f"Rückkauf {eur(rueckkauf)}"
            + (f" · **{eur(itm)} im Geld**" if itm else ""))

        reihen = []
        for t in kandidaten:
            tage = od.tage_bis(t, date.today(), mitzaehlen)
            p = preis(S, k_neu, tage / 365, r, sigma, N_TABELLE, typ)
            reihen.append({"Verfall": t, "Tage": tage, "Neuer Preis": round(p, 2),
                           "Credit": round(p - rueckkauf, 2)})
        beste = next((z for z in reihen if z["Credit"] >= min_credit), None)

        m1, m2, m3 = st.columns(3)
        m1.metric("Rückkauf der alten Option", eur(rueckkauf),
                  help=f"{rest_alt} Tage Restlaufzeit")
        m2.metric("im Geld", eur(itm) if itm else "—",
                  delta="Position im Verlust" if itm else None, delta_color="inverse")
        if beste:
            m3.metric("erster ausreichender Credit",
                      f"{beste['Verfall']:%d.%m.} · {eur(beste['Credit'])}",
                      help=f"{beste['Tage'] - rest_alt} Tage länger als jetzt")
        else:
            m3.metric("erster ausreichender Credit", "keiner",
                      help="auch am spätesten geprüften Termin nicht")

        df = pd.DataFrame([{
            "Verfall": f"{z['Verfall']:%Y-%m-%d (%a)}",
            "Tage": z["Tage"],
            "länger": z["Tage"] - rest_alt,
            "Neuer Preis": z["Neuer Preis"],
            "Credit": z["Credit"],
            "": "⭐" if beste and z["Verfall"] == beste["Verfall"]
                else ("✓" if z["Credit"] >= min_credit else ""),
        } for z in reihen])
        st.dataframe(df, width='stretch', hide_index=True)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[z["Tage"] for z in reihen],
                                 y=[z["Credit"] for z in reihen],
                                 mode="lines+markers", name="Credit",
                                 line=dict(color="#0969da")))
        fig.add_hline(y=min_credit, line_dash="dash", line_color="#cf222e",
                      annotation_text="Mindest-Credit")
        fig.update_layout(height=280, margin=dict(l=10, r=10, t=30, b=10),
                          xaxis_title="Laufzeit in Tagen", yaxis_title="Credit")
        st.plotly_chart(fig, width='stretch')

        if beste:
            eff = op.check_roll_lohnt_sich(
                preis_aktuell=rueckkauf, preis_neu=beste["Neuer Preis"],
                gebuehren=0.0, tage_rest_alt=rest_alt, tage_neu=beste["Tage"])
            e1, e2, e3 = st.columns(3)
            e1.metric("Ertrag je Tag, halten", eur(eff["Ertrag/Tag Alt"]))
            e2.metric("Ertrag je Tag, gerollt", eur(eff["Ertrag/Tag Neu"]))
            e3.metric("Rollen lohnt", eff["Roll-Empfehlung"],
                      help="Vergleicht nur die Prämie je Tag, ohne Gebühren und "
                           "ohne das Andienungsrisiko der alten Position.")
            st.success(
                f"**Heute:** {typ.upper()} {eur(k_alt)} (Verfall "
                f"{verfall_alt:%d.%m.%Y}) für {eur(rueckkauf)} zurückkaufen, "
                f"{typ.upper()} {eur(k_neu)} mit Verfall "
                f"{beste['Verfall']:%d.%m.%Y} für {eur(beste['Neuer Preis'])} "
                f"verkaufen → **Credit {eur(beste['Credit'])}** je Kontrakt "
                f"({eur(beste['Credit'] * 100, 0)} bei Multiplikator 100).")

        with st.expander("Rechenweg"):
            st.code(
                f"Kurs S            {eur(S)}\n"
                f"Volatilität σ     {sigma * 100:.1f} %\n"
                f"Zins r            {r * 100:.2f} %\n"
                f"Verfalltag zählt  {'ja' if mitzaehlen else 'nein'}\n"
                f"\n"
                f"Rückkauf   {typ.upper()} {eur(k_alt)}, {rest_alt} Tage"
                f"  →  {eur(rueckkauf)}\n"
                + "".join(
                    f"Verkauf    {typ.upper()} {eur(k_neu)}, {z['Tage']:>3} Tage"
                    f"  →  {eur(z['Neuer Preis']):>8}   Credit {eur(z['Credit']):>8}\n"
                    for z in reihen),
                language=None)

# ---------------------------------------------------------------------------
# 2) Preis & Griechen
# ---------------------------------------------------------------------------
with tab_preis:
    p1, p2, p3 = st.columns(3)
    with p1:
        typ_p = st.radio("Typ", ["put", "call"], horizontal=True, key="pr_typ")
    with p2:
        k_p = st.number_input(
            "Strike",
            value=od.naechster_strike(
                S, ABSTAND_PUT_PCT if typ_p == "put" else ABSTAND_CALL_PCT, sym),
            step=1.0, format="%.2f", key=f"pr_k_{sym}")
    with p3:
        verfall_p = st.date_input("Verfall", value=od.naechste_freitage(1)[0], key="pr_v")

    tage_p = od.tage_bis(verfall_p, date.today(), mitzaehlen)
    if tage_p <= 0:
        st.warning("Der Verfall liegt nicht in der Zukunft.")
    else:
        T = tage_p / 365
        g = griechen(S, k_p, T, r, sigma, N_EINZEL, typ_p)
        innerer = max(k_p - S, 0) if typ_p == "put" else max(S - k_p, 0)

        c = st.columns(6)
        c[0].metric("Preis", eur(g["Preis"]), help=f"{tage_p} Tage, n = {N_EINZEL}")
        c[1].metric("je Kontrakt", eur(g["Preis"] * 100, 0), help="Multiplikator 100")
        c[2].metric("Delta", f"{g['Delta']:.3f}")
        c[3].metric("Gamma", f"{g['Gamma']:.4f}")
        c[4].metric("Theta / Tag", f"{g['Theta(tgl)']:.3f}")
        c[5].metric("Vega je 1 %", f"{g['Vega(1%)']:.3f}")
        st.caption(f"innerer Wert {eur(innerer)} · Zeitwert "
                   f"{eur(g['Preis'] - innerer)} · Abstand zum Kurs "
                   f"{(k_p / S - 1) * 100:+.1f} %")

        g1, g2 = st.columns(2)
        with g1:
            xs = [S * (1 + i / 100) for i in range(-20, 21, 2)]
            ys = [preis(x, k_p, T, r, sigma, N_TABELLE, typ_p) for x in xs]
            f1 = go.Figure(go.Scatter(x=xs, y=ys, mode="lines", name="Preis",
                                      line=dict(color="#0969da")))
            f1.add_vline(x=S, line_dash="dash", line_color="#57606a",
                         annotation_text="heute")
            f1.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10),
                             title="Preis über Kurs", xaxis_title="Kurs",
                             yaxis_title="Optionspreis")
            st.plotly_chart(f1, width='stretch')
        with g2:
            # Der Zeitwert faellt nicht gleichmaessig, sondern nach Wurzel der
            # Restlaufzeit: am Geld verliert diese Option zwischen Tag 90 und 60
            # rund 0,16 je Tag, zwischen Tag 2 und 1 aber 1,24 — Faktor sieben.
            # Sichtbar wird das nur mit genug Stuetzstellen und ueber einen
            # Horizont, der die Kruemmung enthaelt. Die erste Fassung zeichnete
            # fuenf Punkte ueber fuenf Tage; das ergibt einen Streckenzug, der
            # wie eine Gerade aussieht.
            # Zwei Raster uebereinander: grob ueber den ganzen Horizont, fein
            # ueber die letzten zehn Tage. Dort ist die Kruemmung am groessten,
            # und ein gleichmaessiges Raster von 1,5 Tagen wuerde genau die
            # Stelle glattbuegeln, um die es geht.
            horizont = max(tage_p, 90)
            grob = [horizont * i / 40 for i in range(40, 0, -1)]
            fein = [i * 0.25 for i in range(40, 0, -1)]
            ts = sorted({round(t, 3) for t in grob + fein if t > 0}, reverse=True)
            zs = [preis(S, k_p, t / 365, r, sigma, N_TABELLE, typ_p) - innerer
                  for t in ts]
            # Verlust je Tag aus der Kurve selbst — das ist die Groesse, die
            # den Satz "zum Schluss geht es schnell" belegt.
            verlust = [None] + [(zs[i - 1] - zs[i]) / (ts[i - 1] - ts[i])
                                for i in range(1, len(ts))]

            f2 = go.Figure()
            f2.add_trace(go.Scatter(x=ts, y=zs, mode="lines", name="Zeitwert",
                                    line=dict(color="#1a7f37")))
            f2.add_trace(go.Scatter(x=ts, y=verlust, mode="lines",
                                    name="Verlust je Tag", yaxis="y2",
                                    line=dict(color="#cf222e", dash="dot")))
            f2.add_vline(x=tage_p, line_dash="dash", line_color="#57606a",
                         annotation_text=f"heute · {tage_p} T")
            f2.update_layout(
                height=300, margin=dict(l=10, r=10, t=30, b=10),
                title="Zeitwert über Restlaufzeit",
                xaxis=dict(title="Tage bis Verfall", autorange="reversed"),
                yaxis=dict(title="Zeitwert"),
                yaxis2=dict(title="Verlust je Tag", overlaying="y", side="right",
                            showgrid=False),
                legend=dict(orientation="h", y=1.12, x=0))
            st.plotly_chart(f2, width='stretch')
            hoehepunkt = (max(range(1, len(ts)), key=lambda i: verlust[i])
                          if len(ts) > 2 else 0)
            st.caption(
                "Kurs und Volatilität sind festgehalten, nur die Restlaufzeit "
                "läuft — eine Verfallskurve, keine Prognose. Die gepunktete "
                "Linie ist der Verlust je Tag. Am Geld steigt er bis zuletzt; "
                "aus dem Geld hat er einen Höhepunkt und fällt danach, weil "
                "immer weniger übrig ist, das noch verfallen könnte — hier "
                f"bei {ts[hoehepunkt]:.2f} Tagen mit "
                f"{eur(verlust[hoehepunkt])} je Tag.")

# ---------------------------------------------------------------------------
# 3) Optionskette
# ---------------------------------------------------------------------------
with tab_kette:
    schritt_db, herkunft = od.strike_schritt(sym, S)
    st.caption(
        f"Strike-Raster für **{sym}**: {eur(schritt_db)} — {herkunft}. "
        f"Gerechnet mit n = {N_TABELLE}; der Unterschied zu n = {N_EINZEL} liegt "
        "unter einem Zehntelprozent, die Rechenzeit beim Sechsfachen.")

    modus = st.radio(
        "Strikes", ["echte aus der Optionskette", "berechnet (ohne Netz)"],
        horizontal=True, key="ke_modus",
        help="Die Kette listet jeden Strike, den es wirklich gibt — samt "
             "Marktpreis. Das Raster ist am Geld feiner als in den Flügeln und "
             "je Verfall verschieden; nachbauen lässt sich das nicht, ablesen "
             "schon.")
    spanne = st.slider("Strikes ± % um den Kurs", 2, 25, 8, key="ke_span")

    if modus.startswith("echte"):
        st.info("Holt die Kette von Yahoo — nur auf Knopfdruck: am selben Zugang "
                "hängt der nächtliche Kurs-Cron für alle Titel.")
        schluessel_k = f"ke_dates_{sym}"
        if st.button("Verfallsdaten laden", key="ke_exp"):
            st.session_state[schluessel_k] = od.yahoo_verfallsdaten(sym)
        termine = st.session_state.get(schluessel_k, [])
        if termine:
            gewaehlt = st.multiselect("Verfall", termine, default=termine[:2],
                                      max_selections=3, key="ke_termine")
            if st.button("Ketten holen", type="primary", key="ke_go_y") and gewaehlt:
                for exp in gewaehlt:
                    try:
                        puts = od.yahoo_kette(sym, exp, "put")
                        calls = od.yahoo_kette(sym, exp, "call")
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"{exp}: Yahoo antwortet nicht wie erwartet — {exc}")
                        continue

                    gemessen = od.raster_aus_strikes(puts["strike"].tolist(), S)
                    if gemessen:
                        od.strike_schritt_merken(sym, gemessen, f"Kette {exp}")

                    tage = od.tage_bis(exp, date.today(), mitzaehlen)
                    T = tage / 365
                    im_band = puts[(puts["strike"] >= S * (1 - spanne / 100))
                                   & (puts["strike"] <= S * (1 + spanne / 100))]
                    c_idx = calls.set_index("strike")
                    zeilen = []
                    for _, z in im_band.iterrows():
                        k = float(z["strike"])
                        gp = griechen(S, k, T, r, sigma, N_TABELLE, "put")
                        gc = griechen(S, k, T, r, sigma, N_TABELLE, "call")
                        markt_call = (c_idx.loc[k, "mid"]
                                      if k in c_idx.index else float("nan"))
                        if hasattr(markt_call, "iloc"):
                            markt_call = markt_call.iloc[0]
                        zeilen.append({
                            "Call Δ": gc["Delta"],
                            "Call Modell": gc["Preis"],
                            "Call Markt": None if markt_call != markt_call
                                          else round(float(markt_call), 2),
                            "Strike": k,
                            "Put Markt": None if z["mid"] != z["mid"]
                                         else round(float(z["mid"]), 2),
                            "Put Modell": gp["Preis"],
                            "Put Δ": gp["Delta"],
                            "Abstand %": round((k / S - 1) * 100, 1),
                        })
                    st.markdown(f"**{exp}** · {tage} Tage · {len(zeilen)} echte Strikes"
                                + (f" · gemessenes Raster {eur(gemessen)}"
                                   if gemessen else ""))
                    if zeilen:
                        st.dataframe(pd.DataFrame(zeilen), width='stretch',
                                     hide_index=True)
                    else:
                        st.warning("Keine Strikes in diesem Band.")
                st.caption("„Markt\" ist die Mitte aus bid/ask, nicht der letzte "
                           "Handel — der ist bei dünnen Kontrakten Wochen alt. "
                           "Fehlt der Wert, gab es kein beidseitiges Angebot.")
    else:
        w1, w2 = st.columns(2)
        with w1:
            n_wochen = st.slider("Verfallswochen", 1, 8, 4, key="ke_wochen")
        with w2:
            schritt = st.number_input("Strike-Schritt", min_value=0.25, max_value=50.0,
                                      value=float(schritt_db), step=0.25,
                                      key="ke_schritt",
                                      help="Vorbelegt aus dem gespeicherten Raster. "
                                           "Sobald einmal eine echte Kette geholt "
                                           "wurde, steht hier der gemessene Wert.")
        if st.button("Kette berechnen", type="primary", key="ke_go"):
            strikes = op.find_strike_range(S, -S * spanne / 100, S * spanne / 100,
                                           schritt)
            with st.spinner(f"{len(strikes) * n_wochen * 2} Optionen …"):
                for fr in od.naechste_freitage(n_wochen):
                    tage = od.tage_bis(fr, date.today(), mitzaehlen)
                    T = tage / 365
                    zeilen = []
                    for k in strikes:
                        gc = griechen(S, k, T, r, sigma, N_TABELLE, "call")
                        gp = griechen(S, k, T, r, sigma, N_TABELLE, "put")
                        zeilen.append({
                            "Call Δ": gc["Delta"], "Call Θ": gc["Theta(tgl)"],
                            "Call": gc["Preis"], "Strike": k, "Put": gp["Preis"],
                            "Put Δ": gp["Delta"], "Put Θ": gp["Theta(tgl)"],
                            "Abstand %": round((k / S - 1) * 100, 1),
                        })
                    st.markdown(f"**{fr:%d.%m.%Y} ({fr:%a})** · {tage} Tage")
                    st.dataframe(pd.DataFrame(zeilen), width='stretch',
                                 hide_index=True)
            st.caption("Berechnete Strikes — nicht jeder davon muss an der Börse "
                       "existieren. Sicher ist nur die echte Kette.")

# ---------------------------------------------------------------------------
# 4) Implizite Vola
# ---------------------------------------------------------------------------
with tab_iv:
    st.caption("Die eigene Rechnung dreht den Binomialbaum um: welche Vola erklärt "
               "diesen Marktpreis? Das ist die Erwartung des Marktes — Zukunft. "
               "Vergangenheit ist allein die σ aus der Kursdatenbank.")

    einzel, kette = st.tabs(["einzelner Preis", "ganze Kette von Yahoo"])

    with einzel:
        i1, i2, i3, i4 = st.columns(4)
        with i1:
            typ_i = st.radio("Typ", ["put", "call"], horizontal=True, key="iv_typ")
        with i2:
            k_i = st.number_input(
                "Strike", value=od.naechster_strike(S, ABSTAND_PUT_PCT, sym),
                step=1.0, format="%.2f", key=f"iv_k_{sym}")
        with i3:
            verfall_i = st.date_input("Verfall", value=od.naechste_freitage(1)[0],
                                      key="iv_v")
        with i4:
            markt = st.number_input("Preis beim Broker", min_value=0.0, value=1.0,
                                    step=0.05, format="%.2f", key="iv_p")

        tage_i = od.tage_bis(verfall_i, date.today(), mitzaehlen)
        if markt > 0 and tage_i > 0:
            iv = implizite_vola(markt, S, k_i, tage_i / 365, r, 200, typ_i)
            v1, v2, v3 = st.columns(3)
            v1.metric("implizite Vola", f"{iv * 100:.1f} %", help=f"{tage_i} Tage")
            ref = vola_db.get(30)
            if ref:
                v2.metric("σ historisch 30 Tage", f"{ref * 100:.1f} %")
                v3.metric("IV / σ", f"{iv / ref:.2f}",
                          delta="Markt zahlt mehr als die Historie" if iv > ref
                          else "Markt zahlt weniger", delta_color="off")

    with kette:
        st.info("Holt die Optionskette von Yahoo — ein Symbol, ein Verfall, auf "
                "Knopfdruck. Nicht automatisch: am selben Zugang hängt der "
                "nächtliche Kurs-Cron für alle Titel.")
        # Die geladenen Verfallsdaten gehoeren zu EINEM Symbol. Ohne das Symbol
        # im Schluessel blieben beim Wechsel die Termine des vorigen Titels
        # stehen — und der Abruf liefe gegen Termine, die es dort nicht gibt.
        schluessel = f"yh_dates_{sym}"
        if st.button("Verfallsdaten laden", key="yh_exp"):
            st.session_state[schluessel] = od.yahoo_verfallsdaten(sym)
        daten = st.session_state.get(schluessel, [])
        if daten:
            c1, c2 = st.columns([2, 1])
            with c1:
                verfall_y = st.selectbox("Verfall", daten, key="yh_v")
            with c2:
                typ_y = st.radio("Typ", ["put", "call"], horizontal=True, key="yh_typ")
            if st.button("Kette holen und vergleichen", type="primary", key="yh_go"):
                try:
                    df = od.yahoo_kette(sym, verfall_y, typ_y)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Yahoo antwortet nicht wie erwartet: {exc}")
                    df = pd.DataFrame()
                if not df.empty:
                    tage_y = od.tage_bis(verfall_y, date.today(), mitzaehlen)
                    nah = df[(df["strike"] >= S * 0.85) & (df["strike"] <= S * 1.15)]
                    zeilen = []
                    for _, z in nah.iterrows():
                        mid = z["mid"]
                        iv_eigen = (implizite_vola(mid, S, float(z["strike"]),
                                                   tage_y / 365, r, 200, typ_y)
                                    if mid == mid and mid > 0 else None)
                        alt = ""
                        if "lastTradeDate" in z and pd.notna(z["lastTradeDate"]):
                            tage_alt = (pd.Timestamp.utcnow() - pd.Timestamp(z["lastTradeDate"])).days
                            alt = f"{tage_alt} T" if tage_alt > 2 else ""
                        zeilen.append({
                            "Strike": z["strike"], "bid": z["bid"], "ask": z["ask"],
                            "Mitte": None if mid != mid else round(mid, 2),
                            "letzter Handel": z.get("lastPrice"),
                            "veraltet": alt,
                            "IV Yahoo %": round(z["impliedVolatility"] * 100, 1),
                            "IV eigen %": None if iv_eigen is None else round(iv_eigen * 100, 1),
                            "offene Kontrakte": z.get("openInterest"),
                        })
                    ergebnis = pd.DataFrame(zeilen)
                    if ergebnis.empty:
                        st.warning("Keine Strikes im Bereich ±15 % um den Kurs — "
                                   "meist ein Zeichen, dass Yahoo für diesen Titel "
                                   "keine brauchbare Kette liefert.")
                    else:
                        st.dataframe(ergebnis, width='stretch',
                                     hide_index=True)
                    st.caption(
                        f"{tage_y} Tage Restlaufzeit"
                        + ("" if mitzaehlen else " — ohne Verfalltag; Yahoo zählt ihn mit, "
                                                 "die Spalten sind dann nicht vergleichbar")
                        + ".  „veraltet\" nennt das Alter des letzten Handels: steht dort "
                          "etwas, ist Yahoos IV auf einem Preis von damals gerechnet.")
                    if vola_db.get(30):
                        st.caption(f"σ historisch 30 Tage: **{vola_db[30] * 100:.1f} %** "
                                   "— der Maßstab, an dem sich beide Spalten messen.")

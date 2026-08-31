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
    r1, r2, r3, r4 = st.columns(4)
    with r1:
        typ = st.radio("Typ", ["put", "call"], horizontal=True, key="roll_typ")
    with r2:
        vorschlag_alt = op.find_next_strike_dyn(
            S, S * (ABSTAND_PUT_PCT if typ == "put" else ABSTAND_CALL_PCT) / 100)
        k_alt = st.number_input("Strike der offenen Position", value=float(vorschlag_alt),
                                step=1.0, format="%.2f", key="roll_kalt")
    with r3:
        verfall_alt = st.date_input("Verfall der offenen Position",
                                    value=od.naechste_freitage(1)[0], key="roll_valt")
    with r4:
        k_neu = st.number_input("Neuer Strike", value=float(vorschlag_alt),
                                step=1.0, format="%.2f", key="roll_kneu",
                                help="Gleicher Strike = reines Zeitrollen. Tiefer "
                                     "(Put) heißt defensiver, dafür weniger Prämie.")

    r5, r6 = st.columns(2)
    with r5:
        min_credit = st.number_input("Mindest-Credit je Kontrakt", value=0.0, step=0.05,
                                     format="%.2f", key="roll_credit")
    with r6:
        wochen = st.slider("Wochen prüfen", 4, 52, 12, key="roll_wochen")

    # Mitternacht statt datetime.now(): die Bibliothek rechnet Laufzeiten als
    # Differenz zweier Zeitpunkte und schneidet auf ganze Tage ab. Mit der
    # Uhrzeit von jetzt waere ein Freitag in vier Tagen je nach Tageszeit mal
    # vier und mal drei Tage entfernt — der Preis schwankte dann mit dem
    # Aufrufzeitpunkt statt mit dem Markt.
    heute = datetime.combine(date.today(), datetime.min.time())
    rest_alt = od.tage_bis(verfall_alt, date.today(), mitzaehlen)
    if rest_alt <= 0:
        st.warning("Der Verfall liegt nicht in der Zukunft.")
    else:
        beste, protokoll, alle = op.finde_rolling_laufzeit_mit_datum(
            aktienkurs=S, alter_strike=k_alt, neuer_strike=k_neu,
            aktuelles_datum=heute,
            aktuelles_verfalldatum=datetime.combine(verfall_alt, datetime.min.time()),
            option_type=typ, min_credit=min_credit, r=r, sigma=sigma,
            max_wochen=wochen, n=N_TABELLE, details=True,
            tage_offset=1 if mitzaehlen else 0)

        # Rueckkaufpreis NICHT daneben neu rechnen, sondern aus der Bibliothek
        # ableiten: Credit = neuer Preis - alter Preis. So kann in der Tabelle
        # und im Satz darunter nichts auseinanderlaufen.
        rueckkauf = (alle[0]["neuer_preis"] - alle[0]["credit"]) if alle else 0.0

        # Die Bibliothek prueft alle kommenden Freitage — auch den, an dem die
        # Position ohnehin verfaellt. Auf denselben Tag zu rollen ist kein
        # Rollen, sondern ein Nullgeschaeft: gleicher Strike, gleicher Verfall,
        # Credit exakt 0,00. Als "erster positiver Credit" waere das eine
        # Antwort, die nach einer Empfehlung aussieht und keine ist.
        alle = [e for e in alle if e["verfalldatum"].date() > verfall_alt]
        beste = next((e for e in alle if e["credit"] >= min_credit), None)
        if not alle:
            st.warning("Keine Verfallstermine nach dem aktuellen — Wochen erhöhen.")
            st.stop()
        itm = (max(k_alt - S, 0) if typ == "put" else max(S - k_alt, 0))

        m1, m2, m3 = st.columns(3)
        m1.metric("Rückkauf der alten Option", eur(rueckkauf),
                  help=f"{rest_alt} Tage Restlaufzeit")
        m2.metric("im Geld", eur(itm) if itm else "—",
                  delta="Position im Verlust" if itm else None, delta_color="inverse")
        if beste:
            m3.metric("erster positiver Credit",
                      f"Woche {beste['wochen']} · {eur(beste['credit'])}",
                      help=beste["verfalldatum"].strftime("Verfall %d.%m.%Y"))
        else:
            m3.metric("erster positiver Credit", "keiner",
                      help=f"auch nach {wochen} Wochen nicht")

        df = pd.DataFrame([{
            "Woche": e["wochen"],
            "Verfall": e["verfalldatum"].strftime("%Y-%m-%d (%a)"),
            "Tage": e["tage"],
            "Neuer Preis": round(e["neuer_preis"], 2),
            "Credit": round(e["credit"], 2),
            "": "⭐" if beste and e["wochen"] == beste["wochen"] else
                ("✓" if e["credit"] >= min_credit else ""),
        } for e in alle])
        st.dataframe(df, width='stretch', hide_index=True)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["Tage"], y=df["Credit"], mode="lines+markers",
                                 name="Credit", line=dict(color="#0969da")))
        fig.add_hline(y=min_credit, line_dash="dash", line_color="#cf222e",
                      annotation_text="Mindest-Credit")
        fig.update_layout(height=280, margin=dict(l=10, r=10, t=30, b=10),
                          xaxis_title="Laufzeit in Tagen", yaxis_title="Credit")
        st.plotly_chart(fig, width='stretch')

        if beste:
            eff = op.check_roll_lohnt_sich(
                preis_aktuell=rueckkauf, preis_neu=beste["neuer_preis"],
                gebuehren=0.0, tage_rest_alt=rest_alt, tage_neu=beste["tage"])
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
                f"{beste['verfalldatum']:%d.%m.%Y} für {eur(beste['neuer_preis'])} "
                f"verkaufen → **Credit {eur(beste['credit'])}** je Kontrakt "
                f"({eur(beste['credit'] * 100, 0)} bei Multiplikator 100)."
            )
        with st.expander("Rechenweg der Bibliothek"):
            st.code(protokoll, language=None)

# ---------------------------------------------------------------------------
# 2) Preis & Griechen
# ---------------------------------------------------------------------------
with tab_preis:
    p1, p2, p3 = st.columns(3)
    with p1:
        typ_p = st.radio("Typ", ["put", "call"], horizontal=True, key="pr_typ")
    with p2:
        k_p = st.number_input(
            "Strike", value=float(op.find_next_strike_dyn(
                S, S * (ABSTAND_PUT_PCT if typ_p == "put" else ABSTAND_CALL_PCT) / 100)),
            step=1.0, format="%.2f", key="pr_k")
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
            ts = list(range(max(tage_p, 2), 0, -max(1, tage_p // 20)))
            zs = [preis(S, k_p, t / 365, r, sigma, N_TABELLE, typ_p) - innerer for t in ts]
            f2 = go.Figure(go.Scatter(x=ts, y=zs, mode="lines", name="Zeitwert",
                                      line=dict(color="#1a7f37")))
            f2.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10),
                             title="Zeitwert über Restlaufzeit",
                             xaxis_title="Tage bis Verfall", yaxis_title="Zeitwert",
                             xaxis=dict(autorange="reversed"))
            st.plotly_chart(f2, width='stretch')

# ---------------------------------------------------------------------------
# 3) Optionskette
# ---------------------------------------------------------------------------
with tab_kette:
    st.caption("Strike-Leiter über mehrere Verfallswochen, Put und Call nebeneinander. "
               f"Gerechnet mit n = {N_TABELLE} — der Unterschied zu n = {N_EINZEL} "
               "liegt unter einem Zehntelprozent, die Rechenzeit beim Sechsfachen.")
    q1, q2, q3 = st.columns(3)
    with q1:
        spanne = st.slider("Strikes ± % um den Kurs", 2, 25, 8, key="ke_span")
    with q2:
        n_wochen = st.slider("Verfallswochen", 1, 8, 4, key="ke_wochen")
    with q3:
        # Vorgabe wie an der Boerse ueblich: je hoeher der Kurs, desto weiter
        # die Strikes auseinander (dieselbe Staffel wie find_next_strike_dyn).
        vorgabe = 2.5 if S < 50 else 5.0 if S < 200 else 10.0
        schritt = st.select_slider("Strike-Schritt", [1.0, 2.5, 5.0, 10.0, 20.0],
                                   value=vorgabe, key="ke_schritt")

    if st.button("Kette berechnen", type="primary", key="ke_go"):
        strikes = op.find_strike_range(S, -S * spanne / 100, S * spanne / 100, schritt)
        freitage = od.naechste_freitage(n_wochen)
        with st.spinner(f"{len(strikes) * len(freitage) * 2} Optionen …"):
            for fr in freitage:
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
            k_i = st.number_input("Strike", value=float(op.find_next_strike_dyn(
                S, S * ABSTAND_PUT_PCT / 100)), step=1.0, format="%.2f", key="iv_k")
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

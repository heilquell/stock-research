"""Options-Agent — Politik-Röntgen.

Nicht "was empfiehlt der Agent heute", sondern: **was hat er überhaupt
gelernt?** Der Unterschied ist kein Wortspiel. Ein trainiertes Netz gibt auf
jede Eingabe eine Antwort, und die sieht immer nach einer Empfehlung aus —
auch dann, wenn sie in Wahrheit gar nicht von der Eingabe abhängt.

Deshalb steht hier die Abtastung der Politik vorne und die Order-Ausgabe
hinten, und deshalb bekommt jede Order die Prämienzerlegung mitgeliefert:
innerer Wert gegen Zeitwert. Ohne diese Spalte sieht eine gehebelte
Richtungswette aus wie eine Prämienstrategie.

Zugang nur mit Google-Anmeldung — das Modell ist kein Allgemeingut, und die
Ausgaben lassen sich zu leicht als Handelsempfehlung missverstehen.

Rechenkern: ``agent_infer`` (reines NumPy, kein TensorFlow).
"""
import os
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import agent_infer as ai
from auth import auth_konfiguriert, sidebar_login, user_email

st.set_page_config(page_title="Options-Agent", page_icon="🤖", layout="wide")

# Trainings-Ticker (ARKK fehlt in der Kursdatenbank, SQ liefert keine Daten mehr).
# Alphabetisch, damit man im Auswahlfeld etwas findet. Das ist gefahrlos: die
# Reihenfolge dient nur der Anzeige, gerechnet wird immer mit dem Symbol.
# Die einzige Stelle, an der Reihenfolge zaehlen wuerde, waere ein
# `index=`-Vorgabewert -- der steht deshalb unten als .index("SYMBOL").
TRAIN_TICKER = sorted([
    "SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "TSLA",
    "META", "MDB", "ASML", "ADBE", "PLTR", "LLY", "UNH", "JPM", "CAT", "GE",
    "BA", "DIS", "HON", "AMD", "NFLX", "INTC", "PYPL", "SBUX", "NKE", "JNJ",
    "PG", "MRK", "CRM", "SHOP", "SNOW", "AVGO", "MU", "MRVL", "MRNA", "GILD",
    "ROKU", "BABA", "PDD", "COIN",
])
# Nie im Training gesehen — der ehrlichere Prüfstein.
OOS_TICKER = sorted(["UBER", "CRWD", "PANW", "ZS", "WMT", "COST", "HD", "V",
                     "MA", "ABNB", "DASH"])
ALLE_TICKER = TRAIN_TICKER + OOS_TICKER

VORGABE = "AAPL"   # Startwert der Auswahlfelder, per Symbol statt per Position


# --------------------------------------------------------------------------
# Zugangsschranke — vor allem anderen
# --------------------------------------------------------------------------
sidebar_login()

if not auth_konfiguriert():
    st.title("🤖 Options-Agent")
    st.error(
        "Diese Seite braucht die Google-Anmeldung, und die ist auf diesem "
        "Server gerade nicht eingerichtet (keine Zugangsdaten hinterlegt oder "
        "Authlib fehlt im Image). Damit bleibt die Seite geschlossen."
    )
    st.stop()

if user_email() is None:
    st.title("🤖 Options-Agent")
    st.info(
        "**Anmeldung erforderlich.** Diese Seite zeigt die Politik eines "
        "trainierten Handelsmodells und ist deshalb nur für angemeldete "
        "Nutzer zugänglich. Der Anmelde-Knopf steht links in der Seitenleiste."
    )
    st.stop()


# --------------------------------------------------------------------------
# Modell + Daten
# --------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def gewichte():
    return ai.lade_gewichte()


@st.cache_data(ttl=3600, show_spinner=False)
def merkmale(symbol: str) -> pd.DataFrame:
    return ai.merkmale(symbol)


try:
    G = gewichte()
except FileNotFoundError as e:
    st.title("🤖 Options-Agent")
    st.error(str(e))
    st.stop()

st.title("🤖 Options-Agent — Politik-Röntgen")
# Welches Modell hier rechnet, gehoert sichtbar auf die Seite: v8 und v9
# handeln voellig verschiedene Strikes, und ohne Angabe waere aus den
# Ausgaben nicht zu erkennen, welche Politik man gerade vor sich hat.
_modell = os.path.basename(ai.GEWICHTE_PATH)
try:
    _stand = datetime.fromtimestamp(os.path.getmtime(ai.GEWICHTE_PATH)).strftime("%d.%m.%Y")
except OSError:
    _stand = "unbekannt"
st.caption(
    f"PPO, 24 Eingangsgrößen → 4 Entscheidungsköpfe. Gewichte `{_modell}` "
    f"(Stand {_stand}). Rechnung in reinem NumPy (116.118 Parameter, "
    "~0,1 ms je Entscheidung). "
    "**Keine Handelsempfehlung** — die Seite zeigt, was das Modell ausgibt, "
    "nicht was zu tun ist."
)

tab_sweep, tab_karte, tab_breite, tab_order = st.tabs([
    "📈 Reagiert er?", "🗺 Politik-Karte", "🎯 Über alle Ticker",
    "🧾 Order im Klartext",
])


def basis_zustand(symbol: str, depot: dict | None = None):
    df = merkmale(symbol)
    if df.empty or len(df) < 260:
        return None, None
    return ai.zustand(df, -1, depot), df


# --------------------------------------------------------------------------
# 1) Reagiert er überhaupt?
# --------------------------------------------------------------------------
with tab_sweep:
    st.subheader("Ein Merkmal durchfahren, alle anderen festhalten")
    st.write(
        "Wenn die Kurven flach sind, hängt die Entscheidung nicht an diesem "
        "Merkmal. Sind sie über *alle* Merkmale flach, hat der Agent eine "
        "feste Politik gelernt statt einer situationsabhängigen."
    )

    c1, c2 = st.columns([1, 2])
    sym = c1.selectbox("Ausgangslage von", TRAIN_TICKER,
                       index=TRAIN_TICKER.index(VORGABE), key="sweep_sym")
    feat_idx = c2.selectbox(
        "Merkmal durchfahren", range(24),
        format_func=lambda i: f"{i:2d} · {ai.FEATURE_NAMEN[i]}",
        index=8, key="sweep_feat")

    s0, df = basis_zustand(sym)
    if s0 is None:
        st.warning(f"Zu wenig Historie für {sym}.")
    else:
        # Sinnvolle Bandbreite je Merkmal: die im Training verwendeten Clips.
        grenzen = {
            0: (0.4, 2.0), 1: (0.4, 2.0), 2: (0.4, 2.0), 3: (0.0, 0.15),
            4: (-0.15, 0.15), 5: (-0.30, 0.30), 6: (-0.50, 0.50),
            7: (-0.20, 0.20), 8: (0.0, 1.0), 9: (-0.05, 0.05),
            10: (-0.30, 0.30), 11: (0.0, 1.0), 12: (-0.50, 0.0),
            13: (0.0, 1.0), 14: (0.05, 1.2), 15: (0.5, 2.5),
            16: (0.3, 2.0), 17: (0.0, 2.0), 18: (0.0, 1.0),
            19: (0.0, 1.0), 20: (0.0, 1.0), 21: (0.0, 0.6),
            22: (-1.0, 1.0), 23: (-1.0, 1.0),
        }
        lo, hi = grenzen[feat_idx]
        werte = np.linspace(lo, hi, 60)
        zust = np.tile(s0, (len(werte), 1))
        zust[:, feat_idx] = werte
        koepfe, value = ai.vorwaerts(G, zust)

        fig = go.Figure()
        for j, name in enumerate(ai.AKTIONEN):
            p = koepfe["aktion"][:, j]
            if p.max() < 0.02:      # dauerhaft unter 2 % — nur Rauschen
                continue
            fig.add_trace(go.Scatter(x=werte, y=p, mode="lines", name=name))
        fig.add_vline(x=float(s0[feat_idx]), line_dash="dot",
                      annotation_text="heute", annotation_position="top")
        fig.update_layout(
            height=380, yaxis_title="Wahrscheinlichkeit",
            xaxis_title=ai.FEATURE_NAMEN[feat_idx],
            yaxis_range=[0, 1], margin=dict(t=30, b=40),
            legend=dict(orientation="h", y=1.12))
        st.plotly_chart(fig, width="stretch")

        spanne = float(koepfe["aktion"].max(axis=0).max()
                       - koepfe["aktion"].max(axis=0).min())
        c1, c2, c3 = st.columns(3)
        c1.metric("Bandbreite der Top-Wahrscheinlichkeit", f"{spanne:.3f}",
                  help="Wie stark schwankt die Sicherheit des Agenten über "
                       "den ganzen Wertebereich? Nahe 0 heißt: dieses "
                       "Merkmal ändert nichts.")
        c2.metric("Value am linken Rand", f"{value[0]:.2f}")
        c3.metric("Value am rechten Rand", f"{value[-1]:.2f}")

        st.markdown("**Die drei anderen Köpfe über denselben Bereich**")
        cols = st.columns(3)
        for col, (kopf, werte_liste, titel) in zip(cols, [
            ("strike", ai.STRIKE_PCT, "Strike-Abstand"),
            ("laufzeit", ai.LAUFZEITEN, "Laufzeit (Tage)"),
            ("kontrakte", ai.KONTRAKTE, "Kontrakte"),
        ]):
            f = go.Figure()
            for j, w in enumerate(werte_liste):
                p = koepfe[kopf][:, j]
                if p.max() < 0.05:
                    continue
                etikett = f"{w:+.0%}" if kopf == "strike" else str(w)
                f.add_trace(go.Scatter(x=werte, y=p, mode="lines", name=etikett))
            f.update_layout(height=260, title=titel, yaxis_range=[0, 1],
                            margin=dict(t=40, b=30, l=10, r=10),
                            legend=dict(orientation="h", y=-0.25))
            col.plotly_chart(f, width="stretch")


# --------------------------------------------------------------------------
# 2) Politik-Karte
# --------------------------------------------------------------------------
with tab_karte:
    st.subheader("Aktion über RSI und Volatilität")
    st.write(
        "Zwei Merkmale gleichzeitig durchfahren, der Rest bleibt auf dem "
        "heutigen Stand des gewählten Titels. Eine einfarbige Fläche heißt: "
        "der Agent macht in jeder Marktlage dasselbe."
    )
    sym2 = st.selectbox("Ausgangslage von", TRAIN_TICKER,
                        index=TRAIN_TICKER.index(VORGABE), key="karte_sym")
    s0, _ = basis_zustand(sym2)
    if s0 is None:
        st.warning(f"Zu wenig Historie für {sym2}.")
    else:
        rsi_w = np.linspace(0.05, 0.95, 40)
        vol_w = np.linspace(0.10, 1.00, 40)
        gitter = np.tile(s0, (len(rsi_w) * len(vol_w), 1))
        rr, vv = np.meshgrid(rsi_w, vol_w, indexing="ij")
        gitter[:, 8] = rr.ravel()
        gitter[:, 14] = vv.ravel()
        koepfe, value = ai.vorwaerts(G, gitter)

        aktion_idx = koepfe["aktion"].argmax(axis=1).reshape(len(rsi_w), -1)
        strike_idx = koepfe["strike"].argmax(axis=1).reshape(len(rsi_w), -1)
        gewaehlt = sorted(set(aktion_idx.ravel().tolist()))

        c1, c2 = st.columns(2)
        f1 = go.Figure(go.Heatmap(
            z=aktion_idx.T, x=rsi_w * 100, y=vol_w,
            colorscale="Viridis", zmin=0, zmax=5,
            colorbar=dict(tickvals=list(range(6)), ticktext=ai.AKTIONEN)))
        f1.update_layout(height=380, title="gewählte Aktion",
                         xaxis_title="RSI", yaxis_title="HistVola 20",
                         margin=dict(t=40))
        c1.plotly_chart(f1, width="stretch")

        f2 = go.Figure(go.Heatmap(
            z=np.array(ai.STRIKE_PCT)[strike_idx].T * 100, x=rsi_w * 100,
            y=vol_w, colorscale="RdBu", zmid=0,
            colorbar=dict(title="Strike %")))
        f2.update_layout(height=380, title="gewählter Strike-Abstand",
                         xaxis_title="RSI", yaxis_title="HistVola 20",
                         margin=dict(t=40))
        c2.plotly_chart(f2, width="stretch")

        st.info(
            f"In diesem Gitter aus {len(rsi_w) * len(vol_w)} Marktlagen wählt "
            f"der Agent **{len(gewaehlt)} von 6 Aktionen**: "
            + ", ".join(ai.AKTIONEN[i] for i in gewaehlt)
            + f". Value zwischen {value.min():.2f} und {value.max():.2f}."
        )


# --------------------------------------------------------------------------
# 3) Über alle Ticker
# --------------------------------------------------------------------------
with tab_breite:
    st.subheader("Was würde der Agent heute auf jedem Titel tun?")
    st.write(
        "Aktueller Rand der Kursdatenbank, leeres Depot als Ausgangslage. "
        "Wenn hier für alle Titel dieselbe Zeile steht, ist die Politik "
        "nicht vom Titel abhängig."
    )
    welche = st.radio("Universum", ["Training (44)", "Out-of-Sample (11)", "beide"],
                      horizontal=True, index=2)
    liste = (TRAIN_TICKER if welche.startswith("Training")
             else OOS_TICKER if welche.startswith("Out") else ALLE_TICKER)

    if st.button("Durchrechnen", type="primary"):
        zeilen = []
        balken = st.progress(0.0)
        for i, t in enumerate(liste):
            df = merkmale(t)
            if df.empty or len(df) < 260:
                zeilen.append({"Ticker": t, "Aktion": "— zu wenig Historie"})
            else:
                s = ai.zustand(df, -1)
                k, v = ai.vorwaerts(G, s)
                e = ai.entscheidung(k)
                kurs = float(df["close"].iloc[-1])
                sigma = float(df["IV_Proxy"].iloc[-1] or 0.3)
                z = ai.praemien_zerlegung(kurs, e, sigma)
                zeilen.append({
                    "Ticker": t,
                    "Kurs": kurs,
                    "Aktion": e["aktion"],
                    "p": e["aktion_p"],
                    "Strike": f'{e["strike_pct"]:+.0%}',
                    "Tage": e["laufzeit"],
                    "Kontr.": e["kontrakte"],
                    "im Geld": ("ja" if z and z["im_geld"] else "nein") if z else "—",
                    "Prämie": z["praemie_gesamt"] if z else np.nan,
                    "davon Zeitwert": z["zeitwert"] if z else np.nan,
                    "Zeitwert-Anteil": z["zeitwert_anteil"] * 100 if z else np.nan,
                    "Hebel": z["hebel"] if z else np.nan,
                    "Value": float(v),
                })
            balken.progress((i + 1) / len(liste))
        balken.empty()

        d = pd.DataFrame(zeilen)
        st.dataframe(
            d, width="stretch", hide_index=True,
            column_config={
                "Kurs": st.column_config.NumberColumn(format="%.2f"),
                "p": st.column_config.NumberColumn(format="%.2f"),
                "Prämie": st.column_config.NumberColumn(format="%.0f $"),
                "davon Zeitwert": st.column_config.NumberColumn(format="%.0f $"),
                "Zeitwert-Anteil": st.column_config.NumberColumn(format="%.1f %%"),
                "Hebel": st.column_config.NumberColumn(format="%.1f ×"),
                "Value": st.column_config.NumberColumn(format="%.2f"),
            })

        gueltig = d[d["Aktion"].isin(ai.AKTIONEN)]
        if not gueltig.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("verschiedene Aktionen", gueltig["Aktion"].nunique())
            c2.metric("verschiedene Strikes", gueltig["Strike"].nunique())
            itm = (gueltig["im Geld"] == "ja").sum()
            c3.metric("davon im Geld", f"{itm}/{len(gueltig)}")
            if "Zeitwert-Anteil" in gueltig:
                med = gueltig["Zeitwert-Anteil"].median() / 100.0
                if pd.notna(med) and med < 0.2:
                    st.warning(
                        f"Der Zeitwert macht im Median nur **{med:.1%}** der "
                        f"Prämie aus. Der Rest ist innerer Wert, der bei "
                        f"Andienung wieder abfließt — das ist keine "
                        f"Prämienstrategie, sondern eine Richtungswette.")


# --------------------------------------------------------------------------
# 4) Order im Klartext
# --------------------------------------------------------------------------
with tab_order:
    st.subheader("Was der Agent ausgibt — und was es wirtschaftlich heißt")
    c1, c2 = st.columns([1, 1])
    sym3 = c1.selectbox("Titel", ALLE_TICKER,
                        index=ALLE_TICKER.index(VORGABE), key="ord_sym")
    ref = c2.number_input(
        "Bezugsfenster (Handelstage)", 60, 500, ai.REF_TAGE, 10,
        help="Vier der 24 Merkmale sind auf den Kurs am Episodenstart "
             "normiert. Live gibt es keinen Episodenstart — dieser Wert "
             "setzt den Bezugspunkt. Die Wahl verschiebt den Zustand.")

    df = merkmale(sym3)
    if df.empty or len(df) < 260:
        st.warning(f"Zu wenig Historie für {sym3}.")
    else:
        with st.expander("Depot-Zustand (6 der 24 Merkmale)"):
            st.caption(
                "Vorgabe ist ein leeres Depot auf Startniveau. Die echten "
                "Werte stehen in der Broker-App und lassen sich später über "
                "den MCP-Endpunkt lesend anbinden.")
            d1, d2, d3 = st.columns(3)
            depot = {
                "portfolio_faktor": d1.number_input("Portfolio / Start", 0.1, 3.0, 1.0, 0.05),
                "cash_faktor": d2.number_input("Cash / Start", 0.0, 3.0, 1.0, 0.05),
                "anzahl_optionen": d3.number_input("offene Optionen", 0, 20, 0),
                "margin_benutzt": d1.slider("Margin benutzt", 0.0, 1.0, 0.0),
                "margin_frei": d2.slider("Margin frei", 0.0, 1.0, 0.8),
                "drawdown": d3.slider("Drawdown", 0.0, 0.6, 0.0),
                "bester_profit_pct": 0.0,
                "avg_profit_pct": 0.0,
            }

        s = ai.zustand(df, -1, depot, ref_tage=int(ref))
        k, v = ai.vorwaerts(G, s)
        e = ai.entscheidung(k)
        kurs = float(df["close"].iloc[-1])
        sigma = float(df["IV_Proxy"].iloc[-1] or 0.3)
        stand = str(df.index[-1])

        st.caption(f"Kurs {kurs:,.2f} $ vom {stand} · IV-Proxy {sigma:.1%}")
        m = st.columns(5)
        m[0].metric("Aktion", e["aktion"], f'p={e["aktion_p"]:.2f}')
        m[1].metric("Strike", f'{e["strike_pct"]:+.0%}', f'p={e["strike_p"]:.2f}')
        m[2].metric("Laufzeit", f'{e["laufzeit"]} T', f'p={e["laufzeit_p"]:.2f}')
        m[3].metric("Kontrakte", e["kontrakte"], f'p={e["kontrakte_p"]:.2f}')
        m[4].metric("Value", f"{float(v):.2f}")

        z = ai.praemien_zerlegung(kurs, e, sigma)
        if z is None:
            st.info("Der Agent will nichts eröffnen — keine Order zu zerlegen.")
        else:
            st.markdown("#### Prämienzerlegung")
            lage = "**im Geld**" if z["im_geld"] else "aus dem Geld"
            st.write(
                f"{z['richtung']} {z['typ']}, Strike **{z['strike']:,.2f} $** "
                f"({z['abstand_pct']:+.1%} zum Kurs) — {lage}."
            )
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Prämie gesamt", f"{z['praemie_gesamt']:,.0f} $")
            p2.metric("davon innerer Wert", f"{z['innerer_wert']:,.0f} $")
            p3.metric("echter Zeitwert", f"{z['zeitwert']:,.0f} $",
                      f"{z['zeitwert_anteil']:.1%} der Prämie")
            p4.metric("Hebel auf Nominale",
                      f"{z['hebel']:.1f} ×" if z["hebel"] else "—",
                      f"Margin {z['margin']:,.0f} $" if z["margin"] else None)

            if z["im_geld"] and z["zeitwert_anteil"] < 0.25:
                st.error(
                    f"**Das ist keine Prämienstrategie.** Von "
                    f"{z['praemie_gesamt']:,.0f} $ sind "
                    f"{z['innerer_wert']:,.0f} $ innerer Wert, der bei "
                    f"Andienung wieder abfließt. Eingesammelte "
                    f"Volatilitätsprämie: {z['zeitwert']:,.0f} $. "
                    f"Wirtschaftlich ist das eine gehebelte Wette auf einen "
                    f"steigenden Kurs.")

            st.markdown("#### Ergebnis bei Verfall")
            vp = ai.verfall_profil(kurs, e, z)
            st.dataframe(
                vp, width="stretch", hide_index=True,
                column_config={
                    "Kursänderung": st.column_config.NumberColumn(format="%+.0f %%"),
                    "Kurs bei Verfall": st.column_config.NumberColumn(format="%.2f $"),
                    "Andienung kostet": st.column_config.NumberColumn(format="%.0f $"),
                    "Ergebnis": st.column_config.NumberColumn(format="%.0f $"),
                })

        with st.expander("Zustandsvektor (24 Merkmale)"):
            st.dataframe(
                pd.DataFrame({"Merkmal": ai.FEATURE_NAMEN, "Wert": s}),
                width="stretch", hide_index=True,
                column_config={"Wert": st.column_config.NumberColumn(format="%.4f")})

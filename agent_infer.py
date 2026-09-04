"""Inferenz fuer den RL-Optionsagenten (PPO v8) — ohne TensorFlow.

Das trainierte Netz ist reines Dense/ReLU/Softmax:

    state(24) -> 256 -> 256 -> 128 -> {4 Softmax-Koepfe, Value-Kopf}

Damit ist die Vorwaertsrechnung eine Handvoll Matrixmultiplikationen, und
TensorFlow im Image waere reine Last: mehrere hundert MB fuer 116.118
Parameter, die als ``.npz`` 454 KB wiegen. Gemessen: 1000 Entscheidungen in
102 ms.

**Die Gewichte liegen NICHT im Repo** (``/docker/research`` ist oeffentlich),
sondern neben der Kursdatenbank unter ``/data`` — erzeugt von
``agent_export.py`` aus der ``.keras``-Datei.

Zustands-Aufbau: alle 24 Features kommen aus ``stock_data`` in der lokalen
SQLite (open/high/low/close/volume, 3.246 Symbole ab 2009). Kein yfinance
zur Laufzeit.

⚠️ **Was dieses Modell tatsaechlich gelernt hat**, siehe
``VORSCHLAG_research_integration_2026-09-03.md`` im Projekte-Repo: Der
Strike wird als ``kurs * (1 + strike_pct)`` gebildet, ohne Vorzeichenwechsel
fuer Puts. Ein ``sell_put`` mit +10 % liegt damit *ueber* dem Kurs, also tief
im Geld. Von der Praemie ist dann fast alles innerer Wert. Deshalb liefert
``praemien_zerlegung()`` zu jeder Order den Zeitwert getrennt aus — ohne die
Spalte sieht eine Hebelwette wie eine Praemienstrategie aus.
"""
from __future__ import annotations

import os
import sqlite3

import numpy as np
import pandas as pd

from Option_api import binomial_optionspreis

DB_PATH = os.environ.get("STOCKS_DB", "/data/stocks.db")
GEWICHTE_PATH = os.environ.get("AGENT_WEIGHTS", "/data/agent_v9.npz")

# Aktionsraum aus Opt_tensorflowV8.py (OptionsEnvV8) — Reihenfolge ist
# bindend, sie entspricht der Reihenfolge der Softmax-Ausgaenge.
AKTIONEN = ["nothing", "buy_call", "buy_put", "sell_call", "sell_put",
            "close_position"]
STRIKE_PCT = [-0.10, -0.06, -0.04, -0.02, 0.0, 0.02, 0.04, 0.06, 0.10]
LAUFZEITEN = [7, 14, 28]
KONTRAKTE = [1, 2, 3]

AKTIEN_PRO_KONTRAKT = 100
ZINS = 0.05
MARGIN_NAKED_PCT = 0.20   # 20 % x Kurs x 100 x Kontrakte
REF_TAGE = 252            # Bezugspunkt fuer die auf "anfang" normierten Features

FEATURE_NAMEN = [
    "Kurs/Anfang", "MA5/Anfang", "MA20/Anfang", "Std5/Anfang",
    "Ret 1T", "Ret 5T", "Ret 20T", "Trend (MA5/MA20)",
    "RSI 14", "MACD-Signal", "MA50/MA200", "Volumen-Verhältnis",
    "Abstand 52W-Hoch", "Auf-Tage 20",
    "HistVola 20", "IV/HV",
    "Portfolio/Start", "Cash/Start", "Anzahl Optionen",
    "Margin benutzt", "Margin frei", "Drawdown",
    "Bester Positions-Profit", "Ø Positions-Profit",
]


# --------------------------------------------------------------------------
# Gewichte + Vorwaertsrechnung
# --------------------------------------------------------------------------

def lade_gewichte(pfad: str | None = None) -> dict[str, np.ndarray]:
    pfad = pfad or GEWICHTE_PATH
    if not os.path.exists(pfad):
        raise FileNotFoundError(
            f"Modellgewichte nicht gefunden: {pfad}. Mit agent_export.py aus "
            f"der .keras-Datei erzeugen.")
    with np.load(pfad) as f:
        return {k: f[k] for k in f.files}


def _relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(x, 0.0)


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


def vorwaerts(G: dict, state: np.ndarray) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Ein oder mehrere Zustaende durchs Netz. ``state`` ist (24,) oder (N, 24).

    Returns (Kopf-Wahrscheinlichkeiten, Value). Bei Einzelzustand sind die
    Arrays eindimensional.
    """
    einzeln = state.ndim == 1
    x = np.atleast_2d(state).astype(np.float32)

    h = _relu(x @ G["shared_1.w"] + G["shared_1.b"])
    h = _relu(h @ G["shared_2.w"] + G["shared_2.b"])
    sh = _relu(h @ G["shared_3.w"] + G["shared_3.b"])

    koepfe = {name: _softmax(sh @ G[f"head_{name}.w"] + G[f"head_{name}.b"])
              for name in ("aktion", "strike", "laufzeit", "kontrakte")}
    v = _relu(sh @ G["value_hidden.w"] + G["value_hidden.b"])
    value = (v @ G["value.w"] + G["value.b"])[:, 0]

    if einzeln:
        koepfe = {k: p[0] for k, p in koepfe.items()}
        value = value[0]
    return koepfe, value


def entscheidung(koepfe: dict[str, np.ndarray]) -> dict:
    """Greedy-Auswahl je Kopf, wie ``act_greedy`` im Trainingsskript."""
    i_a = int(np.argmax(koepfe["aktion"]))
    i_s = int(np.argmax(koepfe["strike"]))
    i_l = int(np.argmax(koepfe["laufzeit"]))
    i_k = int(np.argmax(koepfe["kontrakte"]))
    # Die vier Koepfe sind unabhaengig (faktorisierte Politik), also ist das
    # Produkt die Wahrscheinlichkeit der VOLLSTAENDIGEN Order. Bezugspunkt ist
    # nicht 1/6 wie beim Aktionskopf, sondern 1/486 = 0,2 % -- so viel gaebe
    # blindes Raten. Deshalb steht daneben, um das Wievielfache davon.
    p_ges = (float(koepfe["aktion"][i_a]) * float(koepfe["strike"][i_s])
             * float(koepfe["laufzeit"][i_l]) * float(koepfe["kontrakte"][i_k]))
    return {
        "aktion": AKTIONEN[i_a],
        "aktion_p": float(koepfe["aktion"][i_a]),
        "strike_pct": STRIKE_PCT[i_s],
        "strike_p": float(koepfe["strike"][i_s]),
        "laufzeit": LAUFZEITEN[i_l],
        "laufzeit_p": float(koepfe["laufzeit"][i_l]),
        "kontrakte": KONTRAKTE[i_k],
        "kontrakte_p": float(koepfe["kontrakte"][i_k]),
        "p_gesamt": p_ges,
        "p_gesamt_vs_zufall": p_ges * 486.0,
        # Flache Aktionsnummer wie im Training: a*81 + s*9 + l*3 + k
        "aktion_idx": i_a * 81 + i_s * 9 + i_l * 3 + i_k,
    }


# --------------------------------------------------------------------------
# Zustand aus der lokalen Kursdatenbank
# --------------------------------------------------------------------------

def _rsi(s: pd.Series, periode: int = 14) -> pd.Series:
    d = s.diff()
    auf = d.clip(lower=0).rolling(periode).mean()
    ab = (-d.clip(upper=0)).rolling(periode).mean()
    rs = auf / (ab + 1e-10)
    return 100 - 100 / (1 + rs)


def _macd_signal(s: pd.Series) -> pd.Series:
    """MACD-Signal relativ zum Kurs — so wie im Trainingsskript."""
    ema_f = s.ewm(span=12, adjust=False).mean()
    ema_s = s.ewm(span=26, adjust=False).mean()
    macd = ema_f - ema_s
    sig = macd.ewm(span=9, adjust=False).mean()
    return (macd - sig) / (s + 1e-10)


def merkmale(symbol: str, db_path: str | None = None) -> pd.DataFrame:
    """Kursreihe mit allen abgeleiteten Groessen, wie ``lade_alle_daten``.

    Bewusst dieselben Fensterlaengen und dieselbe IV-Proxy-Formel wie im
    Training — eine Abweichung hier verschiebt den Zustand still.
    """
    with sqlite3.connect(db_path or DB_PATH, timeout=5) as c:
        df = pd.read_sql_query(
            "SELECT date, close, volume FROM stock_data "
            " WHERE symbol = ? AND close IS NOT NULL AND close > 0 "
            " ORDER BY date", c, params=(symbol,))
    if df.empty:
        return df
    df = df.set_index("date")

    df["Ret1d"] = df["close"].pct_change()
    df["Ret5d"] = df["close"].pct_change(5)
    df["Ret20d"] = df["close"].pct_change(20)
    df["MA5"] = df["close"].rolling(5).mean()
    df["MA20"] = df["close"].rolling(20).mean()
    df["MA50"] = df["close"].rolling(50).mean()
    df["MA200"] = df["close"].rolling(200).mean()
    df["Std5"] = df["close"].rolling(5).std()
    df["HistVol20"] = df["Ret1d"].rolling(20).std() * np.sqrt(252)
    df["RSI14"] = _rsi(df["close"], 14)
    df["MACD_Signal"] = _macd_signal(df["close"])
    volavg = df["volume"].rolling(20).mean()
    df["VolumeRatio"] = df["volume"] / (volavg + 1)
    df["Dist52WHigh"] = df["close"] / df["close"].rolling(252).max() - 1.0
    df["UpDays20"] = (df["Ret1d"] > 0).astype(float).rolling(20).sum()
    df["Trend"] = (df["MA5"] / df["MA20"] - 1.0).clip(-0.20, 0.20)
    df["MA50_MA200"] = (df["MA50"] / (df["MA200"] + 1e-10) - 1.0).clip(-0.30, 0.30)

    hv60 = df["Ret1d"].rolling(60).std() * np.sqrt(252)
    vol_spike = (df["HistVol20"] / (hv60 + 1e-10)).clip(0.5, 3.0)
    iv_mult = (1.10 + (vol_spike - 1.0) * 0.25
               + df["Ret20d"].abs().clip(0, 0.3) * 1.5).clip(0.90, 1.80)
    df["IV_Proxy"] = df["HistVol20"] * iv_mult
    df["IV_HV_Ratio"] = iv_mult
    return df


# Ein Depot ohne offene Optionen, Portfolio auf Startniveau. Das ist der
# Zustand, in dem der Agent "frisch" entscheidet.
DEPOT_LEER = {
    "portfolio_faktor": 1.0,   # Portfoliowert / Startkapital
    "cash_faktor": 1.0,        # Cash / Startkapital
    "anzahl_optionen": 0,      # absolute Zahl, wird auf /10 normiert
    "margin_benutzt": 0.0,     # Anteil am Portfoliowert
    "margin_frei": 0.80,       # Anteil am Portfoliowert
    "drawdown": 0.0,
    "bester_profit_pct": 0.0,  # -100..+100
    "avg_profit_pct": 0.0,
}


def zustand(df: pd.DataFrame, idx: int = -1, depot: dict | None = None,
            ref_tage: int = REF_TAGE) -> np.ndarray:
    """Baut den 24-Feature-Zustand fuer eine Zeile der Merkmals-Tabelle.

    ``ref_tage`` ist der Bezugspunkt fuer die vier auf ``anfang`` normierten
    Features. Im Training ist das der Beginn eines zufaelligen 252-Tage-
    Fensters; live gibt es den nicht, deshalb hier der Kurs vor ``ref_tage``
    Handelstagen. **Die Wahl verschiebt den Zustand systematisch** und faellt
    nicht auf — sie gehoert im UI sichtbar gemacht.
    """
    d = dict(DEPOT_LEER, **(depot or {}))
    row = df.iloc[idx]
    pos = idx if idx >= 0 else len(df) + idx
    anfang_pos = max(pos - ref_tage, 0)
    anfang = float(df["close"].iloc[anfang_pos])
    kurs = float(row["close"])
    if anfang <= 0:
        anfang = kurs

    def z(name, vorgabe=0.0):
        v = row.get(name, vorgabe)
        try:
            v = float(v)
        except (TypeError, ValueError):
            return vorgabe
        return vorgabe if np.isnan(v) else v

    hv = z("HistVol20", 0.25)
    if hv < 0.01:
        hv = 0.25

    s = np.array([
        kurs / anfang,
        z("MA5", kurs) / anfang,
        z("MA20", kurs) / anfang,
        z("Std5", kurs * 0.02) / anfang,
        np.clip(z("Ret1d"), -0.15, 0.15),
        np.clip(z("Ret5d"), -0.30, 0.30),
        np.clip(z("Ret20d"), -0.50, 0.50),
        z("Trend"),
        z("RSI14", 50.0) / 100.0,
        np.clip(z("MACD_Signal"), -0.05, 0.05),
        z("MA50_MA200"),
        np.clip(z("VolumeRatio", 1.0) / 3.0, 0.0, 1.0),
        np.clip(z("Dist52WHigh"), -0.50, 0.0),
        z("UpDays20", 10.0) / 20.0,
        np.clip(hv, 0.0, 1.5),
        np.clip(z("IV_HV_Ratio", 1.2), 0.5, 2.5),
        d["portfolio_faktor"],
        d["cash_faktor"],
        min(d["anzahl_optionen"] / 10.0, 1.0),
        d["margin_benutzt"],
        d["margin_frei"],
        d["drawdown"],
        np.clip(d["bester_profit_pct"] / 100.0, -1.0, 1.0),
        np.clip(d["avg_profit_pct"] / 100.0, -1.0, 1.0),
    ], dtype=np.float32)
    return np.nan_to_num(s, nan=0.0, posinf=1.0, neginf=-1.0)


# --------------------------------------------------------------------------
# Was eine Order wirtschaftlich bedeutet
# --------------------------------------------------------------------------

def _strike_intervall(kurs: float) -> float:
    if kurs < 25: return 0.5
    if kurs < 50: return 1
    if kurs < 200: return 2.5
    if kurs < 500: return 5
    if kurs < 1000: return 10
    return 25


def runde_strike(strike: float, kurs: float) -> float:
    intv = _strike_intervall(kurs)
    return round(strike / intv) * intv


def praemien_zerlegung(kurs: float, ent: dict, sigma: float) -> dict | None:
    """Zerlegt die Praemie einer Agenten-Order in inneren Wert und Zeitwert.

    Das ist die Spalte, ohne die eine Hebelwette wie eine Praemienstrategie
    aussieht: Ein Short Put mit Strike 10 % ueber dem Kurs bringt scheinbar
    viel Praemie, aber fast alles davon ist innerer Wert, der bei Andienung
    wieder abfliesst.
    """
    if ent["aktion"] in ("nothing", "close_position"):
        return None
    typ = "call" if "call" in ent["aktion"] else "put"
    ist_short = ent["aktion"].startswith("sell_")
    nk = ent["kontrakte"]
    stueck = nk * AKTIEN_PRO_KONTRAKT

    strike = runde_strike(kurs * (1 + ent["strike_pct"]), kurs)
    T = ent["laufzeit"] / 365.0
    p, _ = binomial_optionspreis(S=kurs, K=strike, T=T, r=ZINS, sigma=sigma,
                                 n=50, option_type=typ)
    inner = max(strike - kurs, 0.0) if typ == "put" else max(kurs - strike, 0.0)
    zeitwert = p - inner

    im_geld = inner > 0
    margin = (MARGIN_NAKED_PCT * kurs * AKTIEN_PRO_KONTRAKT * nk) if ist_short else 0.0
    nominale = strike * stueck

    return {
        "typ": typ,
        "richtung": "short" if ist_short else "long",
        "strike": strike,
        "abstand_pct": strike / kurs - 1.0,
        "im_geld": im_geld,
        "preis_je_stueck": p,
        "praemie_gesamt": p * stueck,
        "innerer_wert": inner * stueck,
        "zeitwert": zeitwert * stueck,
        "zeitwert_anteil": (zeitwert / p) if p > 0 else 0.0,
        "margin": margin,
        "nominale": nominale,
        "hebel": (nominale / margin) if margin > 0 else 0.0,
    }


def verfall_profil(kurs: float, ent: dict, zerl: dict,
                   schritte=(-0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15)) -> pd.DataFrame:
    """Ergebnis der Order bei Verfall, je nach Kursentwicklung.

    Nur fuer Short-Positionen sinnvoll aussagekraeftig; bei Long ist die
    Praemie der maximale Verlust.
    """
    zeilen = []
    for pct in schritte:
        ende = kurs * (1 + pct)
        if zerl["typ"] == "put":
            inner_ende = max(zerl["strike"] - ende, 0.0)
        else:
            inner_ende = max(ende - zerl["strike"], 0.0)
        stueck = ent["kontrakte"] * AKTIEN_PRO_KONTRAKT
        if zerl["richtung"] == "short":
            ergebnis = zerl["praemie_gesamt"] - inner_ende * stueck
        else:
            ergebnis = inner_ende * stueck - zerl["praemie_gesamt"]
        zeilen.append({
            # In Prozentpunkten, nicht als Bruch: st.column_config.NumberColumn
            # formatiert nur den Rohwert und rechnet NICHT in Prozent um --
            # aus -0.15 mit "%.0f %%" wuerde sonst "-0 %".
            "Kursänderung": pct * 100,
            "Kurs bei Verfall": ende,
            "Andienung kostet": inner_ende * stueck,
            "Ergebnis": ergebnis,
        })
    return pd.DataFrame(zeilen)

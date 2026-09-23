"""Rechenkern der Put-Schreiber-Liste.

Die Frage, die diese Seite beantwortet: *Auf welche fundamental soliden
US-Aktien kann man einen deutlich aus dem Geld liegenden Put verkaufen, ohne
dass es historisch oft schiefgegangen waere — und was bleibt nach Steuer
davon uebrig?*

Streamlit-frei, wie ``cron_update.py``: der Kern laeuft aus der Kommandozeile,
die Seite ruft ihn nur auf. So ist er ohne Browser pruefbar.

Drei Dinge unterscheiden ihn von der kommerziellen Vorlage:

* **Vertrauensintervall statt blanker Prozentzahl.** Monatliche Startpunkte
  bei drei Monaten Laufzeit ueberlappen sich zu zwei Dritteln. Aus 240
  Beobachtungen werden damit effektiv rund 80 eigenstaendige. Die Quote wird
  deshalb mit einem Wilson-Intervall auf der *effektiven* Fallzahl gezeigt,
  nicht auf der rohen.
* **Rendite auf gebundenes Kapital.** Eine Praemie von 55 $ klingt nach viel
  und ist auf einen bar besicherten Put von 7.500 $ ueber 87 Tage rund 3 %
  im Jahr. Ohne diese Zahl ist die Liste Werbung, keine Entscheidungshilfe.
* **Rendite nach Steuer.** Geschriebene Puts bei IBKR sind unverbriefte
  Derivate (§ 27a Abs 2 Z 7 EStG): Tarifsteuer statt 27,5 %, kein Ausgleich
  mit dem KAP-Topf. Beim Spitzensteuersatz halbiert das die Rendite fast.

Eigene Tabellen (``put_*``), damit der naechtliche Kurs-Cron unberuehrt
bleibt: er liest ``stock_data`` und darf von diesem Modul nichts merken.
"""
from __future__ import annotations

import math
import os
import sqlite3
from datetime import date, timedelta

import pandas as pd

DB_PATH = os.environ.get("STOCKS_DB", "/data/stocks.db")

# Die drei Kombinationen der Vorlage: Abstand zum Kurs und Laufzeit in Monaten.
KOMBINATIONEN: tuple[tuple[int, int], ...] = ((15, 3), (15, 6), (20, 6))

# Handelstage je Monat -- gebraucht, um vom Startpunkt zum Verfall zu zaehlen.
# Kalendertage waeren ungenau, weil die Kursreihe nur Handelstage kennt.
HANDELSTAGE_MONAT = 21

# Fundamentale Ausschlusskriterien (wie die Vorlage).
MAX_NETTOSCHULDEN_EBITDA = 4.0

# Mindestzahl eigenstaendiger Zeitraeume, damit eine Quote ueberhaupt gezeigt
# wird. Bei weniger ist die Zahl ein Zufallsprodukt.
MIN_EIGENSTAENDIG = 20


def verbindung(db_path: str | None = None) -> sqlite3.Connection:
    return sqlite3.connect(db_path or DB_PATH, timeout=30)


def tabellen_anlegen(conn: sqlite3.Connection) -> None:
    """Eigene Tabellen. ``put_hist`` bewusst getrennt von ``stock_data``.

    ``stock_data`` beginnt am 21.10.2009 und wird jede Nacht fortgeschrieben.
    Wir brauchen aber die Jahre 2006-2009, sonst fehlt der Crash 2008/09 --
    also genau der Zeitraum, der eine solche Liste ehrlich macht. Diese
    Altdaten in ``stock_data`` nachzutragen haette den Cron beruehrt; er
    bestimmt seinen Startpunkt aus dem letzten Eintrag und muss unveraendert
    bleiben.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS put_hist (
            symbol TEXT NOT NULL,
            date   TEXT NOT NULL,
            close  REAL NOT NULL,
            PRIMARY KEY (symbol, date)
        );
        CREATE TABLE IF NOT EXISTS put_fundamental (
            symbol          TEXT PRIMARY KEY,
            name            TEXT,
            sektor          TEXT,
            fcf             REAL,
            nettoschulden   REAL,
            ebitda          REAL,
            schulden_ebitda REAL,
            kurs            REAL,
            stand           TEXT
        );
        CREATE TABLE IF NOT EXISTS put_ergebnis (
            symbol          TEXT NOT NULL,
            kombi           TEXT NOT NULL,
            faelle          INTEGER,
            eigenstaendig   INTEGER,
            unter           INTEGER,
            p_ausuebung     REAL,
            ci_lo           REAL,
            ci_hi           REAL,
            mittl_rueckgang REAL,
            max_rueckgang   REAL,
            historie_ab     TEXT,
            kurs            REAL,
            stand           TEXT,
            PRIMARY KEY (symbol, kombi)
        );
        CREATE TABLE IF NOT EXISTS put_universum (
            symbol TEXT PRIMARY KEY,
            quelle TEXT,
            stand  TEXT
        );
        """
    )
    conn.commit()


# --------------------------------------------------------------------------
# Kurshistorie
# --------------------------------------------------------------------------
def kursreihe(conn: sqlite3.Connection, symbol: str) -> pd.Series:
    """Schlusskurse eines Titels, aus beiden Quellen zusammengesetzt.

    ``put_hist`` deckt die Jahre vor 2009 ab, ``stock_data`` den Rest. Wo sich
    beide ueberschneiden, gewinnt ``stock_data`` -- die Reihe wird taeglich
    gepflegt und ist um Splits bereinigt konsistent mit dem Rest der App.
    """
    alt = pd.read_sql_query(
        "SELECT date, close FROM put_hist WHERE symbol = ? ORDER BY date",
        conn, params=(symbol,))
    neu = pd.read_sql_query(
        "SELECT date, close FROM stock_data WHERE symbol = ? ORDER BY date",
        conn, params=(symbol,))
    teile = [d for d in (alt, neu) if not d.empty]
    if not teile:
        return pd.Series(dtype=float)
    # Leere Rahmen bewusst vorher aussortiert: pandas warnt sonst, weil es
    # aus einem leeren Rahmen keine Spaltentypen ableiten kann.
    df = pd.concat(teile)
    df = df.drop_duplicates(subset="date", keep="last").sort_values("date")
    s = pd.Series(df["close"].to_numpy(dtype=float),
                  index=pd.to_datetime(df["date"]))
    return s[s > 0]


def historie_laden(symbols: list[str], start: str = "2005-01-01",
                   db_path: str | None = None, pause: float = 0.6) -> dict:
    """Altdaten von Yahoo nachladen -- einmalig, nicht im Nachtlauf.

    Der Kurs-Cron aktualisiert 3.200 Titel ueber dieselbe Bibliothek und
    dieselbe IP. Wer hier parallel haemmert, riskiert die Drosselung genau
    dieser Verbindung, deshalb die Pause und der Aufruf von Hand.
    """
    import time
    import yfinance as yf

    conn = verbindung(db_path)
    tabellen_anlegen(conn)
    bericht = {"geladen": 0, "zeilen": 0, "fehler": []}
    for sym in symbols:
        try:
            df = yf.Ticker(sym).history(start=start, end="2010-01-01",
                                        auto_adjust=True)
            if df is None or df.empty:
                bericht["fehler"].append((sym, "leer"))
                continue
            rows = [(sym, d.strftime("%Y-%m-%d"), float(c))
                    for d, c in zip(df.index, df["Close"]) if c and c > 0]
            conn.executemany(
                "INSERT OR REPLACE INTO put_hist (symbol, date, close) "
                "VALUES (?, ?, ?)", rows)
            conn.commit()
            bericht["geladen"] += 1
            bericht["zeilen"] += len(rows)
        except Exception as exc:                      # pragma: no cover
            bericht["fehler"].append((sym, type(exc).__name__))
        time.sleep(pause)
    conn.close()
    return bericht


# --------------------------------------------------------------------------
# Backtest
# --------------------------------------------------------------------------
def wilson(treffer: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Vertrauensintervall fuer einen Anteil.

    Wilson und nicht die Normalnaeherung: Bei Quoten nahe 100 % -- und genau
    darum geht es hier -- liefert die Normalnaeherung Intervalle, die ueber
    1 hinausragen, also Unsinn. Wilson bleibt im Bereich.
    """
    if n <= 0:
        return (0.0, 1.0)
    p = treffer / n
    nenner = 1 + z * z / n
    mitte = (p + z * z / (2 * n)) / nenner
    rand = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / nenner
    return (max(0.0, mitte - rand), min(1.0, mitte + rand))


def backtest(kurse: pd.Series, abstand_pct: int, monate: int) -> dict:
    """Wie oft lag der Kurs bei Verfall unter dem Ausuebungspreis?

    Nachgebaut wie in der Vorlage: an jedem Monatsanfang eine gedachte
    Position, Ausuebungspreis ``abstand_pct`` Prozent unter dem damaligen
    Kurs, Vergleich mit dem Kurs ``monate`` Monate spaeter.

    Zusaetzlich zur reinen Quote:

    * ``mittl_rueckgang`` -- wie tief der Kurs lag, *wenn* es schiefging.
      Die Quote allein verschweigt die Fallhoehe.
    * ``eigenstaendig`` -- Zahl der sich nicht ueberlappenden Zeitraeume
      (Beobachtungen geteilt durch die Laufzeit in Monaten). Auf dieser
      kleineren Zahl steht das Vertrauensintervall, denn benachbarte
      Startpunkte teilen sich den groessten Teil ihres Kursverlaufs und sind
      keine unabhaengigen Versuche.
    """
    if kurse.empty:
        return {}
    monatsanfang = kurse.resample("MS").first().dropna()
    schritt = HANDELSTAGE_MONAT * monate
    faktor = 1 - abstand_pct / 100.0

    faelle, unter, rueckgaenge = 0, 0, []
    idx = kurse.index
    for tag, start_kurs in monatsanfang.items():
        pos = idx.searchsorted(tag)
        ziel = pos + schritt
        if ziel >= len(kurse):
            break
        strike = float(start_kurs) * faktor
        end_kurs = float(kurse.iloc[ziel])
        faelle += 1
        if end_kurs < strike:
            unter += 1
            rueckgaenge.append((strike - end_kurs) / strike * 100.0)

    if not faelle:
        return {}
    eigenstaendig = max(1, faelle // monate)
    # Treffer auf die effektive Fallzahl herunterskaliert, sonst waere das
    # Intervall wieder so schmal wie bei unabhaengigen Beobachtungen.
    treffer_eff = round((faelle - unter) / faelle * eigenstaendig)
    lo, hi = wilson(treffer_eff, eigenstaendig)
    return {
        "faelle": faelle,
        "eigenstaendig": eigenstaendig,
        "unter": unter,
        "p_halten": (faelle - unter) / faelle,
        "p_ausuebung": unter / faelle,
        "ci_lo": lo,
        "ci_hi": hi,
        "mittl_rueckgang": (sum(rueckgaenge) / len(rueckgaenge)
                            if rueckgaenge else 0.0),
        "max_rueckgang": max(rueckgaenge) if rueckgaenge else 0.0,
        "von": str(monatsanfang.index[0].date()),
        "bis": str(monatsanfang.index[-1].date()),
    }


def profil(conn: sqlite3.Connection, symbol: str) -> dict:
    """Alle drei Kombinationen eines Titels plus Durchschnittsquote.

    Die Durchschnittsquote ist das Rangkriterium der Vorlage. Sie wird hier
    mitgerechnet, aber die Liste danach zu sortieren ist ein Zirkelschluss --
    man waehlt nach der Zahl aus, die man anschliessend als Guetesiegel zeigt.
    Die Seite sortiert deshalb nach Rendite und zeigt die Quote daneben.
    """
    kurse = kursreihe(conn, symbol)
    if kurse.empty:
        return {}
    out = {"symbol": symbol, "kurs": float(kurse.iloc[-1]),
           "historie_ab": str(kurse.index[0].date()), "kombis": {}}
    quoten = []
    for abstand, monate in KOMBINATIONEN:
        b = backtest(kurse, abstand, monate)
        if not b:
            continue
        out["kombis"][f"{abstand}/{monate}"] = b
        quoten.append(b["p_ausuebung"])
    if not quoten:
        return {}
    out["p_ausuebung_schnitt"] = sum(quoten) / len(quoten)
    out["genug_daten"] = all(
        k["eigenstaendig"] >= MIN_EIGENSTAENDIG for k in out["kombis"].values())
    return out


# --------------------------------------------------------------------------
# Rendite und Steuer
# --------------------------------------------------------------------------
def rendite(praemie_je_aktie: float, strike: float, tage: int,
            grenzsteuer_pct: float = 0.0) -> dict:
    """Was die Praemie auf das gebundene Kapital bringt.

    Bezugsgroesse ist der Ausuebungspreis, nicht der Kurs: Wer den Put bar
    besichert, muss genau ``strike * 100`` bereithalten. Das ist der
    ehrliche Nenner und der Grund, warum aus einer scheinbar hohen Praemie
    eine niedrige Jahresrendite wird.

    Die Steuer ist kein Beiwerk. Unverbriefte Derivate fallen unter den
    Tarif (§ 27a Abs 2 Z 7 EStG), nicht unter die 27,5 %.
    """
    kapital = strike * 100.0
    praemie = praemie_je_aktie * 100.0
    if kapital <= 0 or tage <= 0:
        return {}
    roh = praemie / kapital
    netto_praemie = praemie * (1 - grenzsteuer_pct / 100.0)
    return {
        "praemie_kontrakt": praemie,
        "kapital": kapital,
        "rendite_periode": roh,
        "rendite_pa": roh * 365.0 / tage,
        "rendite_pa_netto": (netto_praemie / kapital) * 365.0 / tage,
        "praemie_netto": netto_praemie,
    }


# --------------------------------------------------------------------------
# Universum und Fundamentaldaten
# --------------------------------------------------------------------------
WIKI_SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# Zum Nasdaq 100 gibt es auf Wikipedia keine maschinenlesbare Mitgliederliste
# mehr (Stand 09/2026: die Seite fuehrt die Werte nur noch im Fliesstext, die
# frueheren Unterseiten antworten mit 404). Die Vorlage nennt S&P 500 UND
# Nasdaq 100 als Universum; wir beschraenken uns deshalb sichtbar auf den
# S&P 500, statt eine handgepflegte Tickerliste in den Code zu schreiben, die
# nach dem naechsten Indexwechsel still falsch waere. Der Verlust ist klein:
# die meisten Nasdaq-100-Werte stehen ohnehin im S&P 500.
QUELLEN = ((WIKI_SP500, "SP500"),)


def universum_laden(db_path: str | None = None) -> dict:
    """Indexmitglieder von Wikipedia, geschnitten mit unserer Kursliste.

    Die Indexzugehoerigkeit aendert sich ein paar Mal im Jahr; sie fest in den
    Code zu schreiben hiesse, eine stille Altlast anzulegen. Der Schnitt mit
    ``stock_list`` ist keine Schoenheitskorrektur: Fuer einen Titel ohne
    Kursreihe kann der Backtest nichts rechnen, er wuerde nur eine leere
    Zeile erzeugen.
    """
    from io import StringIO

    import requests

    kopf = {"User-Agent": "Mozilla/5.0 (research-tool; Kursanalyse)"}
    gefunden: dict[str, str] = {}
    for url, quelle in QUELLEN:
        html = requests.get(url, headers=kopf, timeout=30).text
        for tab in pd.read_html(StringIO(html)):
            spalten = [s for s in tab.columns if str(s).strip() in ("Symbol", "Ticker")]
            if not spalten:
                continue
            for roh in tab[spalten[0]].astype(str):
                # Yahoo schreibt Klassen mit Bindestrich (BRK-B), Wikipedia
                # mit Punkt (BRK.B). Ohne diese Umschrift faende der
                # Kursabruf die Titel nicht.
                sym = roh.strip().upper().replace(".", "-")
                if 1 <= len(sym) <= 6 and sym.isascii() and sym.replace("-", "").isalnum():
                    gefunden.setdefault(sym, quelle)
            break

    conn = verbindung(db_path)
    tabellen_anlegen(conn)

    # Dazu die eigene Options-Merkliste. Der S&P 500 nimmt keine
    # auslaendischen Emittenten auf -- ASML, Novo Nordisk oder AstraZeneca
    # koennen dort gar nicht stehen, obwohl auf sie Optionen gehandelt
    # werden. Der Nasdaq 100 haette sie, ist aber nicht mehr maschinenlesbar
    # abrufbar. Die Merkliste steht in der Datenbank und nicht im Code: das
    # Repository ist oeffentlich, die gehandelten Basiswerte sind es nicht.
    try:
        for (sym,) in conn.execute("SELECT DISTINCT symbol FROM option_watchlist"):
            if sym:
                gefunden.setdefault(sym.strip().upper(), "MERKLISTE")
    except sqlite3.OperationalError:
        pass

    bekannt = {r[0] for r in conn.execute("SELECT symbol FROM stock_list")}
    stand = date.today().isoformat()
    zeilen = [(s, q, stand) for s, q in gefunden.items() if s in bekannt]
    conn.execute("DELETE FROM put_universum")
    conn.executemany(
        "INSERT OR REPLACE INTO put_universum (symbol, quelle, stand) "
        "VALUES (?, ?, ?)", zeilen)
    conn.commit()
    conn.close()
    return {"gefunden": len(gefunden), "mit_kursen": len(zeilen),
            "ohne_kursreihe": len(gefunden) - len(zeilen)}


def fundamental_laden(symbols: list[str], db_path: str | None = None,
                      pause: float = 0.4) -> dict:
    """Freier Cashflow und Nettoverschuldung/EBITDA je Titel.

    Beides aendert sich quartalsweise -- ein woechentlicher Lauf reicht, und
    mehr waere gegenueber Yahoo unhoeflich. Fehlende Werte werden als NULL
    gespeichert und spaeter als "unbekannt" behandelt, nicht als "erfuellt":
    Ein Filter, der bei fehlenden Daten durchwinkt, ist kein Filter.
    """
    import time
    import yfinance as yf

    conn = verbindung(db_path)
    tabellen_anlegen(conn)
    stand = date.today().isoformat()
    ok, leer = 0, 0
    for sym in symbols:
        try:
            info = yf.Ticker(sym).info or {}
        except Exception:
            info = {}
        if not info:
            leer += 1
            time.sleep(pause)
            continue
        fcf = info.get("freeCashflow")
        ebitda = info.get("ebitda")
        schulden = info.get("totalDebt")
        cash = info.get("totalCash")
        netto = (schulden - cash) if (schulden is not None and cash is not None) else None
        quote = (netto / ebitda) if (netto is not None and ebitda) else None
        conn.execute(
            "INSERT OR REPLACE INTO put_fundamental (symbol, name, sektor, fcf, "
            "nettoschulden, ebitda, schulden_ebitda, kurs, stand) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (sym, info.get("shortName"), info.get("sector"),
             fcf, netto, ebitda, quote,
             info.get("currentPrice") or info.get("regularMarketPrice"), stand))
        conn.commit()
        ok += 1
        time.sleep(pause)
    conn.close()
    return {"geschrieben": ok, "ohne_daten": leer}


def kandidaten(conn: sqlite3.Connection) -> pd.DataFrame:
    """Fundamental gesunde Titel des Universums.

    Wie in der Vorlage: negativer freier Cashflow oder Nettoverschuldung ueber
    dem Vierfachen des EBITDA schliessen aus. Unbekannte Werte schliessen
    ebenfalls aus -- siehe ``fundamental_laden``.
    """
    df = pd.read_sql_query(
        "SELECT f.symbol, f.name, f.sektor, f.fcf, f.schulden_ebitda, f.kurs, "
        "       u.quelle "
        "FROM put_fundamental f JOIN put_universum u ON u.symbol = f.symbol",
        conn)
    if df.empty:
        return df
    return df[(df["fcf"] > 0) &
              (df["schulden_ebitda"].notna()) &
              (df["schulden_ebitda"] <= MAX_NETTOSCHULDEN_EBITDA)].copy()


def alles_rechnen(db_path: str | None = None, nur: list[str] | None = None) -> dict:
    """Backtest fuer alle Kandidaten, Ergebnis in ``put_ergebnis``.

    Die Seite rechnet nichts selbst: Vierhundert Kursreihen bei jedem
    Seitenaufruf durchzugehen waere verschwendete Zeit fuer ein Ergebnis, das
    sich nur einmal am Tag aendert -- die Kurse kommen ja aus dem Nachtlauf.
    """
    conn = verbindung(db_path)
    tabellen_anlegen(conn)
    symbole = nur or list(kandidaten(conn)["symbol"])
    stand = date.today().isoformat()
    geschrieben, ohne = 0, 0
    for sym in symbole:
        pr = profil(conn, sym)
        if not pr:
            ohne += 1
            continue
        for kombi, b in pr["kombis"].items():
            conn.execute(
                "INSERT OR REPLACE INTO put_ergebnis (symbol, kombi, faelle, "
                "eigenstaendig, unter, p_ausuebung, ci_lo, ci_hi, "
                "mittl_rueckgang, max_rueckgang, historie_ab, kurs, stand) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (sym, kombi, b["faelle"], b["eigenstaendig"], b["unter"],
                 b["p_ausuebung"], b["ci_lo"], b["ci_hi"],
                 b["mittl_rueckgang"], b["max_rueckgang"],
                 pr["historie_ab"], pr["kurs"], stand))
        geschrieben += 1
    conn.commit()
    conn.close()
    return {"gerechnet": geschrieben, "ohne_kursreihe": ohne}


def rangliste(conn: sqlite3.Connection, kombi: str = "15/3") -> pd.DataFrame:
    """Fertige Tabelle fuer die Seite: Backtest + Stammdaten.

    Sortiert nach Ausuebungswahrscheinlichkeit wie die Vorlage -- mit dem
    Unterschied, dass die Unsicherheit danebensteht. Zwei Titel mit je
    "100 % gehalten" sind nicht gleich gut, wenn der eine auf 67 und der
    andere auf 25 eigenstaendigen Zeitraeumen beruht.
    """
    df = pd.read_sql_query(
        "SELECT e.*, f.name, f.sektor, f.schulden_ebitda, u.quelle "
        "FROM put_ergebnis e "
        "LEFT JOIN put_fundamental f ON f.symbol = e.symbol "
        "LEFT JOIN put_universum u ON u.symbol = e.symbol "
        "WHERE e.kombi = ? ORDER BY e.p_ausuebung, e.ci_lo DESC",
        conn, params=(kombi,))
    return df


# --------------------------------------------------------------------------
# Optionspraemie
# --------------------------------------------------------------------------
def praemie_fuer(symbol: str, abstand_pct: int, monate: int,
                 kurs: float | None = None) -> dict:
    """Marktpraemie fuer den passenden Put -- ein Yahoo-Abruf je Aufruf.

    Bewusst nur fuer einzelne Zeilen auf Knopfdruck, nicht fuer die ganze
    Liste: An derselben Bibliothek und IP haengt der naechtliche Kurslauf
    fuer 3.200 Titel; sechzig Kettenabrufe am Stueck waeren genau die Art
    Last, die zur Drosselung fuehrt.

    Genommen wird die Mitte aus Geld- und Briefkurs. ``lastPrice`` waere
    bequemer, ist bei duenn gehandelten Kontrakten aber unter Umstaenden
    Wochen alt, ohne dass die Zahl das verriete.
    """
    import yfinance as yf

    tk = yf.Ticker(symbol)
    verfalle = list(tk.options or [])
    if not verfalle:
        return {}
    ziel = date.today() + timedelta(days=int(round(monate * 30.44)))
    verfall = min(verfalle, key=lambda v: abs((date.fromisoformat(v) - ziel).days))
    kette = tk.option_chain(verfall).puts
    if kette is None or kette.empty:
        return {}
    if kurs is None:
        # fast_info ist je nach yfinance-Fassung ein dict oder ein Objekt --
        # deshalb beides versuchen, statt sich auf eine Form zu verlassen.
        try:
            fi = tk.fast_info
            kurs = float(fi["last_price"] if "last_price" in dir(fi) or
                         isinstance(fi, dict) else 0) or None
        except Exception:
            kurs = None
    if not kurs:
        return {}
    ziel_strike = kurs * (1 - abstand_pct / 100.0)
    zeile = kette.iloc[(kette["strike"] - ziel_strike).abs().argmin()]
    bid, ask = float(zeile.get("bid") or 0), float(zeile.get("ask") or 0)
    mid = (bid + ask) / 2 if bid > 0 and ask > 0 else float("nan")
    tage = (date.fromisoformat(verfall) - date.today()).days
    return {
        "verfall": verfall, "tage": tage, "strike": float(zeile["strike"]),
        "ziel_strike": ziel_strike, "bid": bid, "ask": ask, "mid": mid,
        "volumen": zeile.get("volume"), "offen": zeile.get("openInterest"),
        "iv": zeile.get("impliedVolatility"),
    }


def _selbsttest() -> int:
    """Rechenkern gegen von Hand nachvollziehbare Faelle."""
    fehler = 0

    # 1. Stetig steigender Kurs -> nie ausgeuebt.
    idx = pd.date_range("2006-01-02", periods=2600, freq="B")
    steigend = pd.Series([100 * (1.0004 ** i) for i in range(len(idx))], index=idx)
    b = backtest(steigend, 15, 3)
    assert b["unter"] == 0, b
    assert b["p_ausuebung"] == 0.0
    assert b["eigenstaendig"] == b["faelle"] // 3

    # 2. Stetig fallender Kurs -> immer ausgeuebt, Rueckgang positiv.
    #    0,5 % je Handelstag: nach 63 Tagen steht der Kurs bei 73 % des
    #    Startwerts, also klar unter dem 85-%-Strike. Mit 0,1 % je Tag waere
    #    er nur 6 % gefallen und der Put trotz Dauerbaisse nie ausgeuebt --
    #    ein Testfall, der nichts zeigt.
    fallend = pd.Series([100 * (0.995 ** i) for i in range(len(idx))], index=idx)
    b2 = backtest(fallend, 15, 3)
    assert b2["p_ausuebung"] == 1.0, b2
    assert b2["mittl_rueckgang"] > 0

    # 3. Wilson bleibt im Bereich [0,1] -- der Grund, warum nicht die
    #    Normalnaeherung benutzt wird.
    lo, hi = wilson(80, 80)
    assert 0.0 <= lo <= 1.0 and hi <= 1.0, (lo, hi)
    assert lo < 1.0, "Obergrenze 1 bei 80/80 ist richtig, Untergrenze nicht"

    # 4. Rendite: 55 $ Praemie, Strike 75, 87 Tage -> 0,73 % / ~3 % p. a.
    r = rendite(0.55, 75.0, 87)
    assert abs(r["rendite_periode"] - 0.007333) < 1e-5, r
    assert abs(r["rendite_pa"] - 0.03077) < 1e-4, r
    # 5. Bei 50 % Grenzsteuer bleibt die Haelfte.
    r2 = rendite(0.55, 75.0, 87, grenzsteuer_pct=50.0)
    assert abs(r2["rendite_pa_netto"] - r["rendite_pa"] / 2) < 1e-9, r2

    print("Selbsttest bestanden (5 Faelle)" if not fehler else "FEHLER")
    return fehler


def merkliste_status(conn: sqlite3.Connection) -> pd.DataFrame:
    """Warum ein Titel der eigenen Merkliste in der Liste fehlt.

    Ohne diese Auskunft endet jede Luecke in derselben Frage -- "warum sehe
    ich ASML nicht?" -- und die Antwort ist jedes Mal eine andere: kein
    Kursverlauf, fundamental ausgeschlossen, oder schlicht noch nicht
    gerechnet. Die Tabelle beantwortet sie von selbst.
    """
    try:
        merk = pd.read_sql_query(
            "SELECT DISTINCT symbol FROM option_watchlist", conn)
    except Exception:
        return pd.DataFrame()
    if merk.empty:
        return merk
    zeilen = []
    for sym in merk["symbol"]:
        f = conn.execute(
            "SELECT fcf, schulden_ebitda, name FROM put_fundamental "
            "WHERE symbol = ?", (sym,)).fetchone()
        hat_kurse = conn.execute(
            "SELECT 1 FROM stock_data WHERE symbol = ? LIMIT 1", (sym,)).fetchone()
        gerechnet = conn.execute(
            "SELECT count(*) FROM put_ergebnis WHERE symbol = ?", (sym,)).fetchone()[0]
        if gerechnet:
            grund = "in der Liste"
        elif not hat_kurse:
            grund = "keine Kursreihe in der Datenbank"
        elif f is None:
            grund = "Fundamentaldaten fehlen — noch nicht abgerufen"
        elif f[0] is None or f[0] <= 0:
            grund = "freier Cashflow negativ oder unbekannt"
        elif f[1] is None:
            grund = "Nettoverschuldung/EBITDA unbekannt"
        elif f[1] > MAX_NETTOSCHULDEN_EBITDA:
            grund = f"Nettoverschuldung {f[1]:.1f}× EBITDA (Grenze {MAX_NETTOSCHULDEN_EBITDA:.0f}×)"
        else:
            grund = "gefiltert — noch nicht gerechnet"
        zeilen.append({"symbol": sym, "name": (f[2] if f else None),
                       "status": grund})
    return pd.DataFrame(zeilen).sort_values(["status", "symbol"])


def main(argv: list[str] | None = None) -> int:
    """Kommandozeile -- der Nachtlauf ruft genau diese Schritte auf.

    Getrennte Schalter, weil die Schritte sehr unterschiedlich teuer sind:
    ``--rechnen`` arbeitet rein lokal und darf jede Nacht laufen,
    ``--fundamental`` und ``--historie`` fragen Yahoo und gehoeren auf einen
    laengeren Takt.
    """
    import argparse

    ap = argparse.ArgumentParser(description="Put-Schreiber-Liste")
    ap.add_argument("--selbsttest", action="store_true")
    ap.add_argument("--universum", action="store_true",
                    help="Indexmitglieder neu holen")
    ap.add_argument("--fundamental", action="store_true",
                    help="Cashflow/Verschuldung neu holen (langsam, woechentlich)")
    ap.add_argument("--nur-neu", action="store_true",
                    help="mit --fundamental: nur Titel ohne gespeicherte Werte")
    ap.add_argument("--historie", action="store_true",
                    help="Kurse 2005-2010 fuer Kandidaten nachladen (einmalig)")
    ap.add_argument("--rechnen", action="store_true",
                    help="Backtest fuer alle Kandidaten (lokal, schnell)")
    a = ap.parse_args(argv)

    if a.selbsttest:
        return _selbsttest()
    if not any((a.universum, a.fundamental, a.historie, a.rechnen)):
        ap.print_help()
        return 0

    if a.universum:
        print("Universum:", universum_laden())
    conn = verbindung()
    tabellen_anlegen(conn)
    if a.fundamental:
        syms = [r[0] for r in conn.execute(
            "SELECT symbol FROM put_universum ORDER BY symbol")]
        if a.nur_neu:
            # Nach einer Erweiterung des Universums waeren sonst 490
            # Abrufe faellig, obwohl zwanzig fehlen.
            da = {r[0] for r in conn.execute("SELECT symbol FROM put_fundamental")}
            syms = [s for s in syms if s not in da]
        print(f"Fundamentaldaten fuer {len(syms)} Titel:", fundamental_laden(syms))
    if a.historie:
        # Nur fuer Kandidaten: Altdaten fuer Titel zu laden, die der
        # Fundamentalfilter ohnehin aussortiert, waeren verschenkte Abrufe.
        syms = list(kandidaten(conn)["symbol"])
        fehlt = [s for s in syms if not conn.execute(
            "SELECT 1 FROM put_hist WHERE symbol=? LIMIT 1", (s,)).fetchone()]
        print(f"Historie: {len(fehlt)} von {len(syms)} Kandidaten offen")
        print("Historie:", historie_laden(fehlt))
    if a.rechnen:
        print("Backtest:", alles_rechnen())
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

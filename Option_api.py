import numpy as np
import pandas as pd
import sys
import contextlib
import math
from datetime import datetime, timedelta
from io import StringIO 


class _NormalVerteilung:
    """Ersatz fuer ``scipy.stats.norm`` — gebraucht wird nur ``cdf``.

    scipy waere fuer eine einzige Funktion rund 40 MB im Image, und der Bau
    wiederholt Prophets cmdstan-Schicht, sobald sich requirements.txt aendert.
    Die Verteilungsfunktion ist exakt ueber die Fehlerfunktion darstellbar:
    Phi(x) = 0.5 * (1 + erf(x / sqrt(2))). ``math.erf`` steht in der
    Standardbibliothek — dasselbe Ergebnis, keine Naeherung.
    """

    @staticmethod
    def cdf(x):
        if isinstance(x, np.ndarray):
            return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))
        return 0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0)))


norm = _NormalVerteilung()


def format_number_eu(value, anz_komma):
    return f"{value:,.{anz_komma}f}".replace(",", "X").replace(".", ",").replace("X", ".")

# Modern mit yield
def generiere_daten(n):
    for i in range(n):
        yield i * i  # Pausiert hier und gibt Wert einzeln ab

def float_range(start, stop, step):
    values = []
    x = float(start)
    stop = float(stop)
    step = float(step)
    # Vorwärts
    if step > 0:
        while x <= stop:
            values.append(round(x, 10))
            x += step
    # Rückwärts
    elif step < 0:
        while x >= stop:
            values.append(round(x, 10))
            x += step
    return values

def float_range_y(start, stop, step):
    x = float(start)
    stop = float(stop)
    step = float(step)
    # Vorwärts
    if step > 0:
        while x <= stop:
            yield round(x, 10)
            x += step
    # Rückwärts
    elif step < 0:
        while x >= stop:
            yield round(x, 10)
            x += step
    

def parse_date_auto(datum_str):
    # mögliche Formate
    formats = [
        "%d.%m.%Y",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%d.%m.%y",
        "%d/%m/%y"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(datum_str, fmt).date()
        except ValueError:
            pass
    # Fallback: Pandas versuchen lassen
    try:
        import pandas as pd
        return pd.to_datetime(datum_str).date()
    except:
        raise ValueError(f"Unbekanntes Datumsformat: {datum_str}")

def tage_diff_heute(datum_str):
    datum = parse_date_auto(datum_str)
    heute = datetime.today().date()
    return (datum - heute ).days


def datum_plus(datum_str, tage):
    # Datum automatisch erkennen
    datum = pd.to_datetime(datum_str, dayfirst=True)
    
    # Tage addieren
    neues_datum = datum + timedelta(days=tage)
    
    # Ausgabe im gleichen Format wie Eingabe
    return neues_datum.strftime("%d.%m.%Y")


def black_scholes(S, K, T, r, sigma, option_type='call'):
    """
    Black-Scholes Formel für europäische Optionen
    """
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    if option_type == 'call':
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:  # put
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    
    return price


# --- Binomial Modell ---
def binomial_preis(S, K, T, r, sigma, n, opt_type='put'):
    if T <= 0: return max(K - S, 0) if opt_type == 'put' else max(S - K, 0)
    dt = T / n
    u = np.exp(sigma * np.sqrt(dt))
    d = 1 / u
    p = (np.exp(r * dt) - d) / (u - d)
    discount = np.exp(-r * dt)
    S_tree = S * d**(np.arange(n, -1, -1)) * u**(np.arange(0, n + 1))
    V = np.maximum(K - S_tree, 0) if opt_type == 'put' else np.maximum(S_tree - K, 0)
    for i in range(n - 1, -1, -1):
        V = (p * V[1:] + (1 - p) * V[:-1]) * discount
    return V

def binomial_optionspreis(S, K, T, r=0.03, sigma=0.2, n=1000, option_type='put', exercise='american'):
    """                  
    S: Aktueller Aktienkurs
    K: Basispreis (Strike)
    T: Restlaufzeit in Jahren
    r: Risikofreier Zinssatz (z.B. 0.03 für 3%)
    sigma: Volatilität (z.B. 0.2 für 20%)
    n: Anzahl der Berechnungsschritte (je höher, desto präziser)
    
    """
    
    dt = T / n                                 # Zeitintervall pro Schritt
    u = np.exp(sigma * np.sqrt(dt))            # Aufwärts-Faktor
    d = 1 / u                                  # Abwärts-Faktor
    p = (np.exp(r * dt) - d) / (u - d)         # Risikoneutrale Wahrscheinlichkeit
    discount = np.exp(-r * dt)                 # Abzinsungsfaktor

    # 1. Kursbaum am Laufzeitende berechnen
    S_tree = S * d**(np.arange(n, -1, -1)) * u**(np.arange(0, n + 1))

    # 2. Innerer Wert am Laufzeitende (Payoff)
    if option_type == 'call':
        V = np.maximum(S_tree - K, 0)
    else:
        V = np.maximum(K - S_tree, 0)

    # 3. Rückwärts-Induktion durch den Baum
    for i in range(n - 1, -1, -1):
        V = (p * V[1:] + (1 - p) * V[:-1]) * discount
        
        if exercise == 'american':
            # Vergleich: Halten vs. Sofortige Ausübung
            S_current = S * d**(np.arange(i, -1, -1)) * u**(np.arange(0, i + 1))
            if option_type == 'call':
                V = np.maximum(V, S_current - K)
            else:
                V = np.maximum(V, K - S_current)
    
    return V[0], n

def binomial_optionspreis_toleranz(S, K, T, r=0.03, sigma=0.2, n=1000, option_type='put', 
                          exercise='american', tolerance=0.001, min_steps=10):
    """                  
    S: Aktueller Aktienkurs
    K: Basispreis (Strike)
    T: Restlaufzeit in Jahren
    r: Risikofreier Zinssatz (z.B. 0.03 für 3%)
    sigma: Volatilität (z.B. 0.2 für 20%)
    n: Maximale Anzahl der Berechnungsschritte
    option_type: 'call' oder 'put'
    exercise: 'american' oder 'european'
    tolerance: Maximale erlaubte relative Änderung für Abbruch (z.B. 0.001 für 0.1%)
    min_steps: Minimale Anzahl Schritte vor Konvergenzprüfung
    """
    
    previous_price = None
    steps_used = 0
    
    # Schrittweise erhöhen und Konvergenz prüfen
    for current_n in range(min_steps, n + 1, max(1, min_steps // 2)):
        dt = T / current_n
        u = np.exp(sigma * np.sqrt(dt))
        d = 1 / u
        p = (np.exp(r * dt) - d) / (u - d)
        discount = np.exp(-r * dt)
        
        # 1. Kursbaum am Laufzeitende
        S_tree = S * d**(np.arange(current_n, -1, -1)) * u**(np.arange(0, current_n + 1))
        
        # 2. Innerer Wert am Laufzeitende
        if option_type == 'call':
            V = np.maximum(S_tree - K, 0)
        else:
            V = np.maximum(K - S_tree, 0)
        
        # 3. Rückwärts-Induktion
        for i in range(current_n - 1, -1, -1):
            V = (p * V[1:] + (1 - p) * V[:-1]) * discount
            
            if exercise == 'american':
                S_current = S * d**(np.arange(i, -1, -1)) * u**(np.arange(0, i + 1))
                if option_type == 'call':
                    V = np.maximum(V, S_current - K)
                else:
                    V = np.maximum(V, K - S_current)
        
        current_price = V[0]
        steps_used = current_n
        
        # Konvergenzprüfung
        if previous_price is not None:
            relative_change = abs(current_price - previous_price) / previous_price
            if relative_change < tolerance:
                break
        
        previous_price = current_price
    
    return current_price, steps_used 

def binomial_optionspreis_toleranz_v2(S, K, T, r=0.05, sigma=0.45, n=50, 
                          option_type='put', exercise='american',
                          tolerance=0.001, min_steps=10):
    """
    Berechnet Optionspreis mit Cox-Ross-Rubinstein Binomialmodell
    
    Parameter:
    ----------
    S : float
        Aktueller Aktienkurs
    K : float
        Strike-Preis der Option
    T : float
        Zeit bis Verfall in Jahren (z.B. 28/365)
    r : float
        Risikofreier Zinssatz (jährlich)
    sigma : float
        Volatilität (jährlich)
    n : int
        Maximale Anzahl Zeitschritte
    option_type : str
        'put' oder 'call'
    exercise : str
        'american' oder 'european'
    tolerance : float
        Konvergenz-Toleranz (0.001 = 0.1%)
    min_steps : int
        Minimale Anzahl Schritte
    
    Returns:
    --------
    tuple : (preis, verwendete_schritte)
    """
    
    # Edge Case: Option bereits verfallen
    if T <= 0:
        if option_type == 'call':
            return max(S - K, 0), 1
        else:
            return max(K - S, 0), 1
    
    previous_price = None
    steps_used = 0
    
    # Adaptive Konvergenz: Erhöhe Schritte bis stabil
    for current_n in range(min_steps, n + 1, max(1, min_steps // 2)):
        # Parameter berechnen
        dt = T / current_n
        u = np.exp(sigma * np.sqrt(dt))
        d = 1 / u
        p = (np.exp(r * dt) - d) / (u - d)
        discount = np.exp(-r * dt)
        
        # Baum aufbauen (alle Endkurse)
        S_tree = S * d**(np.arange(current_n, -1, -1)) * u**(np.arange(0, current_n + 1))
        
        # Optionswerte am Verfall
        if option_type == 'call':
            V = np.maximum(S_tree - K, 0)
        else:
            V = np.maximum(K - S_tree, 0)
        
        # Rückwärts durch Baum
        for i in range(current_n - 1, -1, -1):
            # Diskontierte erwartete Werte
            V = (p * V[1:] + (1 - p) * V[:-1]) * discount
            
            # Amerikanische Option: Early Exercise prüfen
            if exercise == 'american':
                S_current = S * d**(np.arange(i, -1, -1)) * u**(np.arange(0, i + 1))
                
                if option_type == 'call':
                    exercise_values = np.maximum(S_current - K, 0)
                else:
                    exercise_values = np.maximum(K - S_current, 0)
                
                V = np.maximum(V, exercise_values)
        
        current_price = V[0]
        steps_used = current_n
        
        # Konvergenz-Check
        if previous_price is not None:
            denominator = max(abs(previous_price), 0.01)
            relative_change = abs(current_price - previous_price) / denominator
            
            if relative_change < tolerance:
                break  # Konvergiert!
        
        previous_price = current_price
    
    return current_price, steps_used

def calc_griechen(S, K, T, r, sigma=0.3, n=1000, option_type='put', exercise='american'):
    # Kleine Änderungen für die numerische Ableitung
    dS = S * 0.01      # 1% Kursänderung für Delta/Gamma
    dt = 1/365         # 1 Tag für Theta
    dsigma = 0.01      # 1% Vola-Änderung für Vega
    
    # Basis-Preis
    P, dl = binomial_optionspreis(S, K, T, r, sigma, n, option_type, exercise)
    #print(S, K, T, r, sigma, n, option_type, exercise, P)
    
    # 1. Delta: Preisänderung bei Kursänderung
    P_up, dl = binomial_optionspreis(S + dS, K, T, r, sigma, n, option_type, exercise)
    P_down, dl = binomial_optionspreis(S - dS, K, T, r, sigma, n, option_type, exercise)
    delta = (P_up - P_down) / (2 * dS)
    
    # 2. Gamma: Änderung von Delta bei Kursänderung
    gamma = (P_up - 2 * P + P_down) / (dS**2)
    
    # 3. Theta: Zeitwertverfall (pro Tag)
    P_next_day, dl = binomial_optionspreis(S, K, T - dt, r, sigma, n, option_type, exercise)
    theta = (P_next_day - P) # Wertverlust pro Tag
    
    # 4. Vega: Sensitivität gegenüber Volatilität (1%-Punkt)
    P_vola_up, dl = binomial_optionspreis(S, K, T, r, sigma + dsigma, n, option_type, exercise)
    vega = (P_vola_up - P) # Preisänderung bei +1% Vola
    
    return [{
        "Preis": round(P, 2),
        "Delta": round(delta, 3),
        "Gamma": round(gamma, 4),
        "Theta(tgl)": round(theta, 3),
        "Vega(1%)": round(vega, 3)
    },
    {
        "Preis": f'{round(P, 2):.2f}',
        "Delta": f'{round(delta, 3):.3f}',
        "Gamma": f'{round(gamma, 4):.4f}',
        "Theta(tgl)": f'{round(theta, 3):.3f}',
        "Vega(1%)": f'{round(vega, 3):.3f}'
    },
           {
        "Pr.": f'{round(P, 2):.2f}',
        "Dlt": f'{round(delta, 3):.3f}',
        "Gma": f'{round(gamma, 4):.4f}',
        "Tha": f'{round(theta, 3):.3f}',
        "Vga": f'{round(vega, 3):.3f}'
    },
            {
        "P": f'{round(P, 2):.2f}',
        "D": f'{round(delta, 3):.3f}',
        "G": f'{round(gamma, 4):.4f}',
        "T": f'{round(theta, 3):.3f}',
        "V": f'{round(vega, 3):.3f}'
    }
           
           ]

def berechne_implizite_vola(marktpreis, S, K, T, r, n, option_type='call', exercise='american'):
    # Suche die Vola zwischen 0.001% und 500%
    low = 0.00001
    high = 5.0
    toleranz = 0.001 # Wie nah wollen wir an den Marktpreis ran?

    for i in range(1000): # Maximal 100 Iterationen
        mid = (low + high) / 2
        test_preis, dl = binomial_optionspreis(S, K, T, r, mid, n, option_type, exercise)

        if abs(test_preis - marktpreis) < toleranz:
            return mid # Gefunden!
        
        if test_preis < marktpreis:
            low = mid
        else:
            high = mid
            
    return mid

def find_next_strike(aktienkurs, strike_abstand, schrittweite):
    """
    Findet den nächsten verfügbaren Strike basierend auf der Schrittweite.
    
    Parameter:
    ----------
    aktienkurs : float
        Aktueller Kurs der Aktie (z.B. 147.32)
    strike_abstand : float
        Gewünschter Abstand zum Aktienkurs (z.B. -5 für 5 unter, +10 für 10 über)
    schrittweite : float
        Abstände zwischen verfügbaren Strikes (z.B. 2.5, 5, 10, 20)
        
    Returns:
    --------
    float : Der nächste verfügbare Strike
    
    Beispiele:
    ----------
    >>> find_next_strike(147.32, -5, 2.5)
    142.5  # 147.32 - 5 = 142.32 → aufgerundet auf 142.5
    
    >>> find_next_strike(147.32, 10, 5)
    155.0  # 147.32 + 10 = 157.32 → abgerundet auf 155.0
    
    >>> find_next_strike(98.7, 0, 2.5)
    100.0  # 98.7 → aufgerundet auf 100.0
    """
    
    # Ziel-Strike berechnen
    ziel_strike = aktienkurs + strike_abstand
    
    # Auf nächste Schrittweite runden
    naechster_strike = round(ziel_strike / schrittweite) * schrittweite
    
    return naechster_strike


def find_strike_range(aktienkurs, min_abstand, max_abstand, schrittweite):
    """
    Erstellt eine Liste aller verfügbaren Strikes in einem Bereich.
    
    Parameter:
    ----------
    aktienkurs : float
        Aktueller Kurs der Aktie
    min_abstand : float
        Minimaler Abstand zum Aktienkurs (z.B. -20)
    max_abstand : float
        Maximaler Abstand zum Aktienkurs (z.B. +20)
    schrittweite : float
        Abstände zwischen Strikes
        
    Returns:
    --------
    list : Sortierte Liste aller verfügbaren Strikes
    
    Beispiel:
    ---------
    >>> find_strike_range(100, -10, 10, 5)
    [90.0, 95.0, 100.0, 105.0, 110.0]
    """
    
    # Hiess frueher ``finde_naechsten_strike`` — eine Funktion dieses Namens hat
    # es nie gegeben, der Aufruf endete in einem NameError. Im Notebook faellt
    # das nicht auf, weil die Strike-Leiter dort ueber ``float_range`` gebaut
    # wird; erst die Optionskette der Weboberflaeche ruft diese Funktion.
    min_strike = find_next_strike(aktienkurs, min_abstand, schrittweite)
    max_strike = find_next_strike(aktienkurs, max_abstand, schrittweite)

    # Alle Strikes im Bereich generieren. Gerundet wird in jedem Schritt, weil
    # sich Schrittweiten wie 2,5 sonst aufaddieren und der letzte Strike knapp
    # ueber der Grenze landet — dann fehlt er in der Liste.
    strikes = []
    current = min_strike
    while round(current, 6) <= round(max_strike, 6):
        strikes.append(round(current, 6))
        current += schrittweite

    return strikes


# Erweiterte Version mit verschiedenen Schrittweiten je nach Kursbereich
def find_next_strike_dyn(aktienkurs, strike_abstand, kurs_regeln=None):
    """
    Findet Strike mit dynamischer Schrittweite basierend auf Kurshöhe.
    
    Parameter:
    ----------
    aktienkurs : float
        Aktueller Kurs
    strike_abstand : float
        Gewünschter Abstand
    kurs_regeln : list of tuples, optional
        Liste mit (max_kurs, schrittweite) Tupeln
        Default: [(50, 2.5), (200, 5), (float('inf'), 10)]
        
    Beispiel:
    ---------
    Aktien unter 50: Schrittweite 2.5
    Aktien 50-200: Schrittweite 5
    Aktien über 200: Schrittweite 10
    """
    
    if kurs_regeln is None:
        # Standard-Regeln (ähnlich wie bei vielen Börsen)
        kurs_regeln = [
            (50, 2.5),
            (200, 5),
            (float('inf'), 10)
        ]
    
    ziel_strike = aktienkurs + strike_abstand
    
    # Passende Schrittweite finden
    schrittweite = 1  # Fallback
    for max_kurs, step in kurs_regeln:
        if ziel_strike <= max_kurs:
            schrittweite = step
            break
    
    naechster_strike = round(ziel_strike / schrittweite) * schrittweite
    
    return naechster_strike    

def check_roll_lohnt_sich(preis_aktuell, preis_neu, gebuehren, tage_rest_alt, tage_neu):
    """
    Berechnet den täglichen Ertrag (Theta-Effizienz) beim Rollen.
    """
    # Verbleibender Gewinn der aktuellen Position (nach Gebühren für den Rückkauf)
    netto_restgewinn = preis_aktuell - gebuehren
    ertrag_pro_tag_alt = netto_restgewinn / tage_rest_alt if tage_rest_alt > 0 else 0
    
    # Möglicher Gewinn der neuen Position (nach Gebühren für den Verkauf)
    netto_neugewinn = preis_neu - gebuehren
    ertrag_pro_tag_neu = netto_neugewinn / tage_neu
    
    lohnt_sich = ertrag_pro_tag_neu > ertrag_pro_tag_alt
    steigerung = (ertrag_pro_tag_neu / ertrag_pro_tag_alt - 1) * 100 if ertrag_pro_tag_alt > 0 else 100
    
    return {
        "Roll-Empfehlung": "JA" if lohnt_sich else "NEIN",
        "Ertrag/Tag Alt": round(ertrag_pro_tag_alt, 2),
        "Ertrag/Tag Neu": round(ertrag_pro_tag_neu, 2),
        "Effizienz-Steigerung": f"{round(steigerung, 1)}%"
    }


def analyze_roll_strategy(S, K_alt, T_alt_tage, K_neu, T_neu_tage, r, sigma, gebuehr):
    # 1. Theoretische Preise berechnen
    preis_alt, dl = binomial_optionspreis(S, K_alt, T_alt_tage/365, r, sigma, 500)
    preis_neu, dl = binomial_optionspreis(S, K_neu, T_neu_tage/365, r, sigma, 500)
    
    # 2. Theta-Effizienz (Ertrag pro Tag)
    # Alt: Was können wir noch verdienen, wenn wir NICHT rollen?
    rest_ertrag_alt = preis_alt - gebuehr
    daily_alt = rest_ertrag_alt / T_alt_tage if T_alt_tage > 0 else 0
    
    # Neu: Was verdienen wir pro Tag, wenn wir JETZT rollen?
    netto_neu = preis_neu - gebuehr
    daily_neu = netto_neu / T_neu_tage
    
    empfehlung = "ROLLEN" if daily_neu > daily_alt else "HALTEN"
    
    return {
        "Aktueller Preis (Markt-Schätzung)": round(preis_alt, 2),
        "Neuer Preis (Prämie)": round(preis_neu, 2),
        "Täglicher Ertrag ALT": round(daily_alt, 3),
        "Täglicher Ertrag NEU": round(daily_neu, 3),
        "Strategie": empfehlung
    }


import numpy as np
from datetime import datetime, timedelta


def naechster_freitag(datum):
    """Findet den nächsten Freitag ab dem gegebenen Datum"""
    tage_bis_freitag = (4 - datum.weekday()) % 7  # 4 = Freitag (0=Montag)
    if tage_bis_freitag == 0:  # Heute ist Freitag
        tage_bis_freitag = 7  # Nächsten Freitag nehmen
    return datum + timedelta(days=tage_bis_freitag)

def alle_freitage(start_datum, anzahl_wochen):
    """Generiert Liste aller Freitage für die nächsten X Wochen"""
    erster_freitag = naechster_freitag(start_datum)
    freitage = []
    
    for i in range(anzahl_wochen):
        freitag = erster_freitag + timedelta(weeks=i)
        freitage.append(freitag)
    
    return freitage

def finde_rolling_laufzeit_mit_datum(aktienkurs, alter_strike, neuer_strike, 
                                     aktuelles_datum, aktuelles_verfalldatum,
                                     option_type='put', min_credit=0.0, 
                                     r=0.05, sigma=0.45, max_wochen=12,
                                     n=50, details=False, tage_offset=0):
    """
    Findet die minimale Laufzeitverlängerung für positiven Credit beim Rollen
    MIT DATUMS-BERECHNUNG und FREITAGS-VERFALLSDATEN
    
    Parameter:
    ----------
    aktienkurs : float
        Aktueller Aktienkurs
    alter_strike : float
        Aktueller Strike der Position
    neuer_strike : float
        Gewünschter neuer Strike
    aktuelles_datum : datetime oder str (YYYY-MM-DD)
        Heutiges Datum
    aktuelles_verfalldatum : datetime oder str (YYYY-MM-DD)
        Verfalldatum der aktuellen Option
    option_type : str
        'put' oder 'call'
    min_credit : float
        Gewünschter Mindest-Credit
    r : float
        Risikofreier Zinssatz
    sigma : float
        Volatilität
    max_wochen : int
        Maximum Wochen zum Testen
    n : int
        Schritte im Binomialbaum. 50 ist der alte Vorgabewert und bleibt es,
        damit bestehende Aufrufe unveraendert rechnen; die Weboberflaeche
        setzt hoeher, weil dort Preis und Griechen nebeneinander stehen.
    tage_offset : int
        Verschiebt alle Restlaufzeiten um denselben Betrag (0 = wie bisher).
    details : bool
        True gibt zusaetzlich die vollstaendige Wochenliste zurueck
        (dritter Rueckgabewert) — fuer Tabelle und Kurve in der Oberflaeche.
        Der Vorgabewert False laesst die Signatur unveraendert.
    
    Returns:
    --------
    dict mit Ergebnissen
    """
    
    # Datums-Parsing
    if isinstance(aktuelles_datum, str):
        aktuelles_datum = datetime.strptime(aktuelles_datum, '%Y-%m-%d')
    if isinstance(aktuelles_verfalldatum, str):
        aktuelles_verfalldatum = datetime.strptime(aktuelles_verfalldatum, '%Y-%m-%d')
    
    # Restlaufzeit berechnen
    # ``tage_offset`` verschiebt JEDE Laufzeit um denselben Betrag — die der
    # alten Position und die jedes geprueften Freitags. Nur so bleibt der
    # Credit die Differenz zweier gleich gezaehlter Preise. Gebraucht wird das
    # fuer die Frage, ob der Verfalltag selbst mitzaehlt: bei vier Tagen
    # Restlaufzeit macht dieser eine Tag rund drei Vola-Punkte aus.
    restlaufzeit = (aktuelles_verfalldatum - aktuelles_datum).days + tage_offset
    
    # Wochentag-Namen
    wochentag_heute = aktuelles_datum.strftime('%A')
    wochentag_verfall = aktuelles_verfalldatum.strftime('%A')


    # Printbefehle in einen Puffer umleiten.
    #
    # Frueher wurde ``sys.stdout`` von Hand umgebogen und am Ende
    # zurueckgesetzt. Im Notebook harmlos, in einer Web-App nicht:
    # ``sys.stdout`` gehoert dem ganzen Prozess, nicht der einzelnen Sitzung.
    # Fliegt zwischen Umbiegen und Zuruecksetzen eine Ausnahme, bleibt die
    # Serverausgabe dauerhaft im Puffer haengen, und bei zwei gleichzeitigen
    # Nutzern schreibt der eine in den Puffer des anderen. ``redirect_stdout``
    # stellt in jedem Fall zurueck, auch im Fehlerfall.
    buffer = StringIO()
    with contextlib.redirect_stdout(buffer):
    
        print(f"\n{'ZEITLICHE ANALYSE':^90}")
        print(f"{'-'*90}")
        print(f"Heutiges Datum:          {aktuelles_datum.strftime('%Y-%m-%d (%A)')}")
        print(f"Aktuelles Verfalldatum:  {aktuelles_verfalldatum.strftime('%Y-%m-%d (%A)')}")
        print(f"Restlaufzeit:            {restlaufzeit} Tage")
    
        if wochentag_verfall != 'Friday':
            print(f"⚠️  Warnung: Verfalldatum ist kein Freitag!")
    
        # Aktuellen Optionspreis berechnen
        alter_preis, _ = binomial_optionspreis(
            S=aktienkurs, 
            K=alter_strike, 
            T=restlaufzeit/365,
            r=r, 
            sigma=sigma, 
            option_type=option_type,
            n=n
        )
    
        print(f"\n{'AKTUELLE POSITION':^90}")
        print(f"{'-'*90}")
        print(f"Aktienkurs:              ${aktienkurs:,.2f}")
        print(f"Aktueller Strike:        ${alter_strike:,.2f}")
        print(f"Option zurückkaufen:     ${alter_preis:.2f} (Kosten)")
        print(f"Option Typ:              {option_type.upper()}")
    
        if option_type == 'put':
            itm_betrag = max(alter_strike - aktienkurs, 0)
        else:
            itm_betrag = max(aktienkurs - alter_strike, 0)
    
        if itm_betrag > 0:
            print(f"⚠️  Position ist ${itm_betrag:.2f} ITM (im Verlust)")
    
        print(f"\n{'NEUER STRIKE':^90}")
        print(f"{'-'*90}")
        print(f"Gewünschter Strike:      ${neuer_strike:,.2f}")
    
        strike_diff = neuer_strike - alter_strike
        if option_type == 'put':
            if strike_diff < 0:
                print(f"Strike-Änderung:         ${abs(strike_diff):.2f} NIEDRIGER (defensiver)")
            else:
                print(f"Strike-Änderung:         ${strike_diff:.2f} HÖHER (aggressiver)")
        else:
            if strike_diff > 0:
                print(f"Strike-Änderung:         ${strike_diff:.2f} HÖHER (defensiver)")
            else:
                print(f"Strike-Änderung:         ${abs(strike_diff):.2f} NIEDRIGER (aggressiver)")
    
        # Alle verfügbaren Freitage generieren
        verfuegbare_freitage = alle_freitage(aktuelles_datum, max_wochen)
    
        print(f"\n{'VERFÜGBARE VERFALLSDATEN (FREITAGE)':^90}")
        print(f"{'-'*90}")
    
        ergebnisse = []
        erste_positive = None
    
        for idx, freitag in enumerate(verfuegbare_freitage, 1):
            tage_bis_verfall = (freitag - aktuelles_datum).days + tage_offset
            wochen = idx  # Woche 1, 2, 3, etc.
        
            neuer_preis, _ = binomial_optionspreis(
                S=aktienkurs,
                K=neuer_strike,
                T=tage_bis_verfall/365,
                r=r,
                sigma=sigma,
                option_type=option_type,
                n=n
            )
        
            credit = neuer_preis - alter_preis
        
            ergebnisse.append({
                'wochen': wochen,
                'verfalldatum': freitag,
                'tage': tage_bis_verfall,
                'neuer_preis': neuer_preis,
                'credit': credit
            })
        
            if credit >= min_credit and erste_positive is None:
                erste_positive = idx
    
        # Tabelle anzeigen
        print(f"\n{'Woche':<7} {'Verfalldatum':<17} {'Tage':<7} {'Neuer Preis':<15} {'Credit':<15} {'Status':<20}")
        print(f"{'-'*90}")
    
        for erg in ergebnisse:
            status = "✓ POSITIV" if erg['credit'] >= min_credit else "✗ Negativ"
            marker = " ⭐" if erg['credit'] >= min_credit and erg['wochen'] == erste_positive else ""
            datum_str = erg['verfalldatum'].strftime('%Y-%m-%d (%a)')
        
            print(f"{erg['wochen']:<7} {datum_str:<17} {erg['tage']:<7} "
                  f"${erg['neuer_preis']:<14.2f} ${erg['credit']:<14.2f} {status}{marker}")
    
        # Beste Option finden
        positive_credits = [e for e in ergebnisse if e['credit'] >= min_credit]
    
        if positive_credits:
            beste = positive_credits[0]
        
            print(f"\n{'='*90}")
            print(f"{'EMPFEHLUNG':^90}")
            print(f"{'='*90}")
            print(f"Minimale Laufzeit für Credit ≥ ${min_credit:.2f}:")
            print(f"  → Woche {beste['wochen']} - Verfall: {beste['verfalldatum'].strftime('%Y-%m-%d (%A)')}")
            print(f"  → Laufzeit: {beste['tage']} Tage")
            print(f"  → Neuer Optionspreis: ${beste['neuer_preis']:.2f}")
            print(f"  → Credit: ${beste['credit']:.2f} pro Option")
        
            print(f"\n{'TRANSAKTION':^90}")
            print(f"{'-'*90}")
            print(f"Heute ({aktuelles_datum.strftime('%Y-%m-%d')}):")
            print(f"  1. Kaufe zurück: {option_type.upper()} ${alter_strike:.2f} "
                  f"(Verfall {aktuelles_verfalldatum.strftime('%Y-%m-%d')}) @ ${alter_preis:.2f}")
            print(f"  2. Verkaufe neu:  {option_type.upper()} ${neuer_strike:.2f} "
                  f"(Verfall {beste['verfalldatum'].strftime('%Y-%m-%d')}) @ ${beste['neuer_preis']:.2f}")
            print(f"  3. Netto Credit: ${beste['credit']:.2f}")
            print(f"{'='*90}")

            if details:
                return beste, buffer.getvalue(), ergebnisse
            return beste, buffer.getvalue()
        else:
            print(f"\n{'='*90}")
            print(f"⚠️  KEIN POSITIVER CREDIT MÖGLICH")
            print(f"{'='*90}")
            print(f"Selbst mit {max_wochen} Wochen Laufzeit kein positiver Credit erreichbar.")
            print(f"Bester Fall: Woche {ergebnisse[-1]['wochen']} → Credit ${ergebnisse[-1]['credit']:.2f}")
            print(f"\nMögliche Lösungen:")
            print(f"  1. Strike weniger stark ändern")
            print(f"  2. Längere Laufzeit akzeptieren (erhöhe max_wochen)")
            print(f"  3. Negativen Credit akzeptieren")
            print(f"{'='*90}")
        

            if details:
                return False, buffer.getvalue(), ergebnisse
            return False, buffer.getvalue() 
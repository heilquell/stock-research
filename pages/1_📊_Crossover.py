import streamlit as st
import pandas as pd
import streamlit.components.v1 as components

from  stock_db_ops import *
from  stock_show import *
from  stock_screener import *


# Funktion zum automatischen Scrollen nach oben
def scroll_to_top():
    scroll_script = """
    <script>
    window.scrollTo(0, 0);
    </script>
    """
    components.html(scroll_script)

# Setze das Layout auf "wide mode"
st.set_page_config(layout="wide")

def remove_chars(string, chars):
    translation_table = {ord(char): None for char in chars}
    translation_table[ord('"')] = None
    return string.translate(translation_table)


# Main Program---------------------------------------------------------------------------------------
def main():
    st.title("Stock Crossover Database")

    # CSS Styling
    st.markdown("""
        <style>
            /* Streamlit-Buttons: Schrift groesser, kompaktere Box.
               (Selektor war vorher .stButton_** und hat nie gematched.) */
            div[data-testid="stButton"] > button,
            .stButton > button {
                font-size: 15px;
                font-weight: 500;
                padding: 6px 14px;
                min-height: 0;
                line-height: 1.3;
            }
            /* Buy/Sell-Signal-Buttons im Listenmodus links-buendig statt
               zentriert, damit "AAPL: Kaufsignal am 2026-05-15" lesbar
               bleibt auch ohne use_container_width. */
            div[data-testid="stButton"] > button p {
                margin: 0;
                text-align: left;
            }
            .metric-card {
                background-color: #f0f2f6;
                padding: 1rem;
                border-radius: 0.5rem;
                margin: 0.5rem 0;
            }
            .section-header {
                color: #0066cc;
                font-size: 1.2rem;
                font-weight: bold;
                margin: 1rem 0;
            }
            .stDataFrame {
                width: 50%;
            }
        </style>
    """, unsafe_allow_html=True)


    # Datenbank initialisieren
    _conn = init_db()

    # Session-State für ausgewählte Aktie initialisieren
    if 'selected_stock' not in st.session_state:
        st.session_state['selected_stock'] = None
    
    # Session-State für Buy/Sell Signale initialisieren
    if 'buy_signals' not in st.session_state:
        st.session_state['buy_signals'] = []
    if 'sell_signals' not in st.session_state:
        st.session_state['sell_signals'] = []

    # Initialisiere Session State
    if "confirm_delete" not in st.session_state:
        st.session_state.confirm_delete = False        


    # Sidebar für Stock-Hinzufügung und Datenaktualisierung
    #st.sidebar.link_button('Home', 'http://localhost:8501',  help=None, type="primary", icon=None, disabled=False, use_container_width=False)
    if st.sidebar.button("Home", type="primary", help='Seite wird neu geladen'):
        st.session_state.confirm_delete = False
        st.rerun()

    

    st.sidebar.header("Neue Aktien hinzufügen")
    new_stocks = st.sidebar.text_area("Gib neue Aktiensymbole ein (komma-getrennt)", "")

    if st.sidebar.button("Aktien hinzufügen"):
        chars_to_remove = ['"', '{', '}', '[', ']']
        new_stocks = remove_chars(new_stocks, chars_to_remove)
        new_stock_list = [s.strip().upper() for s in new_stocks.split(',') if s.strip()]
        new_stock_list_last = new_stock_list[-1]
        store_sentences(_conn, new_stock_list_last)
        if new_stock_list:
            update_stock_info(_conn, new_stock_list)
            update_stock_data(_conn, new_stock_list)
            st.sidebar.success("Neue Aktie(n)  hinzugefügt!")
            plot_stock_data(new_stock_list[-1], _conn, 3, crossover=1)
            with st.spinner('Lade Daten...'):
                data, success = get_stock_info_data(_conn, new_stock_list[-1])
                #st.text(data)
                if success and data.get('Allgemeine Informationen')['Name'] != 'N/A':
                    stock_info_show(new_stock_list[-1],data)
                else:
                    st.sidebar.warning("Keine gültigen Aktiensymbole eingegeben.")
        else:
            st.sidebar.warning("Keine gültigen Aktiensymbole eingegeben.")
    
    if st.sidebar.button("Aktien löschen"):
        if not st.session_state.confirm_delete:
            st.session_state.confirm_delete = True
            st.sidebar.warning("Bist du sicher, dass du alle Aktien löschen möchtest? Klicke erneut, um zu bestätigen.")
        else:
            # Hier kommt der Code zum tatsächlichen Löschen hin
            chars_to_remove = ['"', '{', '}', '[', ']']
            new_stocks = remove_chars(new_stocks, chars_to_remove)
            new_stock_list = [s.strip().upper() for s in new_stocks.split(',') if s.strip()]
            delete_all_stock_info(_conn, new_stock_list)

            st.sidebar.success("Alle Aktien in der Liste wurden gelöscht.")
            st.session_state.confirm_delete = False  # Zurücksetzen

    # Alle Aktien aus der Datenbank holen
    all_stocks, stocks_dict, count_stocks = get_all_stocks(_conn)
    #st.write(all_stocks)

    if st.sidebar.button("alle Aktien Kurse updaten"):
        st.cache_data
        update_stock_data(_conn, all_stocks)

    if st.sidebar.button("alle Aktien-Infos updaten"):
        stocks = get_stocks_4infoupdate(_conn)
        update_stock_info(_conn, stocks)


    # Hauptbereich------------------------------------------------------------------------------------
    st.header("Aktienanalyse")

    if not all_stocks:
        st.warning("Keine Aktien in der Datenbank. Bitte füge einige Aktien über die Sidebar hinzu.")
    else:
        # Jahresslider zur Vorhersage der Zukunftsperiode
        forecast_years = st.slider(f"Wähle die Anzahl der Jahre für die Prognose", 1, 10, 3)
        crossover_fak1 = st.slider("Wähle den Crossover-Faktor(9/21)", 1, 10, 1)
        st.text(f'{crossover_fak1*9}/{crossover_fak1*21}')
        # Live-Suche mit echtem Substring-Match (Symbol UND Firmenname).
        # streamlit-searchbox triggert die Filter-Funktion bei JEDEM
        # Keystroke und zeigt die Treffer als Dropdown — anders als das
        # native selectbox das Fuzzy-Matching macht und text_input das
        # erst bei Enter aktualisiert.
        from streamlit_searchbox import st_searchbox

        def search_aktien(q: str) -> list[tuple[str, str]]:
            ql = (q or "").strip().lower()
            if not ql:
                # Leere Suche: erste 50 alphabetisch
                items = list(stocks_dict.items())[:50]
            else:
                items = [
                    (sym, name) for sym, name in stocks_dict.items()
                    if ql in sym.lower() or ql in (name or "").lower()
                ][:50]
            return [(f"{sym} — {name}", sym) for sym, name in items]

        if "selected_stock" not in st.session_state:
            st.session_state.selected_stock = None

        selected_stock = st_searchbox(
            search_aktien,
            placeholder=f"Aktie suchen ({count_stocks} verfügbar) — Symbol oder Firmenname",
            key="aktien_searchbox",
            default=st.session_state.get("selected_stock"),
        )
        
        # Wenn eine Aktie ausgewählt ist, die Analyse direkt anzeigen
        # Speichern der Auswahl
        st.session_state.selected_stock = selected_stock


        # Code nach Auswahl ausführen
        if st.session_state.selected_stock:
        #if selected_stock:

        #if st.button("Analyse starten"):
            # stock in senteces speichern als history
            df = find_fav(_conn, selected_stock)
            if df.empty:
                listfav = get_fav_lists(_conn)
                #st.write('keine Favoriten')
                f_col1, f_col2 = st.columns(2)
                with f_col1:
                    selected_favlist = st.selectbox(f"Favoritenlisten",  
                            options=listfav)
                with f_col2:
                    button_placeholder = st.empty()
                    button = button_placeholder.button("Zu Favoriten hinzufügen")
                    if button:
                        #st.write('selected_favlist', selected_favlist)
                        add_fav(_conn, selected_favlist, selected_stock)
                        st.success(f"{selected_stock} wurde zu den Favoriten hinzugefügt!")
                        button_placeholder.empty()
            else:
                f_col1, f_col2 = st.columns(2)
                with f_col1:
                    st.write(df['listname'][0])
                with f_col2:
                    if st.button(f"von Favoriten entfernen"):
                            del_fav(_conn,  selected_stock)
                            st.success(f"{selected_stock} wurde von den Favoriten entfernt!")
                            st.rerun()
        

            store_sentences(_conn, selected_stock)
            plot_stock_data(selected_stock, _conn, forecast_years, crossover=crossover_fak1)
            with st.spinner('Lade Daten...'):
                data, success = get_stock_info_data_db(_conn, selected_stock)
                if success and data:
                    stock_info_show(selected_stock,data)


    # Signal-Analyse Bereich----------------------------------------------------
    st.header("Kauf-/Verkaufssignale")
    days_back = st.slider("Wähle die Anzahl der Tage zurück", 1, 100, 5)
    crossover_fak2 = st.slider("Wähle den Crossover-Faktor(9/21) ", 1, 10, 1)
    st.text(f'{crossover_fak2*9}/{crossover_fak2*21}')
    
    check = st.checkbox("Filter: MA-long > MA-long(4*Crossover-Faktor zurück)") 
    #st.text('Filter: MA-long > MA-long(4*Crossover-Faktor zurück)')
    # Überprüfen, ob die Checkbox aktiviert ist
    filter_MA = False
    if check:
        #st.write("Die Option ist aktiviert.")
        filter_MA = True
       

    #check = st.checkbox("Filter: Volatilitätsfilter")
    filtervola = False
    #st.text('Filter: MA-long > MA-long(4*Crossover-Faktor zurück)')
    # Überprüfen, ob die Checkbox aktiviert ist
    #if check:
        #st.write("Die Option ist aktiviert.")
        #filtervola = True
    
    filterfav = False
    check = st.checkbox('Filter: Nur Favoriten') 
    if check:
        #st.write("Die Option ist aktiviert.")
        filterfav = True  
        
        

    if st.button("Signale berechnen"):
        buy_signals, sell_signals = calculate_ma_signals(_conn, days_back, crossover=crossover_fak2, filterma=filter_MA, filtervola=filtervola, filterfav=filterfav)
        # Die ermittelten Signale in den Session-State speichern
        st.session_state['buy_signals'] = buy_signals
        st.session_state['sell_signals'] = sell_signals

    # Zeige Kauf-/Verkaufssignale aus dem Session-State an
    st.subheader("Kaufsignale")
    for signal in st.session_state['buy_signals']:
        symbol, date, action = signal
        # Klickelement, das die Aktie auswählt und die Seite nach oben scrollt
        if st.button(f"{symbol}: Kaufsignal am {date}", key=f"buy_{symbol}_{date}"):
            #st.session_state['selected_stock'] = symbol  # Setze die neue Aktie als ausgewählt
            #scroll_to_top()  # Scrolle nach oben
            plot_stock_data(symbol, _conn, forecast_years, crossover=crossover_fak2)
            with st.spinner('Lade Daten...'):
                data, success = get_stock_info_data_db(_conn, symbol)
                if success and data:
                    stock_info_show(symbol,data)
    st.text( f"{len(st.session_state['buy_signals'])} Kaufsignale")

    #st.experimental_rerun()  # Erneutes Rendering der Seite sicherstellen

    st.subheader("Verkaufssignale")
    for signal in st.session_state['sell_signals']:
        symbol, date, action = signal
        # Klickelement, das die Aktie auswählt und die Seite nach oben scrollt
        if st.button(f"{symbol}: Verkaufssignal am {date}", key=f"sell_{symbol}_{date}"):
            #st.session_state['selected_stock'] = symbol  # Setze die neue Aktie als ausgewählt
            #scroll_to_top()  # Scrolle nach oben
            plot_stock_data(symbol, _conn, forecast_years, crossover=crossover_fak2)
            with st.spinner('Lade Daten...'):
                data, success = get_stock_info_data_db(_conn, symbol)
                if success and data:
                    stock_info_show(symbol,data)
    st.text( f"{len(st.session_state['sell_signals'])} Veraufsignale")

    # Screener
    show_screener(_conn, forecast_years=forecast_years, crossover_fak=crossover_fak1)

    # Verbindung zur Datenbank schließen
    _conn.close()


if __name__ == "__main__":
    main()

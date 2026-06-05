import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from  stock_db_ops import *

def stock_info_show(ticker_symbol, data):
    # Zeige die wichtigsten Kennzahlen in Karten an
    # Erstellen Sie zwei Spalten
    st.markdown(f"<h2 class='section-header'>{data['Allgemeine Informationen']['Name']} ({ticker_symbol})</h2>", unsafe_allow_html=True)

    # Top Metrics in Spalten
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(
            f"""
            <div class='metric-card'>
                <h4>Aktueller Preis</h4>
                <h2>{data['Aktuelle Marktdaten']['Aktueller Preis']}</h2>
            </div>
            """, 
            unsafe_allow_html=True
        )
    
    with col2:
        st.markdown(
            f"""
            <div class='metric-card'>
                <h4>Market Cap</h4>
                <h2>{data['Fundamentaldaten']['Market Cap']}</h2>
            </div>
            """, 
            unsafe_allow_html=True
        )
    
    with col3:
        st.markdown(
            f"""
            <div class='metric-card'>
                <h4>KGV (P/E)</h4>
                <h2>{data['Wichtige Kennzahlen']['KGV (P/E)']}</h2>
            </div>
            """, 
            unsafe_allow_html=True
        )
    
    with col4:
        st.markdown(
            f"""
            <div class='metric-card'>
                <h4>Dividendenrendite / 5J</h4>
                <h2>{data['Wichtige Kennzahlen']['Dividendenrendite']} / {data['Wichtige Kennzahlen']['Dividendenrendite-5J']} </h2>
            </div>
            """, 
            unsafe_allow_html=True
        )
# Detaillierte Daten in einem Expander
    with st.expander("Detaillierte Informationen", expanded=True):
        # Liste für die Sammlung der Sections
        sections_data = []
        
        # Sammle erst alle Sections
        for section, section_data in data.items():
            df = pd.DataFrame.from_dict(section_data, orient='index', columns=['Wert'])
            df.reset_index(inplace=True)
            df.columns = ['Kennzahl', 'Wert']
            sections_data.append((section, df))
        
        # Verarbeite die Sections in Gruppen von 2 oder 3
        anz_spalten = 3
        for i in range(0, len(sections_data), anz_spalten):  
            # Erstelle Spalten für diese Gruppe
            cols = st.columns(anz_spalten)  
            
            # Fülle die Spalten mit den verfügbaren Sections
            for j in range(anz_spalten): 
                if i + j < len(sections_data):
                    section, df = sections_data[i + j]
                    with cols[j]:
                        st.markdown(f"<h3 class='section-header'>{section}</h3>", unsafe_allow_html=True)
                        st.dataframe(
                            df,
                            width=400,
                            hide_index=True,
                            column_config={
                                "Kennzahl": st.column_config.TextColumn("Kennzahl", width="200"),
                                "Wert": st.column_config.TextColumn("Wert", width="200")
                            },
                            use_container_width=True
                        )
    pass 

# Modified plot_stock_data function with enhanced title
# @st.cache_data  # deaktiviert: führte zu identischer Anzeige für verschiedene Aktien
def plot_stock_data(symbol, _conn, forecast_years=3, crossover=1):
    window_s = 9 * crossover
    window_l = 21 * crossover
    #query = f"SELECT date, adj_close FROM stock_data WHERE symbol = '{symbol}' ORDER BY date"
    query = "SELECT * FROM stock_data WHERE symbol = ? ORDER BY date"
    df = pd.read_sql(query, _conn, params=(symbol,))
    df['date'] = pd.to_datetime(df['date'])
    
    # Get company info
    company_info = get_company_info(symbol)
    #print(company_info)
    #st.text(company_info.get('getinfo'))
    if company_info.get('getinfo') == False:
        st.text('Keine (neue) Info gefunden!')
        #return()

    # Create title with company info
    if company_info:
        title = (f"{symbol} - {company_info['company_name']} | \n"
                f"Sector: {company_info['sector']} | Industry: {company_info['industry']} | \n"
                f"Dividend Yield/5Y: {company_info['dividend_yield']:.2f}% /  {company_info['fiveyearavgdividendyield']:.2f}%          ")
    else:
        title = f"{symbol} Stock Price, Moving Averages, and Forecast"
    
    # Calculate moving averages and other indicators
    df['MA_short'] = df['adj_close'].rolling(window=window_s).mean()
    df['MA_long'] = df['adj_close'].rolling(window=window_l).mean()

    
    # Calculate buy/sell signals...     df.loc[zeile:, spalte]
    df['Signal'] = 0
    df.loc[window_l:, 'Signal'] = (df['MA_short'][window_l:] > df['MA_long'][window_l:]).astype(int)
    df['Position'] = df['Signal'].diff()
    
    # Add buy/sell signals
    buy_signals = df[df['Position'] == 1]
    sell_signals = df[df['Position'] == -1]
    
    
    # Forecast with Prophet
    forecast = forecast_with_prophet(df, forecast_years)

    specific_date = '2024-10-28'
    # Wenn das Datum nicht der Index ist, sondern eine normale Spalte:
    #filtered_row = forecast.loc[forecast['ds'] == specific_date, 'yhat' ]
    #st.text(filtered_row*1000)

    
    # Momentum
    df['momentum'] = df['adj_close'].pct_change(periods=20)

    # Distanz zum Moving Average
    df['ma_distance'] = (df['adj_close'] - df['MA_long']) / df['MA_long']
    
    # Create figure
    fig = go.Figure()
    
    # Add traces
    #fig.add_trace(go.Scatter(x=df['date'], y=df['adj_close'], mode='lines', name='Stock Price'))
    fig.add_trace(go.Scatter(x=df['date'], y=df['MA_short'], mode='lines', name='MA-'+str(window_s), line=dict(color='red') ))
    fig.add_trace(go.Scatter(x=df['date'], y=df['MA_long'], mode='lines', name='MA-'+str(window_l), line=dict(color='green') ))

    #fig.add_trace(go.Scatter(x=df['date'], y=df['momentum'], mode='lines', name='Momentum'))
    #fig.add_trace(go.Scatter(x=df['date'], y=df['ma_distance'], mode='lines', name='ma_distance'))

    fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Stock Price') ) 

    # Add forecast traces
    fig.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat'], mode='lines', name='Forecast', line=dict(dash='dot')))
    fig.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat_lower'], mode='lines', name='Lower Bound', line=dict(width=0)))
    fig.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat_upper'], mode='lines', name='Upper Bound', line=dict(width=0), fillcolor='rgba(0,100,80,0.2)', fill='tonexty'))
    

    
    fig.add_trace(go.Scatter(
        x=buy_signals['date'],
        y=buy_signals['adj_close'],
        mode='markers',
        marker=dict(symbol='triangle-up', size=15, color='green'),
        name='Buy Signal'
    ))
    
    fig.add_trace(go.Scatter(
        x=sell_signals['date'],
        y=sell_signals['adj_close'],
        mode='markers',
        marker=dict(symbol='triangle-down', size=15, color='red'),
        name='Sell Signal'
    ))
    
    # Update layout with new title
    fig.update_layout(
        title=title,
        xaxis_title='Date',
        yaxis_title='Price',
        width=1000,
        height=600,
        xaxis=dict(
            rangeselector=dict(
                buttons=list([
                    dict(count=3, label="3m", step="month", stepmode="backward"),
                    dict(count=1, label="1y", step="year", stepmode="backward"),
                    dict(count=2, label="2y", step="year", stepmode="backward"),
                    dict(count=5, label="5y", step="year", stepmode="backward"),
                    dict(step="all")
                ])
            ),
            rangeslider=dict(visible=True),
            type="date"
        ),
        yaxis=dict(
            rangemode='normal',
            fixedrange=False
        )
    )
    st.plotly_chart(fig)
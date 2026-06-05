import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from stock_show import plot_stock_data, stock_info_show
from stock_db_ops import get_stock_info_data_db


@st.cache_data
def get_fundamental_data(_conn):
    query = """
    SELECT symbol, company_name, sector, industry,
           currentprice, marketcap, trailingpe, forwardpe,
           dividend_yield, fiveyearavgdividendyield, payoutratio,
           beta, returnonequity, returnonassets, profitmargins,
           operatingmargins, shortratio, shortpercentoffloat,
           debttoequity, currentratio, quickratio,
           revenuegrowth, earningsgrowth,
           fiftytwoweeklow, fiftytwoweekhigh,
           recommendationmean, recommendationkey,
           pegratio, pricetobook, enterprisetoebitda
    FROM company_info
    WHERE company_name IS NOT NULL AND company_name != 'N/A'
    """
    df = pd.read_sql(query, _conn)
    ratio_cols = ['trailingpe', 'forwardpe', 'dividend_yield', 'payoutratio',
                  'beta', 'returnonequity', 'returnonassets', 'profitmargins',
                  'operatingmargins', 'shortratio', 'shortpercentoffloat',
                  'debttoequity', 'pegratio', 'pricetobook', 'enterprisetoebitda',
                  'currentprice', 'marketcap', 'fiftytwoweeklow', 'fiftytwoweekhigh',
                  'recommendationmean']
    for col in ratio_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            df[col] = df[col].replace(0, np.nan)
    return df


@st.cache_data
def get_performance_data(_conn):
    cutoff = str(datetime.today().date() - timedelta(days=370))
    query = "SELECT symbol, date, adj_close FROM stock_data WHERE date >= ? ORDER BY symbol, date"
    df = pd.read_sql(query, _conn, params=(cutoff,))
    df['date'] = pd.to_datetime(df['date']).dt.date
    today_dt = datetime.today().date()
    results = []

    for symbol, sdf in df.groupby('symbol'):
        sdf = sdf.sort_values('date')
        current_price = sdf.iloc[-1]['adj_close']

        def get_price_n_days_ago(days):
            target = today_dt - timedelta(days=days)
            past = sdf[sdf['date'] <= target]
            return past.iloc[-1]['adj_close'] if not past.empty else None

        p1m  = get_price_n_days_ago(30)
        p3m  = get_price_n_days_ago(90)
        p6m  = get_price_n_days_ago(180)
        p12m = get_price_n_days_ago(365)

        def calc_perf(past_price):
            if not past_price or past_price <= 0:
                return None
            val = (current_price / past_price - 1) * 100
            return round(val, 1) if -99 <= val <= 500 else None

        results.append({
            'symbol': symbol,
            'Kurs':   round(current_price, 2),
            '1M %':   calc_perf(p1m),
            '3M %':   calc_perf(p3m),
            '6M %':   calc_perf(p6m),
            '12M %':  calc_perf(p12m),
        })

    return pd.DataFrame(results) if results else pd.DataFrame()


@st.cache_data
def get_technical_data(_conn):
    cutoff = str(datetime.today().date() - timedelta(days=320))
    query = "SELECT symbol, date, adj_close FROM stock_data WHERE date >= ? ORDER BY symbol, date"
    df = pd.read_sql(query, _conn, params=(cutoff,))
    results = []

    for symbol, sdf in df.groupby('symbol'):
        sdf = sdf.sort_values('date').copy()
        if len(sdf) < 50:
            continue
        sdf['MA50']  = sdf['adj_close'].rolling(50).mean()
        sdf['MA200'] = sdf['adj_close'].rolling(200).mean()
        last    = sdf.iloc[-1]
        current = last['adj_close']
        ma50    = last['MA50']  if pd.notna(last['MA50'])  else np.nan
        ma200   = last['MA200'] if pd.notna(last['MA200']) else np.nan

        results.append({
            'symbol':        symbol,
            'Kurs':          round(current, 2),
            'MA50':          round(ma50,  2) if not np.isnan(ma50)  else np.nan,
            'MA200':         round(ma200, 2) if not np.isnan(ma200) else np.nan,
            '> MA50':        bool(current > ma50)  if not np.isnan(ma50)  else np.nan,
            '> MA200':       bool(current > ma200) if not np.isnan(ma200) else np.nan,
            'Abst. MA50 %':  round((current / ma50  - 1) * 100, 1) if not np.isnan(ma50)  else np.nan,
            'Abst. MA200 %': round((current / ma200 - 1) * 100, 1) if not np.isnan(ma200) else np.nan,
        })

    return pd.DataFrame(results) if results else pd.DataFrame()


# ---------------------------------------------------------------------------
# Hilfsfunktion: Chart + Info anzeigen
# ---------------------------------------------------------------------------

def _show_stock_detail(_conn, symbol, forecast_years, crossover_fak):
    st.divider()
    st.subheader(f"Chart: {symbol}")
    col1, col2 = st.columns([1, 3])
    with col1:
        local_fak = st.slider("Crossover-Faktor (9/21)", 1, 10, crossover_fak,
                              key=f"scr_cf_{symbol}")
        st.text(f"{local_fak*9} / {local_fak*21}")
    plot_stock_data(symbol, _conn, forecast_years, crossover=local_fak)
    with st.spinner('Lade Daten...'):
        data, success = get_stock_info_data_db(_conn, symbol)
        if success and data:
            stock_info_show(symbol, data)


# ---------------------------------------------------------------------------
# TAB 1 – Fundamentalscreener
# ---------------------------------------------------------------------------

def show_fundamental_screener(_conn, forecast_years=3, crossover_fak=1):
    st.subheader("Fundamentalscreener")
    df = get_fundamental_data(_conn)
    if df.empty:
        st.warning("Keine Fundamentaldaten verfügbar.")
        return

    sectors = ['Alle'] + sorted(df['sector'].dropna().unique().tolist())

    col1, col2, col3 = st.columns(3)
    with col1:
        selected_sector = st.selectbox("Sektor", sectors, key='fs_sector')
        kgv_max   = st.number_input("KGV max (0 = kein Filter)",       value=0,   min_value=0,   step=5,   key='fs_kgv')
        div_min   = st.number_input("Dividende min %",                  value=0.0, step=0.5,               key='fs_div')
    with col2:
        beta_min, beta_max = st.slider("Beta-Range", 0.0, 3.0, (0.0, 3.0), step=0.1, key='fs_beta')
        roe_min   = st.number_input("ROE min %",                        value=0,   step=5,                 key='fs_roe')
        marge_min = st.number_input("Gewinnmarge min %",                value=0,   step=5,                 key='fs_marge')
    with col3:
        mcap_min  = st.number_input("Market Cap min (Mrd.)",            value=0,   step=1,                 key='fs_mcap')
        short_max = st.number_input("Short Ratio max (0 = kein Filter)",value=0.0, step=1.0,               key='fs_short')
        only_buy  = st.checkbox("Nur Analyst-Empfehlung ≤ 2.5 (Buy)",                                      key='fs_buy')

    result = df.copy()
    if selected_sector != 'Alle':
        result = result[result['sector'] == selected_sector]
    if kgv_max > 0:
        result = result[result['trailingpe'].notna() & (result['trailingpe'] > 0) & (result['trailingpe'] <= kgv_max)]
    if div_min > 0:
        result = result[result['dividend_yield'].notna() & (result['dividend_yield'] >= div_min)]
    result = result[result['beta'].isna() | ((result['beta'] >= beta_min) & (result['beta'] <= beta_max))]
    if roe_min > 0:
        result = result[result['returnonequity'].notna() & (result['returnonequity'] * 100 >= roe_min)]
    if marge_min > 0:
        result = result[result['profitmargins'].notna() & (result['profitmargins'] * 100 >= marge_min)]
    if mcap_min > 0:
        result = result[result['marketcap'].notna() & (result['marketcap'] >= mcap_min * 1e9)]
    if short_max > 0:
        result = result[result['shortratio'].isna() | (result['shortratio'] <= short_max)]
    if only_buy:
        result = result[result['recommendationmean'].notna() & (result['recommendationmean'] <= 2.5)]

    out = pd.DataFrame()
    out['Symbol']      = result['symbol'].values
    out['Name']        = result['company_name'].values
    out['Sektor']      = result['sector'].values
    out['Kurs']        = result['currentprice'].round(2).values
    out['Market Cap']  = result['marketcap'].apply(
        lambda x: f"{x/1e9:.1f}B" if pd.notna(x) and x >= 1e9 else (f"{x/1e6:.0f}M" if pd.notna(x) and x > 0 else '-')).values
    out['KGV']         = result['trailingpe'].apply(lambda x: f"{x:.1f}" if pd.notna(x) and x > 0 else '-').values
    out['Div %']       = result['dividend_yield'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) and x > 0 else '-').values
    out['Beta']        = result['beta'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else '-').values
    out['ROE %']       = result['returnonequity'].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else '-').values
    out['Marge %']     = result['profitmargins'].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else '-').values
    out['Short Ratio'] = result['shortratio'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else '-').values
    out['Empfehlung']  = result['recommendationkey'].values

    st.write(f"**{len(out)} Aktien gefunden** – Zeile anklicken für Chart")
    sel = st.dataframe(out, use_container_width=True, hide_index=True,
                       on_select="rerun", selection_mode="single-row")
    rows = sel.selection.rows if sel and sel.selection else []
    if rows:
        symbol = out.iloc[rows[0]]['Symbol']
        _show_stock_detail(_conn, symbol, forecast_years, crossover_fak)


# ---------------------------------------------------------------------------
# TAB 2 – Technischer Screener
# ---------------------------------------------------------------------------

def show_technical_screener(_conn, forecast_years=3, crossover_fak=1):
    st.subheader("Technischer Screener")

    col1, col2 = st.columns(2)
    with col1:
        above_ma50       = st.checkbox("Kurs > MA50",                    key='ts_a50')
        above_ma200      = st.checkbox("Kurs > MA200",                   key='ts_a200')
        below_ma50       = st.checkbox("Kurs < MA50 (Reversal-Kandidat)",key='ts_b50')
        ma50_above_ma200 = st.checkbox("MA50 > MA200 (Golden-Cross-Zone)",key='ts_gc')
    with col2:
        d50_min,  d50_max  = st.slider("Abstand MA50 %",  -60, 100, (-60, 100), key='ts_d50')
        d200_min, d200_max = st.slider("Abstand MA200 %", -60, 100, (-60, 100), key='ts_d200')
        pos52w_min = st.slider("52-Wochen-Position min % (0 = kein Filter)", 0, 100, 0, key='ts_52w')

    df_tech = get_technical_data(_conn)
    if df_tech.empty:
        st.warning("Keine Kursdaten verfügbar.")
        return

    fund = get_fundamental_data(_conn)[['symbol', 'company_name', 'sector',
                                         'fiftytwoweeklow', 'fiftytwoweekhigh']]
    result = df_tech.merge(fund, on='symbol', how='left')

    if above_ma50:
        result = result[result['> MA50'] == True]
    if above_ma200:
        result = result[result['> MA200'] == True]
    if below_ma50:
        result = result[result['> MA50'] == False]
    if ma50_above_ma200:
        result = result[result['MA50'].notna() & result['MA200'].notna() & (result['MA50'] > result['MA200'])]

    if (d50_min, d50_max) != (-60, 100):
        result = result[result['Abst. MA50 %'].isna() | result['Abst. MA50 %'].between(d50_min, d50_max)]
    if (d200_min, d200_max) != (-60, 100):
        result = result[result['Abst. MA200 %'].isna() | result['Abst. MA200 %'].between(d200_min, d200_max)]

    # 52-Wochen-Position berechnen
    denom = result['fiftytwoweekhigh'] - result['fiftytwoweeklow']
    mask = denom > 0
    result.loc[mask, '52W-Pos %'] = (
        (result.loc[mask, 'Kurs'] - result.loc[mask, 'fiftytwoweeklow']) / denom[mask] * 100
    ).round(1)

    if pos52w_min > 0:
        result = result[result['52W-Pos %'].notna() & (result['52W-Pos %'] >= pos52w_min)]

    show_cols = ['symbol', 'company_name', 'sector', 'Kurs', 'MA50', 'MA200',
                 '> MA50', '> MA200', 'Abst. MA50 %', 'Abst. MA200 %', '52W-Pos %']
    result = result[[c for c in show_cols if c in result.columns]].reset_index(drop=True)

    st.write(f"**{len(result)} Aktien gefunden** – Zeile anklicken für Chart")
    fmt = {'Kurs': '{:.2f}', 'MA50': '{:.2f}', 'MA200': '{:.2f}',
           'Abst. MA50 %': '{:.1f}%', 'Abst. MA200 %': '{:.1f}%', '52W-Pos %': '{:.1f}%'}
    sel = st.dataframe(result.style.format(fmt, na_rep='-'), use_container_width=True, hide_index=True,
                       on_select="rerun", selection_mode="single-row")
    rows = sel.selection.rows if sel and sel.selection else []
    if rows:
        symbol = result.iloc[rows[0]]['symbol']
        _show_stock_detail(_conn, symbol, forecast_years, crossover_fak)


# ---------------------------------------------------------------------------
# TAB 3 – Performance-Ranking
# ---------------------------------------------------------------------------

def show_performance_ranking(_conn, forecast_years=3, crossover_fak=1):
    st.subheader("Performance-Ranking")

    col1, col2, col3 = st.columns(3)
    with col1:
        sort_by      = st.selectbox("Sortieren nach", ['12M %', '6M %', '3M %', '1M %'], key='pr_sort')
    with col2:
        top_n        = st.slider("Anzahl anzeigen", 10, 200, 25, key='pr_topn')
    with col3:
        only_positive = st.checkbox("Nur positive Performance", key='pr_pos')
        filter_sector = st.checkbox("Sektor-Filter", key='pr_secflt')

    df_perf = get_performance_data(_conn)
    if df_perf.empty:
        st.warning("Keine Kursdaten verfügbar.")
        return

    fund = get_fundamental_data(_conn)[['symbol', 'company_name', 'sector']]
    df_perf = df_perf.merge(fund, on='symbol', how='left')

    if filter_sector:
        sectors = sorted(df_perf['sector'].dropna().unique().tolist())
        sel_sec = st.multiselect("Sektoren", sectors, key='pr_secs')
        if sel_sec:
            df_perf = df_perf[df_perf['sector'].isin(sel_sec)]

    result = df_perf.dropna(subset=[sort_by]).sort_values(sort_by, ascending=False)
    if only_positive:
        result = result[result[sort_by] > 0]

    perf_cols = [c for c in ['1M %', '3M %', '6M %', '12M %'] if c in result.columns]
    col_order = ['symbol', 'company_name', 'sector', 'Kurs'] + perf_cols
    result = result[[c for c in col_order if c in result.columns]].head(top_n).reset_index(drop=True)

    st.write(f"**Top {len(result)} nach {sort_by}** – Zeile anklicken für Chart")
    fmt = {'Kurs': '{:.2f}', **{col: '{:.1f}%' for col in perf_cols}}
    sel = st.dataframe(
        result.style.format(fmt).background_gradient(subset=perf_cols, cmap='RdYlGn', vmin=-20, vmax=20),
        use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row"
    )
    rows = sel.selection.rows if sel and sel.selection else []
    if rows:
        symbol = result.iloc[rows[0]]['symbol']
        _show_stock_detail(_conn, symbol, forecast_years, crossover_fak)

    # Sektor-Heatmap
    if 'sector' in df_perf.columns and not df_perf.empty:
        with st.expander("Sektor-Durchschnitt"):
            sector_perf = (df_perf.groupby('sector')[perf_cols].mean().round(1)
                           .sort_values(sort_by, ascending=False))
            st.dataframe(
                sector_perf.style.background_gradient(cmap='RdYlGn', vmin=-20, vmax=20),
                use_container_width=True
            )


# ---------------------------------------------------------------------------
# TAB 4 – Scoring-Modell
# ---------------------------------------------------------------------------

def show_scoring_screener(_conn, forecast_years=3, crossover_fak=1):
    st.subheader("Scoring-Modell")
    st.caption("Gewichtetes Perzentil-Ranking aller Aktien in der Datenbank. Score 0–100.")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        w_momentum = st.slider("Momentum (3M)", 0, 10, 3, key='sc_mom')
    with col2:
        w_dividend = st.slider("Dividende",     0, 10, 2, key='sc_div')
    with col3:
        w_value    = st.slider("Value (KGV↓)",  0, 10, 3, key='sc_val')
    with col4:
        w_quality  = st.slider("Qualität (ROE)",0, 10, 2, key='sc_qual')

    total_weight = w_momentum + w_dividend + w_value + w_quality
    if total_weight == 0:
        st.warning("Bitte mindestens ein Kriterium > 0 setzen.")
        return

    perf_df = get_performance_data(_conn)[['symbol', '3M %']]
    fund_df = get_fundamental_data(_conn)[['symbol', 'company_name', 'sector',
                                            'dividend_yield', 'trailingpe', 'returnonequity']]
    df = fund_df.merge(perf_df, on='symbol', how='left')

    def prank(series):
        return series.rank(pct=True, na_option='bottom') * 100

    s_mom  = prank(df['3M %'].fillna(df['3M %'].median()))           if w_momentum > 0 else 0
    s_div  = prank(df['dividend_yield'].fillna(0))                    if w_dividend > 0 else 0
    kgv    = df['trailingpe'].where(df['trailingpe'] > 0)
    s_val  = 100 - prank(kgv.fillna(kgv.median()))                   if w_value    > 0 else 0
    s_qual = prank(df['returnonequity'].fillna(df['returnonequity'].median())) if w_quality > 0 else 0

    df['Score'] = (
        s_mom  * w_momentum +
        s_div  * w_dividend +
        s_val  * w_value    +
        s_qual * w_quality
    ) / total_weight
    df['Score'] = df['Score'].round(1)
    df = df.sort_values('Score', ascending=False)

    df['KGV']   = df['trailingpe'].apply(     lambda x: f"{x:.1f}"     if pd.notna(x) and x > 0 else '-')
    df['Div %'] = df['dividend_yield'].apply( lambda x: f"{x:.2f}%"    if pd.notna(x) and x > 0 else '-')
    df['ROE %'] = df['returnonequity'].apply( lambda x: f"{x*100:.1f}%"if pd.notna(x) else '-')
    df['3M %']  = df['3M %'].apply(           lambda x: f"{x:.1f}%"    if pd.notna(x) else '-')

    top_n = st.slider("Anzahl anzeigen", 10, 200, 25, key='sc_topn')
    show  = df[['symbol', 'company_name', 'sector', 'Score', '3M %', 'KGV', 'Div %', 'ROE %']].head(top_n).reset_index(drop=True)

    st.write(f"**Top {top_n} nach Score** – Zeile anklicken für Chart")
    sel = st.dataframe(
        show.style.format({'Score': '{:.1f}'}).background_gradient(subset=['Score'], cmap='RdYlGn', vmin=0, vmax=100),
        use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row"
    )
    rows = sel.selection.rows if sel and sel.selection else []
    if rows:
        symbol = show.iloc[rows[0]]['symbol']
        _show_stock_detail(_conn, symbol, forecast_years, crossover_fak)


# ---------------------------------------------------------------------------
# TAB 5 – Kauf- / Short-Empfehlungen
# ---------------------------------------------------------------------------

def show_recommendations(_conn, forecast_years=3, crossover_fak=1):
    st.subheader("Kauf- & Short-Empfehlungen")
    st.caption(
        "Kombiniertes Signal aus Trend (MA50/200), Momentum (1M/3M) und Fundamentaldaten. "
        "Punkte 0–7 für Kauf, 0–6 für Short."
    )

    # --- Daten zusammenführen ---
    tech  = get_technical_data(_conn)
    perf  = get_performance_data(_conn)[['symbol', '1M %', '3M %']]
    fund  = get_fundamental_data(_conn)[['symbol', 'company_name', 'sector',
                                          'currentprice', 'trailingpe',
                                          'returnonequity', 'recommendationmean',
                                          'recommendationkey']]
    if tech.empty or fund.empty:
        st.warning("Nicht genug Daten für Empfehlungen.")
        return

    df = tech.merge(fund, on='symbol', how='inner').merge(perf, on='symbol', how='left')

    # --- Kauf-Score (0–7) ---
    buy = pd.Series(0, index=df.index)
    buy += (df['> MA50']  == True).astype(int)                          # +1 Kurs > MA50
    buy += (df['> MA200'] == True).astype(int)                          # +1 Kurs > MA200
    buy += ((df['MA50'].notna()) & (df['MA200'].notna()) &
            (df['MA50'] > df['MA200'])).astype(int)                     # +1 Golden-Cross-Zone
    buy += (df['Abst. MA50 %'].between(0, 15)).astype(int)             # +1 nicht überkauft
    buy += (df['1M %'].fillna(0) > 0).astype(int)                      # +1 Momentum 1M
    buy += (df['3M %'].fillna(0) > 0).astype(int)                      # +1 Momentum 3M
    buy += (df['recommendationmean'].notna() &
            (df['recommendationmean'] <= 2.5)).astype(int)              # +1 Analyst Buy
    df['Kauf-Score'] = buy

    # --- Short-Score (0–6) ---
    short = pd.Series(0, index=df.index)
    short += (df['> MA50']  == False).astype(int)                       # +1 Kurs < MA50
    short += (df['> MA200'] == False).astype(int)                       # +1 Kurs < MA200
    short += ((df['MA50'].notna()) & (df['MA200'].notna()) &
              (df['MA50'] < df['MA200'])).astype(int)                   # +1 Death-Cross-Zone
    short += (df['Abst. MA50 %'].between(-20, -5)).astype(int)        # +1 nicht überverkauft
    short += (df['1M %'].fillna(0) < 0).astype(int)                    # +1 Momentum 1M negativ
    short += (df['3M %'].fillna(0) < 0).astype(int)                    # +1 Momentum 3M negativ
    df['Short-Score'] = short

    # --- Filter-Einstellungen ---
    col1, col2 = st.columns(2)
    with col1:
        min_buy_score = st.slider("Kauf-Mindestscore",  0, 7, 5, key='rec_buy_min')
        top_n_buy     = st.slider("Kauf: Anzahl anzeigen", 5, 100, 20, key='rec_buy_n')
    with col2:
        min_short_score = st.slider("Short-Mindestscore", 0, 6, 4, key='rec_short_min')
        top_n_short     = st.slider("Short: Anzahl anzeigen", 5, 100, 20, key='rec_short_n')

    disp_cols = ['symbol', 'company_name', 'sector', 'Kurs',
                 '1M %', '3M %', 'Abst. MA50 %', 'Abst. MA200 %', 'recommendationkey']
    perf_fmt  = {c: '{:.1f}%' for c in ['1M %', '3M %', 'Abst. MA50 %', 'Abst. MA200 %']}

    # --- Kaufempfehlungen ---
    st.markdown("### Kaufempfehlungen")
    buy_df = (df[df['Kauf-Score'] >= min_buy_score]
              .sort_values('Kauf-Score', ascending=False)
              .head(top_n_buy)
              .reset_index(drop=True))
    buy_show = buy_df[['Kauf-Score'] + [c for c in disp_cols if c in buy_df.columns]]

    if buy_show.empty:
        st.info("Keine Aktien erreichen den gewählten Kauf-Mindestscore.")
    else:
        st.write(f"**{len(buy_show)} Kandidaten** – Zeile anklicken für Chart")
        fmt_cols = {c: v for c, v in perf_fmt.items() if c in buy_show.columns}
        sel_buy = st.dataframe(
            buy_show.style.format(fmt_cols, na_rep='-')
                          .background_gradient(subset=['Kauf-Score'], cmap='Greens', vmin=0, vmax=7),
            use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="single-row",
            key='rec_buy_df'
        )
        rows = sel_buy.selection.rows if sel_buy and sel_buy.selection else []
        if rows:
            symbol = buy_show.iloc[rows[0]]['symbol']
            _show_stock_detail(_conn, symbol, forecast_years, crossover_fak)

    # --- Short-Empfehlungen ---
    st.markdown("### Short-Empfehlungen")
    short_df = (df[df['Short-Score'] >= min_short_score]
                .sort_values('Short-Score', ascending=False)
                .head(top_n_short)
                .reset_index(drop=True))
    short_show = short_df[['Short-Score'] + [c for c in disp_cols if c in short_df.columns]]

    if short_show.empty:
        st.info("Keine Aktien erreichen den gewählten Short-Mindestscore.")
    else:
        st.write(f"**{len(short_show)} Kandidaten** – Zeile anklicken für Chart")
        fmt_cols = {c: v for c, v in perf_fmt.items() if c in short_show.columns}
        sel_short = st.dataframe(
            short_show.style.format(fmt_cols, na_rep='-')
                            .background_gradient(subset=['Short-Score'], cmap='Reds', vmin=0, vmax=6),
            use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="single-row",
            key='rec_short_df'
        )
        rows = sel_short.selection.rows if sel_short and sel_short.selection else []
        if rows:
            symbol = short_show.iloc[rows[0]]['symbol']
            _show_stock_detail(_conn, symbol, forecast_years, crossover_fak)


# ---------------------------------------------------------------------------
# Haupt-Einstiegspunkt
# ---------------------------------------------------------------------------

def show_screener(_conn, forecast_years=3, crossover_fak=1):
    st.header("Aktien-Screener")
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Fundamental", "Technisch", "Performance-Ranking", "Scoring-Modell", "Empfehlungen"
    ])
    with tab1:
        show_fundamental_screener(_conn, forecast_years, crossover_fak)
    with tab2:
        show_technical_screener(_conn, forecast_years, crossover_fak)
    with tab3:
        show_performance_ranking(_conn, forecast_years, crossover_fak)
    with tab4:
        show_scoring_screener(_conn, forecast_years, crossover_fak)
    with tab5:
        show_recommendations(_conn, forecast_years, crossover_fak)

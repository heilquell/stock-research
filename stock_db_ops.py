'''
numpy==1.26.4
pandas==2.2.2
prophet==1.1.5
streamlit==1.33.0
'''


import os
import sqlite3, json
from datetime import datetime, timedelta
import streamlit as st
import yfinance as yf
import pandas as pd
from time import time, sleep
from prophet import Prophet

import numpy as np
np.rec = np  # rudimentärer Workaround

DEFAULT_DB_PATH = os.environ.get("STOCKS_DB", "/data/stocks.db")

def init_db(db_name=None):
    if db_name is None:
        db_name = DEFAULT_DB_PATH
    _conn = sqlite3.connect(db_name, timeout=10)
    cursor = _conn.cursor()

    # tabelle "sentences" mit den spalten "id" und "sentence" erzeugen
    cursor.execute('''
        create table if not exists sentences (
            id integer primary key AUTOINCREMENT,
            sentence text
        )  ''')

    # Tabelle mit den Namen der Favoritenlisten erstellen
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS fav_names (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL
    )   ''')

    # Tabelle mit den Namen der Favoritenlisten erstellen
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS fav_list (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    ID_fav INTEGER,
    symbol TEXT NOT NULL,
    created_at DATETIME DEFAULT NULL
    )   ''')

    cursor.execute(""" 
    CREATE TRIGGER if not exists set_created_at_fav
    AFTER INSERT ON fav_list
    FOR EACH ROW
    BEGIN
        UPDATE fav_list
        SET created_at = CURRENT_TIMESTAMP
        WHERE ID = NEW.ID;
    END;    
    """)

    # Create stock_data table
    cursor.execute('''CREATE TABLE IF NOT EXISTS stock_list (
                        symbol TEXT,
                        PRIMARY KEY (symbol)
                    )''')
    
    # Create stock_data table
    cursor.execute('''CREATE TABLE IF NOT EXISTS stock_data (
                        symbol TEXT,
                        date DATE,
                        open REAL,
                        high REAL,
                        low REAL,
                        close REAL,
                        adj_close REAL,
                        volume INTEGER,
                        PRIMARY KEY (symbol, date)
                    )''')
    
    # Create company_info table  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    cursor.execute('''CREATE TABLE IF NOT EXISTS company_info (
                        created_at DATETIME DEFAULT NULL,
                        updated_at DATETIME  DEFAULT NULL,
                        symbol TEXT PRIMARY KEY,
                        company_name TEXT,
                        sector TEXT,
                        industry TEXT,
                        dividend_yield REAL,
                        fiveyearavgdividendyield REAL,
                        fulltimeemployees LONGINT,
                        overallrisk INT,
                        recommendationmean REAL,
                        recommendationkey TEXT,
                        last_updated DATE,
                        address1 TEXT, 
                        city TEXT, 
                        state TEXT, 
                        zip TEXT, 
                        country TEXT, 
                        phone TEXT, 
                        website TEXT, 
                        industrykey TEXT, 
                        industrydisp TEXT, 
                        sectorkey TEXT, 
                        sectordisp TEXT, 
                        longbusinesssummary TEXT, 
                        companyofficers TEXT, 
                        auditrisk REAL, 
                        boardrisk REAL, 
                        compensationrisk REAL, 
                        shareholderrightsrisk REAL, 
                        governanceepochdate TEXT, 
                        compensationasofepochdate TEXT, 
                        irwebsite TEXT, 
                        maxage TEXT, 
                        pricehint REAL, 
                        previousclose REAL, 
                        open REAL, 
                        daylow REAL, 
                        dayhigh REAL, 
                        regularmarketpreviousclose REAL, 
                        regularmarketopen REAL, 
                        regularmarketdaylow REAL, 
                        regularmarketdayhigh REAL, 
                        dividendrate REAL, 
                        exdividenddate REAL, 
                        payoutratio REAL, 
                        beta REAL, 
                        trailingpe REAL, 
                        forwardpe REAL, 
                        volume REAL, 
                        regularmarketvolume REAL, 
                        averagevolume REAL, 
                        averagevolume10days REAL, 
                        averagedailyvolume10day REAL, 
                        bid REAL, 
                        ask REAL, 
                        bidsize REAL, 
                        asksize REAL, 
                        marketcap REAL, 
                        fiftytwoweeklow REAL, 
                        fiftytwoweekhigh REAL, 
                        pricetosalestrailing12months REAL, 
                        fiftydayaverage REAL, 
                        twohundreddayaverage REAL, 
                        trailingannualdividendrate REAL, 
                        trailingannualdividendyield REAL, 
                        currency TEXT, 
                        enterprisevalue REAL, 
                        profitmargins REAL, 
                        floatshares REAL, 
                        sharesoutstanding REAL, 
                        sharesshort REAL, 
                        sharesshortpriormonth REAL, 
                        sharesshortpreviousmonthdate REAL, 
                        dateshortinterest REAL, 
                        sharespercentsharesout REAL, 
                        heldpercentinsiders REAL, 
                        heldpercentinstitutions REAL, 
                        shortratio REAL, 
                        shortpercentoffloat REAL, 
                        impliedsharesoutstanding REAL, 
                        bookvalue REAL, 
                        pricetobook REAL, 
                        lastfiscalyearend TEXT, 
                        nextfiscalyearend TEXT, 
                        mostrecentquarter TEXT, 
                        earningsquarterlygrowth REAL, 
                        netincometocommon REAL, 
                        trailingeps REAL, 
                        forwardeps REAL, 
                        pegratio REAL, 
                        lastsplitfactor REAL, 
                        lastsplitdate TEXT, 
                        enterprisetorevenue REAL, 
                        enterprisetoebitda REAL, 
                        _52weekchange REAL, 
                        sandp52weekchange REAL, 
                        lastdividendvalue REAL, 
                        lastdividenddate REAL, 
                        exchange REAL, 
                        quotetype REAL, 
                        underlyingsymbol TEXT, 
                        shortname TEXT, 
                        longname TEXT, 
                        firsttradedateepochutc TEXT, 
                        timezonefullname TEXT, 
                        timezoneshortname TEXT, 
                        uuid TEXT, 
                        messageboardid TEXT, 
                        gmtoffsetmilliseconds TEXT, 
                        currentprice REAL, 
                        targethighprice REAL, 
                        targetlowprice REAL, 
                        targetmeanprice REAL, 
                        targetmedianprice REAL, 
                        numberofanalystopinions REAL, 
                        totalcash REAL, 
                        totalcashpershare REAL, 
                        ebitda REAL, 
                        totaldebt REAL, 
                        quickratio REAL, 
                        currentratio REAL, 
                        totalrevenue REAL, 
                        debttoequity REAL, 
                        revenuepershare REAL, 
                        returnonassets REAL, 
                        returnonequity REAL, 
                        freecashflow REAL, 
                        operatingcashflow REAL, 
                        earningsgrowth REAL, 
                        revenuegrowth REAL, 
                        grossmargins REAL, 
                        ebitdamargins REAL, 
                        operatingmargins REAL, 
                        financialcurrency TEXT, 
                        trailingpegratio REAL
                    )''')

                
    cursor.execute("""
            CREATE TRIGGER if not exists set_created_at
            AFTER INSERT ON company_info
            FOR EACH ROW
            BEGIN
                UPDATE company_info
                SET created_at = CURRENT_TIMESTAMP
                WHERE symbol = NEW.symbol;
            END;
            """)                  

    cursor.execute( """ 
            CREATE TRIGGER if not exists set_updated_at
            AFTER UPDATE ON company_info
            FOR EACH ROW
            BEGIN
                UPDATE company_info
                SET updated_at = CURRENT_TIMESTAMP
                WHERE symbol = OLD.symbol;
            END;    
            """)

    _conn.commit()
    return _conn


# Funktion, um Unternehmensinformationen abzurufen
def get_company_info(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info  # Versucht, die Informationen abzurufen

        if not info or 'quoteType' not in info:  # Falls keine Daten zurückkommen
            raise ValueError("Keine Daten gefunden.")


        companyofficers = info.get('companyOfficers', {})
        json_str_companyofficers = json.dumps(companyofficers)  # Serialize the entire list to a JSON string

        response =  {
            'company_name': info.get('longName', 'N/A'),
            'sector': info.get('sector', 'N/A'),
            'industry': info.get('industry', 'N/A'),
            'fiveyearavgdividendyield': info.get('fiveYearAvgDividendYield', 0) ,#* 1 if info.get('fiveYearAvgDividendYield') else 0 ,
            'dividend_yield': info.get('dividendYield', 0) ,#if info.get('dividendYield') else 0,
            'fulltimeemployees': info.get('fullTimeEmployees', 0) ,#if info.get('fullTimeEmployees') else 0,
            'overallrisk': info.get('overallRisk', -1) ,#if info.get('overallRisk') else -1,
            'recommendationmean': info.get('recommendationMean', 0) ,#if info.get('recommendationMean') else -1,
            'recommendationkey': info.get('recommendationKey', '-'), # if info.get('recommendationKey') else '-',
            
            'address1': info.get('address1', 0), 
            'city': info.get('city', 0), 
            'state': info.get('state', 0), 
            'zip': info.get('zip', 0), 
            'country': info.get('country', 0), 
            'phone': info.get('phone', 0), 
            'website': info.get('website', 0), 
            'industrykey': info.get('industryKey', 0), 
            'industrydisp': info.get('industryDisp', 0), 
            'sectorkey': info.get('sectorKey', 0), 
            'sectordisp': info.get('sectorDisp', 0), 
            'longbusinesssummary': info.get('longBusinessSummary', 0), 
                'companyofficers': json_str_companyofficers, 
            'auditrisk': info.get('auditRisk', 0), 
            'boardrisk': info.get('boardRisk', 0), 
            'compensationrisk': info.get('compensationRisk', 0), 
            'shareholderrightsrisk': info.get('shareHolderRightsRisk', 0), 
            'governanceepochdate': info.get('governanceEpochDate', 0), 
            'compensationasofepochdate': info.get('compensationAsOfEpochDate', 0), 
            'irwebsite': info.get('irWebsite', 0), 
            'maxage': info.get('maxAge', 0), 
            'pricehint': info.get('priceHint', 0), 
            'previousclose': info.get('previousClose', 0), 
            'open': info.get('open', 0), 
            'daylow': info.get('dayLow', 0), 
            'dayhigh': info.get('dayHigh', 0), 
            'regularmarketpreviousclose': info.get('regularMarketPreviousClose', 0), 
            'regularmarketopen': info.get('regularMarketOpen', 0), 
            'regularmarketdaylow': info.get('regularMarketDayLow', 0), 
            'regularmarketdayhigh': info.get('regularMarketDayHigh', 0), 
            'dividendrate': info.get('dividendRate', 0), 
            'dividendyield': info.get('dividendYield', 0), 
            'exdividenddate': info.get('exDividendDate', 0), 
            'payoutratio': info.get('payoutRatio', 0), 
            'beta': info.get('beta', 0), 
            'trailingpe': info.get('trailingPE', 0), 
            'forwardpe': info.get('forwardPE', 0), 
            'volume': info.get('volume', 0), 
            'regularmarketvolume': info.get('regularMarketVolume', 0), 
            'averagevolume': info.get('averageVolume', 0), 
            'averagevolume10days': info.get('averageVolume10days', 0), 
            'averagedailyvolume10day': info.get('averageDailyVolume10Day', 0), 
            'bid': info.get('bid', 0), 
            'ask': info.get('ask', 0), 
            'bidsize': info.get('bidSize', 0), 
            'asksize': info.get('askSize', 0), 
            'marketcap': info.get('marketCap', 0), 
            'fiftytwoweeklow': info.get('fiftyTwoWeekLow', 0), 
            'fiftytwoweekhigh': info.get('fiftyTwoWeekHigh', 0), 
            'pricetosalestrailing12months': info.get('priceToSalesTrailing12Months', 0), 
            'fiftydayaverage': info.get('fiftyDayAverage', 0), 
            'twohundreddayaverage': info.get('twoHundredDayAverage', 0), 
            'trailingannualdividendrate': info.get('trailingAnnualDividendRate', 0), 
            'trailingannualdividendyield': info.get('trailingAnnualDividendYield', 0), 
            'currency': info.get('currency', 0), 
            'enterprisevalue': info.get('enterpriseValue', 0), 
            'profitmargins': info.get('profitMargins', 0), 
            'floatshares': info.get('floatShares', 0), 
            'sharesoutstanding': info.get('sharesOutstanding', 0), 
            'sharesshort': info.get('sharesShort', 0), 
            'sharesshortpriormonth': info.get('sharesShortPriorMonth', 0), 
            'sharesshortpreviousmonthdate': info.get('sharesShortPreviousMonthDate', 0), 
            'dateshortinterest': info.get('dateShortInterest', 0), 
            'sharespercentsharesout': info.get('sharesPercentSharesOut', 0), 
            'heldpercentinsiders': info.get('heldPercentInsiders', 0), 
            'heldpercentinstitutions': info.get('heldPercentInstitutions', 0), 
            'shortratio': info.get('shortRatio', 0), 
            'shortpercentoffloat': info.get('shortPercentOfFloat', 0), 
            'impliedsharesoutstanding': info.get('impliedSharesOutstanding', 0), 
            'bookvalue': info.get('bookValue', 0), 
            'pricetobook': info.get('priceToBook', 0), 
            'lastfiscalyearend': info.get('lastFiscalYearEnd', 0), 
            'nextfiscalyearend': info.get('nextFiscalYearEnd', 0), 
            'mostrecentquarter': info.get('mostRecentQuarter', 0), 
            'earningsquarterlygrowth': info.get('earningsQuarterlyGrowth', 0), 
            'netincometocommon': info.get('netIncomeToCommon', 0), 
            'trailingeps': info.get('trailingEps', 0), 
            'forwardeps': info.get('forwardEps', 0), 
            'pegratio': info.get('pegRatio', 0), 
            'lastsplitfactor': info.get('lastSplitFactor', 0), 
            'lastsplitdate': info.get('lastSplitDate', 0), 
            'enterprisetorevenue': info.get('enterpriseToRevenue', 0), 
            'enterprisetoebitda': info.get('enterpriseToEbitda', 0), 
            '_52weekchange': info.get('52WeekChange', 0), 
            'sandp52weekchange': info.get('SandP52WeekChange', 0), 
            'lastdividendvalue': info.get('lastDividendValue', 0), 
            'lastdividenddate': info.get('lastDividendDate', 0), 
            'exchange': info.get('exchange', 0), 
            'quotetype': info.get('quoteType', 0), 
            'symbol': info.get('symbol', 0), 
            'underlyingsymbol': info.get('underlyingSymbol', 0), 
            'shortname': info.get('shortName', 0), 
            'longname': info.get('longName', 0), 
            'firsttradedateepochutc': info.get('firstTradeDateEpochUtc', 0), 
            'timezonefullname': info.get('timeZoneFullName', 0), 
            'timezoneshortname': info.get('timeZoneShortName', 0), 
            'uuid': info.get('uuid', 0), 
            'messageboardid': info.get('messageBoardId', 0), 
            'gmtoffsetmilliseconds': info.get('gmtOffSetMilliseconds', 0), 
            'currentprice': info.get('currentPrice', 0), 
            'targethighprice': info.get('targetHighPrice', 0), 
            'targetlowprice': info.get('targetLowPrice', 0), 
            'targetmeanprice': info.get('targetMeanPrice', 0), 
            'targetmedianprice': info.get('targetMedianPrice', 0), 
            'numberofanalystopinions': info.get('numberOfAnalystOpinions', 0), 
            'totalcash': info.get('totalCash', 0), 
            'totalcashpershare': info.get('totalCashPerShare', 0), 
            'ebitda': info.get('ebitda', 0), 
            'totaldebt': info.get('totalDebt', 0), 
            'quickratio': info.get('quickRatio', 0), 
            'currentratio': info.get('currentRatio', 0), 
            'totalrevenue': info.get('totalRevenue', 0), 
            'debttoequity': info.get('debtToEquity', 0), 
            'revenuepershare': info.get('revenuePerShare', 0), 
            'returnonassets': info.get('returnOnAssets', 0), 
            'returnonequity': info.get('returnOnEquity', 0), 
            'freecashflow': info.get('freeCashflow', 0), 
            'operatingcashflow': info.get('operatingCashflow', 0), 
            'earningsgrowth': info.get('earningsGrowth', 0), 
            'revenuegrowth': info.get('revenueGrowth', 0), 
            'grossmargins': info.get('grossMargins', 0), 
            'ebitdamargins': info.get('ebitdaMargins', 0), 
            'operatingmargins': info.get('operatingMargins', 0), 
            'financialcurrency': info.get('financialCurrency', 0), 
            'trailingpegratio': info.get('trailingPegRatio', 0),
            'getinfo': True
        } 
        return response
    
    except Exception as e:
        print("Fehler beim Abrufen der Unternehmensdaten:", e)
        response = {
            'company_name': 'N/A',
            'sector': 'N/A',
            'industry': 'N/A',
            'fiveyearavgdividendyield': 0,
            'dividend_yield': 0,
            'fulltimeemployees': 0,
            'overallrisk': 0, 
            'recommendationmean':  -1,
            'recommendationkey': '-',

            'address1': 0, 
            'city': 0, 
            'state': 0, 
            'zip': 0, 
            'country': 0, 
            'phone': 0, 
            'website': 0, 
            'industrykey': 0, 
            'industrydisp': 0, 
            'sectorkey': 0, 
            'sectordisp': 0, 
            'longbusinesssummary': 0, 
            'companyofficers': '', 
            'auditrisk': 0, 
            'boardrisk': 0, 
            'compensationrisk': 0, 
            'shareholderrightsrisk': 0, 
            'governanceepochdate': 0, 
            'compensationasofepochdate': 0, 
            'irwebsite': 0, 
            'maxage': 0, 
            'pricehint': 0, 
            'previousclose': 0, 
            'open': 0, 
            'daylow': 0, 
            'dayhigh': 0, 
            'regularmarketpreviousclose': 0, 
            'regularmarketopen': 0, 
            'regularmarketdaylow': 0, 
            'regularmarketdayhigh': 0, 
            'dividendrate': 0, 
            'exdividenddate': 0, 
            'payoutratio': 0, 
            'beta': 0, 
            'trailingpe': 0, 
            'forwardpe': 0, 
            'volume': 0, 
            'regularmarketvolume': 0, 
            'averagevolume': 0, 
            'averagevolume10days': 0, 
            'averagedailyvolume10day': 0, 
            'bid': 0, 
            'ask': 0, 
            'bidsize': 0, 
            'asksize': 0, 
            'marketcap': 0, 
            'fiftytwoweeklow': 0, 
            'fiftytwoweekhigh': 0, 
            'pricetosalestrailing12months': 0, 
            'fiftydayaverage': 0, 
            'twohundreddayaverage': 0, 
            'trailingannualdividendrate': 0, 
            'trailingannualdividendyield': 0, 
            'currency': 0, 
            'enterprisevalue': 0, 
            'profitmargins': 0, 
            'floatshares': 0, 
            'sharesoutstanding': 0, 
            'sharesshort': 0, 
            'sharesshortpriormonth': 0, 
            'sharesshortpreviousmonthdate': 0, 
            'dateshortinterest': 0, 
            'sharespercentsharesout': 0, 
            'heldpercentinsiders': 0, 
            'heldpercentinstitutions': 0, 
            'shortratio': 0, 
            'shortpercentoffloat': 0, 
            'impliedsharesoutstanding': 0, 
            'bookvalue': 0, 
            'pricetobook': 0, 
            'lastfiscalyearend': 0, 
            'nextfiscalyearend': 0, 
            'mostrecentquarter': 0, 
            'earningsquarterlygrowth': 0, 
            'netincometocommon': 0, 
            'trailingeps': 0, 
            'forwardeps': 0, 
            'pegratio': 0, 
            'lastsplitfactor': 0, 
            'lastsplitdate': 0, 
            'enterprisetorevenue': 0, 
            'enterprisetoebitda': 0, 
            '_52weekchange': 0, 
            'sandp52weekchange': 0, 
            'lastdividendvalue': 0, 
            'lastdividenddate': 0, 
            'exchange': 0, 
            'quotetype': 0, 
            'symbol': 0, 
            'underlyingsymbol': 0, 
            'shortname': 0, 
            'longname': 0, 
            'firsttradedateepochutc': 0, 
            'timezonefullname': 0, 
            'timezoneshortname': 0, 
            'uuid': 0, 
            'messageboardid': 0, 
            'gmtoffsetmilliseconds': 0, 
            'currentprice': 0, 
            'targethighprice': 0, 
            'targetlowprice': 0, 
            'targetmeanprice': 0, 
            'targetmedianprice': 0, 
            'numberofanalystopinions': 0, 
            'totalcash': 0, 
            'totalcashpershare': 0, 
            'ebitda': 0, 
            'totaldebt': 0, 
            'quickratio': 0, 
            'currentratio': 0, 
            'totalrevenue': 0, 
            'debttoequity': 0, 
            'revenuepershare': 0, 
            'returnonassets': 0, 
            'returnonequity': 0, 
            'freecashflow': 0, 
            'operatingcashflow': 0, 
            'earningsgrowth': 0, 
            'revenuegrowth': 0, 
            'grossmargins': 0, 
            'ebitdamargins': 0, 
            'operatingmargins': 0, 
            'financialcurrency': 0, 
            'trailingpegratio': 0,
            'getinfo': False

        }
        return response

# Modified function to get company info from database
def get_company_info_db(_conn, symbol):
    cursor = _conn.cursor()
    cursor.execute("SELECT * FROM company_info WHERE symbol = ?", (symbol,))
    row = cursor.fetchone()

    column_names = [desc[0] for desc in cursor.description]
    result_dict = dict(zip(column_names, row))
    return(result_dict)    

# Funktion zum Aktualisieren der Unternehmensinformationen in der Datenbank
def update_company_info(_conn, symbol):
    ret = 'Fehler: '
    cursor = _conn.cursor()
    info = get_company_info(symbol)
    #st.text(info)
    print('info', info)
    # Insert the data into the table
    ret = f"Fehler beim Speichern !"
    info_updated = False
    if info['getinfo'] == True:
        info_updated = True
        st_symbol = str(symbol)
        cursor.execute('INSERT OR REPLACE INTO stock_list (symbol) VALUES (?)', (st_symbol,))
        cursor.execute('''INSERT OR REPLACE INTO company_info 
            (symbol, company_name, sector, industry, dividend_yield, fiveyearavgdividendyield, fulltimeemployees, overallrisk, 
            recommendationmean, recommendationkey, last_updated, address1, city, state, zip, country, phone, website, 
            industrykey, industrydisp, sectorkey, sectordisp, longbusinesssummary, companyofficers, auditrisk, boardrisk, 
            compensationrisk, shareholderrightsrisk, governanceepochdate, compensationasofepochdate, irwebsite, maxage, 
            pricehint, previousclose, open, daylow, dayhigh, regularmarketpreviousclose, regularmarketopen, regularmarketdaylow, 
            regularmarketdayhigh, dividendrate, exdividenddate, payoutratio, beta, trailingpe, forwardpe, volume, 
            regularmarketvolume, averagevolume, averagevolume10days, averagedailyvolume10day, bid, ask, bidsize, asksize, 
            marketcap, fiftytwoweeklow, fiftytwoweekhigh, pricetosalestrailing12months, fiftydayaverage, twohundreddayaverage, 
            trailingannualdividendrate, trailingannualdividendyield, currency, enterprisevalue, profitmargins, floatshares, 
            sharesoutstanding, sharesshort, sharesshortpriormonth, sharesshortpreviousmonthdate, dateshortinterest, 
            sharespercentsharesout, heldpercentinsiders, heldpercentinstitutions, shortratio, shortpercentoffloat, 
            impliedsharesoutstanding, bookvalue, pricetobook, lastfiscalyearend, nextfiscalyearend, mostrecentquarter, 
            earningsquarterlygrowth, netincometocommon, trailingeps, forwardeps, pegratio, lastsplitfactor, lastsplitdate, 
            enterprisetorevenue, enterprisetoebitda, _52weekchange, sandp52weekchange, lastdividendvalue, lastdividenddate, 
            exchange, quotetype, underlyingsymbol, shortname, longname, firsttradedateepochutc, timezonefullname, 
            timezoneshortname, uuid, messageboardid, gmtoffsetmilliseconds, currentprice, targethighprice, targetlowprice, 
            targetmeanprice, targetmedianprice, numberofanalystopinions, totalcash, totalcashpershare, ebitda, totaldebt, 
            quickratio, currentratio, totalrevenue, debttoequity, revenuepershare, returnonassets, returnonequity, freecashflow, 
            operatingcashflow, earningsgrowth, revenuegrowth, grossmargins, ebitdamargins, operatingmargins, financialcurrency, 
            trailingpegratio)
            VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,   ?, ?, ?, ?)''',
            (symbol, 
            info['company_name'], 
            info['sector'], 
            info['industry'], 
            info['dividend_yield'], 
            info['fiveyearavgdividendyield'], 
            info['fulltimeemployees'],
            info['overallrisk'],
            info['recommendationmean'],
            info['recommendationkey'],
            datetime.today().date(),
            info['address1'],
            info['city'],
            info['state'],
            info['zip'],
            info['country'],
            info['phone'],
            info['website'],
            info['industrykey'],
            info['industrydisp'],
            info['sectorkey'],
            info['sectordisp'],
            info['longbusinesssummary'],
            info['companyofficers'],
            info['auditrisk'],
            info['boardrisk'],
            info['compensationrisk'],
            info['shareholderrightsrisk'],
            info['governanceepochdate'],
            info['compensationasofepochdate'],
            info['irwebsite'],
            info['maxage'],
            info['pricehint'],
            info['previousclose'],
            info['open'],
            info['daylow'],
            info['dayhigh'],
            info['regularmarketpreviousclose'],
            info['regularmarketopen'],
            info['regularmarketdaylow'],
            info['regularmarketdayhigh'],
            info['dividendrate'],
            info['exdividenddate'],
            info['payoutratio'],
            info['beta'],
            info['trailingpe'],
            info['forwardpe'],
            info['volume'],
            info['regularmarketvolume'],
            info['averagevolume'],
            info['averagevolume10days'],
            info['averagedailyvolume10day'],
            info['bid'],
            info['ask'],
            info['bidsize'],
            info['asksize'],
            info['marketcap'],
            info['fiftytwoweeklow'],
            info['fiftytwoweekhigh'],
            info['pricetosalestrailing12months'],
            info['fiftydayaverage'],
            info['twohundreddayaverage'],
            info['trailingannualdividendrate'],
            info['trailingannualdividendyield'],
            info['currency'],
            info['enterprisevalue'],
            info['profitmargins'],
            info['floatshares'],
            info['sharesoutstanding'],
            info['sharesshort'],
            info['sharesshortpriormonth'],
            info['sharesshortpreviousmonthdate'],
            info['dateshortinterest'],
            info['sharespercentsharesout'],
            info['heldpercentinsiders'],
            info['heldpercentinstitutions'],
            info['shortratio'],
            info['shortpercentoffloat'],
            info['impliedsharesoutstanding'],
            info['bookvalue'],
            info['pricetobook'],
            info['lastfiscalyearend'],
            info['nextfiscalyearend'],
            info['mostrecentquarter'],
            info['earningsquarterlygrowth'],
            info['netincometocommon'],
            info['trailingeps'],
            info['forwardeps'],
            info['pegratio'],
            info['lastsplitfactor'],
            info['lastsplitdate'],
            info['enterprisetorevenue'],
            info['enterprisetoebitda'],
            info['_52weekchange'],
            info['sandp52weekchange'],
            info['lastdividendvalue'],
            info['lastdividenddate'],
            info['exchange'],
            info['quotetype'],
            info['underlyingsymbol'],
            info['shortname'],
            info['longname'],
            info['firsttradedateepochutc'],
            info['timezonefullname'],
            info['timezoneshortname'],
            info['uuid'],
            info['messageboardid'],
            info['gmtoffsetmilliseconds'],
            info['currentprice'],
            info['targethighprice'],
            info['targetlowprice'],
            info['targetmeanprice'],
            info['targetmedianprice'],
            info['numberofanalystopinions'],
            info['totalcash'],
            info['totalcashpershare'],
            info['ebitda'],
            info['totaldebt'],
            info['quickratio'],
            info['currentratio'],
            info['totalrevenue'],
            info['debttoequity'],
            info['revenuepershare'],
            info['returnonassets'],
            info['returnonequity'],
            info['freecashflow'],
            info['operatingcashflow'],
            info['earningsgrowth'],
            info['revenuegrowth'],
            info['grossmargins'],
            info['ebitdamargins'],
            info['operatingmargins'],
            info['financialcurrency'],
            info['trailingpegratio']
            ))
        if cursor.rowcount == 1:
            ret = "Datensatz erfolgreich gespeichert!"
        else:
            ret = f"Fehler beim Speichern des Datensatzes: {cursor.error}"
        _conn.commit()
    else: 
        ret = "kein aktueller Datensatz  gespeichert!"        
    return(ret)

def format_number(number, is_currency=False, is_percentage=False, currency = '$' ):
    """
    Formatiert Zahlen für die Anzeige
    """
    currency = '$' if currency == 'USD' else currency
    currency = '€' if currency == 'EUR' else currency
    if isinstance(number, (float, int)):
        if abs(number) >= 1e12:
            formatted = f"{currency} {number/1e12:.2f}T" if is_currency else f"{number/1e12:.2f}T"
        elif abs(number) >= 1e9:
            formatted = f"{currency} {number/1e9:.2f}B" if is_currency else f"{number/1e9:.2f}B"
        elif abs(number) >= 1e6:
            formatted = f"{currency} {number/1e6:.2f}M" if is_currency else f"{number/1e6:.2f}M"
        else:
            formatted = f"{currency} {number:,.2f}" if is_currency else f"{number:,.2f}"
        
        if is_percentage:
            formatted = f"{number:.2f}%"
        
        return formatted
    return str(number)    


def get_last_entry_date(_conn, symbol):
    cursor = _conn.cursor()
    cursor.execute('''SELECT MAX(date) FROM stock_data WHERE symbol = ?''', (symbol,))
    result = cursor.fetchone()[0]
    return result

def get_stock_data(symbol, start_date, end_date):
    stock = yf.Ticker(symbol)

    data = stock.history(start=start_date, end=end_date)
    if isinstance(data.index, pd.DatetimeIndex) and data.index.tz is not None:
        data.index = data.index.tz_localize(None)  # Removendo o fuso horário se existir

    #stock = yf.download(symbol, start=start_date, end=end_date)
    #stock.reset_index(inplace=True)
    return data


# funktion um eine liste von satzen in die datenbank zu speichern
def store_sentences(_conn, sentence):
    cursor = _conn.cursor()
    cursor.execute('insert into sentences (sentence) values (?)', (sentence,))
    _conn.commit()

# funktion um den letzten eintrag aus der datenbank zu holen
def get_last_sentence(_conn):
    cursor = _conn.cursor()
    cursor.execute('select sentence from sentences order by id desc limit 1')
    last_sentence = cursor.fetchone()
    return last_sentence[0] if last_sentence else None


def calculate_atr(df, period=14):
    """
    Berechnet den Average True Range (ATR) Indikator
    """
    df = df.copy()
    df['high_low'] = df['high'] - df['low']
    df['high_close'] = abs(df['high'] - df['adj_close'].shift())
    df['low_close'] = abs(df['low'] - df['adj_close'].shift())
    
    df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
    df['atr'] = df['tr'].rolling(window=period).mean()
    
    return df['atr']


# @st.cache_data  # deaktiviert: DataFrame-Hashing kollidierte zwischen Aktien
def forecast_with_prophet(df, periods):
    # Prepare data for Prophet
    prophet_df = df[['date', 'adj_close']].rename(columns={'date': 'ds', 'adj_close': 'y'})
    
    # Create and fit the model
    model = Prophet()
    model.fit(prophet_df)
    
    # Make future dataframe
    future = model.make_future_dataframe(periods=periods * 365)
    
    # Forecast
    forecast = model.predict(future)
    
    return forecast


def save_to_db(_conn, symbol, data):
    cursor = _conn.cursor()
    symbol = symbol.upper()  # Symbol in Großbuchstaben umwandeln
    for index, row in data.iterrows():
        #date = row['Date'].date() if isinstance(row['Date'], pd.Timestamp) else row['Date']
        date = index.date() if isinstance(index.date(), pd.Timestamp) else index.date() # ab 15.2.2025
        row['Adj Close'] = row['Close']  # ab 15.2.2025
        cursor.execute('''INSERT OR IGNORE INTO stock_data 
                        (symbol, date, open, high, low, close, adj_close, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                        (symbol, date, row['Open'], row['High'], row['Low'],
                         row['Close'], row['Adj Close'], row['Volume']))
    _conn.commit() 


# Function to get all stocks from database
def get_all_stocks(_conn):
    cursor = _conn.cursor()
    #query = "SELECT DISTINCT symbol FROM stock_data ORDER BY symbol"
    #query = "SELECT symbol from stock_list group by symbol order by symbol"
    query = "SELECT symbol from stock_list group by symbol order by symbol "

    cursor.execute(query)
    stocks = [row[0] for row in cursor.fetchall()]

    query = "SELECT symbol, company_name from company_info group by symbol order by symbol"
    df = pd.read_sql(query, _conn)
    stocks_dict = dict(zip(df['symbol'], df['company_name']))
    
    return stocks, stocks_dict, df.shape[0]

def get_stocks_4infoupdate(_conn):
    cursor = _conn.cursor()
    today = datetime.today().date()
    #st.write(today)
    query = "SELECT symbol from company_info where updated_at < ? group by symbol order by symbol"

    cursor.execute(query, (str(today),))
    stocks = [row[0] for row in cursor.fetchall()]
    #st.write(stocks)
    return stocks

def find_fav(_conn, symbol):
    query = "SELECT fav_list.symbol, fav_names.symbol as listname from fav_list LEFT JOIN fav_names ON fav_names.ID = fav_list.ID_fav where fav_list.symbol = ?"
    df = pd.read_sql(query, _conn, params=(symbol,))
    return df

def get_fav_lists(_conn):
    query = "SELECT symbol from fav_names  "
    df = pd.read_sql(query, _conn)
    if df.empty:
        result = None
    else:
        liste = list(df["symbol"])
        result = liste        
    return result

def add_fav(_conn, sel_list, selected_stock):
    #query = f"SELECT fav_names.ID from fav_names LEFT JOIN fav_list ON fav_names.ID = fav_list.ID_fav where fav_names.symbol = '{sel_list}' and fav_list.symbol = '{selected_stock}'"
    query = "SELECT ID, symbol as listname from fav_names where symbol = ?"
    df = pd.read_sql(query, _conn, params=(sel_list,))
    id = int(df['ID'])
    cursor = _conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO fav_list (ID_fav, symbol) VALUES (?, ?)', (id, selected_stock))
    _conn.commit() 

def del_fav(_conn, selected_stock):
    cursor = _conn.cursor()
    cursor.execute('DELETE FROM fav_list WHERE symbol = ?', (selected_stock,))
    _conn.commit() 



def update_stock_info(_conn, stock_list):
    t_start = time()
    notupdated = []
    i = 0
    wait = 0
    for symbol in stock_list:
        i+=1
        if i % 100 == 0:
            wait = 10
        if i % 500 == 0:
            wait = 30            
        if wait > 0:
            st.write(f'Warte {wait} sec')
            sleep(wait)
            wait = 0
        symbol = symbol.upper()
        
        # Update company info
        # st.write(f"Updating company info for {symbol}")
        updated = update_company_info(_conn, symbol)
        st.write(f"{i}: Updating for company info {symbol} : {updated}")
        if updated == f"Fehler beim Speichern !" :
            notupdated.append(symbol)


    st.write(f'Duration: {round(time()-t_start,1)}sec')
    st.write(notupdated) 

def delete_all_stock_info(_conn, stock_list):
    cursor = _conn.cursor()
    
    #query = '''drop table company_info'''
    #query = '''delete from stock_data where symbol = "4GLD.SG" '''
    #cursor.execute(query)
    for symbol in stock_list:
        cursor.execute('DELETE FROM company_info WHERE symbol = ?', (symbol,))
        cursor.execute('DELETE FROM stock_data WHERE symbol = ?', (symbol,))
        cursor.execute('DELETE FROM stock_list WHERE symbol = ?', (symbol,))
        st.write(f"Deleted company: {symbol}")

    _conn.commit()
    pass
    

# Modified update_stock_data function to also update company info
def update_stock_data(_conn, stock_list):
    nadata_stock_list = []
    t_start = time()
    i = 0
    z = 1
    today = datetime.today().date()
    fifteen_years_ago = today - timedelta(days=15*365)
    
    for symbol in stock_list:
        symbol = symbol.upper()
        i+=1
        if z % 100 == 0:
            z=1
            wait = 5
            st.write(f'Warte {wait} sec')
            sleep(wait)

        # Update stock price data
        last_date = get_last_entry_date(_conn, symbol)
        if last_date:
            start_date = datetime.strptime(last_date, "%Y-%m-%d").date() + timedelta(days=1)
        else:
            start_date = fifteen_years_ago
        
        if start_date >= today:
            st.write(f"{i}: No new data for {symbol}, already up-to-date.")
            continue
        
        st.write(f"{i}: Fetching price data for {symbol} from {start_date} to {today}")
        try:

            data = get_stock_data(symbol, start_date, today)
            if data.empty:
                st.write(f"No new data found for {symbol}.")
                nadata_stock_list.append(symbol)
            else:
                save_to_db(_conn, symbol, data)
        except Exception as e:
            st.write(f'No data available for {symbol}: {e}')

        z+=1
    
    st.write(f'Duration: {round(time()-t_start,1)}sec')
    if nadata_stock_list:
        st.warning(f"Keine neuen Daten gefunden für: {', '.join(nadata_stock_list)}")


@st.cache_data
def calculate_ma_signals(_conn, days_back, crossover=1, filterma=False, filtervola=False, filterfav=False):
    window_s = 9 * crossover
    window_l = 21 * crossover
    # Mehr Tage zurück holen für genauere Berechnung der MAs am Anfang
    last_n_days = datetime.today().date() - timedelta(days=21*crossover+days_back+window_l)
    

    if filterfav == True:
        query = '''SELECT stock_data.* FROM stock_data inner join fav_list on fav_list.symbol = stock_data.symbol WHERE stock_data.date >= ? ORDER BY stock_data.symbol, stock_data.date'''
    else:
        query = '''SELECT * FROM stock_data WHERE date >= ? ORDER BY symbol, date'''
        
    
    df = pd.read_sql(query, _conn, params=[last_n_days])
    last_days = datetime.today().date() - timedelta(days=days_back)

    #st.write(df)
    
    buy_signal_list = []
    sell_signal_list = []

    for symbol in df['symbol'].unique():
        stock_df = df[df['symbol'] == symbol].copy()
        
        # Berechnung der Moving Averages
        stock_df['MA_short'] = stock_df['adj_close'].rolling(window=window_s, min_periods=window_s).mean()
        stock_df['MA_long'] = stock_df['adj_close'].rolling(window=window_l, min_periods=window_l).mean()
        
        # Präzisere Signalberechnung mit Berücksichtigung des vorherigen Tages
        stock_df['Above'] = stock_df['MA_short'] > stock_df['MA_long']
        stock_df['Cross_Up'] = (stock_df['Above'] != stock_df['Above'].shift(1)) & stock_df['Above']
        stock_df['Cross_Down'] = (stock_df['Above'] != stock_df['Above'].shift(1)) & ~stock_df['Above']
        
        stock_df['date'] = pd.to_datetime(stock_df['date']).dt.date
        stock_df_recent = stock_df[stock_df['date'] >= last_days]
        
        # Signale identifizieren
        buy_signals = stock_df_recent[stock_df_recent['Cross_Up']]
        sell_signals = stock_df_recent[stock_df_recent['Cross_Down']]
        
        # Volumenbestätigung
        volume_condition = True
        #volume_condition = stock_df['volume'] > stock_df['volume'].rolling(window=5).mean()

        # Trend-Bestätigung
        trend_condition = True
        if filterma==True:
            trend_condition = stock_df['MA_long'] > stock_df['MA_long'].shift(4*crossover)

        # Volatilitätsfilter
        volatility_condition = True
        if filtervola == True:
            atr = calculate_atr(stock_df, period=14)
            volatility_condition = atr < atr.rolling(window=20).mean()

        # Kombinierte Bedingungen
        buy_signals = stock_df_recent[
            stock_df_recent['Cross_Up'] & 
            volume_condition & 
            trend_condition & 
            volatility_condition
        ]

        # Relative Stärke zu einem Index
        # Index-Daten aus der Datenbank laden
        #query_index = '''SELECT * FROM index_data WHERE date >= ? ORDER BY date'''
        #index_df = pd.read_sql(query_index, _conn, params=[last_n_days])
        # stock_df['relative_strength'] = stock_df['adj_close'] / index_df['adj_close']

        # Momentum
        #stock_df['momentum'] = stock_df['adj_close'].pct_change(periods=20)

        # Distanz zum Moving Average
        #stock_df['ma_distance'] = (stock_df['adj_close'] - stock_df['MA_long']) / stock_df['MA_long']


        
        # Signale zur Liste hinzufügen
        if not buy_signals.empty:
            for _, row in buy_signals.iterrows():
                buy_signal_list.append((
                    symbol, 
                    row['date'], 
                    'Buy',
                    #row['adj_close'],  # Optional: Preis hinzufügen
                    #row['MA_short'],    # Optional: MA-Werte hinzufügen
                    #row['MA_long']
                ))
                
        if not sell_signals.empty:
            for _, row in sell_signals.iterrows():
                sell_signal_list.append((
                    symbol, 
                    row['date'], 
                    'Sell',
                    #row['adj_close'],  # Optional: Preis hinzufügen
                    #row['MA_short'],    # Optional: MA-Werte hinzufügen
                    #row['MA_long']
                ))

    # Sortierung nach Datum und Symbol
    buy_signal_list.sort(key=lambda x: (x[1], x[0]))
    sell_signal_list.sort(key=lambda x: (x[1], x[0]))
    
    return buy_signal_list, sell_signal_list
   
def format_stock_info_data(info):
    try:
        info = {k.lower(): v for k, v in info.items()}  # Variablennamen werden auf kleinschreibung gesetzt
        dateupdated = info.get('updated_at', 'N/A')
        webadress = info.get('website', 'N/A')
        current_currency = info.get('financialcurrency', '')
        employees = format_number(info.get('fulltimeemployees', 'N/A'))
        volume = format_number(info.get('volume', 'N/A'))
        
        #return format_stock_info_data(info, schreibung='.lower()')
        # Organisiere die Daten in Kategorien
        data = {
            'Allgemeine Informationen': {
                'Name': info.get('longname', 'N/A'),
                'Adresse': info.get('address1', 'N/A'),
                'Stadt': info.get('city', 'N/A'),
                'Land': info.get('country', 'N/A'),
                'Website': webadress ,
                #'web': st.markdown(f'<a href="{webadress}" class="link" target="_blank">{webadress}</a>', unsafe_allow_html=True),
                'Mitarbeiter': employees[:-3] if employees.replace('.','').replace(',','').isdigit() else  employees,
                'Branche': info.get('industry', 'N/A'),
                'Sektor': info.get('sector', 'N/A'),
            },
            'Aktuelle Marktdaten': {
                'Letzter update':dateupdated,
                'Aktueller Preis': format_number(info.get('currentprice', 0), is_currency=True, currency=current_currency),
                'Tageshoch': format_number(info.get('dayhigh', 0), is_currency=True, currency=current_currency),
                'Tagestief': format_number(info.get('daylow', 0), is_currency=True, currency=current_currency),
                'Handelsvolumen': volume[:-3] if volume.replace('.','').replace(',','').isdigit() else  volume,
                '52-Wochen-Hoch': format_number(info.get('fiftytwoWeekhigh', 0), is_currency=True, currency=current_currency),
                '52-Wochen-Tief': format_number(info.get('fiftytwoWeeklow', 0), is_currency=True, currency=current_currency),
            },
            'Fundamentaldaten': {
                'Market Cap': format_number(info.get('marketcap', 0), is_currency=True, currency=current_currency),
                'Enterprise Value': format_number(info.get('enterprisevalue', 0), is_currency=True, currency=current_currency),
                'Umsatz': format_number(info.get('totalrevenue', 0), is_currency=True, currency=current_currency),
                'EBITDA': format_number(info.get('ebitda', 0), is_currency=True, currency=current_currency),
                'Nettogewinn': format_number(info.get('netincometoCommon', 0), is_currency=True, currency=current_currency),
                'Freier Cashflow': format_number(info.get('freecashflow', 0), is_currency=True, currency=current_currency),
                
            },
            'Wichtige Kennzahlen': {
                'KGV (P/E)': format_number(info.get('trailingpe', 0)),
                'Forward P/E': format_number(info.get('forwardpe', 0)),
                'PEG Ratio': format_number(info.get('pegratio', 0)),
                'Kurs/Buchwert': format_number(info.get('pricetobook', 0)),
                'EV/EBITDA': format_number(info.get('enterprisetoebitda', 0)),
                'Dividendenrendite': format_number(info.get('dividend_yield', 0) , is_percentage=True),
                'Dividendenrendite-5J': format_number(info.get('fiveyearavgdividendyield', 0)  , is_percentage=True),
                'Payout Ratio': format_number(info.get('payoutratio', 0) * 100 , is_percentage=True),
            },
            'Performance & Risiko': {
                'Beta': format_number(info.get('beta', 0)),
                'ROE': format_number(info.get('returnonequity', 0) * 100 , is_percentage=True),
                'ROA': format_number(info.get('returnonassets', 0) * 100 , is_percentage=True),
                'Gewinnmarge': format_number(info.get('profitmargins', 0) * 100 , is_percentage=True),
                'Operative Marge': format_number(info.get('operatingmargins', 0) * 100 , is_percentage=True),
                'Short Prozent von Float': format_number(info.get('shortpercentoffloat', 0) *100 , is_percentage=True),
                'Risiko über alles': info.get('overallrisk') if info.get('overallrisk') else '-', 
            },
            'Analystenbewertung':{
                'targetHighPrice': format_number(info.get('targethighprice', 0), is_currency=True, currency=current_currency),
                'targetLowPrice': format_number(info.get('targetlowprice', 0), is_currency=True, currency=current_currency),
                'targetMeanPrice': format_number(info.get('targetmeanprice', 0), is_currency=True, currency=current_currency),
                'targetMedianPrice': format_number(info.get('targetmedianprice', 0), is_currency=True, currency=current_currency),
                'recommendationMean': format_number(info.get('recommendationmean', 0)),
                'recommendationKey': info.get('recommendationkey', 0),
                'numberOfAnalystOpinions': info.get('numberofanalystopinions', 0),
            }
        }
        return data, True
    except Exception as e:
        st.error(f"Fehler beim Formatieren der Daten: {str(e)}")
        return None, False    

def get_stock_info_data(_conn, ticker_symbol):
    #  Holt Aktieninformationen von yfinance
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        #info = json.dumps(info)
        #info = json.loads(info)

        # Organisiere die Daten in Kategorien       
        return format_stock_info_data(info)
    except Exception as e:
        st.error(f"Fehler beim Abrufen der Daten: {str(e)}")
        return None, False
    
def get_stock_info_data_db(_conn, ticker_symbol):
    # Holt Aktieninformationen von yfinance
    try:
        info = get_company_info_db(_conn,ticker_symbol)
        info = {k.lower(): v for k, v in info.items()}
        return format_stock_info_data(info)
        
    except Exception as e:
        st.error(f"Fehler beim Abrufen der Daten: {str(e)}")
        return None, False    
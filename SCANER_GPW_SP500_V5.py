import yfinance as yf
import pandas as pd
import numpy as np
import requests
from io import StringIO
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')

def calculate_rsi(data, periods=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def run_market_scanner(tickers, market_name, top_n=50):
    print(f"\nRozpoczynam pobieranie danych dla {market_name} ({len(tickers)} spółek)... To może chwilę potrwać.")
    results = []
    
    data = yf.download(tickers, period="1y", group_by='ticker', threads=True)
    
    for ticker in tickers:
        try:
            if len(tickers) == 1:
                df = data.copy()
            else:
                df = data[ticker].copy()
                
            df.dropna(subset=['Close'], inplace=True)
            if df.empty or len(df) < 200:
                continue
                
            current_price = df['Close'].iloc[-1]
            rsi = calculate_rsi(df['Close']).iloc[-1]
            avg_volume = df['Volume'].rolling(window=30).mean().iloc[-1]
            
            sma_200 = df['Close'].rolling(window=200).mean().iloc[-1]
            trend_dist = ((current_price - sma_200) / sma_200) * 100
            
            info = yf.Ticker(ticker).info
            pe_ratio = info.get('trailingPE', np.nan)
            
            # Pobieranie nazwy spółki i skracanie zbyt długich tekstów do 20 znaków dla czytelności tabeli
            company_name = info.get('shortName', info.get('longName', 'Brak nazwy'))
            company_name = str(company_name)[:20] 
            
            raw_div = info.get('dividendYield', 0)
            if raw_div is None:
                dividend_yield = 0.0
            else:
                dividend_yield = raw_div * 100 if raw_div < 1 else raw_div
            
            score = 50
            if rsi < 60: score += 15
            if pe_ratio < 15 and pe_ratio > 0: score += 15
            if dividend_yield > 2: score += 10
            if trend_dist > 0: score += 10
            
            results.append({
                'Ticker': ticker.replace('.WA', ''),
                'Nazwa': company_name,
                'Cena': current_price,
                'C/Z': pe_ratio,
                'Dywidenda (%)': dividend_yield,
                'Śr. Wolumen (30d)': avg_volume,
                'RSI': rsi,
                'Trend od SMA200 (%)': trend_dist,
                'Score': score,
                'RSI_Dist_50': abs(rsi - 50)
            })
            
        except Exception:
            continue

    if not results:
        print(f"Brak wystarczających danych do wygenerowania raportu dla {market_name}.")
        return

    results_df = pd.DataFrame(results)
    results_df.dropna(subset=['Cena'], inplace=True)
    results_df.sort_values(by=['Score', 'RSI_Dist_50'], ascending=[False, True], inplace=True)
    
    top_results = results_df.head(top_n).drop(columns=['RSI_Dist_50']).reset_index(drop=True)
    top_results.index += 1
    
    top_results['Cena'] = top_results['Cena'].round(2)
    top_results['C/Z'] = top_results['C/Z'].round(1)
    top_results['Dywidenda (%)'] = top_results['Dywidenda (%)'].round(1)
    top_results['Śr. Wolumen (30d)'] = top_results['Śr. Wolumen (30d)'].apply(lambda x: f"{x/1e6:.1f}M" if x >= 1e6 else f"{x/1e3:.0f}K")
    top_results['RSI'] = top_results['RSI'].round(1)
    top_results['Trend od SMA200 (%)'] = top_results['Trend od SMA200 (%)'].round(1)
    
    report_title = f"--- TOP {top_n} SPÓŁEK {market_name} WEDŁUG AI SKORINGU ({datetime.today().strftime('%Y-%m-%d')}) ---"
    print(f"\n{report_title}")
    print(top_results.to_string())

    filename = f"Wyniki_{market_name.replace(' ', '')}_{datetime.today().strftime('%Y-%m-%d')}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"{report_title}\n\n")
        f.write(top_results.to_string())


# ==========================================
# 1. AUTOMATYCZNE POBIERANIE S&P 500
# ==========================================
try:
    print("Pobieranie listy spółek S&P 500 z Wikipedii...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    html_data = requests.get(url, headers=headers).text
    
    table = pd.read_html(StringIO(html_data))
    df_sp500 = table[0]
    sp500_symbols = df_sp500['Symbol'].tolist()
    sp500_tickers = [ticker.replace('.', '-') for ticker in sp500_symbols]
    run_market_scanner(sp500_tickers, "S&P 500", top_n=50)
except Exception as e:
    print(f"Błąd podczas pobierania listy S&P 500: {e}")

# ==========================================
# 2. BAZA SPÓŁEK GPW (WIG20, mWIG40, sWIG80)
# ==========================================
wig20 = ['11B', 'ACP', 'ALE', 'ALR', 'BDX', 'BHW', 'CDR', 'CPS', 'DNP', 'JSW', 
         'KGH', 'KRU', 'KTY', 'LPP', 'MBK', 'OPL', 'PEO', 'PGE', 'PKO', 'PZU', 'SPL']

mwig40 = ['APR', 'ASB', 'CAR', 'CIE', 'CIG', 'CMR', 'DAT', 'DOM', 'DVL', 'ENA', 
          'EUR', 'FMF', 'GPW', 'GRX', 'HUU', 'ING', 'INT', 'LWB', 'MAB', 'MIL', 
          'NEU', 'PKP', 'PLW', 'RBW', 'RVC', 'SLV', 'TEN', 'TPE', 'TXT', 'WPL', 'XTB', 'ZEP']

swig80 = ['AAT', 'ABE', 'ACG', 'ACT', 'AGO', 'ALL', 'AMC', 'AML', 'ANR', 'APA', 
          'APT', 'AST', 'ATC', 'ATG', 'ATD', 'BFT', 'BKM', 'BML', 'BOS', 'BPN', 
          'BRS', 'CAV', 'CEZ', 'CFI', 'CLN', 'CNT', 'CPA', 'CPG', 'CRM', 'CRJ', 
          'DBC', 'DEK', 'DTR', 'EAT', 'ECH', 'EDI', 'ENT', 'ERB', 'FRO', 'GTC', 
          'GTN', 'INC', 'KGN', 'LSI', 'MCI', 'MCO', 'MDG', 'MND', 'MOJ', 'MRB', 
          'MSZ', 'MZA', 'OAT', 'OEX', 'PCE', 'PCR', 'PEN', 'PEP', 'PXM', 'QNT', 
          'R22', 'RVU', 'SAN', 'SNT', 'STX', 'TIM', 'TOA', 'TOR', 'TRK', 'VGO', 
          'VOT', 'VRC', 'WLT', 'ZMT']

gpw_symbols = wig20 + mwig40 + swig80
gpw_tickers = [f"{sym}.WA" for sym in gpw_symbols]

run_market_scanner(gpw_tickers, "GPW (WIG140)", top_n=50)
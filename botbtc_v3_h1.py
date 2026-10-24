import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import requests
import time
from datetime import datetime
from IPython.display import clear_output

# --- KONFIGURACJA POWIADOMIEŃ ---
TELEGRAM_TOKEN = '8488356348:AAHpjRHW4X-NPJV0C-BJVV21-30RoLctu1Q'
CHAT_ID = '738220792'

# --- PARAMETRY STRATEGII (ZOPTYMALIZOWANE) ---
SYMBOL = "BTC-USD"
EMA_S_LEN = 5
EMA_L_LEN = 30
EMA_H1_TREND = 50
ADX_THRESHOLD = 40  # Wysoki próg dla BTC
SL_PCT = 0.015      # 1.5% Stop Loss
TP_PCT = 0.070      # 7.0% Take Profit

def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Błąd Telegrama: {e}")

def get_confirmed_live_data():
    """Pobiera dane M15 i trend H1."""
    try:
        m15 = yf.Ticker(SYMBOL).history(period="3d", interval="15m")
        h1 = yf.Ticker(SYMBOL).history(period="5d", interval="1h")
        if m15.empty or h1.empty:
            return None
        
        # Obliczanie trendu H1
        h1['EMA_TREND'] = ta.ema(h1['Close'], length=EMA_H1_TREND)
        h1['Trend_H1'] = np.where(h1['Close'] > h1['EMA_TREND'], 1, -1)
        
        # Wskaźniki M15
        m15['EMA_S'] = ta.ema(m15['Close'], length=EMA_S_LEN)
        m15['EMA_L'] = ta.ema(m15['Close'], length=EMA_L_LEN)
        macd = ta.macd(m15['Close'])
        m15 = pd.concat([m15, macd], axis=1)
        m15['RSI'] = ta.rsi(m15['Close'], length=14)
        adx = ta.adx(m15['High'], m15['Low'], m15['Close'], length=14)
        m15 = pd.concat([m15, adx], axis=1)
        
        # Synchronizacja
        df = pd.merge_asof(m15.sort_index(), h1[['Trend_H1']].sort_index(),
                           left_index=True, right_index=True, direction='backward')
        return df
    except:
        return None

def run_live_btc_monitor():
    print(f"[PRODUKCJA] Rozpoczęto monitorowanie {SYMBOL} (ADX > {ADX_THRESHOLD})...")
    last_candle_time = None
    
    while True:
        try:
            df = get_confirmed_live_data()
            if df is None or len(df) < 50:
                time.sleep(30)
                continue
                
            row = df.iloc[-2]  # Ostatnia ZAMKNIĘTA świeca
            c_time = df.index[-2]
            current_price = df.iloc[-1]['Close']
            
            # Odświeżanie dashboardu w konsoli
            clear_output(wait=True)
            print(f"=== MONITOR BTC LIVE (EMA 5/30 + ADX) ===")
            print(f"Ostatnia świeca: {c_time.strftime('%Y-%m-%d %H:%M')}")
            print(f"Cena: {current_price:.2f} | Trend H1: {'Bull ⬆️' if row['Trend_H1']==1 else 'Bear ⬇️'}")
            print(f"ADX: {row['ADX_14']:.2f} | RSI: {row['RSI']:.2f}")
            print(f"==========================================")

            if last_candle_time != c_time:
                sig = 0
                # Logika LONG: Indicators + ADX + H1 Bull
                if (row['EMA_S'] > row['EMA_L']) and (row['MACD_12_26_9'] > row['MACDs_12_26_9']) and \
                   (row['ADX_14'] > ADX_THRESHOLD) and (row['Trend_H1'] == 1):
                    sig = 1
                # Logika SHORT: Indicators + ADX + H1 Bear
                elif (row['EMA_S'] < row['EMA_L']) and (row['MACD_12_26_9'] < row['MACDs_12_26_9']) and \
                     (row['ADX_14'] > ADX_THRESHOLD) and (row['Trend_H1'] == -1):
                    sig = -1
                
                if sig != 0:
                    side = "LONG 🟢" if sig == 1 else "SHORT 🔴"
                    entry = row['Close']
                    sl = entry * (1 - SL_PCT if sig == 1 else 1 + SL_PCT)
                    tp = entry * (1 + TP_PCT if sig == 1 else 1 - TP_PCT)
                    
                    alert = (f"*🚀 SYGNAŁ BTC-USD LIVE*\n"
                             f"Kierunek: {side}\n"
                             f"Wejście: {entry:.2f}\n"
                             f"🎯 TP: {tp:.2f} | 🛡️ SL: {sl:.2f}\n"
                             f"📊 ADX: {row['ADX_14']:.2f} | Trend H1: Zgodny")
                    send_telegram_msg(alert)
                
                last_candle_time = c_time
            
            time.sleep(60) # Sprawdzenie co minutę
            
        except KeyboardInterrupt:
            print("\n🛑 Monitorowanie zatrzymane.")
            break
        except Exception as e:
            print(f"⚠️ Błąd: {e}")
            time.sleep(60)

run_live_btc_monitor()
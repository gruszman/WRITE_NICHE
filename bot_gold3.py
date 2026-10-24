import yfinance as yf
import pandas_ta as ta
import pandas as pd
import numpy as np
import requests
import time
import os
from datetime import datetime

# --- KONFIGURACJA PRODUKCYJNA ---
SYMBOL = "GC=F"
TELEGRAM_TOKEN = '8488356348:AAHpjRHW4X-NPJV0C-BJVV21-30RoLctu1Q'
CHAT_ID = '738220792'

# Parametry zoptymalizowane
EMA_S = 5
EMA_L = 35
EMA_TREND_H1 = 50
ADX_MIN = 20
ATR_SL_MULT = 1.5
ATR_TP_MULT = 3.5

# Lokalna ścieżka na Windows (utworzy folder 'logs' w folderze skryptu)
LOGS_PATH = os.path.join(os.path.dirname(__file__), 'logs')
if not os.path.exists(LOGS_PATH):
    os.makedirs(LOGS_PATH)

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: 
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    except: 
        pass

def log_trade(side, entry, tp, sl, atr):
    file_path = os.path.join(LOGS_PATH, 'production_log.csv')
    log_data = pd.DataFrame([{
        'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'Side': side, 'Entry': round(entry, 2), 'TP': round(tp, 2),
        'SL': round(sl, 2), 'ATR': round(atr, 2)
    }])
    log_data.to_csv(file_path, mode='a', header=not os.path.exists(file_path), index=False)

def get_mtf_data():
    m15 = yf.Ticker(SYMBOL).history(period="3d", interval="15m")
    h1 = yf.Ticker(SYMBOL).history(period="5d", interval="1h")
    if m15.empty or h1.empty: 
        return None
    h1['Trend_H1'] = np.where(h1['Close'] > ta.ema(h1['Close'], length=EMA_TREND_H1), 1, -1)
    m15['EMA_S'] = ta.ema(m15['Close'], length=EMA_S)
    m15['EMA_L'] = ta.ema(m15['Close'], length=EMA_L)
    m15['ATR'] = ta.atr(m15['High'], m15['Low'], m15['Close'], length=14)
    adx = ta.adx(m15['High'], m15['Low'], m15['Close'], length=14)
    m15 = pd.concat([m15, adx], axis=1)
    macd = ta.macd(m15['Close'])
    m15 = pd.concat([m15, macd], axis=1)
    df = pd.merge_asof(m15.sort_index(), h1[['Trend_H1']].sort_index(),
                       left_index=True, right_index=True, direction='backward')
    return df

def run_production_monitor():
    print(f"🚀 Uruchomiono system Gold MTF ATR-Pro dla {SYMBOL} (ADX > {ADX_MIN})")
    last_candle_time = None
    retry_delay = 60 

    while True:
        try:
            df = get_mtf_data()
            if df is None or len(df) < 50:
                raise ValueError("Puste dane rynkowe")

            retry_delay = 60

            row = df.iloc[-2]
            c_time = df.index[-2]

            if last_candle_time != c_time:
                sig = 0
                if (row['EMA_S'] > row['EMA_L']) and (row['MACD_12_26_9'] > row['MACDs_12_26_9']) and (row['Trend_H1'] == 1) and (row['ADX_14'] > ADX_MIN):
                    sig = 1
                elif (row['EMA_S'] < row['EMA_L']) and (row['MACD_12_26_9'] < row['MACDs_12_26_9']) and (row['Trend_H1'] == -1) and (row['ADX_14'] > ADX_MIN):
                    sig = -1

                if sig != 0:
                    side = "LONG 🟢" if sig == 1 else "SHORT 🔴"
                    entry = row['Close']
                    atr = row['ATR']
                    sl = entry - (atr * ATR_SL_MULT) if sig == 1 else entry + (atr * ATR_SL_MULT)
                    tp = entry + (atr * ATR_TP_MULT) if sig == 1 else entry - (atr * ATR_TP_MULT)
                    alert = (f"*🚨 SYGNAŁ GOLD MTF-ATR-ADX*\nKierunek: {side}\nWejście: {entry:.2f}\n🎯 TP: {tp:.2f} | 🛡️ SL: {sl:.2f}\n📊 ADX: {row['ADX_14']:.2f} | Trend H1: {'Bull' if row['Trend_H1']==1 else 'Bear'}")
                    send_telegram(alert)
                    log_trade(side, entry, tp, sl, atr)
                    print(f"[{datetime.now().strftime('%H:%M')}] Sygnał {side} wysłany.")

                last_candle_time = c_time
            time.sleep(60)

        except KeyboardInterrupt:
            print("Stopping...")
            break
        except Exception as e:
            print(f"⚠️ Błąd połączenia/API: {e}. Ponowna próba za {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 600)

run_production_monitor()
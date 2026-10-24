import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import time
import numpy as np
from datetime import datetime
from IPython.display import clear_output

# --- ⚙️ KONFIGURACJA TELEGRAM --- 
# Uzyskaj token od @BotFather i ID od @userinfobot
TELEGRAM_TOKEN = '8488356348:AAHpjRHW4X-NPJV0C-BJVV21-30RoLctu1Q'
CHAT_ID = '738220792'

# --- 📊 PARAMETRY STRATEGII ---
SYMBOL = "BTC-USD"
EMA_S_LEN = 5
EMA_L_LEN = 35
EMA_H1_TREND = 50
SL_PCT = 0.010  # 1.0%
TP_PCT = 0.015  # 1.5%

def send_telegram_alert(message):
    """Wysyła sformatowaną wiadomość na Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Błąd Telegrama: {e}")

def get_live_data():
    """Pobiera i synchronizuje dane M15 oraz H1."""
    try:
        # Pobieranie danych
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
        
        # Łączenie
        df = pd.merge_asof(m15.sort_index(), h1[['Trend_H1']].sort_index(), 
                           left_index=True, right_index=True, direction='backward')
        return df
    except Exception as e:
        print(f"Błąd pobierania danych: {e}")
        return None

def run_realtime_monitor():
    print(f"[START] Monitorowanie {SYMBOL} aktywne...")
    last_processed_candle = None
    
    while True:
        try:
            df = get_live_data()
            if df is None or len(df) < 50:
                time.sleep(30)
                continue
            
            # Najświeższe dane (świeca jeszcze otwarta)
            current_candle = df.iloc[-1]
            # Ostatnia ZAMKNIĘTA świeca (na niej bazują sygnały)
            row = df.iloc[-2]
            candle_time = df.index[-2]
            
            # Wizualizacja statusu w konsoli Colab
            clear_output(wait=True)
            print(f"=== MONITOR BTC REAL-TIME ===")
            print(f"Czas: {datetime.now().strftime('%H:%M:%S')}")
            print(f"Aktualna cena: {current_candle['Close']:.2f}")
            print(f"Trend H1: {'Wzrostowy 📈' if row['Trend_H1'] == 1 else 'Spadkowy 📉'}")
            print(f"RSI: {row['RSI']:.2f} | EMA 5/35: {row['EMA_S']:.1f}/{row['EMA_L']:.1f}")
            print(f"==============================")

            # Sprawdź sygnał tylko raz na zamknięcie świecy
            if last_processed_candle != candle_time:
                sig = 0
                # Logika LONG
                if (row['EMA_S'] > row['EMA_L']) and \
                   (row['MACD_12_26_9'] > row['MACDs_12_26_9']) and \
                   (row['RSI'] < 75) and (row['Trend_H1'] == 1):
                    sig = 1
                
                # Logika SHORT
                elif (row['EMA_S'] < row['EMA_L']) and \
                     (row['MACD_12_26_9'] < row['MACDs_12_26_9']) and \
                     (row['RSI'] > 25) and (row['Trend_H1'] == -1):
                    sig = -1
                
                if sig != 0:
                    side = "LONG 🟢" if sig == 1 else "SHORT 🔴"
                    entry = row['Close']
                    sl = entry * (1 - SL_PCT if sig == 1 else 1 + SL_PCT)
                    tp = entry * (1 + TP_PCT if sig == 1 else 1 - TP_PCT)
                    
                    msg = (f"*🚨 NOWY SYGNAŁ {SYMBOL}*\n"
                           f"Typ: {side}\n"
                           f"Wejście: {entry:.2f}\n"
                           f"🎯 TP: {tp:.2f} | 🛡️ SL: {sl:.2f}\n"
                           f"Czas świecy: {candle_time.strftime('%H:%M')}")
                    send_telegram_alert(msg)
                    print(f"!!! SYGNAŁ {side} WYSŁANY !!!")
                
                last_processed_candle = candle_time
            
            time.sleep(60) # Sprawdzaj co minutę
            
        except KeyboardInterrupt:
            print("\n🛑 Monitorowanie zatrzymane ręcznie.")
            break
        except Exception as e:
            print(f"⚠️ Błąd pętli: {e}")
            time.sleep(60)

# Uruchomienie silnika
run_realtime_monitor()
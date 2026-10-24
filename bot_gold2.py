# Install pandas_ta and mplfinance if not already installed

import pandas as pd
import yfinance as yf
import pandas_ta as ta
import mplfinance as mpf
import matplotlib.pyplot as plt
import numpy as np
import requests
import time
from datetime import datetime


# --- KONFIGURACJA ---
SYMBOL = "GC=F"
TELEGRAM_BOT_TOKEN = '8488356348:AAHpjRHW4X-NPJV0C-BJVV21-30RoLctu1Q'
TELEGRAM_CHAT_ID = '738220792'
SL_PCT = 0.01  # 1% Stop Loss
TP_PCT = 0.02  # 2% Take Profit

# 1. POBIERANIE DANYCH
print("Pobieranie danych rynkowych...")
df_m15 = yf.Ticker(SYMBOL).history(period="60d", interval="15m")
df_m30 = yf.Ticker(SYMBOL).history(period="60d", interval="30m")
df_h1 = yf.Ticker(SYMBOL).history(period="60d", interval="60m")

# 2. OBLICZANIE WSKAŹNIKÓW (Zoptymalizowane EMA 5/35)
df_m15['EMA_S'] = ta.ema(df_m15['Close'], length=5)
df_m15['EMA_L'] = ta.ema(df_m15['Close'], length=35)
macd = ta.macd(df_m15['Close'])
df_m15 = pd.concat([df_m15, macd], axis=1)
df_m15['RSI'] = ta.rsi(df_m15['Close'], length=14)

# 3. TREND GLOBALNY (M30/H1)
df_m30['EMA50'] = ta.ema(df_m30['Close'], length=50)
df_h1['EMA50'] = ta.ema(df_h1['Close'], length=50)

df_m15 = pd.merge_asof(df_m15, df_m30[['EMA50']].rename(columns={'EMA50': 'EMA50_M30'}), left_index=True, right_index=True)
df_m15 = pd.merge_asof(df_m15, df_h1[['EMA50']].rename(columns={'EMA50': 'EMA50_H1'}), left_index=True, right_index=True)

df_m15['Trend_Global'] = 'Neutral'
df_m15.loc[(df_m15['Close'] > df_m15['EMA50_M30']) & (df_m15['Close'] > df_m15['EMA50_H1']), 'Trend_Global'] = 'Wzrostowy'
df_m15.loc[(df_m15['Close'] < df_m15['EMA50_M30']) & (df_m15['Close'] < df_m15['EMA50_H1']), 'Trend_Global'] = 'Spadkowy'

# 4. GENEROWANIE SYGNAŁÓW
df_m15['Signal'] = 0
df_m15.loc[(df_m15['EMA_S'] > df_m15['EMA_L']) & (df_m15['MACD_12_26_9'] > df_m15['MACDs_12_26_9']) & (df_m15['RSI'] < 70) & (df_m15['Trend_Global'] == 'Wzrostowy'), 'Signal'] = 1
df_m15.loc[(df_m15['EMA_S'] < df_m15['EMA_L']) & (df_m15['MACD_12_26_9'] < df_m15['MACDs_12_26_9']) & (df_m15['RSI'] > 30) & (df_m15['Trend_Global'] == 'Spadkowy'), 'Signal'] = -1

# 5. BACKTESTING Z SL/TP
def run_backtest(df):
    df = df.copy()
    df['Strategy_Returns'] = 0.0
    df['Exit_Type'] = None
    in_pos = 0; entry_p = 0.0

    for i in range(1, len(df)):
        curr = df.iloc[i]; prev = df.iloc[i-1]
        if in_pos == 1: # Long
            if curr['Low'] <= entry_p * (1 - SL_PCT):
                df.iloc[i, df.columns.get_loc('Strategy_Returns')] = -SL_PCT; df.iloc[i, df.columns.get_loc('Exit_Type')] = 'SL'; in_pos = 0
            elif curr['High'] >= entry_p * (1 + TP_PCT):
                df.iloc[i, df.columns.get_loc('Strategy_Returns')] = TP_PCT; df.iloc[i, df.columns.get_loc('Exit_Type')] = 'TP'; in_pos = 0
            else:
                df.iloc[i, df.columns.get_loc('Strategy_Returns')] = np.log(curr['Close']/prev['Close'])
        elif in_pos == -1: # Short
            if curr['High'] >= entry_p * (1 + SL_PCT):
                df.iloc[i, df.columns.get_loc('Strategy_Returns')] = -SL_PCT; df.iloc[i, df.columns.get_loc('Exit_Type')] = 'SL'; in_pos = 0
            elif curr['Low'] <= entry_p * (1 - TP_PCT):
                df.iloc[i, df.columns.get_loc('Strategy_Returns')] = TP_PCT; df.iloc[i, df.columns.get_loc('Exit_Type')] = 'TP'; in_pos = 0
            else:
                df.iloc[i, df.columns.get_loc('Strategy_Returns')] = -np.log(curr['Close']/prev['Close'])

        if in_pos == 0:
            if prev['Signal'] == 1: in_pos = 1; entry_p = curr['Open']
            elif prev['Signal'] == -1: in_pos = -1; entry_p = curr['Open']
    return df

df_m15 = run_backtest(df_m15)
print(f"Skumulowany zwrot strategii (z SL/TP): {(np.exp(df_m15['Strategy_Returns'].cumsum().iloc[-1])-1)*100:.2f}%")

# 6. FUNKCJE TELEGRAM
def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try: requests.post(url, json=payload)
    except Exception as e: print(f"Błąd Telegrama: {e}")

def check_for_realtime_signals():
    print("Monitoring aktywny. Czekam na zamknięcie świec M15...")
    last_signal_time = None
    last_periodic_update_time = time.time() # Initialize for periodic updates

    # Note on gold price source: yfinance provides reliable historical data. For real-time trading,
    # a dedicated broker API would typically be used for ultra-low latency data.
    # This setup is suitable for strategy backtesting and monitoring, but may have slight delays
    # compared to direct broker feeds.

    while True:
        try:
            live = yf.Ticker(SYMBOL).history(period="1d", interval="15m")
            if live.empty:
                time.sleep(30)
                continue

            # Ensure enough data for indicators
            if len(live) < 35: # Needs at least 35 for EMA_L
                time.sleep(30)
                continue

            live['EMA_S'] = ta.ema(live['Close'], length=5)
            live['EMA_L'] = ta.ema(live['Close'], length=35)
            macd_live = ta.macd(live['Close'])
            live = pd.concat([live, macd_live], axis=1)
            live['RSI'] = ta.rsi(live['Close'], length=14)

            # Get the latest *completed* 15-minute candle data for signals
            row_signal = live.iloc[-2]
            c_time = live.index[-2]

            # --- Handle new signals ---
            if last_signal_time != c_time: # Only check for signals on new closed candles
                sig = 0
                # Signal logic simplified for live feed (removed global trend for efficiency)
                if (row_signal['EMA_S'] > row_signal['EMA_L']) and \
                   (row_signal['MACD_12_26_9'] > row_signal['MACDs_12_26_9']) and \
                   (row_signal['RSI'] < 70):
                    sig = 1 # Long signal

                elif (row_signal['EMA_S'] < row_signal['EMA_L']) and \
                     (row_signal['MACD_12_26_9'] < row_signal['MACDs_12_26_9']) and \
                     (row_signal['RSI'] > 30):
                    sig = -1 # Short signal

                if sig != 0:
                    side = "LONG 🟢" if sig == 1 else "SHORT 🔴"
                    entry_price_sig = row_signal['Close']
                    sl_sig = entry_price_sig * (1 - SL_PCT if sig == 1 else 1 + SL_PCT)
                    tp_sig = entry_price_sig * (1 + TP_PCT if sig == 1 else 1 - TP_PCT)

                    msg = f"*ALERT Gold ({SYMBOL})*\n" \
                          f"Typ: {side}\n" \
                          f"Wejście: {entry_price_sig:.2f}\n" \
                          f"SL: {sl_sig:.2f}\n" \
                          f"TP: {tp_sig:.2f}\n" \
                          f"Czas świecy: {c_time.strftime('%Y-%m-%d %H:%M')}"
                    send_telegram_msg(msg)
                    last_signal_time = c_time # Update last signal time

            # --- Handle periodic status update every 5 minutes ---
            if time.time() - last_periodic_update_time >= 300: # 300 seconds = 5 minutes
                # Use the absolute latest price (current, possibly still-forming candle)
                current_price = live.iloc[-1]['Close']
                current_ema_s = live['EMA_S'].iloc[-1]
                current_ema_l = live['EMA_L'].iloc[-1]

                # Determine immediate trend based on 15m EMAs
                if current_ema_s > current_ema_l:
                    current_trend_status = "Wzrostowy (Short-term)"
                elif current_ema_s < current_ema_l:
                    current_trend_status = "Spadkowy (Short-term)"
                else:
                    current_trend_status = "Neutralny (Short-term)"

                periodic_msg = f"*Monitoring Gold ({SYMBOL}) Status ({datetime.now().strftime('%H:%M')})*\n" \
                               f"Aktualna cena: {current_price:.2f}\n" \
                               f"Kierunek trendu (M15): {current_trend_status}\n" \
                               f"Źródło danych: Yahoo Finance"
                send_telegram_msg(periodic_msg)
                last_periodic_update_time = time.time() # Reset timer

            time.sleep(60) # Check every minute
        except KeyboardInterrupt:
            print("Monitoring zatrzymany przez użytkownika.")
            break
        except Exception as e:
            print(f"Błąd podczas monitorowania: {e}")
            time.sleep(60)


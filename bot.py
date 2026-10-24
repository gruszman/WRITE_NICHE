import os
import time
from datetime import datetime
import numpy as np
import pandas as pd
import requests
import ta
import yfinance as yf

# --- KONFIGURACJA ---
SYMBOL = "GC=F"
TELEGRAM_TOKEN = "8488356348:AAHpjRHW4X-NPJV0C-BJVV21-30RoLctu1Q"
CHAT_ID = "738220792"

EMA_S = 5
EMA_L = 35
EMA_TREND_H1 = 50
ADX_MIN = 20
ATR_SL_MULT = 1.5
ATR_TP_MULT = 3.5

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
DATA_PATH = os.path.join(BASE_DIR, "GoldStrategy")
os.makedirs(DATA_PATH, exist_ok=True)


def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print(f"Błąd wysyłania Telegram: {e}")


def log_trade(side, entry, tp, sl, atr):
    file_path = os.path.join(DATA_PATH, "production_log.csv")
    log_data = pd.DataFrame(
        [
            {
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Side": side,
                "Entry": round(entry, 2),
                "TP": round(tp, 2),
                "SL": round(sl, 2),
                "ATR": round(atr, 2),
            }
        ]
    )
    log_data.to_csv(file_path, mode="a", header=not os.path.exists(file_path), index=False)


def get_mtf_data():
    m15 = yf.Ticker(SYMBOL).history(period="3d", interval="15m")
    h1 = yf.Ticker(SYMBOL).history(period="5d", interval="1h")
    if m15.empty or h1.empty:
        return None

    # Obliczenia H1
    h1_ema = ta.trend.EMAIndicator(h1["Close"], window=EMA_TREND_H1).ema_indicator()
    h1["Trend_H1"] = np.where(h1["Close"] > h1_ema, 1, -1)

    # Obliczenia M15
    m15["EMA_S"] = ta.trend.EMAIndicator(m15["Close"], window=EMA_S).ema_indicator()
    m15["EMA_L"] = ta.trend.EMAIndicator(m15["Close"], window=EMA_L).ema_indicator()
    m15["ATR"] = ta.volatility.AverageTrueRange(m15["High"], m15["Low"], m15["Close"], window=14).average_true_range()

    # ADX
    adx_indicator = ta.trend.ADXIndicator(m15["High"], m15["Low"], m15["Close"], window=14)
    m15["ADX_14"] = adx_indicator.adx()

    # MACD
    macd_indicator = ta.trend.MACD(m15["Close"], window_slow=26, window_fast=12, window_sign=9)
    m15["MACD_line"] = macd_indicator.macd()
    m15["MACD_signal"] = macd_indicator.macd_signal()

    df = pd.merge_asof(
        m15.sort_index(),
        h1[["Trend_H1"]].sort_index(),
        left_index=True,
        right_index=True,
        direction="backward",
    )
    return df


def run_production_monitor():
    print(f"🚀 Uruchomiono system Gold MTF ATR-Pro dla {SYMBOL} (ADX > {ADX_MIN})")
    last_candle_time = None
    retry_delay = 60

    while True:
        try:
            df = get_mtf_data()
            if df is None or len(df) < 50:
                raise ValueError("Puste lub niewystarczające dane rynkowe")

            retry_delay = 60
            row = df.iloc[-2]
            c_time = df.index[-2]

            if last_candle_time != c_time:
                sig = 0
                if (
                    (row["EMA_S"] > row["EMA_L"])
                    and (row["MACD_line"] > row["MACD_signal"])
                    and (row["Trend_H1"] == 1)
                    and (row["ADX_14"] > ADX_MIN)
                ):
                    sig = 1
                elif (
                    (row["EMA_S"] < row["EMA_L"])
                    and (row["MACD_line"] < row["MACD_signal"])
                    and (row["Trend_H1"] == -1)
                    and (row["ADX_14"] > ADX_MIN)
                ):
                    sig = -1

                if sig != 0:
                    side = "LONG 🟢" if sig == 1 else "SHORT 🔴"
                    entry = row["Close"]
                    atr = row["ATR"]
                    sl = entry - (atr * ATR_SL_MULT) if sig == 1 else entry + (atr * ATR_SL_MULT)
                    tp = entry + (atr * ATR_TP_MULT) if sig == 1 else entry - (atr * ATR_TP_MULT)

                    alert = (
                        f"*🚨 SYGNAŁ GOLD MTF-ATR-ADX*\n"
                        f"Kierunek: {side}\n"
                        f"Wejście: {entry:.2f}\n"
                        f"🎯 TP: {tp:.2f} | 🛡️ SL: {sl:.2f}\n"
                        f"📊 ADX: {row['ADX_14']:.2f} | Trend H1: {'Bull' if row['Trend_H1']==1 else 'Bear'}"
                    )
                    send_telegram(alert)
                    log_trade(side, entry, tp, sl, atr)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Sygnał {side} wysłany.")

                last_candle_time = c_time

            time.sleep(60)

        except KeyboardInterrupt:
            print("\nZatrzymano monitorowanie.")
            break
        except Exception as e:
            print(f"⚠️ Błąd: {e}. Ponowna próba za {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 600)


if __name__ == "__main__":
    run_production_monitor()
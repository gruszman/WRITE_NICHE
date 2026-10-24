import os
import sys
import time
from datetime import datetime
import numpy as np
import pandas as pd
import requests
import ta
import ccxt # Wymaga: pip install ccxt

# Konfiguracja jednoczesnego logowania do pliku i konsoli CLI
class TeeLogger:
    def __init__(self, filename):
        self.terminal = sys.__stdout__
        self.log_file = open(filename, "a", buffering=1, encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

# Zmienione nazwy plików logowania dla ETH
sys.stdout = TeeLogger("bot_eth_v6.txt")
sys.stderr = sys.stdout

# --- KONFIGURACJA KRYPTO ---
EXCHANGE_ID = "binance"
SYMBOL = "ETH/USDT"

TELEGRAM_TOKEN = "8488356348:AAHpjRHW4X-NPJV0C-BJVV21-30RoLctu1Q"
CHAT_ID = "738220792"

EMA_S = 5
EMA_L = 35
EMA_TREND_H1 = 50
ADX_MIN = 20
RSI_PERIOD = 14
ATR_SL_MULT = 1.5
ATR_TP_MULT = 3.5

# Ochrona przed wejściami z gigantycznym ryzykiem
# ETH jest bardziej zmienne niż BTC, więc próg odrzucenia został podniesiony do 3.5%
MAX_SL_PCT = 0.035 

# Interwał raportu w konsoli CLI (w sekundach: 30 min = 1800s)
STATUS_INTERVAL_SEC = 30 * 60

TRADE_START_HOUR = 0
TRADE_END_HOUR = 24

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
DATA_PATH = os.path.join(BASE_DIR, "CryptoStrategy")
os.makedirs(DATA_PATH, exist_ok=True)

# Inicjalizacja ccxt
exchange_class = getattr(ccxt, EXCHANGE_ID)
exchange = exchange_class({'enableRateLimit': True})

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print(f"Błąd wysyłania Telegram: {e}")

def log_trade(side, entry, tp, sl, atr):
    file_path = os.path.join(DATA_PATH, "production_log_eth.csv")
    log_data = pd.DataFrame([{
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Side": side,
        "Entry": round(entry, 2),
        "TP": round(tp, 2),
        "SL": round(sl, 2),
        "ATR": round(atr, 2),
    }])
    log_data.to_csv(file_path, mode="a", header=not os.path.exists(file_path), index=False)

def fetch_crypto_candles(timeframe, limit=200):
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df['Time'] = pd.to_datetime(df['Time'], unit='ms')
        df.set_index('Time', inplace=True)
        return df
    except Exception as e:
        print(f"Błąd pobierania danych z {EXCHANGE_ID.upper()}: {e}")
        return pd.DataFrame()

def get_mtf_data():
    m15 = fetch_crypto_candles('15m', limit=200)
    h1 = fetch_crypto_candles('1h', limit=200)
    
    if m15.empty or h1.empty:
        return None

    # Obliczenia H1
    h1_ema = ta.trend.EMAIndicator(h1["Close"], window=EMA_TREND_H1).ema_indicator()
    h1["Trend_H1"] = np.where(h1["Close"] > h1_ema, 1, -1)
    h1["Trend_H1"] = h1["Trend_H1"].shift(1)

    # Obliczenia M15
    m15["EMA_S"] = ta.trend.EMAIndicator(m15["Close"], window=EMA_S).ema_indicator()
    m15["EMA_L"] = ta.trend.EMAIndicator(m15["Close"], window=EMA_L).ema_indicator()
    m15["ATR"] = ta.volatility.AverageTrueRange(m15["High"], m15["Low"], m15["Close"], window=14).average_true_range()
    m15["RSI"] = ta.momentum.RSIIndicator(m15["Close"], window=RSI_PERIOD).rsi()

    # Wolumen SMA 20
    m15["Volume_SMA_20"] = m15["Volume"].rolling(window=20).mean()

    # ADX
    adx_indicator = ta.trend.ADXIndicator(m15["High"], m15["Low"], m15["Close"], window=14)
    m15["ADX_14"] = adx_indicator.adx()

    # MACD
    macd_indicator = ta.trend.MACD(m15["Close"], window_slow=26, window_fast=12, window_sign=9)
    m15["MACD_line"] = macd_indicator.macd()
    m15["MACD_signal"] = macd_indicator.macd_signal()

    df = pd.merge_asof(
        m15.sort_index(),
        h1[["Trend_H1"]].dropna().sort_index(),
        left_index=True,
        right_index=True,
        direction="backward",
    )
    return df

def is_trading_session():
    current_hour = datetime.now().hour
    return TRADE_START_HOUR <= current_hour < TRADE_END_HOUR

def sleep_until_next_minute():
    now = datetime.now()
    seconds_to_sleep = 60 - now.second - (now.microsecond / 1_000_000.0)
    time.sleep(seconds_to_sleep + 3)

def print_cli_status(df, current_position):
    current_price = df["Close"].iloc[-1]      
    closed_row = df.iloc[-2]                  
    closed_time = df.index[-2]

    # Ustalanie trendu M15 (EMA + MACD)
    m15_ema_bull = closed_row["EMA_S"] > closed_row["EMA_L"]
    m15_macd_bull = closed_row["MACD_line"] > closed_row["MACD_signal"]
    
    if m15_ema_bull and m15_macd_bull:
        trend_m15 = "🟢 WZROSTOWY (Bullish)"
    elif not m15_ema_bull and not m15_macd_bull:
        trend_m15 = "🔴 SPADKOWY (Bearish)"
    else:
        trend_m15 = "🟡 MIESZANY (Konsolidacja)"

    trend_h1 = "🟢 WZROSTOWY" if closed_row["Trend_H1"] == 1 else "🔴 SPADKOWY"
    vol_status = "✅ POWYŻEJ ŚREDNIEJ" if closed_row["Volume"] > closed_row["Volume_SMA_20"] else "❌ PONIŻEJ ŚREDNIEJ"
    pos_str = current_position if current_position else "BRAK POZYCJI ⚪"

    now_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    separator = "=" * 55

    print(f"\n{separator}")
    print(f"🕒 STATUS BOTA ETH (HEARTBEAT) — {now_local}")
    print(f"💰 Symbol: {SYMBOL} | Aktualna cena: ${current_price:.2f}")
    print(f"📈 Trend H1:  {trend_h1}")
    print(f"⏱️ Trend M15: {trend_m15}")
    print(f"📊 ADX (14):  {closed_row['ADX_14']:.2f} (Próg > {ADX_MIN})")
    print(f"📉 RSI (14):  {closed_row['RSI']:.2f} (Zgodne z trendem >50/<50)")
    print(f"🔊 Wolumen:   {vol_status}")
    print(f"🎯 Aktualna pozycja: {pos_str}")
    print(f"✅ Status: AKTYWNY (Ostatnia świeca: {closed_time.strftime('%H:%M')})")
    print(f"{separator}\n")

def run_production_monitor():
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🚀 Uruchomiono system KRYPTO MTF V6 na {EXCHANGE_ID.upper()} dla {SYMBOL}")
    last_candle_time = None
    last_status_time = 0 
    retry_delay = 60
    current_position = None  

    while True:
        try:
            sleep_until_next_minute()
            
            if not is_trading_session():
                continue

            df = get_mtf_data()
            if df is None or len(df) < 50:
                raise ValueError(f"Puste lub niewystarczające dane rynkowe z {EXCHANGE_ID.upper()}")

            current_timestamp = time.time()
            retry_delay = 60
            row = df.iloc[-2]  
            c_time = df.index[-2]

            # --- RAPORT STATUSU CO 30 MINUT ---
            if current_timestamp - last_status_time >= STATUS_INTERVAL_SEC:
                print_cli_status(df, current_position)
                last_status_time = current_timestamp

            if last_candle_time != c_time:
                sig = 0
                trend_str = "Bull 🟢" if row["Trend_H1"] == 1 else "Bear 🔴"
                
                raport = (
                    f"[{datetime.now().strftime('%H:%M:%S')}] 📊 M15 | "
                    f"Cena: {row['Close']:.2f} | "
                    f"RSI: {row['RSI']:.2f} | "
                    f"ADX: {row['ADX_14']:.2f} | "
                    f"Trend H1: {trend_str}"
                )

                if (
                    (row["EMA_S"] > row["EMA_L"])
                    and (row["MACD_line"] > row["MACD_signal"])
                    and (row["Trend_H1"] == 1)
                    and (row["ADX_14"] > ADX_MIN)
                    and (row["RSI"] > 50) 
                    and (row["Volume"] > row["Volume_SMA_20"])
                ):
                    sig = 1
                    
                elif (
                    (row["EMA_S"] < row["EMA_L"])
                    and (row["MACD_line"] < row["MACD_signal"])
                    and (row["Trend_H1"] == -1)
                    and (row["ADX_14"] > ADX_MIN)
                    and (row["RSI"] < 50) 
                    and (row["Volume"] > row["Volume_SMA_20"])
                ):
                    sig = -1

                if sig == 1 and current_position != 'LONG 🟢':
                    side = "LONG 🟢"
                elif sig == -1 and current_position != 'SHORT 🔴':
                    side = "SHORT 🔴"
                else:
                    sig = 0 

                if sig != 0:
                    entry = row["Close"]
                    atr = row["ATR"]
                    sl = entry - (atr * ATR_SL_MULT) if sig == 1 else entry + (atr * ATR_SL_MULT)
                    tp = entry + (atr * ATR_TP_MULT) if sig == 1 else entry - (atr * ATR_TP_MULT)

                    sl_distance_pct = abs(entry - sl) / entry
                    if sl_distance_pct > MAX_SL_PCT:
                        print(f"{raport} ➡️ Sygnał {side} ODRZUCONY: Za duże ryzyko (SL: {sl_distance_pct*100:.2f}% > {MAX_SL_PCT*100}%)")
                    else:
                        current_position = side
                        print(f"{raport} ➡️ WYGENEROWANO SYGNAŁ {side}")
                        
                        alert = (
                            f"*🚨 SYGNAŁ {EXCHANGE_ID.upper()} {SYMBOL} MTF V6*\n"
                            f"Kierunek: {side}\n"
                            f"Wejście: {entry:.2f}\n"
                            f"🎯 TP: {tp:.2f} | 🛡️ SL: {sl:.2f} (Zasięg SL: {sl_distance_pct*100:.2f}%)\n"
                            f"📊 ADX: {row['ADX_14']:.2f} | RSI: {row['RSI']:.2f} | Vol: Wzmocniony\n"
                            f"📈 Trend H1: {'Bull' if row['Trend_H1']==1 else 'Bear'}"
                        )
                        send_telegram(alert)
                        log_trade(side, entry, tp, sl, atr)
                else:
                    print(f"{raport} ➡️ Brak sygnału (Oczekuję na Vol & RSI).")

                last_candle_time = c_time

        except KeyboardInterrupt:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Zatrzymano monitorowanie giełdy {EXCHANGE_ID.upper()}.")
            break
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Błąd: {e}. Ponowna próba za {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 600)

if __name__ == "__main__":
    run_production_monitor()
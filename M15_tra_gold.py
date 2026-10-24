import time
import requests
import pandas as pd
import pandas_ta_classic as ta
import yfinance as yf
import sys
sys.stdout = open("bot_log.txt", "a", buffering=1)
sys.stderr = open("bot_log.txt", "a", buffering=1)


# --- KONFIGURACJA ---
SYMBOL = "GC=F"       # Złoto (Gold Futures) na Yahoo Finance
TIMEFRAME_M15 = "15m"
TIMEFRAME_H1 = "60m"
TARGET_PCT = 0.018    # 1.8%
SL_PCT = 0.010        # 1.0%
COOLDOWN_BARS = 10    # Min. 10 świec M15 odstępu

TELEGRAM_BOT_TOKEN = "8488356348:AAHpjRHW4X-NPJV0C-BJVV21-30RoLctu1Q"
TELEGRAM_CHAT_ID = "738220792"

def send_telegram_alert(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"[!] Błąd Telegram: {resp.text}")
    except Exception as e:
        print(f"[!] Błąd połączenia z Telegramem: {e}")

def fetch_gold_data(interval: str) -> pd.DataFrame:
    """Pobiera ostatnie świece złota przez yfinance."""
    ticker = yf.Ticker(SYMBOL)
    df = ticker.history(period="5d", interval=interval)
    
    if df.empty:
        return df

    # Zamiana indeksu DatetimeIndex bezpośrednio na kolumnę 'datetime'
    df = df.copy()
    df["datetime"] = pd.to_datetime(df.index)
    
    # Standaryzacja nazw kolumn cenowych na małe litery
    df.columns = [str(col).lower() for col in df.columns]
    
    # Usunięcie informacji o strefie czasowej, aby uniknąć błędów formatowania
    if df["datetime"].dt.tz is not None:
        df["datetime"] = df["datetime"].dt.tz_localize(None)

    df = df.reset_index(drop=True)
    return df

def calculate_bear_score(df: pd.DataFrame) -> pd.Series:
    """
    Punktacja spadkowa (0-5) z Twojego wskaźnika:
    1. RSI(14) < 48 i > 25
    2. MACD(12, 26, 9): mLine < sLine
    3. Bollinger Bands (20, 2): close < middle
    4. DMI / ADX (14, 14): diM > diP
    5. Stoch RSI (14, 14, 3, 3): %K < %D oraz %K > 40
    """
    # 1. RSI
    rsi = df.ta.rsi(length=14)
    b_rsi = ((rsi < 48) & (rsi > 25)).astype(int)

    # 2. MACD
    macd_df = df.ta.macd(fast=12, slow=26, signal=9)
    m_line = macd_df.iloc[:, 0]
    s_line = macd_df.iloc[:, 1]
    b_macd = (m_line < s_line).astype(int)

    # 3. Bollinger Bands
    bb_df = df.ta.bbands(length=20, std=2)
    bb_mid = bb_df.iloc[:, 1]
    b_bb = (df["close"] < bb_mid).astype(int)

    # 4. DMI / ADX
    dmi_df = df.ta.adx(length=14, lensig=14)
    dmp = dmi_df.iloc[:, 1]
    dmn = dmi_df.iloc[:, 2]
    b_adx = (dmn > dmp).astype(int)

    # 5. Stoch RSI
    stoch_df = df.ta.stochrsi(length=14, rsi_length=14, k=3, d=3)
    k = stoch_df.iloc[:, 0]
    d = stoch_df.iloc[:, 1]
    b_stoch = ((k < d) & (k > 40)).astype(int)

    return b_rsi + b_macd + b_bb + b_adx + b_stoch

def run_scanner():
    print(f"[*] Rozpoczynam nasłuch sygnałów dla ZŁOTA ({SYMBOL})...")
    bars_since_last_signal = COOLDOWN_BARS + 1
    last_processed_candle_time = None

    while True:
        try:
            df_m15 = fetch_gold_data(TIMEFRAME_M15)
            df_h1 = fetch_gold_data(TIMEFRAME_H1)

            if df_m15.empty or df_h1.empty or len(df_m15) < 35:
                time.sleep(15)
                continue

            # Bierzemy ostatnią zamkniętą świecę (-2), pomijając wciąż trwającą (-1)
            closed_candle_m15 = df_m15.iloc[-2]
            candle_time = closed_candle_m15["datetime"]

            if last_processed_candle_time != candle_time:
                last_processed_candle_time = candle_time
                bars_since_last_signal += 1

                # Punktacja na zamkniętych świecach
                score_m15 = calculate_bear_score(df_m15).iloc[-2]
                score_h1 = calculate_bear_score(df_h1).iloc[-2]

                close_price = closed_candle_m15["close"]
                time_str = candle_time.strftime("%Y-%m-%d %H:%M")

                print(f"[{time_str}] Złoto: ${close_price:.2f} | M15: {score_m15}/5 | H1: {score_h1}/5 | Cooldown: {bars_since_last_signal}")

                condition_m15 = score_m15 >= 4
                condition_h1 = score_h1 >= 3
                cooldown_ok = bars_since_last_signal > COOLDOWN_BARS

                if condition_m15 and condition_h1 and cooldown_ok:
                    target_price = close_price * (1.0 - TARGET_PCT)
                    sl_price = close_price * (1.0 + SL_PCT)

                    alert_msg = (
                        f"🚨 <b>SYGNAŁ SHORT DLA ZŁOTA (GC=F)</b> 🚨\n\n"
                        f"<b>Świeca:</b> {time_str}\n"
                        f"<b>Cena wejścia:</b> <code>${close_price:.2f}</code>\n"
                        f"🎯 <b>Target (-1.8%):</b> <code>${target_price:.2f}</code>\n"
                        f"🛑 <b>Stop Loss (+1.0%):</b> <code>${sl_price:.2f}</code>\n\n"
                        f"📊 <b>Score:</b> M15={score_m15}/5, H1={score_h1}/5"
                    )

                    print("[!] Sygnał SHORT dla złota wykryty! Wysyłam na Telegram...")
                    send_telegram_alert(alert_msg)
                    bars_since_last_signal = 0

            # Sprawdzaj co 20 sekund
            time.sleep(20)

        except Exception as e:
            print(f"[!] Błąd pobierania danych: {e}")
            time.sleep(15)

if __name__ == "__main__":
    run_scanner()
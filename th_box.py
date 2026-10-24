import os
import sys
import time
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

# ====== TU WKLEJ SWOJE DANE ======
TG_TOKEN_MANUAL ="8488356348:AAHpjRHW4X-NPJV0C-BJVV21-30RoLctu1Q" # np. "123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
TG_CHAT_ID_MANUAL ="738220792" # np. "123456789" (dla grupy: "-1001234567890")
# =================================

TG_TOKEN = TG_TOKEN_MANUAL.strip() or os.getenv("TG_TOKEN", "").strip()
TG_CHAT_ID = TG_CHAT_ID_MANUAL.strip() or os.getenv("TG_CHAT_ID", "").strip()

SYMBOL = "BTCUSDT"
INTERVAL = "15m"
INTERVAL_SEC = 15 * 60
CANDLES = 500

BOX_LEN = 20
USE_CLOSE_BREAK = True
RETEST_MIN_BARS = 1
RETEST_MAX_BARS = 20
RETEST_TOLERANCE_PCT = 0.15
CONFIRM_BY_CLOSE = False
RR = 2.0

KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
LOG_FILE = "the_box_bot.log"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
    force=True,
)
log = logging.getLogger("the_box_bot")

if not TG_TOKEN or not TG_CHAT_ID:
    print("UWAGA: brak TG_TOKEN lub TG_CHAT_ID - wiadomosci nie zostana wyslane na Telegram")


def num(x, d=2) -> str:
    return f"{x:,.{d}f}".replace(",", " ")


def pct(a, b) -> float:
    return (a / b - 1.0) * 100.0


def fmt_time(ts) -> str:
    return ts.tz_convert("Europe/Warsaw").strftime("%d.%m %H:%M")


def ago(bars: int) -> str:
    mins = bars * (INTERVAL_SEC // 60)
    if mins < 60:
        return f"{mins} min temu"
    h, m = divmod(mins, 60)
    return f"{h}h {m}min temu" if m else f"{h}h temu"


def send_telegram(text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT_ID:
        log.warning("Brak TG_TOKEN / TG_CHAT_ID - wiadomosc tylko w logu:
%s", text)
        return False
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=payload, timeout=15)
        r.raise_for_status()
        log.info("Telegram: wyslano wiadomosc")
        return True
    except Exception as e:
        log.error("Telegram: blad wysylki: %s", e)
        return False


def fetch_klines() -> pd.DataFrame:
    params = {"symbol": SYMBOL, "interval": INTERVAL, "limit": CANDLES}
    r = requests.get(KLINES_URL, params=params, timeout=20)
    r.raise_for_status()
    cols = ["open_time", "open", "high", "low", "close", "volume", "close_time",
            "qav", "trades", "tbb", "tbq", "ignore"]
    df = pd.DataFrame(r.json(), columns=cols)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("time")[["open", "high", "low", "close", "volume", "close_time"]]
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    df = df[df["close_time"] < now_ms]
    return df.drop(columns=["close_time"])


def the_box_signals(df: pd.DataFrame):
    data = df.copy().sort_index()
    data["prev_top"] = data["high"].rolling(BOX_LEN).max().shift(1)
    data["prev_bottom"] = data["low"].rolling(BOX_LEN).min().shift(1)

    if USE_CLOSE_BREAK:
        bull = (data["close"] > data["prev_top"]).values
        bear = (data["close"] < data["prev_bottom"]).values
    else:
        bull = (data["high"] > data["prev_top"]).values
        bear = (data["low"] < data["prev_bottom"]).values

    n = len(data)
    events = [""] * n
    signals = [""] * n
    sl_levels = [np.nan] * n
    zones = []

    highs = data["high"].values
    lows = data["low"].values
    closes = data["close"].values
    tops = data["prev_top"].values
    bottoms = data["prev_bottom"].values

    for i in range(n):
        if not np.isnan(tops[i]) and not np.isnan(bottoms[i]):
            if bull[i]:
                zones.append(dict(dir=1, top=float(tops[i]), bottom=float(bottoms[i]),
                                  start=i, retested=False, rh=np.nan, rl=np.nan, done=False))
                events[i] = "BULL_BREAK"
            elif bear[i]:
                zones.append(dict(dir=-1, top=float(tops[i]), bottom=float(bottoms[i]),
                                  start=i, retested=False, rh=np.nan, rl=np.nan, done=False))
                events[i] = "BEAR_BREAK"

        for z in zones:
            if z["done"]:
                continue
            age = i - z["start"]
            if age > RETEST_MAX_BARS:
                z["done"] = True
                continue
            if age < RETEST_MIN_BARS:
                continue

            if z["dir"] == 1:
                tol = z["top"] * RETEST_TOLERANCE_PCT / 100.0
                if not z["retested"]:
                    if lows[i] <= z["top"] + tol and closes[i] > z["top"]:
                        z["retested"] = True
                        z["rh"], z["rl"] = float(highs[i]), float(lows[i])
                        events[i] = "RETEST_LONG"
                else:
                    ok = closes[i] > z["rh"] if CONFIRM_BY_CLOSE else highs[i] > z["rh"]
                    if ok:
                        z["done"] = True
                        signals[i] = "BUY"
                        sl_levels[i] = z["rl"]
            else:
                tol = z["bottom"] * RETEST_TOLERANCE_PCT / 100.0
                if not z["retested"]:
                    if highs[i] >= z["bottom"] - tol and closes[i] < z["bottom"]:
                        z["retested"] = True
                        z["rh"], z["rl"] = float(highs[i]), float(lows[i])
                        events[i] = "RETEST_SHORT"
                else:
                    ok = closes[i] < z["rl"] if CONFIRM_BY_CLOSE else lows[i] < z["rl"]
                    if ok:
                        z["done"] = True
                        signals[i] = "SELL"
                        sl_levels[i] = z["rh"]

    data["event"] = events
    data["signal"] = signals
    data["sl"] = sl_levels
    return data, zones


def signal_levels(side: str, entry: float, sl: float):
    if np.isnan(sl):
        return None, None
    risk = abs(entry - sl)
    if risk <= 0:
        return None, None
    tp = entry + RR * risk if side == "BUY" else entry - RR * risk
    return sl, tp


def build_status(data: pd.DataFrame, zones: list) -> str:
    last_i = len(data) - 1
    last = data.iloc[-1]
    price = last["close"]

    box_top = data["high"].tail(BOX_LEN).max()
    box_bottom = data["low"].tail(BOX_LEN).min()
    rng = box_top - box_bottom
    pos = (price - box_bottom) / rng * 100 if rng > 0 else 50
    if pos >= 80:
        pos_txt = "blisko gory"
    elif pos <= 20:
        pos_txt = "blisko dolu"
    else:
        pos_txt = "srodek"

    lines = [
        f"📊 <b>THE BOX | {SYMBOL} {INTERVAL}</b>",
        f"🕒 {fmt_time(data.index[-1])} 💰 <b>{num(price)}</b>",
        "",
        f"📦 <b>BOX ({BOX_LEN} swiec)</b>",
        f"Gora: {num(box_top)} | Dol: {num(box_bottom)}",
        f"Pozycja w pudelku: {pos:.0f}% ({pos_txt})",
        "",
        "🎯 <b>AKTYWNA STREFA</b>",
    ]

    active = [z for z in zones if not z["done"]]
    if active:
        z = max(active, key=lambda x: x["start"])
        icon = "🟢" if z["dir"] == 1 else "🔴"
        side = "LONG" if z["dir"] == 1 else "SHORT"
        level = z["top"] if z["dir"] == 1 else z["bottom"]
        stage = "retest byl, czeka na potwierdzenie" if z["retested"] else "czeka na retest"
        left = max(0, RETEST_MAX_BARS - (last_i - z["start"]))
        mins = left * (INTERVAL_SEC // 60)
        lines += [
            f"{icon} <b>{side}</b> - {stage}",
            f"Poziom: {num(level)} (cena {pct(price, level):+.2f}%)",
            f"Wygasa za: {left} swiec ({mins // 60}h {mins % 60}min)",
        ]
    else:
        lines.append("Brak aktywnej strefy - czekam na wybicie")

    lines += ["", "📌 <b>OSTATNI SYGNAL</b>"]
    sig_df = data[data["signal"] != ""]
    if len(sig_df):
        s = sig_df.iloc[-1]
        s_i = data.index.get_loc(sig_df.index[-1])
        side = s["signal"]
        icon = "🟢" if side == "BUY" else "🔴"
        entry = s["close"]
        sl, tp = signal_levels(side, entry, s["sl"])
        move = pct(price, entry) if side == "BUY" else -pct(price, entry)
        lines += [
            f"{icon} <b>{side}</b> | {fmt_time(sig_df.index[-1])} ({ago(last_i - s_i)})",
            f"Wejscie: {num(entry)}",
        ]
        if sl is not None:
            lines.append(f"SL: {num(sl)} | TP: {num(tp)} (RR 1:{RR:g})")
        lines.append(f"Teraz: {move:+.2f}% od wejscia")
    else:
        lines.append("Brak sygnalu w zaladowanych danych")

    return "
".join(lines)


def build_alert(data: pd.DataFrame) -> str:
    r = data.iloc[-1]
    side = r["signal"]
    icon = "🟢" if side == "BUY" else "🔴"
    entry = r["close"]
    sl, tp = signal_levels(side, entry, r["sl"])
    txt = [
        f"🔔 {icon} <b>NOWY SYGNAL {side}</b> | {SYMBOL} {INTERVAL}",
        f"🕒 {fmt_time(data.index[-1])}",
        f"Wejscie: <b>{num(entry)}</b>",
    ]
    if sl is not None:
        txt.append(f"SL: {num(sl)} | TP: {num(tp)} (RR 1:{RR:g})")
    return "
".join(txt)


def seconds_to_next_candle(extra: int = 5) -> float:
    now = time.time()
    nxt = (int(now // INTERVAL_SEC) + 1) * INTERVAL_SEC
    return max(1.0, nxt - now + extra)


def run_once(last_alert_ts):
    df = fetch_klines()
    if len(df) < BOX_LEN + 5:
        raise RuntimeError(f"Za malo swiec: {len(df)}")

    data, zones = the_box_signals(df)
    log.info("Swiece=%s | ostatnia=%s | close=%.2f", len(data), data.index[-1], data["close"].iloc[-1])

    if data.iloc[-1]["signal"] in ("BUY", "SELL") and last_alert_ts != data.index[-1]:
        send_telegram(build_alert(data))
        last_alert_ts = data.index[-1]

    send_telegram(build_status(data, zones))
    data.to_csv("the_box_signals.csv")
    return last_alert_ts


def main():
    log.info("=== START BOTA THE BOX ===")
    send_telegram(f"✅ <b>Bot THE BOX wystartowal</b>: {SYMBOL} {INTERVAL}. Status co 15 minut.")
    last_alert_ts = None
    error_notified = False

    while True:
        try:
            last_alert_ts = run_once(last_alert_ts)
            error_notified = False
        except Exception as e:
            log.exception("Blad w petli glownej: %s", e)
            if not error_notified:
                send_telegram(f"⚠️ Blad bota: {e}")
                error_notified = True

        wait = seconds_to_next_candle()
        log.info("Nastepny cykl za %.0f s", wait)
        time.sleep(wait)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Zatrzymano recznie (Ctrl+C)")
    except Exception:
        log.exception("KRYTYCZNY BLAD")
        raise
    finally:
        logging.shutdown()
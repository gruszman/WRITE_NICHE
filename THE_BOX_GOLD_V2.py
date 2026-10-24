
import os
import sys
import time
import html
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

# ====== TU WKLEJ SWOJE DANE ======
TG_TOKEN_MANUAL ="8654630605:AAGBYsAYlFX01R-DS1vnjhOFDuTMVs0rmnE"      # np. "123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
TG_CHAT_ID_MANUAL ="738220792"    # np. "123456789"  (dla grupy: "-1001234567890")
# =================================

TG_TOKEN = TG_TOKEN_MANUAL.strip() or os.getenv("TG_TOKEN", "").strip()
TG_CHAT_ID = TG_CHAT_ID_MANUAL.strip() or os.getenv("TG_CHAT_ID", "").strip()

# ---- INSTRUMENT (dane z Binance; cena PAXG ~ cena zlota) ----
MARKET = "spot"            # "spot" (PAXGUSDT) albo "futures" (XAUUSDT)
SYMBOL = "PAXGUSDT"
LABEL = "ZLOTO"
INTERVAL = "1h"
INTERVAL_SEC = 60 * 60
CANDLES = 500
NDEC = 2

# ---- STRATEGIA (ustawienia z optymalizacji: zloto 1h) ----
BOX_LEN = 15
USE_CLOSE_BREAK = True
RETEST_MIN_BARS = 1
RETEST_MAX_BARS = 20
RETEST_TOLERANCE_PCT = 0.15
CONFIRM_BY_CLOSE = True
RR = 3.0

# ---- FILTRY ----
ATR_LEN = 14
MIN_RISK_ATR = 1.5         # min. odleglosc SL w wielokrotnosciach ATR (0 = wylaczony)
MIN_RISK_PCT = 0.0         # min. odleglosc SL w % ceny (0 = wylaczony)
EMA_LEN = 0                # filtr trendu: 200 = tylko z trendem EMA200, 0 = wylaczony

# ---- POWIADOMIENIA ----
STATUS_EVERY_N = 1         # status co N cykli (1 = co swiece 1h); 0 = tylko alerty

URLS = {
    "spot": "https://data-api.binance.vision/api/v3/klines",
    "futures": "https://fapi.binance.com/fapi/v1/klines",
}
KLINES_URL = URLS[MARKET]
LOG_FILE = "gold_box_bot_1h.log"
CSV_FILE = "gold_box_signals_1h.csv"

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
log = logging.getLogger("gold_box_bot")

if not TG_TOKEN or not TG_CHAT_ID:
    print("UWAGA: brak TG_TOKEN lub TG_CHAT_ID - wiadomosci nie zostana wyslane na Telegram")


def num(x, d=None) -> str:
    d = NDEC if d is None else d
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
        log.warning("Brak TG_TOKEN / TG_CHAT_ID - wiadomosc tylko w logu:\n%s", text)
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
    last_err = None
    for attempt in range(3):
        try:
            r = requests.get(KLINES_URL, params=params, timeout=20)
            r.raise_for_status()
            break
        except Exception as e:
            last_err = e
            log.warning("Binance: proba %s nieudana: %s", attempt + 1, e)
            time.sleep(2)
    else:
        raise RuntimeError(f"Binance niedostepny: {last_err}")

    cols = ["open_time", "open", "high", "low", "close", "volume", "close_time",
            "qav", "trades", "tbb", "tbq", "ignore"]
    df = pd.DataFrame(r.json(), columns=cols)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("time")[["open", "high", "low", "close", "volume", "close_time"]]
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    df = df[df["close_time"] < now_ms]          # tylko zamkniete swiece
    return df.drop(columns=["close_time"])


def add_indicators(data: pd.DataFrame) -> pd.DataFrame:
    pc = data["close"].shift(1)
    tr = pd.concat([data["high"] - data["low"],
                    (data["high"] - pc).abs(),
                    (data["low"] - pc).abs()], axis=1).max(axis=1)
    data["atr"] = tr.rolling(ATR_LEN).mean()
    data["ema"] = data["close"].ewm(span=EMA_LEN, adjust=False).mean() if EMA_LEN else np.nan
    return data


def signal_passes_filters(side: str, entry: float, sl: float, atr: float, ema: float):
    """Zwraca (True/False, powod odrzucenia)."""
    risk = abs(entry - sl)
    if risk <= 0:
        return False, "ryzyko=0"
    if (side == "BUY" and sl >= entry) or (side == "SELL" and sl <= entry):
        return False, "SL po zlej stronie"
    if MIN_RISK_ATR > 0:
        if np.isnan(atr) or risk < MIN_RISK_ATR * atr:
            return False, f"SL za blisko ({risk:.2f} < {MIN_RISK_ATR:g} ATR)"
    if MIN_RISK_PCT > 0 and risk / entry * 100 < MIN_RISK_PCT:
        return False, f"SL za blisko ({risk / entry * 100:.2f}% < {MIN_RISK_PCT:g}%)"
    if EMA_LEN:
        if np.isnan(ema):
            return False, "brak EMA"
        if side == "BUY" and entry <= ema:
            return False, f"BUY pod EMA{EMA_LEN}"
        if side == "SELL" and entry >= ema:
            return False, f"SELL nad EMA{EMA_LEN}"
    return True, ""


def the_box_signals(df: pd.DataFrame):
    data = add_indicators(df.copy().sort_index())
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
    rejected = [""] * n
    zones = []

    highs = data["high"].values
    lows = data["low"].values
    closes = data["close"].values
    tops = data["prev_top"].values
    bottoms = data["prev_bottom"].values
    atrs = data["atr"].values
    emas = data["ema"].values

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
                        passed, why = signal_passes_filters("BUY", closes[i], z["rl"], atrs[i], emas[i])
                        if passed:
                            signals[i] = "BUY"
                            sl_levels[i] = z["rl"]
                        else:
                            rejected[i] = "BUY odrzucony: " + why
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
                        passed, why = signal_passes_filters("SELL", closes[i], z["rh"], atrs[i], emas[i])
                        if passed:
                            signals[i] = "SELL"
                            sl_levels[i] = z["rh"]
                        else:
                            rejected[i] = "SELL odrzucony: " + why

    data["event"] = events
    data["signal"] = signals
    data["sl"] = sl_levels
    data["rejected"] = rejected
    return data, zones


def signal_levels(side: str, entry: float, sl: float):
    if np.isnan(sl):
        return None, None
    risk = abs(entry - sl)
    if risk <= 0:
        return None, None
    tp = entry + RR * risk if side == "BUY" else entry - RR * risk
    return sl, tp


def filters_txt() -> str:
    parts = []
    if MIN_RISK_ATR > 0:
        parts.append(f"SL>={MIN_RISK_ATR:g} ATR")
    if MIN_RISK_PCT > 0:
        parts.append(f"SL>={MIN_RISK_PCT:g}%")
    if EMA_LEN:
        parts.append(f"EMA{EMA_LEN}")
    return ", ".join(parts) if parts else "brak"


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
        f"🥇 <b>THE BOX | {LABEL} ({SYMBOL}) {INTERVAL}</b>",
        f"🕒 {fmt_time(data.index[-1])}   💰 <b>{num(price)}</b>",
        f"ATR({ATR_LEN}): {num(last['atr']) if not np.isnan(last['atr']) else '-'} | Filtry: {filters_txt()}",
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

    rej_df = data[data["rejected"] != ""]
    if len(rej_df):
        r_i = data.index.get_loc(rej_df.index[-1])
        lines += ["", f"🚫 Ostatnio odrzucony: {rej_df.iloc[-1]['rejected']} ({ago(last_i - r_i)})"]

    return "\n".join(lines)


def build_alert(data: pd.DataFrame) -> str:
    r = data.iloc[-1]
    side = r["signal"]
    icon = "🟢" if side == "BUY" else "🔴"
    entry = r["close"]
    sl, tp = signal_levels(side, entry, r["sl"])
    txt = [
        f"🔔 {icon} <b>NOWY SYGNAL {side}</b> | {LABEL} ({SYMBOL}) {INTERVAL}",
        f"🕒 {fmt_time(data.index[-1])}",
        f"Wejscie: <b>{num(entry)}</b>",
    ]
    if sl is not None:
        risk_pct = abs(entry - sl) / entry * 100
        txt.append(f"SL: {num(sl)} | TP: {num(tp)} (RR 1:{RR:g})")
        txt.append(f"Ryzyko: {risk_pct:.2f}% ceny (SL {abs(entry - sl) / r['atr']:.1f} ATR)"
                   if not np.isnan(r["atr"]) else f"Ryzyko: {risk_pct:.2f}% ceny")
    return "\n".join(txt)


def seconds_to_next_candle(extra: int = 5) -> float:
    now = time.time()
    nxt = (int(now // INTERVAL_SEC) + 1) * INTERVAL_SEC
    return max(1.0, nxt - now + extra)


def run_once(last_alert_ts, last_reject_ts, cycle: int):
    df = fetch_klines()
    if len(df) < max(BOX_LEN, ATR_LEN, EMA_LEN) + 5:
        raise RuntimeError(f"Za malo swiec: {len(df)}")

    data, zones = the_box_signals(df)
    log.info("Swiece=%s | ostatnia=%s | close=%.2f", len(data), data.index[-1], data["close"].iloc[-1])

    last = data.iloc[-1]
    if last["signal"] in ("BUY", "SELL") and last_alert_ts != data.index[-1]:
        send_telegram(build_alert(data))
        last_alert_ts = data.index[-1]
    elif last["rejected"] and last_reject_ts != data.index[-1]:
        log.info("Sygnal odrzucony przez filtr: %s", last["rejected"])
        send_telegram(f"🚫 {LABEL} {INTERVAL}: {html.escape(last['rejected'])}")
        last_reject_ts = data.index[-1]

    if STATUS_EVERY_N and cycle % STATUS_EVERY_N == 0:
        send_telegram(build_status(data, zones))

    data.to_csv(CSV_FILE)
    return last_alert_ts, last_reject_ts


def main():
    log.info("=== START BOTA THE BOX (ZLOTO %s) ===", INTERVAL)
    status_txt = f"status co {STATUS_EVERY_N * INTERVAL_SEC // 3600}h" if STATUS_EVERY_N else "tylko alerty"
    send_telegram(
        f"✅ <b>Bot THE BOX wystartowal</b>: {LABEL} {SYMBOL} {INTERVAL} ({MARKET})\n"
        f"Box {BOX_LEN}, RR 1:{RR:g}, filtry: {filters_txt()}, {status_txt}."
    )
    last_alert_ts = None
    last_reject_ts = None
    error_notified = False
    cycle = 0

    while True:
        try:
            last_alert_ts, last_reject_ts = run_once(last_alert_ts, last_reject_ts, cycle)
            error_notified = False
        except Exception as e:
            log.exception("Blad w petli glownej: %s", e)
            if not error_notified:
                send_telegram(f"⚠️ Blad bota: {html.escape(str(e))}")
                error_notified = True
        cycle += 1

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

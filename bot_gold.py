import pandas_ta as ta
import pandas as pd
import numpy as np
import yfinance as yf

def apply_advanced_filters(df):
    # 1. Obliczanie podstawowych wskaźników
    df['EMA_S'] = ta.ema(df['Close'], length=5)
    df['EMA_L'] = ta.ema(df['Close'], length=35)
    macd = ta.macd(df['Close'])
    df = pd.concat([df, macd], axis=1)
    df['RSI'] = ta.rsi(df['Close'], length=14)

    # 2. Obliczanie ATR dla dynamicznego SL
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

    # 3. Obliczanie ADX i łączenie z DF
    adx_df = ta.adx(df['High'], df['Low'], df['Close'], length=14)
    df = pd.concat([df, adx_df], axis=1)

    # 4. Filtr Godzinowy (Płynność: 08:00 - 22:00 UTC)
    df['Hour'] = df.index.hour
    liquidity_filter = (df['Hour'] >= 8) & (df['Hour'] <= 22)

    # 5. Zaostrzona logika wejścia: Trend + MACD + RSI + ADX + ATR + Godziny
    df['Signal_Pro'] = 0

    # Warunek: Siła trendu (ADX > 25), Zmienność (ATR > 80% średniej) i Godziny handlu
    entry_filter = (df['ADX_14'] > 25) & (df['ATR'] > df['ATR'].rolling(20).mean() * 0.8) & liquidity_filter

    # Logika sygnałów Pro
    df.loc[(df['EMA_S'] > df['EMA_L']) & (df['MACD_12_26_9'] > df['MACDs_12_26_9']) & (df['RSI'] < 70) & entry_filter, 'Signal_Pro'] = 1
    df.loc[(df['EMA_S'] < df['EMA_L']) & (df['MACD_12_26_9'] < df['MACDs_12_26_9']) & (df['RSI'] > 30) & entry_filter, 'Signal_Pro'] = -1

    return df

# Pobranie danych
df_m15 = yf.Ticker("GC=F").history(period="60d", interval="15m")

# Aplikacja ulepszeń z filtrem godzinowym
df_m15 = apply_advanced_filters(df_m15)

print("✅ Zaktualizowano strategię o filtr godzinowy (08:00 - 22:00) oraz wskaźniki ADX/ATR.")
print(df_m15[['Close', 'ADX_14', 'Hour', 'Signal_Pro']].tail(10))
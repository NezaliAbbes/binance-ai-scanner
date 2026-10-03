import requests
import pandas as pd
import numpy as np
import os
import json
import time

BASE = "https://data-api.binance.vision"

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HISTORY_FILE = "signals.json"

# ============================================================
# SETTINGS
# ============================================================

INTERVAL = "15m"
KLINE_LIMIT = 150

MIN_SCORE = 75
COOLDOWN = 21600       # 6 hours

MIN_VOLUME_RATIO = 1.30
MIN_ADX = 18

print("=" * 65)
print("BINANCE AI SCANNER PRO 5.0")
print("STRONG SIGNAL MODE")
print("=" * 65)

# ============================================================
# HISTORY
# ============================================================

if os.path.exists(HISTORY_FILE):

    try:
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)

    except Exception:
        history = {}

else:
    history = {}

# ============================================================
# BINANCE SPOT PAIRS
# ============================================================

try:

    response = requests.get(
        f"{BASE}/api/v3/exchangeInfo",
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    pairs = [
        s["symbol"]
        for s in data["symbols"]
        if s["quoteAsset"] == "USDT"
        and s["status"] == "TRADING"
        and s.get("isSpotTradingAllowed", False)
    ]

except Exception as e:

    print("ExchangeInfo Error:", e)
    raise SystemExit

print(f"USDT Spot pairs: {len(pairs)}")

# ============================================================
# INDICATORS
# ============================================================

def rsi_calc(close, period=14):

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    return 100 - (100 / (1 + rs))


def atr_calc(high, low, close, period=14):

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    return tr.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()


def macd_calc(close):

    ema12 = close.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False
    ).mean()

    macd = ema12 - ema26

    signal = macd.ewm(
        span=9,
        adjust=False
    ).mean()

    histogram = macd - signal

    return macd, signal, histogram


def adx_calc(high, low, close, period=14):

    up = high.diff()
    down = -low.diff()

    plus_dm = pd.Series(
        np.where(
            (up > down) & (up > 0),
            up,
            0
        ),
        index=high.index
    )

    minus_dm = pd.Series(
        np.where(
            (down > up) & (down > 0),
            down,
            0
        ),
        index=high.index
    )

    atr = atr_calc(
        high,
        low,
        close,
        period
    )

    plus_di = (
        100
        * plus_dm.ewm(
            alpha=1 / period,
            adjust=False
        ).mean()
        / atr
    )

    minus_di = (
        100
        * minus_dm.ewm(
            alpha=1 / period,
            adjust=False
        ).mean()
        / atr
    )

    denominator = (
        plus_di + minus_di
    ).replace(0, np.nan)

    dx = (
        100
        * (plus_di - minus_di).abs()
        / denominator
    )

    return dx.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()


# ============================================================
# SCANNER
# ============================================================

candidates = []

scanned = 0
technical_candidates = 0

for i, symbol in enumerate(pairs, 1):

    try:

        response = requests.get(
            f"{BASE}/api/v3/klines",
            params={
                "symbol": symbol,
                "interval": INTERVAL,
                "limit": KLINE_LIMIT
            },
            timeout=8
        )

        if response.status_code != 200:
            continue

        kl = response.json()

        if not isinstance(kl, list):
            continue

        if len(kl) < 100:
            continue

        df = pd.DataFrame

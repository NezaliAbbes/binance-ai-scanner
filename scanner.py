import os
import time
import requests
from datetime import datetime

# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BASE = "https://data-api.binance.vision"

INTERVAL = "5m"
CONFIRM_INTERVAL = "15m"
LIMIT = 150

MIN_SCORE = 85
MAX_SIGNALS = 2
COOLDOWN = 3600

# =========================================================
# HELPERS
# =========================================================

def get_json(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def ema(values, period):
    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)
    result = sum(values[:period]) / period

    for price in values[period:]:
        result = (price - result) * multiplier + result

    return result


def rsi(values, period=14):
    if len(values) <= period:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]

        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    current_rsi = 100 - (100 / (1 + rs))

    for i in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        current_rsi = 100 - (100 / (1 + rs))

    return current_rsi


def get_klines(symbol, interval, limit=150):
    data = get_json(
        f"{BASE}/api/v3/klines",
        {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
    )

    if not data or len(data) < 60:
        return None

    return data


def get_spot_symbols():
    data = get_json(f"{BASE}/api/v3/exchangeInfo")

    if not data:
        return []

    symbols = []

    for item in data.get("symbols", []):
        if (
            item.get("status") == "TRADING"
            and item.get("quoteAsset") == "USDT"
            and item.get("isSpotTradingAllowed") is True
        ):
            symbols.append(item["symbol"])

    return symbols


# =========================================================
# DIAGNOSTIC STATS
# =========================================================

stats = {
    "data": 0,
    "trend": 0,
    "rsi": 0,
    "volume": 0,
    "momentum": 0,
    "breakout": 0,
    "passed": 0
}


# =========================================================
# BTC MARKET
# =========================================================

def btc_market():

    klines = get_klines("BTCUSDT", "15m", 100)

    if not klines:
        return "UNKNOWN"

    closes = [float(x[4]) for x in klines]

    e20 = ema(closes, 20)
    e50 = ema(closes, 50)

    if not e20 or not e50:
        return "UNKNOWN"

    if closes[-1] > e20 > e50:
        return "BULLISH"

    if closes[-1] < e20 < e50:
        return "WEAK"

    return "NEUTRAL"


# =========================================================
# ANALYZE SYMBOL
# =========================================================

def analyze(symbol):

    global stats

    data = get_klines(symbol, INTERVAL, LIMIT)

    if not data:
        stats["data"] += 1
        return None

    closes = [float(x[4]) for x in data]
    highs = [float(x[2]) for x in data]
    volumes = [float(x[5]) for x in data]

    price = closes[-1]

    # -----------------------------------------------------
    # 1. TREND
    # -----------------------------------------------------

    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    e100 = ema(closes, 100)

    if not e20 or not e50 or not e100:
        stats["data"] += 1
        return None

    if not (price > e20 > e50):
        stats["trend"] += 1
        return None

    # -----------------------------------------------------
    # 2. RSI
    # -----------------------------------------------------

    r = rsi(closes)

    if r is None or not (50 <= r <= 65):
        stats["rsi"] += 1
        return None

    # -----------------------------------------------------
    # 3. VOLUME
    # -----------------------------------------------------

    recent_volume = sum(volumes[-5:]) / 5
    previous_volume = sum(volumes[-25:-5]) / 20

    if previous_volume == 0:
        stats["data"] += 1
        return None

    volume_ratio = recent_volume / previous_volume

    if volume_ratio < 1.5:
        stats["volume"] += 1
        return None

    # -----------------------------------------------------
    # 4. MOMENTUM
    # -----------------------------------------------------

    old_price = closes[-6]

    if old_price == 0:
        stats["data"] += 1
        return None

    momentum = ((price - old_price) / old_price) * 100

    if not (0.5 <= momentum <= 4):
        stats["momentum"] += 1
        return None

    # -----------------------------------------------------
    # 5. BREAKOUT
    # -----------------------------------------------------

    previous_high = max(highs[-21:-1])

    breakout = ((price - previous_high) / previous_high) * 100

    if breakout < -0.10:
        stats["breakout"] += 1
        return None

    if breakout > 1.5:
        stats["breakout"] += 1
        return None

    # -----------------------------------------------------
    # PASSED
    # -----------------------------------------------------

    stats["passed"] += 1

    score = 0

    score += 15
    score += 15

    if price > e100:
        score += 10

    if 50 <= r <= 65:
        score += 10

    if volume_ratio >= 2:
        score += 15
    else:
        score += 8

    if breakout >= 0.20:
        score += 10
    else:
        score += 5

    if 0.5 <= momentum <= 4:
        score += 10

    # -----------------------------------------------------
    # 15m CONFIRMATION
    # -----------------------------------------------------

    data15 = get_klines(symbol, CONFIRM_INTERVAL, 100)

    if not data15:
        return None

    closes15 = [float(x[4]) for x in data15]

    e20_15 = ema(closes15, 20)
    e50_15 = ema(closes15, 50)

    if not e20_15 or not e50_15:
        return None

    if not (closes15[-1] > e20_15 > e50_15):
        return None

    score += 15

    # -----------------------------------------------------
    # RESULT
    # -----------------------------------------------------

    if score < MIN_SCORE:
        return None

    return {
        "symbol": symbol,
        "price": price,
        "score": score,
        "rsi": r,
        "volume": volume_ratio,
        "momentum": momentum,
        "breakout": breakout
    }


# =========================================================
# MAIN
# =========================================================

print("=" * 50)
print("BINANCE AI SCANNER")
print("DIAGNOSTIC MODE")
print("=" * 50)

btc_state = btc_market()

print(f"BTC Market: {btc_state}")

symbols = get_spot_symbols()

print(f"USDT Spot pairs: {len(symbols)}")
print()

signals = []

for i, symbol in enumerate(symbols, 1):

    try:

        result = analyze(symbol)

        if result:
            signals.append(result)

        if i % 50 == 0:
            print(f"Scanned: {i}/{len(symbols)}")

    except Exception:
        stats["data"] += 1

# =========================================================
# DIAGNOSTIC REPORT
# =========================================================

print()
print("=" * 50)
print("DIAGNOSTIC REPORT")
print("=" * 50)

print(f"Data errors       : {stats['data']}")
print(f"Rejected - Trend  : {stats['trend']}")
print(f"Rejected - RSI    : {stats['rsi']}")
print(f"Rejected - Volume : {stats['volume']}")
print(f"Rejected - Mom.   : {stats['momentum']}")
print(f"Rejected - Break. : {stats['breakout']}")
print(f"Passed first scan : {stats['passed']}")
print(f"Qualified signals : {len(signals)}")

print("=" * 50)

if signals:

    signals.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    print()
    print("TOP CANDIDATES")
    print()

    for s in signals[:MAX_SIGNALS]:

        print(
            f"{s['symbol']} | "
            f"Score {s['score']} | "
            f"RSI {s['rsi']:.1f} | "
            f"Vol x{s['volume']:.2f} | "
            f"Momentum {s['momentum']:+.2f}% | "
            f"Breakout {s['breakout']:+.2f}%"
        )

else:

    print()
    print("NO QUALIFIED SIGNALS")
    print("The diagnostic report above shows the bottleneck.")

print()
print("SCAN COMPLETED")

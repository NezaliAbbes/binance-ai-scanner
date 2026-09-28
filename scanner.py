import os
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BASE = "https://data-api.binance.vision"

LIMIT = 120
MIN_SCORE = 85
MAX_SIGNALS = 2


def get_json(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except:
        return None


def ema(values, period):
    if len(values) < period:
        return None

    k = 2 / (period + 1)
    e = sum(values[:period]) / period

    for price in values[period:]:
        e = price * k + e * (1 - k)

    return e


def rsi(values, period=14):
    if len(values) <= period:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]

        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def klines(symbol, interval):
    return get_json(
        f"{BASE}/api/v3/klines",
        {
            "symbol": symbol,
            "interval": interval,
            "limit": LIMIT
        }
    )


def symbols():
    data = get_json(f"{BASE}/api/v3/exchangeInfo")

    if not data:
        return []

    return [
        x["symbol"]
        for x in data["symbols"]
        if x.get("status") == "TRADING"
        and x.get("quoteAsset") == "USDT"
        and x.get("isSpotTradingAllowed") is True
    ]


def analyze(symbol):

    data = klines(symbol, "5m")

    if not data or len(data) < 100:
        return None

    close = [float(x[4]) for x in data]
    high = [float(x[2]) for x in data]
    volume = [float(x[5]) for x in data]

    price = close[-1]

    ema20 = ema(close, 20)
    ema50 = ema(close, 50)
    ema100 = ema(close, 100)

    if not ema20 or not ema50:
        return None

    # =====================================================
    # 1 — FIRST TREND FILTER
    # =====================================================

    # Modified:
    # price only needs to be above EMA50
    if price <= ema50:
        return None

    score = 0
    reasons = []

    score += 10
    reasons.append("Price above EMA50")

    # Stronger trend
    if price > ema20 > ema50:
        score += 15
        reasons.append("Strong 5m trend")

    if ema100 and price > ema100:
        score += 10
        reasons.append("Price above EMA100")

    # =====================================================
    # 2 — RSI
    # =====================================================

    r = rsi(close)

    if r is None:
        return None

    if 50 <= r <= 60:
        score += 15
        reasons.append(f"Perfect RSI {r:.1f}")

    elif 60 < r <= 65:
        score += 10
        reasons.append(f"High RSI {r:.1f}")

    else:
        return None

    # =====================================================
    # 3 — VOLUME
    # =====================================================

    recent_volume = sum(volume[-5:]) / 5
    previous_volume = sum(volume[-25:-5]) / 20

    if previous_volume == 0:
        return None

    volume_ratio = recent_volume / previous_volume

    if volume_ratio < 1.5:
        return None

    if volume_ratio >= 2:
        score += 15
        reasons.append(f"Strong volume x{volume_ratio:.2f}")

    else:
        score += 8
        reasons.append(f"Good volume x{volume_ratio:.2f}")

    # =====================================================
    # 4 — MOMENTUM
    # =====================================================

    momentum = ((price - close[-6]) / close[-6]) * 100

    if not 0.5 <= momentum <= 4:
        return None

    score += 10
    reasons.append(f"Momentum +{momentum:.2f}%")

    # Reject very fast movement
    if momentum > 3.5:
        score -= 5

    # =====================================================
    # 5 — BREAKOUT
    # =====================================================

    previous_high = max(high[-21:-1])

    breakout = ((price - previous_high) / previous_high) * 100

    if breakout > 1.5:
        return None

    if breakout >= 0.20:
        score += 10
        reasons.append(f"Confirmed breakout +{breakout:.2f}%")

    elif breakout >= -0.10:
        score += 5
        reasons.append(f"Near breakout {breakout:.2f}%")

    else:
        return None

    # =====================================================
    # 6 — 15m CONFIRMATION
    # =====================================================

    data15 = klines(symbol, "15m")

    if not data15 or len(data15) < 60:
        return None

    close15 = [float(x[4]) for x in data15]

    ema20_15 = ema(close15, 20)
    ema50_15 = ema(close15, 50)

    if not ema20_15 or not ema50_15:
        return None

    if not (close15[-1] > ema20_15 > ema50_15):
        return None

    score += 15
    reasons.append("15m trend confirmed")

    # =====================================================
    # FINAL SCORE
    # =====================================================

    if score < MIN_SCORE:
        return None

    return {
        "symbol": symbol,
        "price": price,
        "score": score,
        "rsi": r,
        "volume": volume_ratio,
        "momentum": momentum,
        "breakout": breakout,
        "reasons": reasons
    }


# =========================================================
# MAIN
# =========================================================

print("=" * 50)
print("BINANCE AI SCANNER")
print("FAST PRECISION MODE")
print("=" * 50)

all_symbols = symbols()

print(f"USDT Spot pairs: {len(all_symbols)}")

signals = []

for i, symbol in enumerate(all_symbols, 1):

    result = analyze(symbol)

    if result:
        signals.append(result)

    if i % 100 == 0:
        print(f"Scanned: {i}/{len(all_symbols)}")


signals.sort(
    key=lambda x: x["score"],
    reverse=True
)

signals = signals[:MAX_SIGNALS]

print()
print("=" * 50)
print(f"QUALIFIED SIGNALS: {len(signals)}")
print("=" * 50)

for s in signals:

    print()
    print(f"🟢 {s['symbol']}")
    print(f"Score: {s['score']}/100")
    print(f"Price: {s['price']}")
    print(f"RSI: {s['rsi']:.1f}")
    print(f"Volume: x{s['volume']:.2f}")
    print(f"Momentum: +{s['momentum']:.2f}%")
    print(f"Breakout: {s['breakout']:+.2f}%")

    for reason in s["reasons"]:
        print(f"✅ {reason}")

print()
print("SCAN COMPLETED")

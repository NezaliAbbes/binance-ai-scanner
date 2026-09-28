import os
import time
import json
import requests

from chart import save_chart


# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BASE = "https://data-api.binance.vision"

INTERVAL = "5m"
CONFIRM_INTERVAL = "15m"
TREND_INTERVAL = "1h"

LIMIT = 150

MIN_SCORE = 85
MAX_SIGNALS = 2

COOLDOWN = 3600

SIGNALS_FILE = "signals.json"


# =========================================================
# TELEGRAM
# =========================================================

def send_photo(photo_path, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    try:
        with open(photo_path, "rb") as photo:
            r = requests.post(
                url,
                data={
                    "chat_id": CHAT_ID,
                    "caption": caption
                },
                files={
                    "photo": photo
                },
                timeout=30
            )

        print("Telegram:", r.status_code)

    except Exception as e:
        print("Telegram error:", e)


def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": text
            },
            timeout=20
        )

    except Exception as e:
        print("Telegram message error:", e)


# =========================================================
# BINANCE
# =========================================================

def get_json(path, params=None):

    try:
        r = requests.get(
            BASE + path,
            params=params,
            timeout=15
        )

        if r.status_code != 200:
            return None

        return r.json()

    except Exception:
        return None


# =========================================================
# MEMORY
# =========================================================

def load_signals():

    if not os.path.exists(SIGNALS_FILE):
        return {}

    try:
        with open(SIGNALS_FILE, "r") as f:
            return json.load(f)

    except Exception:
        return {}


def save_signals(data):

    with open(SIGNALS_FILE, "w") as f:
        json.dump(data, f, indent=2)


# =========================================================
# EMA
# =========================================================

def ema(values, period):

    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)

    result = values[0]

    for price in values[1:]:
        result = (
            (price - result)
            * multiplier
            + result
        )

    return result


# =========================================================
# RSI
# =========================================================

def rsi(values, period=14):

    if len(values) < period + 1:
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

    for i in range(period, len(gains)):

        avg_gain = (
            avg_gain * (period - 1)
            + gains[i]
        ) / period

        avg_loss = (
            avg_loss * (period - 1)
            + losses[i]
        ) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


# =========================================================
# ATR
# =========================================================

def atr(highs, lows, closes, period=14):

    if len(closes) < period + 1:
        return None

    trs = []

    for i in range(1, len(closes)):

        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )

        trs.append(tr)

    return sum(trs[-period:]) / period


# =========================================================
# KLINES
# =========================================================

def get_klines(symbol, interval, limit=150):

    data = get_json(
        "/api/v3/klines",
        {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
    )

    if not data:
        return None

    try:

        return {
            "opens": [float(x[1]) for x in data],
            "highs": [float(x[2]) for x in data],
            "lows": [float(x[3]) for x in data],
            "closes": [float(x[4]) for x in data],
            "volumes": [float(x[5]) for x in data]
        }

    except Exception:
        return None


# =========================================================
# TREND
# =========================================================

def bullish_trend(data):

    if not data:
        return False

    closes = data["closes"]

    e20 = ema(closes, 20)
    e50 = ema(closes, 50)

    if e20 is None or e50 is None:
        return False

    return closes[-1] > e20 > e50


# =========================================================
# BTC CONDITION
# =========================================================

def btc_condition():

    data = get_klines(
        "BTCUSDT",
        "15m",
        100
    )

    if not data:
        return "UNKNOWN"

    closes = data["closes"]

    e20 = ema(closes, 20)
    e50 = ema(closes, 50)

    if e20 is None or e50 is None:
        return "UNKNOWN"

    price = closes[-1]

    # Strong bullish
    if price > e20 > e50:
        return "BULLISH"

    # Neutral
    if price > e50:
        return "NEUTRAL"

    # Bearish
    return "WEAK"


# =========================================================
# ORDER BOOK
# =========================================================

def order_book_analysis(symbol):

    data = get_json(
        "/api/v3/depth",
        {
            "symbol": symbol,
            "limit": 20
        }
    )

    if not data:
        return 0

    try:

        bids = sum(
            float(price) * float(quantity)
            for price, quantity in data["bids"]
        )

        asks = sum(
            float(price) * float(quantity)
            for price, quantity in data["asks"]
        )

        if asks == 0:
            return 0

        return bids / asks

    except Exception:
        return 0


# =========================================================
# SCORE
# =========================================================

def analyze(
    data5,
    data15,
    data1h,
    book_ratio,
    btc_state
):

    closes = data5["closes"]
    highs = data5["highs"]
    lows = data5["lows"]
    volumes = data5["volumes"]

    price = closes[-1]

    e20 = ema(closes, 20)
    e50 = ema(closes, 50)

    if not e20 or not e50:
        return None

    score = 0
    reasons = []

    # =====================================================
    # 5M TREND - 15
    # =====================================================

    if price > e20 > e50:

        score += 15

        reasons.append(
            "Price above EMA20"
        )

        reasons.append(
            "EMA20 above EMA50"
        )

    else:
        return None

    # =====================================================
    # LONG TERM TREND - 10
    # =====================================================

    e100 = ema(closes, 100)

    if e100 and price > e100:

        score += 10

        reasons.append(
            "Price above long-term EMA"
        )

    # =====================================================
    # RSI - 10
    # =====================================================

    current_rsi = rsi(closes)

    if current_rsi is None:
        return None

    # Strict but not excessive
    if not 50 <= current_rsi <= 65:
        return None

    score += 10

    reasons.append(
        f"RSI {current_rsi:.1f}"
    )

    # =====================================================
    # VOLUME - 15
    # =====================================================

    average_volume = (
        sum(volumes[-21:-1])
        / 20
    )

    if average_volume <= 0:
        return None

    volume_ratio = (
        volumes[-1]
        / average_volume
    )

    if volume_ratio < 1.5:
        return None

    if volume_ratio >= 3:

        score += 15

    elif volume_ratio >= 2:

        score += 12

    else:

        score += 7

    reasons.append(
        f"Volume x{volume_ratio:.2f}"
    )

    # =====================================================
    # BREAKOUT - 15
    # =====================================================

    previous_high = max(
        highs[-21:-1]
    )

    breakout = (
        (price - previous_high)
        / previous_high
        * 100
    )

    # We allow near-breakout
    # to avoid zero candidates

    if breakout >= 0.20:

        score += 15

        reasons.append(
            f"Confirmed breakout +{breakout:.2f}%"
        )

    elif breakout >= -0.10:

        score += 8

        reasons.append(
            f"Near breakout {breakout:+.2f}%"
        )

    else:

        return None

    # =====================================================
    # MOMENTUM - 10
    # =====================================================

    momentum = (
        (price - closes[-6])
        / closes[-6]
        * 100
    )

    if not 0.5 <= momentum <= 4:

        return None

    score += 10

    reasons.append(
        f"Momentum +{momentum:.2f}%"
    )

    # =====================================================
    # ATR - 5
    # =====================================================

    atr_value = atr(
        data5["highs"],
        data5["lows"],
        closes
    )

    if not atr_value:
        return None

    atr_percent = (
        atr_value
        / price
        * 100
    )

    if not 0.3 <= atr_percent <= 3:

        return None

    score += 5

    reasons.append(
        f"Healthy ATR {atr_percent:.2f}%"
    )

    # =====================================================
    # 15M - 15
    # =====================================================

    if bullish_trend(data15):

        score += 15

        reasons.append(
            "15m trend confirmed"
        )

    else:

        return None

    # =====================================================
    # 1H - 10
    # =====================================================

    if bullish_trend(data1h):

        score += 10

        reasons.append(
            "1h trend confirmed"
        )

    # =====================================================
    # ORDER BOOK - 10
    # =====================================================

    if book_ratio >= 1.30:

        score += 10

        reasons.append(
            f"Strong buy pressure x{book_ratio:.2f}"
        )

    elif book_ratio >= 1.10:

        score += 5

        reasons.append(
            f"Buy pressure x{book_ratio:.2f}"
        )

    else:

        return None

    # =====================================================
    # BTC - 5
    # =====================================================

    if btc_state == "BULLISH":

        score += 5

        reasons.append(
            "BTC market supportive"
        )

    elif btc_state == "NEUTRAL":

        score += 2

        reasons.append(
            "BTC market neutral"
        )

    else:

        # Do NOT immediately reject.
        # But no BTC points.

        reasons.append(
            "BTC market weak"
        )

    return {
        "score": score,
        "price": price,
        "rsi": current_rsi,
        "volume_ratio": volume_ratio,
        "breakout": breakout,
        "momentum": momentum,
        "atr_percent": atr_percent,
        "atr_value": atr_value,
        "book_ratio": book_ratio,
        "reasons": reasons
    }


# =========================================================
# START
# =========================================================

print(
    "=========================================="
)

print(
    "BINANCE AI SCANNER"
)

print(
    "ULTRA PRECISION BALANCED"
)

print(
    "=========================================="
)

if not BOT_TOKEN or not CHAT_ID:

    print(
        "ERROR: BOT_TOKEN or CHAT_ID missing"
    )

    raise SystemExit


signals = load_signals()

btc_state = btc_condition()

print(
    "BTC Market:",
    btc_state
)


# =========================================================
# SYMBOLS
# =========================================================

exchange_info = get_json(
    "/api/v3/exchangeInfo"
)

if not exchange_info:

    print(
        "ERROR: Cannot get exchange info"
    )

    raise SystemExit


symbols = []

for s in exchange_info["symbols"]:

    if (
        s["status"] == "TRADING"
        and s["quoteAsset"] == "USDT"
        and s["isSpotTradingAllowed"]
    ):

        symbols.append(
            s["symbol"]
        )


print(
    "USDT Spot pairs:",
    len(symbols)
)


# =========================================================
# FIRST PASS
# =========================================================

pre_candidates = []

for index, symbol in enumerate(
    symbols,
    1
):

    try:

        data5 = get_klines(
            symbol,
            INTERVAL,
            LIMIT
        )

        if not data5:
            continue

        closes = data5["closes"]

        if len(closes) < 100:
            continue

        price = closes[-1]

        e20 = ema(
            closes,
            20
        )

        e50 = ema(
            closes,
            50
        )

        if not e20 or not e50:
            continue

        # 5m trend

        if not price > e20 > e50:
            continue

        # RSI

        current_rsi = rsi(
            closes
        )

        if (
            current_rsi is None
            or current_rsi < 50
            or current_rsi > 65
        ):
            continue

        # Volume

        volumes = data5["volumes"]

        average_volume = (
            sum(volumes[-21:-1])
            / 20
        )

        if average_volume <= 0:
            continue

        volume_ratio = (
            volumes[-1]
            / average_volume
        )

        if volume_ratio < 1.5:
            continue

        # Momentum

        momentum = (
            (price - closes[-6])
            / closes[-6]
            * 100
        )

        if not 0.5 <= momentum <= 4:
            continue

        # Breakout / near breakout

        previous_high = max(
            data5["highs"][-21:-1]
        )

        breakout = (
            (price - previous_high)
            / previous_high
            * 100
        )

        if breakout < -0.10:
            continue

        # Avoid chasing

        if breakout > 1.5:
            continue

        pre_candidates.append(
            (
                symbol,
                data5
            )
        )

    except Exception as e:

        print(
            "5m error:",
            symbol,
            e
        )

    if index % 50 == 0:

        print(
            f"5m scan: "
            f"{index}/{len(symbols)}"
        )


print(
    "Pre-candidates:",
    len(pre_candidates)
)


# =========================================================
# SECOND PASS
# =========================================================

candidates = []

for symbol, data5 in pre_candidates:

    try:

        data15 = get_klines(
            symbol,
            CONFIRM_INTERVAL,
            100
        )

        if not data15:
            continue

        # 15m remains mandatory

        if not bullish_trend(data15):
            continue

        data1h = get_klines(
            symbol,
            TREND_INTERVAL,
            100
        )

        if not data1h:
            continue

        book_ratio = (
            order_book_analysis(
                symbol
            )
        )

        result = analyze(
            data5,
            data15,
            data1h,
            book_ratio,
            btc_state
        )

        if not result:
            continue

        if result["score"] < MIN_SCORE:
            continue

        # =================================================
        # RISK
        # =================================================

        price = result["price"]

        atr_value = result["atr_value"]

        risk = max(
            atr_value * 1.2,
            price * 0.01
        )

        stop = price - risk

        if stop <= 0:
            continue

        tp1 = price + risk * 1.5
        tp2 = price + risk * 2
        tp3 = price + risk * 3

        result.update(
            {
                "symbol": symbol,
                "stop": stop,
                "tp1": tp1,
                "tp2": tp2,
                "tp3": tp3
            }
        )

        candidates.append(
            result
        )

    except Exception as e:

        print(
            "Candidate error:",
            symbol,
            e
        )


# =========================================================
# SORT
# =========================================================

candidates.sort(
    key=lambda x: (
        x["score"],
        x["book_ratio"],
        x["volume_ratio"]
    ),
    reverse=True
)


print(
    "Qualified signals:",
    len(candidates)
)


# =========================================================
# SEND TOP 2
# =========================================================

sent = 0

now = time.time()

for signal in candidates:

    if sent >= MAX_SIGNALS:
        break

    symbol = signal["symbol"]

    last_sent = signals.get(
        symbol,
        0
    )

    if now - last_sent < COOLDOWN:

        print(
            "Cooldown:",
            symbol
        )

        continue

    score = signal["score"]

    if score >= 95:

        label = (
            "🟢 ULTRA STRONG SETUP"
        )

    elif score >= 90:

        label = (
            "🟢 VERY STRONG SETUP"
        )

    else:

        label = (
            "🟢 HIGH PRECISION SETUP"
        )

    caption = (

        f"{label}\n\n"

        f"🪙 {symbol}\n"

        f"💰 Price: "
        f"{signal['price']:.8g}\n"

        f"📊 Score: "
        f"{score}/100\n"

        f"📈 RSI: "
        f"{signal['rsi']:.1f}\n"

        f"📊 Volume: "
        f"x{signal['volume_ratio']:.2f}\n"

        f"🔥 Momentum: "
        f"+{signal['momentum']:.2f}%\n"

        f"📐 ATR: "
        f"{signal['atr_percent']:.2f}%\n"

        f"📚 Order Book: "
        f"x{signal['book_ratio']:.2f}\n\n"

        f"🛑 Stop: "
        f"{signal['stop']:.8g}\n"

        f"🎯 TP1: "
        f"{signal['tp1']:.8g}\n"

        f"🎯 TP2: "
        f"{signal['tp2']:.8g}\n"

        f"🎯 TP3: "
        f"{signal['tp3']:.8g}\n\n"

        f"⚖️ RR TP1: 1:1.50\n"
        f"⚖️ RR TP2: 1:2.00\n"
        f"⚖️ RR TP3: 1:3.00\n\n"

        f"📌 Reasons:\n"

        + "\n".join(
            f"✅ {reason}"
            for reason
            in signal["reasons"]
        )

        + "\n\n"

        f"⚠️ SPOT\n"
        f"Technical analysis only."
    )

    # =====================================================
    # CHART
    # =====================================================

    chart_path = None

    try:

        chart_path = save_chart(
            symbol,
            INTERVAL
        )

    except Exception as e:

        print(
            "Chart error:",
            symbol,
            e
        )

    # =====================================================
    # TELEGRAM
    # =====================================================

    if (
        chart_path
        and os.path.exists(
            chart_path
        )
    ):

        send_photo(
            chart_path,
            caption
        )

    else:

        send_message(
            caption
        )

    signals[symbol] = now

    save_signals(
        signals
    )

    sent += 1

    print(
        "SIGNAL SENT:",
        symbol,
        score
    )


# =========================================================
# FINISH
# =========================================================

print(
    f"Signals sent: {sent}"
)

print(
    "SCAN COMPLETED"
)

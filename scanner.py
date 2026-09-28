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

MIN_SCORE = 80
MAX_SIGNALS = 3

COOLDOWN = 3600

SIGNALS_FILE = "signals.json"


# =========================================================
# TELEGRAM
# =========================================================

def send_photo(photo_path, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    try:
        with open(photo_path, "rb") as photo:
            response = requests.post(
                url,
                data={
                    "chat_id": CHAT_ID,
                    "caption": caption,
                },
                files={
                    "photo": photo,
                },
                timeout=30,
            )

        print("Telegram:", response.status_code)

    except Exception as e:
        print("Telegram error:", e)


# =========================================================
# BINANCE REQUEST
# =========================================================

def get_json(path, params=None):
    try:
        r = requests.get(
            BASE + path,
            params=params,
            timeout=15,
        )

        if r.status_code != 200:
            return None

        return r.json()

    except Exception:
        return None


# =========================================================
# SIGNAL MEMORY
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
# INDICATORS
# =========================================================

def ema(values, period):
    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)

    result = values[0]

    for price in values[1:]:
        result = (price - result) * multiplier + result

    return result


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
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None

    trs = []

    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
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
            "limit": limit,
        },
    )

    if not data:
        return None

    try:
        return {
            "opens": [float(x[1]) for x in data],
            "highs": [float(x[2]) for x in data],
            "lows": [float(x[3]) for x in data],
            "closes": [float(x[4]) for x in data],
            "volumes": [float(x[5]) for x in data],
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
# BTC FILTER
# =========================================================

def btc_market_ok():
    data = get_klines(
        "BTCUSDT",
        "15m",
        100,
    )

    if not data:
        return False

    return bullish_trend(data)


# =========================================================
# ORDER BOOK
# =========================================================

def order_book_analysis(symbol):

    data = get_json(
        "/api/v3/depth",
        {
            "symbol": symbol,
            "limit": 20,
        },
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

def calculate_score(data5, data15, data1h, book_ratio, btc_ok):

    closes = data5["closes"]
    highs = data5["highs"]
    lows = data5["lows"]
    volumes = data5["volumes"]

    price = closes[-1]

    e20 = ema(closes, 20)
    e50 = ema(closes, 50)

    r = rsi(closes)

    average_volume = sum(volumes[-21:-1]) / 20
    volume_ratio = volumes[-1] / average_volume if average_volume else 0

    previous_high = max(highs[-21:-1])

    breakout_percent = ((price - previous_high) / previous_high) * 100

    momentum_percent = ((price - closes[-6]) / closes[-6]) * 100

    atr_value = atr(
        data5["highs"],
        data5["lows"],
        closes,
    )

    atr_percent = (
        atr_value / price * 100
        if atr_value
        else 0
    )

    score = 0
    reasons = []

    # -----------------------------------------------------
    # 5M TREND - 15 points
    # -----------------------------------------------------

    if e20 and e50 and price > e20 > e50:
        score += 15
        reasons.append("5m bullish trend")

    elif e20 and price > e20:
        score += 7
        reasons.append("5m price above EMA20")

    # -----------------------------------------------------
    # 15M TREND - 15 points
    # -----------------------------------------------------

    if bullish_trend(data15):
        score += 15
        reasons.append("15m bullish confirmation")

    # -----------------------------------------------------
    # 1H TREND - 10 points
    # -----------------------------------------------------

    if bullish_trend(data1h):
        score += 10
        reasons.append("1h bullish trend")

    # -----------------------------------------------------
    # RSI - 10 points
    # -----------------------------------------------------

    if r is not None:

        if 50 <= r <= 65:
            score += 10
            reasons.append(f"RSI {r:.1f}")

        elif 65 < r <= 70:
            score += 5
            reasons.append(f"High RSI {r:.1f}")

        else:
            return None

    else:
        return None

    # -----------------------------------------------------
    # VOLUME - 15 points
    # -----------------------------------------------------

    if volume_ratio >= 3:
        score += 15
        reasons.append(f"Volume x{volume_ratio:.2f}")

    elif volume_ratio >= 2:
        score += 10
        reasons.append(f"Volume x{volume_ratio:.2f}")

    elif volume_ratio >= 1.5:
        score += 5
        reasons.append(f"Volume x{volume_ratio:.2f}")

    # -----------------------------------------------------
    # BREAKOUT - 10 points
    # -----------------------------------------------------

    if breakout_percent > 0:
        score += 10
        reasons.append(f"Breakout +{breakout_percent:.2f}%")

    elif breakout_percent > -0.20:
        score += 5
        reasons.append("Near breakout")

    # -----------------------------------------------------
    # MOMENTUM - 10 points
    # -----------------------------------------------------

    if 0.5 <= momentum_percent <= 4:
        score += 10
        reasons.append(f"Momentum +{momentum_percent:.2f}%")

    elif 0.2 <= momentum_percent < 0.5:
        score += 5
        reasons.append(f"Momentum +{momentum_percent:.2f}%")

    elif 4 < momentum_percent <= 5:
        score += 5
        reasons.append(f"Strong momentum +{momentum_percent:.2f}%")

    # -----------------------------------------------------
    # ORDER BOOK - 10 points
    # -----------------------------------------------------

    if book_ratio >= 1.30:
        score += 10
        reasons.append(f"Buy pressure x{book_ratio:.2f}")

    elif book_ratio >= 1.10:
        score += 5
        reasons.append(f"Buy pressure x{book_ratio:.2f}")

    # -----------------------------------------------------
    # BTC - 5 points
    # -----------------------------------------------------

    if btc_ok:
        score += 5
        reasons.append("BTC bullish")

    return {
        "score": score,
        "price": price,
        "rsi": r,
        "volume_ratio": volume_ratio,
        "breakout": breakout_percent,
        "momentum": momentum_percent,
        "atr_percent": atr_percent,
        "book_ratio": book_ratio,
        "reasons": reasons,
    }


# =========================================================
# MAIN
# =========================================================

print("==============================================")
print("BINANCE AI SCANNER - HIGH PRECISION MODE")
print("==============================================")


if not BOT_TOKEN or not CHAT_ID:
    print("ERROR: BOT_TOKEN or CHAT_ID missing")
    raise SystemExit


signals = load_signals()

btc_ok = btc_market_ok()

print(
    "BTC Market:",
    "BULLISH" if btc_ok else "WEAK"
)


# =========================================================
# GET USDT SPOT SYMBOLS
# =========================================================

exchange_info = get_json(
    "/api/v3/exchangeInfo"
)

if not exchange_info:
    print("ERROR: Cannot get exchange info")
    raise SystemExit


symbols = []

for s in exchange_info["symbols"]:

    if (
        s["status"] == "TRADING"
        and s["quoteAsset"] == "USDT"
        and s["isSpotTradingAllowed"]
    ):
        symbols.append(s["symbol"])


print("USDT Spot pairs:", len(symbols))


# =========================================================
# FIRST PASS
# Only 5m data for all coins
# =========================================================

pre_candidates = []

for index, symbol in enumerate(symbols, 1):

    try:

        data5 = get_klines(
            symbol,
            INTERVAL,
            LIMIT,
        )

        if not data5:
            continue

        closes = data5["closes"]

        if len(closes) < 100:
            continue

        price = closes[-1]

        e20 = ema(closes, 20)
        e50 = ema(closes, 50)

        if not e20 or not e50:
            continue

        # Basic 5m trend
        if price <= e20:
            continue

        if e20 <= e50:
            continue

        r = rsi(closes)

        if r is None:
            continue

        # Reject weak or overbought RSI
        if r < 50 or r > 70:
            continue

        volumes = data5["volumes"]

        average_volume = sum(volumes[-21:-1]) / 20

        if average_volume <= 0:
            continue

        volume_ratio = volumes[-1] / average_volume

        # Require some volume
        if volume_ratio < 1.5:
            continue

        # Momentum
        momentum = (
            (price - closes[-6])
            / closes[-6]
            * 100
        )

        if momentum < 0.2 or momentum > 5:
            continue

        pre_candidates.append(
            (
                symbol,
                data5,
            )
        )

    except Exception as e:
        print("5m error:", symbol, e)

    if index % 50 == 0:
        print(
            f"5m scan: {index}/{len(symbols)}"
        )


print(
    "Pre-candidates:",
    len(pre_candidates)
)


# =========================================================
# SECOND PASS
# Strong candidates only
# =========================================================

candidates = []

for symbol, data5 in pre_candidates:

    try:

        data15 = get_klines(
            symbol,
            CONFIRM_INTERVAL,
            100,
        )

        data1h = get_klines(
            symbol,
            TREND_INTERVAL,
            100,
        )

        if not data15 or not data1h:
            continue

        # 15m is mandatory
        if not bullish_trend(data15):
            continue

        book_ratio = order_book_analysis(symbol)

        result = calculate_score(
            data5,
            data15,
            data1h,
            book_ratio,
            btc_ok,
        )

        if not result:
            continue

        score = result["score"]

        if score < MIN_SCORE:
            continue

        # -------------------------------------------------
        # RISK
        # -------------------------------------------------

        price = result["price"]

        atr_value = atr(
            data5["highs"],
            data5["lows"],
            data5["closes"],
        )

        if not atr_value:
            continue

        risk = max(
            atr_value * 1.2,
            price * 0.01,
        )

        stop = price - risk

        if stop <= 0:
            continue

        tp1 = price + risk * 1.5
        tp2 = price + risk * 2
        tp3 = price + risk * 3

        reward1 = (
            (tp1 - price)
            / price
            * 100
        )

        # Avoid tiny setups
        if reward1 < 1:
            continue

        result.update(
            {
                "symbol": symbol,
                "stop": stop,
                "tp1": tp1,
                "tp2": tp2,
                "tp3": tp3,
                "reward1": reward1,
            }
        )

        candidates.append(result)

    except Exception as e:
        print("Candidate error:", symbol, e)


# =========================================================
# SORT
# =========================================================

candidates.sort(
    key=lambda x: x["score"],
    reverse=True,
)


print(
    "Qualified signals:",
    len(candidates)
)


# =========================================================
# SEND TOP SIGNALS
# =========================================================

sent = 0

now = time.time()

for signal in candidates:

    if sent >= MAX_SIGNALS:
        break

    symbol = signal["symbol"]

    last_sent = signals.get(symbol, 0)

    if now - last_sent < COOLDOWN:
        print(
            "Cooldown:",
            symbol
        )
        continue

    score = signal["score"]

    if score >= 90:
        label = "🟢 VERY STRONG SETUP"

    elif score >= 85:
        label = "🟢 STRONG SETUP"

    else:
        label = "🟢 HIGH QUALITY SETUP"

    caption = (
        f"{label}\n\n"
        f"#{symbol}\n"
        f"Score: {score}/100\n\n"

        f"💰 Price: {signal['price']:.8g}\n"
        f"📊 RSI: {signal['rsi']:.1f}\n"
        f"📈 Volume: x{signal['volume_ratio']:.2f}\n"
        f"🚀 Momentum: +{signal['momentum']:.2f}%\n"
        f"🔥 ATR: {signal['atr_percent']:.2f}%\n"
        f"📚 Order Book: x{signal['book_ratio']:.2f}\n\n"

        f"🛑 Stop: {signal['stop']:.8g}\n"
        f"🎯 TP1: {signal['tp1']:.8g}\n"
        f"🎯 TP2: {signal['tp2']:.8g}\n"
        f"🎯 TP3: {signal['tp3']:.8g}\n\n"

        f"RR TP1: 1:1.5\n"
        f"RR TP2: 1:2\n"
        f"RR TP3: 1:3\n\n"

        f"✅ Confirmations:\n"
        + "\n".join(
            f"• {reason}"
            for reason in signal["reasons"]
        )
        + "\n\n"
        f"⚠️ SPOT\n"
        f"Technical analysis only."
    )

    chart_path = None

    try:

        chart_path = save_chart(
            symbol,
            INTERVAL,
        )

    except Exception as e:

        print(
            "Chart error:",
            symbol,
            e
        )

    if chart_path and os.path.exists(chart_path):

        send_photo(
            chart_path,
            caption,
        )

    else:

        url = (
            f"https://api.telegram.org/"
            f"bot{BOT_TOKEN}/sendMessage"
        )

        try:
            requests.post(
                url,
                data={
                    "chat_id": CHAT_ID,
                    "text": caption,
                },
                timeout=20,
            )

        except Exception as e:
            print(
                "Telegram message error:",
                e
            )

    signals[symbol] = now

    save_signals(signals)

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

print("SCAN COMPLETED")

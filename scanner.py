import os
import time
import requests
from datetime import datetime, timezone

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BINANCE_BASE = "https://data-api.binance.vision"

INTERVAL = "5m"
KLINE_LIMIT = 120

MIN_SCORE = 60
MAX_SIGNALS = 5

session = requests.Session()


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        response = session.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=15
        )

        print("Telegram status:", response.status_code)

    except Exception as e:
        print("Telegram error:", e)


def get_binance(endpoint, params=None):

    try:
        response = session.get(
            BINANCE_BASE + endpoint,
            params=params,
            timeout=15
        )

        response.raise_for_status()

        return response.json()

    except Exception as e:

        print("Binance error:", e)

        return None


def get_symbols():

    data = get_binance(
        "/api/v3/exchangeInfo"
    )

    if not data:
        return []

    symbols = []

    for item in data.get("symbols", []):

        if item.get("status") != "TRADING":
            continue

        if item.get("quoteAsset") != "USDT":
            continue

        if item.get("isSpotTradingAllowed") is not True:
            continue

        symbols.append(
            item.get("symbol")
        )

    return symbols


def get_klines(symbol):

    return get_binance(
        "/api/v3/klines",
        {
            "symbol": symbol,
            "interval": INTERVAL,
            "limit": KLINE_LIMIT
        }
    )


def ema(values, period):

    if len(values) < period:
        return None

    value = sum(
        values[:period]
    ) / period

    multiplier = 2 / (period + 1)

    for price in values[period:]:

        value = (
            price - value
        ) * multiplier + value

    return value


def calculate_rsi(values, period=14):

    if len(values) <= period:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):

        change = (
            values[i] - values[i - 1]
        )

        if change >= 0:

            gains.append(change)
            losses.append(0)

        else:

            gains.append(0)
            losses.append(abs(change))

    average_gain = (
        sum(gains[:period]) / period
    )

    average_loss = (
        sum(losses[:period]) / period
    )

    for i in range(period, len(gains)):

        average_gain = (
            average_gain * (period - 1)
            + gains[i]
        ) / period

        average_loss = (
            average_loss * (period - 1)
            + losses[i]
        ) / period

    if average_loss == 0:
        return 100

    rs = average_gain / average_loss

    return 100 - (
        100 / (1 + rs)
    )


def analyze(symbol, klines):

    if not klines or len(klines) < 60:
        return None

    closes = [
        float(candle[4])
        for candle in klines
    ]

    highs = [
        float(candle[2])
        for candle in klines
    ]

    volumes = [
        float(candle[5])
        for candle in klines
    ]

    price = closes[-1]

    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)

    rsi = calculate_rsi(
        closes,
        14
    )

    if ema20 is None:
        return None

    if ema50 is None:
        return None

    if rsi is None:
        return None

    score = 0

    reasons = []

    # EMA20
    if price > ema20:

        score += 20

        reasons.append(
            "Price above EMA20"
        )

    # EMA20 / EMA50
    if ema20 > ema50:

        score += 20

        reasons.append(
            "EMA20 above EMA50"
        )

    # RSI
    if 50 <= rsi <= 65:

        score += 20

        reasons.append(
            f"RSI healthy {rsi:.1f}"
        )

    elif 65 < rsi <= 72:

        score += 10

        reasons.append(
            f"RSI strong {rsi:.1f}"
        )

    elif rsi > 72:

        score -= 10

        reasons.append(
            f"RSI overheated {rsi:.1f}"
        )

    # Volume
    average_volume = sum(
        volumes[-21:-1]
    ) / 20

    if average_volume > 0:

        volume_ratio = (
            volumes[-1] /
            average_volume
        )

    else:

        volume_ratio = 0

    if volume_ratio >= 1.5:

        score += 20

        reasons.append(
            f"Strong volume x{volume_ratio:.2f}"
        )

    elif volume_ratio >= 1.2:

        score += 10

        reasons.append(
            f"Volume x{volume_ratio:.2f}"
        )

    # Breakout
    previous_high = max(
        highs[-21:-1]
    )

    if price > previous_high:

        score += 20

        reasons.append(
            "Breakout"
        )

    # Momentum
    momentum = (
        price / closes[-6] - 1
    ) * 100

    if 0.3 <= momentum <= 5:

        score += 10

        reasons.append(
            f"Momentum +{momentum:.2f}%"
        )

    # Limit score
    score = max(
        0,
        min(score, 100)
    )

    if score < MIN_SCORE:
        return None

    return {
        "symbol": symbol,
        "price": price,
        "score": score,
        "rsi": rsi,
        "volume": volume_ratio,
        "momentum": momentum,
        "reasons": reasons
    }


def create_message(signal):

    reasons = "\n".join(
        "✅ " + reason
        for reason in signal["reasons"]
    )

    return (
        "🚨 BINANCE SPOT SIGNAL 🚨\n\n"

        f"🪙 Coin: {signal['symbol']}\n"
        f"💰 Price: {signal['price']:g}\n"
        f"📊 Score: {signal['score']}/100\n"
        f"📈 RSI: {signal['rsi']:.1f}\n"
        f"📊 Volume: x{signal['volume']:.2f}\n"
        f"🔥 Momentum: "
        f"{signal['momentum']:+.2f}%\n\n"

        "📌 Reasons:\n"
        f"{reasons}\n\n"

        "⚠️ Market: SPOT\n"
        "Technical analysis only."
    )


def main():

    print(
        "=============================="
    )

    print(
        "BINANCE AI SCANNER STARTED"
    )

    print(
        "=============================="
    )

    if not BOT_TOKEN:

        print(
            "BOT_TOKEN missing"
        )

        return

    if not CHAT_ID:

        print(
            "CHAT_ID missing"
        )

        return

    symbols = get_symbols()

    if not symbols:

        print(
            "No USDT Spot pairs found"
        )

        return

    print(
        f"Found {len(symbols)} "
        "USDT Spot pairs."
    )

    signals = []

    for number, symbol in enumerate(
        symbols,
        1
    ):

        print(
            f"[{number}/{len(symbols)}] "
            f"{symbol}"
        )

        klines = get_klines(
            symbol
        )

        if not klines:
            continue

        try:

            signal = analyze(
                symbol,
                klines
            )

            if signal:

                signals.append(
                    signal
                )

        except Exception as e:

            print(
                f"Analysis error "
                f"{symbol}: {e}"
            )

        time.sleep(0.05)

    signals.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    print(
        f"Signals found: "
        f"{len(signals)}"
    )

    for signal in signals[
        :MAX_SIGNALS
    ]:

        print(
            f"Signal: "
            f"{signal['symbol']} "
            f"{signal['score']}/100"
        )

        send_telegram(
            create_message(signal)
        )

    print(
        "SCAN COMPLETED:",
        datetime.now(
            timezone.utc
        ).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    )


if __name__ == "__main__":

    main()

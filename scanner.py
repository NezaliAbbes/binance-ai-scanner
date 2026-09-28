import os
import time
import requests
from datetime import datetime, timezone

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BINANCE_BASE = "https://data-api.binance.vision"

INTERVAL = "5m"
KLINE_LIMIT = 120

MIN_SCORE = 70
MIN_QUOTE_VOLUME = 1_000_000

REQUEST_TIMEOUT = 15
MAX_SIGNALS = 5

session = requests.Session()


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("BOT_TOKEN or CHAT_ID missing.")
        return False

    try:
        response = session.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=REQUEST_TIMEOUT
        )

        if response.ok:
            return True

        print("Telegram error:", response.text)
        return False

    except Exception as e:
        print("Telegram exception:", e)
        return False


def binance_get(endpoint, params=None):
    try:
        response = session.get(
            BINANCE_BASE + endpoint,
            params=params,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()
        return response.json()

    except Exception as e:
        print("Binance error:", e)
        return None


def get_symbols():
    data = binance_get("/api/v3/exchangeInfo")

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

        symbol = item.get("symbol")

        if symbol:
            symbols.append(symbol)

    return symbols


def get_klines(symbol):
    return binance_get(
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

    value = sum(values[:period]) / period
    multiplier = 2 / (period + 1)

    for price in values[period:]:
        value = (price - value) * multiplier + value

    return value


def rsi(values, period=14):
    if len(values) <= period:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):

        change = values[i] - values[i - 1]

        if change >= 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):

        avg_gain = (
            (avg_gain * (period - 1)) + gains[i]
        ) / period

        avg_loss = (
            (avg_loss * (period - 1)) + losses[i]
        ) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def macd(values):

    if len(values) < 40:
        return None, None

    macd_values = []

    for i in range(26, len(values) + 1):

        ema12 = ema(values[:i], 12)
        ema26 = ema(values[:i], 26)

        if ema12 is not None and ema26 is not None:
            macd_values.append(ema12 - ema26)

    if len(macd_values) < 9:
        return None, None

    macd_line = macd_values[-1]
    signal_line = ema(macd_values, 9)

    return macd_line, signal_line


def analyze(symbol, klines):

    if not klines or len(klines) < 60:
        return None

    closes = [float(k[4]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    volumes = [float(k[5]) for k in klines]
    quote_volumes = [float(k[7]) for k in klines]

    price = closes[-1]

    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)

    rsi_value = rsi(closes, 14)

    macd_value, macd_signal = macd(closes)

    if (
        ema20 is None
        or ema50 is None
        or rsi_value is None
        or macd_value is None
        or macd_signal is None
    ):
        return None

    score = 0
    reasons = []

    # -------------------------
    # TREND
    # -------------------------

    if price > ema20:
        score += 15
        reasons.append("Price above EMA20")

    if ema20 > ema50:
        score += 20
        reasons.append("EMA20 above EMA50")

    # -------------------------
    # RSI
    # -------------------------

    if 50 <= rsi_value <= 65:

        score += 15
        reasons.append(f"RSI healthy {rsi_value:.1f}")

    elif 65 < rsi_value <= 72:

        score += 8
        reasons.append(f"RSI strong {rsi_value:.1f}")

    elif rsi_value > 72:

        score -= 10
        reasons.append("RSI overheated")

    # -------------------------
    # MACD
    # -------------------------

    if macd_value > macd_signal:

        score += 15
        reasons.append("MACD bullish")

    # -------------------------
    # VOLUME
    # -------------------------

    avg_volume = sum(volumes[-21:-1]) / 20

    if avg_volume > 0:

        volume_ratio = volumes[-1] / avg_volume

    else:

        volume_ratio = 0

    if volume_ratio >= 1.5:

        score += 15
        reasons.append(f"Strong volume x{volume_ratio:.2f}")

    elif volume_ratio >= 1.2:

        score += 8
        reasons.append(f"Volume x{volume_ratio:.2f}")

    elif volume_ratio < 0.8:

        score -= 10
        reasons.append(f"Low volume x{volume_ratio:.2f}")

    # -------------------------
    # BREAKOUT
    # -------------------------

    previous_high = max(highs[-21:-1])

    if price > previous_high:

        score += 15
        reasons.append("Breakout above 20-candle high")

    # -------------------------
    # MOMENTUM
    # -------------------------

    momentum = ((price / closes[-6]) - 1) * 100

    if 0.3 <= momentum <= 5:

        score += 10
        reasons.append(f"Momentum +{momentum:.2f}%")

    elif momentum > 5:

        score -= 5
        reasons.append("Momentum too fast")

    # -------------------------
    # SUPPORT / STOP LOSS
    # -------------------------

    recent_low = min(lows[-20:])

    risk_distance = price - recent_low

    if risk_distance <= 0:

        return None

    stop_loss = recent_low

    # Do not allow an excessively distant stop loss
    if (risk_distance / price) > 0.08:

        return None

    # -------------------------
    # TAKE PROFITS
    # -------------------------

    risk = price - stop_loss

    tp1 = price + (risk * 1.5)
    tp2 = price + (risk * 2.0)
    tp3 = price + (risk * 3.0)

    # -------------------------
    # ENTRY RANGE
    # -------------------------

    entry_low = price * 0.995
    entry_high = price * 1.005

    quote_volume = sum(quote_volumes[-24:])

    final_score = max(0, min(score, 100))

    return {
        "symbol": symbol,
        "price": price,
        "score": final_score,
        "rsi": rsi_value,
        "volume_ratio": volume_ratio,
        "momentum": momentum,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "quote_volume": quote_volume,
        "reasons": reasons
    }


def build_message(signal):

    reasons = "\n".join(
        "✅ " + reason
        for reason in signal["reasons"]
    )

    return (
        "🚨 BINANCE SPOT SIGNAL 🚨\n\n"

        f"🪙 Coin: {signal['symbol']}\n"
        f"💰 Price: {signal['price']:g}\n\n"

        f"📊 Score: {signal['score']}/100\n"
        f"📈 RSI: {signal['rsi']:.1f}\n"
        f"📊 Volume: x{signal['volume_ratio']:.2f}\n"
        f"🔥 Momentum: {signal['momentum']:+.2f}%\n\n"

        "🎯 TRADE PLAN\n\n"

        f"🟢 Entry: "
        f"{signal['entry_low']:g} - "
        f"{signal['entry_high']:g}\n"

        f"🛑 Stop Loss: "
        f"{signal['stop_loss']:g}\n"

        f"🎯 TP1: {signal['tp1']:g}\n"
        f"🎯 TP2: {signal['tp2']:g}\n"
        f"🎯 TP3: {signal['tp3']:g}\n\n"

        "📌 Reasons:\n"
        f"{reasons}\n\n"

        "⚠️ Market: SPOT\n"
        "Technical signal only — not a guarantee of profit."
    )


def main():

    print("BINANCE AI SCANNER STARTED")

    if not BOT_TOKEN or not CHAT_ID:

        print("BOT_TOKEN or CHAT_ID missing.")
        return

    symbols = get_symbols()

    if not symbols:

        print("No USDT Spot pairs found.")
        return

    print(
        f"Found {len(symbols)} USDT Spot pairs."
    )

    signals = []

    for index, symbol in enumerate(symbols, 1):

        print(
            f"[{index}/{len(symbols)}] {symbol}"
        )

        klines = get_klines(symbol)

        if not klines:
            continue

        try:

            signal = analyze(
                symbol,
                klines
            )

            if signal is None:
                continue

            if signal["quote_volume"] < MIN_QUOTE_VOLUME:
                continue

            if signal["score"] < MIN_SCORE:
                continue

            signals.append(signal)

        except Exception as e:

            print(
                f"Analysis error {symbol}: {e}"
            )

        time.sleep(0.05)

    signals.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    print(
        f"Signals found: {len(signals)}"
    )

    for signal in signals[:MAX_SIGNALS]:

        message = build_message(signal)

        send_telegram(message)

        print(
            f"Signal sent: "
            f"{signal['symbol']} "
            f"{signal['score']}/100"
        )

    print(
        "SCAN COMPLETED:",
        datetime.now(timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    )


if __name__ == "__main__":
    main()

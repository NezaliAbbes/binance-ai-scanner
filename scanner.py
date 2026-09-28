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
MIN_QUOTE_VOLUME = 1000000
MAX_SIGNALS = 5

TIMEOUT = 15

session = requests.Session()


def telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials missing")
        return

    try:
        r = session.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=TIMEOUT
        )

        if r.ok:
            print("Telegram message sent")
        else:
            print("Telegram error:", r.text)

    except Exception as e:
        print("Telegram exception:", e)


def binance(endpoint, params=None):
    try:
        r = session.get(
            BINANCE_BASE + endpoint,
            params=params,
            timeout=TIMEOUT
        )

        r.raise_for_status()

        return r.json()

    except Exception as e:
        print("Binance error:", e)
        return None


def get_symbols():
    data = binance("/api/v3/exchangeInfo")

    if not data:
        return []

    result = []

    for item in data.get("symbols", []):
        if item.get("status") != "TRADING":
            continue

        if item.get("quoteAsset") != "USDT":
            continue

        if item.get("isSpotTradingAllowed") is not True:
            continue

        symbol = item.get("symbol")

        if symbol:
            result.append(symbol)

    return result


def get_klines(symbol):
    return binance(
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
        value = (
            (price - value) * multiplier
            + value
        )

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


def macd(values):
    if len(values) < 40:
        return None, None

    values_macd = []

    for i in range(26, len(values) + 1):
        e12 = ema(values[:i], 12)
        e26 = ema(values[:i], 26)

        if e12 is not None and e26 is not None:
            values_macd.append(e12 - e26)

    if len(values_macd) < 9:
        return None, None

    line = values_macd[-1]
    signal = ema(values_macd, 9)

    return line, signal


def analyze(symbol, klines):
    if not klines or len(klines) < 60:
        return None

    closes = [float(x[4]) for x in klines]
    highs = [float(x[2]) for x in klines]
    lows = [float(x[3]) for x in klines]
    volumes = [float(x[5]) for x in klines]
    quote_volumes = [float(x[7]) for x in klines]

    price = closes[-1]

    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    rsi_value = rsi(closes, 14)
    macd_line, macd_signal = macd(closes)

    if (
        e20 is None
        or e50 is None
        or rsi_value is None
        or macd_line is None
        or macd_signal is None
    ):
        return

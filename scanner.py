import os
import time
import requests
from datetime import datetime, timezone

# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BINANCE_BASE = "https://api.binance.com"

INTERVAL = "5m"
KLINE_LIMIT = 120

MIN_SCORE = 70
MAX_SYMBOLS = 0          # 0 = scan ALL USDT spot pairs
MIN_QUOTE_VOLUME = 1_000_000

REQUEST_TIMEOUT = 15

# Avoid sending the same signal repeatedly
SIGNAL_COOLDOWN = 30 * 60

last_signals = {}


# =========================================================
# TELEGRAM
# =========================================================

def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("BOT_TOKEN أو CHAT_ID غير موجود.")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
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


# =========================================================
# BINANCE
# =========================================================

session = requests.Session()


def binance_get(endpoint, params=None):
    url = BINANCE_BASE + endpoint

    try:
        response = session.get(
            url,
            params=params,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()
        return response.json()

    except Exception as e:
        print(f"Binance error {endpoint}: {e}")
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


# =========================================================
# TECHNICAL INDICATORS
# =========================================================

def ema(values, period):
    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)

    value = sum(values[:period]) / period

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
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def macd(values):
    if len(values) < 35:
        return None, None

    ema12_values = []

    for i in range(12, len(values) + 1):
        ema12_values.append(ema(values[:i], 12))

    ema26_values = []

    for i in range(26, len(values) + 1):
        ema26_values.append(ema(values[:i], 26))

    macd_values = []

    start = 25

    for i in range(start, len(values)):
        e12 = ema(values[:i + 1], 12)
        e26 = ema(values[:i + 1], 26)

        if e12 is not None and e26 is not None:
            macd_values.append(e12 - e26)

    if len(macd_values) < 9:
        return None, None

    signal = ema(macd_values, 9)

    if signal is None:
        return None, None

    return macd_values[-1], signal


# =========================================================
# ANALYSIS
# =========================================================

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

    if None in (ema20, ema50, rsi_value, macd_value, macd_signal):
        return None

    # Average volume of previous 20 candles
    avg_volume = sum(volumes[-21:-1]) / 20

    current_volume = volumes[-1]

    volume_ratio = (
        current_volume / avg_volume
        if avg_volume > 0
        else 0
    )

    # Previous 20 candle high
    previous_high = max(highs[-21:-1])

    # Previous candle close
    previous_close = closes[-2]

    score = 0
    reasons = []

    # -----------------------------------------------------
    # TREND
    # -----------------------------------------------------

    if price > ema20:
        score += 15
        reasons.append("Price > EMA20")

    if ema20 > ema50:
        score += 20
        reasons.append("EMA20 > EMA50")

    # -----------------------------------------------------
    # RSI
    # -----------------------------------------------------

    if 50 <= rsi_value <= 68:
        score += 15
        reasons.append(f"RSI {rsi_value:.1f}")

    elif 68 < rsi_value <= 75:
        score += 8
        reasons.append(f"RSI strong {rsi_value:.1f}")

    elif rsi_value > 75:
        score -= 5

    # -----------------------------------------------------
    # MACD
    # -----------------------------------------------------

    if macd_value > macd_signal:
        score += 15
        reasons.append("MACD bullish")

    # -----------------------------------------------------
    # VOLUME
    # -----------------------------------------------------

    if volume

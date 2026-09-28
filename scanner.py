import os
import json
import time
import requests
from chart import save_chart

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BASE = "https://data-api.binance.vision"

INTERVAL = "5m"
CONFIRM_INTERVAL = "15m"
LIMIT = 120

MIN_SCORE = 60
MAX_SIGNALS = 3
COOLDOWN = 3600

session = requests.Session()


def send_photo(photo_path, caption):
    with open(photo_path, "rb") as img:
        session.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            data={"chat_id": CHAT_ID, "caption": caption},
            files={"photo": img},
            timeout=20
        )


def get_json(endpoint, params=None):
    r = session.get(BASE + endpoint, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def load_signals():
    try:
        with open("signals.json", "r") as f:
            return json.load(f)
    except:
        return {}


def save_signals(data):
    with open("signals.json", "w") as f:
        json.dump(data, f)


def ema(values, period):
    if len(values) < period:
        return None
    value = sum(values[:period]) / period
    k = 2 / (period + 1)
    for p in values[period:]:
        value = (p - value) * k + value
    return value


def rsi(values, period=14):
    if len(values) <= period:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def confirm_trend(symbol):
    try:
        klines = get_json(
            "/api/v3/klines",
            {"symbol": symbol, "interval": CONFIRM_INTERVAL, "limit": 60}
        )

        closes = [float(k[4]) for k in klines]

        e20 = ema(closes, 20)
        e50 = ema(closes, 50)
        r = rsi(closes)

        return (
            e20 is not None and
            e50 is not None and
            r is not None and
            closes[-1] > e20 and
            e20 > e50 and
            r > 50
        )

    except:
        return False


def btc_market_ok():
    try:
        klines = get_json(
            "/api/v3/klines",
            {"symbol": "BTCUSDT", "interval": "15m", "limit": 60}
        )

        closes = [float(k[4]) for k in klines]

        e20 = ema(closes, 20)
        e50 = ema(closes, 50)
        r = rsi(closes)

        return closes[-1] > e20 and e20 > e50 and r > 50

    except:
        return True


print("BINANCE AI SCANNER PRO 2.1 STARTED")

market_ok = btc_market_ok()

data = get_json("/api/v3/exchangeInfo")

symbols = [
    s["symbol"]
    for s in data["symbols"]
    if s["status"] == "TR

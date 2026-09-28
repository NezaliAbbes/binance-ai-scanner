import os
import time
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BINANCE_BASE = "https://data-api.binance.vision"
INTERVAL = "5m"
LIMIT = 120
MIN_SCORE = 60
MAX_SIGNALS = 3

session = requests.Session()


def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    session.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=15)


def get_json(endpoint, params=None):
    r = session.get(BINANCE_BASE + endpoint, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def ema(values, period):
    if len(values) < period:
        return None
    e = sum(values[:period]) / period
    m = 2 / (period + 1)
    for p in values[period:]:
        e = (p - e) * m + e
    return e


def rsi(values, period=14):
    if len(values) <= period:

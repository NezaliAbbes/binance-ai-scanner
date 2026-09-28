import os
import time
import requests
from datetime import datetime, timezone

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BINANCE_BASE = "https://api.binance.com"

INTERVAL = "5m"
KLINE_LIMIT = 120

MIN_SCORE = 70
MIN_QUOTE_VOLUME = 1000000

REQUEST_TIMEOUT = 15
SIGNAL_COOLDOWN = 1800

last_signals = {}


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("BOT_TOKEN or CHAT_ID missing.")
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


session = requests.Session()


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
        if item.get("status

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

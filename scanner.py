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

session =

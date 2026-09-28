import os
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

print("BINANCE AI SCANNER STARTED")
print("BOT_TOKEN:", "OK" if BOT_TOKEN else "MISSING")
print("CHAT_ID:", "OK" if CHAT_ID else "MISSING")

try:
    response = requests.get(
        "https://data-api.binance.vision/api/v3/exchangeInfo",
        timeout=15
    )

    print("Binance status:", response.status_code)

    if response.ok:
        data = response.json()
        symbols = [
            x["symbol"]
            for x in data["symbols"]
            if x.get("quoteAsset") == "USDT"
            and x.get("status") == "TRADING"
        ]

        print("USDT Spot pairs:", len(symbols))

    else:
        print("Binance error:", response.text)

except Exception as e:
    print("ERROR:", e)

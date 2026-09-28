import os
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg}
    )

if BOT_TOKEN and CHAT_ID:
    send("✅ Binance AI Scanner يعمل بنجاح على GitHub.")
else:
    print("BOT_TOKEN أو CHAT_ID غير موجود.")

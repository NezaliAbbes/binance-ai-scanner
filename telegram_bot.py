import os
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials missing")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        r = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=15
        )

        if r.ok:
            print("Telegram OK")
            return True

        print("Telegram Error:", r.text)
        return False

    except Exception as e:
        print("Telegram Exception:", e)
        return False

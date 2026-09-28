
import requests
import pandas as pd
import numpy as np
import os
import json
import time

BASE = "https://data-api.binance.vision"
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HISTORY_FILE = "signals.json"

print("="*50)
print("BINANCE AI SCANNER PRO 2.3")
print("="*50)

# تحميل سجل الإشارات
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r") as f:
        history = json.load(f)
else:
    history = {}

# جلب الأزواج
data = requests.get(f"{BASE}/api/v3/exchangeInfo", timeout=20).json()
pairs = [s["symbol"] for s in data["symbols"]
         if s["quoteAsset"]=="USDT" and s["status"]=="TRADING"]

print(f"USDT Spot pairs: {len(pairs)}")

best = []

for i, symbol in enumerate(pairs,1):
    try:
        kl = requests.get(
            f"{BASE}/api/v3/klines?symbol={symbol}&interval=15m&limit=120",
            timeout=10
        ).json()

        if len(kl) < 60:
            continue

        df = pd.DataFrame(kl)

        close = df[4].astype(float)
        high = df[2].astype(float)
        low = df[3].astype(float)
        vol = df[5].astype(float)

        # RSI
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain/loss.replace(0,np.nan)
        rsi = (100-(100/(1+rs))).iloc[-2]

        if np.isnan(rsi) or not (45<=rsi<=68):
            continue

        # Volume
        vol_ratio = vol.iloc[-2]/vol.iloc[-22:-2].mean()
        if vol_ratio<1.3:
            continue

        # EMA Trend
        ema20 = close.ewm(span=20,adjust=False).mean().iloc[-2]
        ema50 = close.ewm(span=50,adjust=False).mean().iloc[-2]
        if ema20<=ema50:
            continue

        # Breakout
        last_close = close.iloc[-2]
        highest20 = high.iloc[-22:-2].max()
        if last_close<=highest20*0.998:
            continue

        entry = last_close
        stop = low.iloc[-12:-2].min()
        risk = entry-stop
        if risk<=0:
            continue

        tp1 = entry+risk*1.5
        tp2 = entry+risk*2.5
        tp3 = entry+risk*4

        volume_score=min(vol_ratio*15,35)
        rsi_score=max(0,35-abs(rsi-56)*2)
        score=min(round(volume_score+rsi_score+15+15),100)

        best.append({
            "symbol":symbol,
            "score":score,
            "rsi":round(rsi,1),
            "vol":round(vol_ratio,2),
            "entry":entry,
            "stop":stop,
            "tp1":tp1,
            "tp2":tp2,
            "tp3":tp3
        })

    except:
        continue

    if i%100==0:
        print(f"Scanned: {i}/{len(pairs)}")

best=sorted(best,key=lambda x:x["score"],reverse=True)

print("\nQualified:",len(best))

# إرسال تيليغرام
if best and TOKEN and CHAT_ID:
    s=best[0]
    now=time.time()

    if s["symbol"] not in history or now-history[s["symbol"]]>21600:
        msg=f"""🚀 BINANCE AI SIGNAL

Pair: {s['symbol']}
Score: {s['score']}/100
RSI: {s['rsi']}
Volume: x{s['vol']}

Entry: {s['entry']:.6f}
Stop: {s['stop']:.6f}
TP1: {s['tp1']:.6f}
TP2: {s['tp2']:.6f}
TP3: {s['tp3']:.6f}
"""

        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id":CHAT_ID,"text":msg}
        )

        history[s["symbol"]]=now

        with open(HISTORY_FILE,"w") as f:
            json.dump(history,f)

        print("Telegram sent.")
    else:
        print("Signal already sent recently.")
else:
    print("No Telegram message sent.")

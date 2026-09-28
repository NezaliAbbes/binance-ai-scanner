import requests
import pandas as pd
import numpy as np

BASE = "https://api.binance.com"

print("="*50)
print("BINANCE AI SCANNER")
print("FAST PRECISION MODE")
print("="*50)

# عدادات التشخيص
stats = {
    "total": 0,
    "rsi": 0,
    "volume": 0,
    "trend": 0,
    "breakout": 0,
    "qualified": 0
}

best = []

# أزواج USDT
pairs = [
    s["symbol"] for s in requests.get(f"{BASE}/api/v3/exchangeInfo").json()["symbols"]
    if s["quoteAsset"] == "USDT" and s["status"] == "TRADING"
]

print(f"USDT Spot pairs: {len(pairs)}")

for i, symbol in enumerate(pairs, 1):
    try:
        kl = requests.get(
            f"{BASE}/api/v3/klines?symbol={symbol}&interval=15m&limit=120",
            timeout=10
        ).json()

        if not isinstance(kl, list):
            continue

        df = pd.DataFrame(kl)
        close = df[4].astype(float)
        high = df[2].astype(float)
        low = df[3].astype(float)
        vol = df[5].astype(float)

        stats["total"] += 1

        # RSI
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = (100 - (100 / (1 + rs))).iloc[-1]

        if np.isnan(rsi) or not (45 <= rsi <= 68):
            continue
        stats["rsi"] += 1

        # حجم التداول
        vol_ratio = vol.iloc[-1] / vol.tail(20).mean()
        if vol_ratio < 1.8:
            continue
        stats["volume"] += 1

        # الاتجاه
        ema20 = close.ewm(span=20).mean().iloc[-1]
        ema50 = close.ewm(span=50).mean().iloc[-1]
        if ema20 <= ema50:
            continue
        stats["trend"] += 1

        # الاختراق
        if close.iloc[-1] <= high.tail(20).max() * 0.995:
            continue
        stats["breakout"] += 1

        entry = close.iloc[-1]
        stop = low.tail(10).min()
        risk = entry - stop

        if risk <= 0:
            continue

        tp1 = entry + risk * 1.5
        tp2 = entry + risk * 2.5
        tp3 = entry + risk * 4

        score = (
            min(vol_ratio * 15, 40) +
            (68 - abs(rsi - 56)) +
            20
        )

        rr = round((tp3 - entry) / risk, 2)

        stats["qualified"] += 1

        best.append({
            "symbol": symbol,
            "score": round(score),
            "rsi": round(rsi, 1),
            "vol": round(vol_ratio, 2),
            "entry": round(entry, 6),
            "stop": round(stop, 6),
            "tp1": round(tp1, 6),
            "tp2": round(tp2, 6),
            "tp3": round(tp3, 6),
            "rr": rr
        })

    except:
        pass

    if i % 100 == 0:
        print(f"Scanned: {i}/{len(pairs)}")

best = sorted(best, key=lambda x: x["score"], reverse=True)

print("\n" + "="*50)
print("DIAGNOSTIC")
print("="*50)
print(f"Total scanned : {stats['total']}")
print(f"Passed RSI    : {stats['rsi']}")
print(f"Passed Volume : {stats['volume']}")
print(f"Passed Trend  : {stats['trend']}")
print(f"Passed Breakout: {stats['breakout']}")
print(f"Qualified     : {stats['qualified']}")

print("\n" + "="*50)
print("TOP OPPORTUNITIES")
print("="*50)

if not best:
    print("No qualified signals.")
else:
    for s in best[:10]:
        print(
            f"{s['symbol']} | Score {s['score']} | RSI {s['rsi']} | "
            f"Vol x{s['vol']} | RR 1:{s['rr']}"
        )

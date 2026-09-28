import requests
import pandas as pd
import numpy as np

BASE = "https://data-api.binance.vision"

print("=" * 50)
print("BINANCE AI SCANNER")
print("FAST PRECISION MODE")
print("=" * 50)

stats = {
    "total": 0,
    "rsi": 0,
    "volume": 0,
    "trend": 0,
    "breakout": 0,
    "qualified": 0
}

best = []

# جلب أزواج USDT
try:
    r = requests.get(f"{BASE}/api/v3/exchangeInfo", timeout=20)
    r.raise_for_status()
    data = r.json()

    pairs = [
        s["symbol"] for s in data["symbols"]
        if s["quoteAsset"] == "USDT" and s["status"] == "TRADING"
    ]
except Exception as e:
    print(f"ERROR loading pairs: {e}")
    exit()

print(f"USDT Spot pairs: {len(pairs)}")

for i, symbol in enumerate(pairs, 1):
    try:
        kl = requests.get(
            f"{BASE}/api/v3/klines?symbol={symbol}&interval=15m&limit=120",
            timeout=10
        )
        kl.raise_for_status()
        kl = kl.json()

        if not isinstance(kl, list) or len(kl) < 60:
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
        ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]

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

        rr = round((tp3 - entry) / risk, 2)

        score = (
            min(vol_ratio * 15, 40)
            + (68 - abs(rsi - 56))
            + 20
        )

        stats["qualified"] += 1

        best.append({
            "symbol": symbol,
            "score": round(score),
            "rsi": round(rsi, 1),
            "vol": round(vol_ratio, 2),
            "entry": round(entry,

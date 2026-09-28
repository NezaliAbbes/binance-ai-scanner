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
    raise SystemExit

print(f"USDT Spot pairs: {len(pairs)}")

for i, symbol in enumerate(pairs, 1):
    try:
        response = requests.get(
            f"{BASE}/api/v3/klines?symbol={symbol}&interval=15m&limit=120",
            timeout=10
        )
        response.raise_for_status()
        kl = response.json()

        if not isinstance(kl, list) or len(kl) < 60:
            continue

        df = pd.DataFrame(kl)

        close = df[4].astype(float)
        high = df[2].astype(float)
        low = df[3].astype(float)
        vol = df[5].astype(float)

        stats["total"] += 1

        # RSI (آخر شمعة مغلقة)
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = (100 - (100 / (1 + rs))).iloc[-2]

        if np.isnan(rsi) or not (45 <= rsi <= 68):
            continue
        stats["rsi"] += 1

        # حجم التداول (آخر شمعة مغلقة)
        last_vol = vol.iloc[-2]
        avg_vol = vol.iloc[-22:-2].mean()
        vol_ratio = last_vol / avg_vol

        if vol_ratio < 1.3:
            continue
        stats["volume"] += 1

        # الاتجاه
        ema20 = close.ewm(span=20, adjust=False).mean().iloc[-2]
        ema50 = close.ewm(span=50, adjust=False).mean().iloc[-2]

        if ema20 <= ema50:
            continue
        stats["trend"] += 1

        # الاختراق
        last_close = close.iloc[-2]
        highest20 = high.iloc[-22:-2].max()

        if last_close <= highest20 * 0.998:
            continue
        stats["breakout"] += 1

        entry = last_close
        stop = low.iloc[-12:-2].min()
        risk = entry - stop

        if risk <= 0:
            continue

        tp1 = entry + risk * 1.5
        tp2 = entry + risk * 2.5
        tp3 = entry + risk * 4

        rr = round((tp3 - entry) / risk, 2)

        score = (
            min(vol_ratio * 20, 40)
            + (68 - abs(rsi - 56))
            + 20
        )

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

    except Exception:
        continue

    if i % 100 == 0:
        print(f"Scanned: {i}/{len(pairs)}")

best = sorted(best, key=lambda x: x["score"], reverse=True)

print("\n" + "=" * 50)
print("DIAGNOSTIC")
print("=" * 50)
print(f"Total scanned   : {stats['total']}")
print(f"Passed RSI      : {stats['rsi']}")
print(f"Passed Volume   : {stats['volume']}")
print(f"Passed Trend    : {stats['trend']}")
print(f"Passed Breakout : {stats['breakout']}")
print(f"Qualified       : {stats['qualified']}")

print("\n" + "=" * 50)
print("TOP OPPORTUNITIES")
print("=" * 50)

if not best:
    print("No qualified signals.")
else:
    for s in best[:10]:
        print(
            f"{s['symbol']} | Score {s['score']} | "
            f"RSI {s['rsi']} | Vol x{s['vol']} | RR 1:{s['rr']}"
        )
        print(f" Entry : {s['entry']}")
        print(f" Stop  : {s['stop']}")
        print(f" TP1   : {s['tp1']}")
        print(f" TP2   : {s['tp2']}")
        print(f" TP3   : {s['tp3']}")
        print("-" * 50)

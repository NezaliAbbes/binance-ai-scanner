
import os
import json
import time
import requests
from chart import save_chart

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BASE = "https://data-api.binance.vision"

INTERVAL = "5m"
CONFIRM_INTERVAL = "15m"
LIMIT = 120

MIN_SCORE = 60
MAX_SIGNALS = 3
COOLDOWN = 3600

session = requests.Session()


def send_photo(photo_path, caption):
    with open(photo_path, "rb") as img:
        session.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            data={"chat_id": CHAT_ID, "caption": caption},
            files={"photo": img},
            timeout=20,
        )


def get_json(endpoint, params=None):
    r = session.get(BASE + endpoint, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def load_signals():
    try:
        with open("signals.json", "r") as f:
            return json.load(f)
    except:
        return {}


def save_signals(data):
    with open("signals.json", "w") as f:
        json.dump(data, f)


def ema(values, period):
    if len(values) < period:
        return None

    value = sum(values[:period]) / period
    k = 2 / (period + 1)

    for p in values[period:]:
        value = (p - value) * k + value

    return value


def rsi(values, period=14):
    if len(values) <= period:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def confirm_trend(symbol):
    try:
        klines = get_json(
            "/api/v3/klines",
            {
                "symbol": symbol,
                "interval": CONFIRM_INTERVAL,
                "limit": 60,
            },
        )

        closes = [float(k[4]) for k in klines]

        e20 = ema(closes, 20)
        e50 = ema(closes, 50)
        r = rsi(closes)

        if None in (e20, e50, r):
            return False

        return closes[-1] > e20 and e20 > e50 and r > 50

    except Exception:
        return False


def btc_market_ok():
    try:
        klines = get_json(
            "/api/v3/klines",
            {
                "symbol": "BTCUSDT",
                "interval": "15m",
                "limit": 60,
            },
        )

        closes = [float(k[4]) for k in klines]

        e20 = ema(closes, 20)
        e50 = ema(closes, 50)
        r = rsi(closes)

        return closes[-1] > e20 and e20 > e50 and r > 50

    except Exception:
        return True


print("BINANCE AI SCANNER PRO 2.2 STARTED")

market_ok = btc_market_ok()

data = get_json("/api/v3/exchangeInfo")

symbols = [
    s["symbol"]
    for s in data["symbols"]
    if s["status"] == "TRADING"
    and s["quoteAsset"] == "USDT"
    and s["isSpotTradingAllowed"]
]

print(f"Pairs: {len(symbols)}")

sent = load_signals()
signals = []

for i, symbol in enumerate(symbols, 1):

    print(f"[{i}/{len(symbols)}] {symbol}")

    try:

        klines = get_json(
            "/api/v3/klines",
            {
                "symbol": symbol,
                "interval": INTERVAL,
                "limit": LIMIT,
            },
        )

        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        volumes = [float(k[5]) for k in klines]

        price = closes[-1]

        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)
        r = rsi(closes)

        if None in (ema20, ema50, r):
            continue

        score = 0
        reasons = []

        if price > ema20:
            score += 20
            reasons.append("Price above EMA20")

        if ema20 > ema50:
            score += 20
            reasons.append("EMA20 above EMA50")

        # فلتر RSI النهائي (Pro 2.2)
if 50 <= r <= 65:
    score += 20
    reasons.append(f"Perfect RSI {r:.1f}")
elif 65 < r <= 70:
    score += 10
    reasons.append(f"High RSI {r:.1f}")
else:
    continue

        avg_volume = sum(volumes[-21:-1]) / 20
        vr = volumes[-1] / avg_volume if avg_volume else 0

        if vr >= 2.0:
            score += 25
            reasons.append(f"Strong volume x{vr:.2f}")
        elif vr >= 1.5:
            score += 15
            reasons.append(f"Good volume x{vr:.2f}")
        else:
            continue

        if price > max(highs[-21:-1]):
            score += 20
            reasons.append("Breakout")

        momentum = ((price / closes[-6]) - 1) * 100

        if 0.5 <= momentum <= 4:
            score += 15
            reasons.append(f"Strong momentum +{momentum:.2f}%")
        else:
            continue

        if not market_ok:
            score -= 20
            reasons.append("BTC market weak")

        stop = min(lows[-20:])
        risk = price - stop

        if risk <= 0:
            continue

        tp1 = price + risk * 1.5
        tp2 = price + risk * 2
        tp3 = price + risk * 3

        reward_percent = ((tp1 - price) / price) * 100

        if reward_percent < 2:
            continue

        if score >= MIN_SCORE and confirm_trend(symbol):

            signals.append(
                {
                    "symbol": symbol,
                    "price": price,
                    "score": min(score, 100),
                    "rsi": r,
                    "volume": vr,
                    "momentum": momentum,
                    "stop": stop,
                    "tp1": tp1,
                    "tp2": tp2,
                    "tp3": tp3,
                    "klines": klines,
                    "reasons": reasons,
                }
            )

    except Exception as e:
        print(symbol, e)

    time.sleep(0.05)

signals.sort(key=lambda x: x["score"], reverse=True)

print(f"Signals found: {len(signals)}")

now = int(time.time())

for s in signals[:MAX_SIGNALS]:

    last = sent.get(s["symbol"], 0)

    if now - last < COOLDOWN:
        continue

    filename = f"{s['symbol']}.png"

    save_chart(s, s["klines"], filename)

    reward = s["tp1"] - s["price"]
    risk_value = s["price"] - s["stop"]
    rr = reward / risk_value if risk_value > 0 else 0

    if rr >= 2:
        label = "🟢 STRONG BUY"
    elif rr >= 1.5:
        label = "🟡 GOOD SETUP"
    else:
        continue

    caption = f"""{label}

🪙 {s['symbol']}
💰 Price: {s['price']:g}
📊 Score: {s['score']}/100
📈 RSI: {s['rsi']:.1f}
📊 Volume: x{s['volume']:.2f}
🔥 Momentum: {s['momentum']:+.2f}%

🛑 Stop: {s['stop']:g}
🎯 TP1: {s['tp1']:g}
🎯 TP2: {s['tp2']:g}
🎯 TP3: {s['tp3']:g}
⚖️ Risk/Reward: 1:{rr:.2f}

📌 Reasons:
{chr(10).join("✅ " + r for r in s["reasons"])}
"""

    send_photo(filename, caption)

    sent[s["symbol"]] = now

    print(f"Sent: {s['symbol']}")

save_signals(sent)

print("SCAN COMPLETED")

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

# ============================================================
# SETTINGS
# ============================================================

MIN_SCORE = 72
COOLDOWN = 21600  # 6 hours

print("=" * 55)
print("BINANCE AI SCANNER PRO 3.1")
print("=" * 55)

# ============================================================
# HISTORY
# ============================================================

if os.path.exists(HISTORY_FILE):
    try:
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
    except Exception:
        history = {}
else:
    history = {}

# ============================================================
# BINANCE SPOT PAIRS
# ============================================================

try:
    response = requests.get(
        f"{BASE}/api/v3/exchangeInfo",
        timeout=20
    )

    data = response.json()

    pairs = [
        s["symbol"]
        for s in data["symbols"]
        if s["quoteAsset"] == "USDT"
        and s["status"] == "TRADING"
        and s.get("isSpotTradingAllowed", False)
    ]

except Exception as e:
    print("ExchangeInfo Error:", e)
    raise SystemExit

print(f"USDT Spot pairs: {len(pairs)}")

# ============================================================
# INDICATORS
# ============================================================

def rsi_calc(close, period=14):

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    return 100 - (100 / (1 + rs))


def atr_calc(high, low, close, period=14):

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    return tr.rolling(period).mean()


def macd_calc(close):

    ema12 = close.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False
    ).mean()

    macd = ema12 - ema26

    signal = macd.ewm(
        span=9,
        adjust=False
    ).mean()

    histogram = macd - signal

    return macd, signal, histogram


def adx_calc(high, low, close, period=14):

    up = high.diff()
    down = -low.diff()

    plus_dm = np.where(
        (up > down) & (up > 0),
        up,
        0
    )

    minus_dm = np.where(
        (down > up) & (down > 0),
        down,
        0
    )

    atr = atr_calc(
        high,
        low,
        close,
        period
    )

    plus_di = (
        100 *
        pd.Series(plus_dm).rolling(period).mean()
        / atr
    )

    minus_di = (
        100 *
        pd.Series(minus_dm).rolling(period).mean()
        / atr
    )

    denominator = (
        plus_di + minus_di
    ).replace(0, np.nan)

    dx = (
        100 *
        (plus_di - minus_di).abs()
        / denominator
    )

    return dx.rolling(period).mean()


# ============================================================
# SCANNER
# ============================================================

candidates = []
best_raw = []

for i, symbol in enumerate(pairs, 1):

    try:

        response = requests.get(
            f"{BASE}/api/v3/klines",
            params={
                "symbol": symbol,
                "interval": "15m",
                "limit": 150
            },
            timeout=10
        )

        kl = response.json()

        if not isinstance(kl, list):
            continue

        if len(kl) < 100:
            continue

        df = pd.DataFrame(kl)

        open_price = df[1].astype(float)
        high = df[2].astype(float)
        low = df[3].astype(float)
        close = df[4].astype(float)
        volume = df[5].astype(float)

        # ----------------------------------------------------
        # LAST CLOSED CANDLE
        # ----------------------------------------------------

        idx = -2

        entry = close.iloc[idx]

        # ----------------------------------------------------
        # RSI
        # ----------------------------------------------------

        rsi_series = rsi_calc(close)
        rsi = rsi_series.iloc[idx]

        if np.isnan(rsi):
            continue

        # Very broad RSI filter
        if rsi < 48 or rsi > 70:
            continue

        # ----------------------------------------------------
        # VOLUME
        # ----------------------------------------------------

        avg_volume = volume.iloc[-22:-2].mean()

        if avg_volume <= 0:
            continue

        volume_ratio = (
            volume.iloc[idx] /
            avg_volume
        )

        if volume_ratio < 1.30:
            continue

        # ----------------------------------------------------
        # EMA
        # ----------------------------------------------------

        ema20 = close.ewm(
            span=20,
            adjust=False
        ).mean()

        ema50 = close.ewm(
            span=50,
            adjust=False
        ).mean()

        ema20_now = ema20.iloc[idx]
        ema50_now = ema50.iloc[idx]

        # Main trend filter
        if ema20_now <= ema50_now:
            continue

        ema_distance = (
            (ema20_now - ema50_now)
            / ema50_now
        ) * 100

        # ----------------------------------------------------
        # MACD
        # ----------------------------------------------------

        macd, signal, histogram = macd_calc(close)

        macd_now = macd.iloc[idx]
        signal_now = signal.iloc[idx]
        hist_now = histogram.iloc[idx]

        if np.isnan(hist_now):
            continue

        # ----------------------------------------------------
        # ADX
        # ----------------------------------------------------

        adx_series = adx_calc(
            high,
            low,
            close
        )

        adx = adx_series.iloc[idx]

        if np.isnan(adx):
            continue

        if adx < 15:
            continue

        # ----------------------------------------------------
        # BREAKOUT / RESISTANCE
        # ----------------------------------------------------

        highest20 = high.iloc[-22:-2].max()

        distance_to_resistance = (
            (entry - highest20)
            / highest20
        ) * 100

        # We allow near-breakouts
        # Price cannot be more than 0.8% below resistance

        if distance_to_resistance < -0.8:
            continue

        # ----------------------------------------------------
        # CANDLE
        # ----------------------------------------------------

        candle_open = open_price.iloc[idx]
        candle_high = high.iloc[idx]
        candle_low = low.iloc[idx]

        candle_range = (
            candle_high - candle_low
        )

        if candle_range <= 0:
            continue

        body = abs(
            entry - candle_open
        )

        body_ratio = (
            body /
            candle_range
        )

        # Must be bullish
        if entry <= candle_open:
            continue

        if body_ratio < 0.30:
            continue

        # ----------------------------------------------------
        # ATR
        # ----------------------------------------------------

        atr_series = atr_calc(
            high,
            low,
            close
        )

        atr = atr_series.iloc[idx]

        if np.isnan(atr) or atr <= 0:
            continue

        # ----------------------------------------------------
        # STOP
        # ----------------------------------------------------

        recent_low = low.iloc[-12:-2].min()

        stop = recent_low

        risk = entry - stop

        if risk <= 0:
            continue

        # Do not allow very wide stop
        if risk > atr * 3.5:
            continue

        # ----------------------------------------------------
        # TARGETS
        # ----------------------------------------------------

        tp1 = entry + risk * 1.5
        tp2 = entry + risk * 2.5
        tp3 = entry + risk * 4.0

        # ====================================================
        # SCORE
        # ====================================================

        # ----------------------------------------------------
        # VOLUME / 25
        # ----------------------------------------------------

        volume_score = min(
            (volume_ratio / 3.0) * 25,
            25
        )

        # ----------------------------------------------------
        # RSI / 15
        # ----------------------------------------------------

        if 54 <= rsi <= 62:
            rsi_score = 15

        elif 51 <= rsi <= 65:
            rsi_score = 12

        elif 48 <= rsi <= 68:
            rsi_score = 9

        else:
            rsi_score = 6

        # ----------------------------------------------------
        # EMA TREND / 15
        # ----------------------------------------------------

        if ema_distance >= 1.5:
            ema_score = 15

        elif ema_distance >= 0.8:
            ema_score = 12

        elif ema_distance >= 0.3:
            ema_score = 9

        else:
            ema_score = 6

        # ----------------------------------------------------
        # MACD / 15
        # ----------------------------------------------------

        if (
            macd_now > signal_now
            and hist_now > 0
        ):

            macd_strength = abs(hist_now)

            base = max(
                abs(macd_now),
                1e-12
            )

            ratio = (
                macd_strength /
                base
            )

            if ratio >= 0.20:
                macd_score = 15

            elif ratio >= 0.10:
                macd_score = 12

            else:
                macd_score = 9

        elif hist_now > 0:

            macd_score = 7

        else:

            macd_score = 3

        # ----------------------------------------------------
        # ADX / 10
        # ----------------------------------------------------

        if adx >= 30:
            adx_score = 10

        elif adx >= 25:
            adx_score = 8

        elif adx >= 20:
            adx_score = 7

        elif adx >= 15:
            adx_score = 5

        else:
            adx_score = 2

        # ----------------------------------------------------
        # BREAKOUT / 10
        # ----------------------------------------------------

        if distance_to_resistance >= 1.0:
            breakout_score = 10

        elif distance_to_resistance >= 0.3:
            breakout_score = 9

        elif distance_to_resistance >= 0:
            breakout_score = 8

        elif distance_to_resistance >= -0.3:
            breakout_score = 7

        else:
            breakout_score = 5

        # ----------------------------------------------------
        # CANDLE / 10
        # ----------------------------------------------------

        if body_ratio >= 0.75:
            candle_score = 10

        elif body_ratio >= 0.60:
            candle_score = 8

        elif body_ratio >= 0.45:
            candle_score = 7

        else:
            candle_score = 5

        # ----------------------------------------------------
        # FINAL SCORE
        # ----------------------------------------------------

        score = round(
            volume_score
            + rsi_score
            + ema_score
            + macd_score
            + adx_score
            + breakout_score
            + candle_score
        )

        score = min(
            score,
            100
        )

        candidate = {
            "symbol": symbol,
            "score": score,
            "rsi": round(rsi, 1),
            "vol": round(volume_ratio, 2),
            "adx": round(adx, 1),
            "entry": entry,
            "stop": stop,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3
        }

        # Save every valid candidate
        best_raw.append(candidate)

        # Only strong candidates
        if score >= MIN_SCORE:
            candidates.append(candidate)

    except Exception:
        continue

    if i % 100 == 0:
        print(
            f"Scanned: {i}/{len(pairs)}"
        )

# ============================================================
# RESULTS
# ============================================================

best_raw = sorted(
    best_raw,
    key=lambda x: x["score"],
    reverse=True
)

candidates = sorted(
    candidates,
    key=lambda x: x["score"],
    reverse=True
)

print()
print(
    f"Valid candidates: {len(best_raw)}"
)

print(
    f"Qualified signals: {len(candidates)}"
)

# ============================================================
# DIAGNOSTIC
# ============================================================

if best_raw:

    print()
    print("TOP 5 SCORES")

    for x in best_raw[:5]:

        print(
            f"{x['symbol']} | "
            f"Score {x['score']} | "
            f"RSI {x['rsi']} | "
            f"Vol x{x['vol']} | "
            f"ADX {x['adx']}"
        )

else:

    print(
        "No valid candidates found."
    )

# ============================================================
# TELEGRAM
# ============================================================

if not TOKEN:

    print(
        "❌ Missing TELEGRAM_BOT_TOKEN"
    )

elif not CHAT_ID:

    print(
        "❌ Missing TELEGRAM_CHAT_ID"
    )

elif not candidates:

    print(
        "No signal above minimum score."
    )

else:

    s = candidates[0]

    now = time.time()

    # --------------------------------------------------------
    # COOLDOWN
    # --------------------------------------------------------

    if (
        s["symbol"] in history
        and
        now - history[s["symbol"]] < COOLDOWN
    ):

        print(
            "Signal already sent recently:",
            s["symbol"]
        )

    else:

        message = (
            "🚀 BINANCE AI SIGNAL\n\n"

            f"Pair: {s['symbol']}\n"

            f"Score: {s['score']}/100\n"

            f"RSI: {s['rsi']}\n"

            f"Volume: x{s['vol']}\n"

            f"ADX: {s['adx']}\n\n"

            f"Entry: {s['entry']:.6f}\n"

            f"Stop: {s['stop']:.6f}\n"

            f"TP1: {s['tp1']:.6f}\n"

            f"TP2: {s['tp2']:.6f}\n"

            f"TP3: {s['tp3']:.6f}"
        )

        try:

            r = requests.post(
                f"https://api.telegram.org/"
                f"bot{TOKEN}/sendMessage",

                data={
                    "chat_id": CHAT_ID,
                    "text": message
                },

                timeout=20
            )

            print(
                "Telegram API:",
                r.status_code
            )

            if r.status_code == 200:

                print(
                    "✅ Telegram sent."
                )

                history[s["symbol"]] = now

                with open(
                    HISTORY_FILE,
                    "w"
                ) as f:

                    json.dump(
                        history,
                        f
                    )

            else:

                print(
                    r.text
                )

        except Exception as e:

            print(
                "Telegram Error:",
                e
            )

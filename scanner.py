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

INTERVAL = "15m"
KLINE_LIMIT = 150

MIN_SCORE = 75
COOLDOWN = 21600          # 6 hours

MIN_VOLUME_RATIO = 1.30
MIN_ADX = 18

print("=" * 65)
print("BINANCE AI SCANNER PRO 5.1")
print("STRONG SIGNAL MODE")
print("=" * 65)


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

    response.raise_for_status()

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

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    return 100 - (100 / (1 + rs))


def atr_calc(high, low, close, period=14):

    previous_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - previous_close).abs()
    tr3 = (low - previous_close).abs()

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    return tr.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()


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

    plus_dm = pd.Series(
        np.where(
            (up > down) & (up > 0),
            up,
            0
        ),
        index=high.index
    )

    minus_dm = pd.Series(
        np.where(
            (down > up) & (down > 0),
            down,
            0
        ),
        index=high.index
    )

    atr = atr_calc(
        high,
        low,
        close,
        period
    )

    plus_di = (
        100
        * plus_dm.ewm(
            alpha=1 / period,
            adjust=False
        ).mean()
        / atr
    )

    minus_di = (
        100
        * minus_dm.ewm(
            alpha=1 / period,
            adjust=False
        ).mean()
        / atr
    )

    denominator = (
        plus_di + minus_di
    ).replace(0, np.nan)

    dx = (
        100
        * (plus_di - minus_di).abs()
        / denominator
    )

    return dx.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()


# ============================================================
# SCANNER
# ============================================================

candidates = []

scanned = 0
technical_candidates = 0

for i, symbol in enumerate(pairs, 1):

    try:

        response = requests.get(
            f"{BASE}/api/v3/klines",
            params={
                "symbol": symbol,
                "interval": INTERVAL,
                "limit": KLINE_LIMIT
            },
            timeout=8
        )

        if response.status_code != 200:
            continue

        klines = response.json()

        if not isinstance(klines, list):
            continue

        if len(klines) < 100:
            continue

        df = pd.DataFrame(klines)

        open_price = df[1].astype(float)
        high = df[2].astype(float)
        low = df[3].astype(float)
        close = df[4].astype(float)
        volume = df[5].astype(float)

        scanned += 1

        # ====================================================
        # LAST CLOSED CANDLE
        # ====================================================

        idx = -2

        entry = close.iloc[idx]

        # ====================================================
        # RSI
        # ====================================================

        rsi_series = rsi_calc(close)
        rsi = rsi_series.iloc[idx]

        if np.isnan(rsi):
            continue

        if rsi < 48 or rsi > 72:
            continue

        # ====================================================
        # VOLUME
        # ====================================================

        average_volume = volume.iloc[-22:-2].mean()

        if average_volume <= 0:
            continue

        volume_ratio = (
            volume.iloc[idx] / average_volume
        )

        if volume_ratio < MIN_VOLUME_RATIO:
            continue

        # ====================================================
        # EMA
        # ====================================================

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

        ema_distance = (
            (ema20_now - ema50_now)
            / ema50_now
        ) * 100

        # Price should be above EMA20
        if entry < ema20_now:
            continue

        # ====================================================
        # MACD
        # ====================================================

        macd, signal, histogram = macd_calc(close)

        macd_now = macd.iloc[idx]
        signal_now = signal.iloc[idx]
        hist_now = histogram.iloc[idx]

        if np.isnan(hist_now):
            continue

        if hist_now < 0:
            continue

        # ====================================================
        # ADX
        # ====================================================

        adx_series = adx_calc(
            high,
            low,
            close
        )

        adx = adx_series.iloc[idx]

        if np.isnan(adx):
            continue

        if adx < MIN_ADX:
            continue

        # ====================================================
        # RESISTANCE
        # ====================================================

        highest20 = high.iloc[-22:-2].max()

        distance_to_resistance = (
            (entry - highest20)
            / highest20
        ) * 100

        if distance_to_resistance < -1.0:
            continue

        # ====================================================
        # CANDLE
        # ====================================================

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
            body / candle_range
        )

        bullish = entry > candle_open

        # ====================================================
        # ATR
        # ====================================================

        atr_series = atr_calc(
            high,
            low,
            close
        )

        atr = atr_series.iloc[idx]

        if np.isnan(atr) or atr <= 0:
            continue

        # ====================================================
        # STOP
        # ====================================================

        recent_low = low.iloc[-12:-2].min()

        stop = recent_low

        risk = entry - stop

        if risk <= 0:
            continue

        if risk > atr * 3.5:
            continue

        if risk < atr * 0.30:
            continue

        # ====================================================
        # TARGETS
        # ====================================================

        tp1 = entry + risk * 1.5
        tp2 = entry + risk * 2.5
        tp3 = entry + risk * 4.0

        # ====================================================
        # SCORE
        # ====================================================

        score = 0

        # ----------------------------------------------------
        # VOLUME / 20
        # ----------------------------------------------------

        if volume_ratio >= 5.0:
            volume_score = 20
        elif volume_ratio >= 3.5:
            volume_score = 18
        elif volume_ratio >= 2.5:
            volume_score = 16
        elif volume_ratio >= 2.0:
            volume_score = 14
        elif volume_ratio >= 1.5:
            volume_score = 12
        else:
            volume_score = 9

        score += volume_score

        # ----------------------------------------------------
        # RSI / 15
        # ----------------------------------------------------

        if 55 <= rsi <= 63:
            rsi_score = 15
        elif 52 <= rsi <= 66:
            rsi_score = 13
        elif 48 <= rsi <= 70:
            rsi_score = 10
        else:
            rsi_score = 7

        score += rsi_score

        # ----------------------------------------------------
        # EMA / 15
        # ----------------------------------------------------

        if ema_distance >= 2.0:
            ema_score = 15
        elif ema_distance >= 1.2:
            ema_score = 14
        elif ema_distance >= 0.8:
            ema_score = 12
        elif ema_distance >= 0.4:
            ema_score = 10
        elif ema_distance >= 0:
            ema_score = 8
        else:
            ema_score = 5

        score += ema_score

        # ----------------------------------------------------
        # MACD / 15
        # ----------------------------------------------------

        macd_base = max(
            abs(macd_now),
            1e-12
        )

        macd_ratio = (
            abs(hist_now)
            / macd_base
        )

        if hist_now > 0 and macd_ratio >= 0.25:
            macd_score = 15
        elif hist_now > 0 and macd_ratio >= 0.18:
            macd_score = 14
        elif hist_now > 0 and macd_ratio >= 0.10:
            macd_score = 12
        elif hist_now > 0:
            macd_score = 9
        else:
            macd_score = 4

        score += macd_score

        # ----------------------------------------------------
        # ADX / 15
        # ----------------------------------------------------

        if adx >= 40:
            adx_score = 15
        elif adx >= 35:
            adx_score = 14
        elif adx >= 30:
            adx_score = 13
        elif adx >= 25:
            adx_score = 11
        elif adx >= 20:
            adx_score = 9
        else:
            adx_score = 7

        score += adx_score

        # ----------------------------------------------------
        # BREAKOUT / 10
        # ----------------------------------------------------

        if distance_to_resistance >= 1.0:
            breakout_score = 10
        elif distance_to_resistance >= 0.5:
            breakout_score = 9
        elif distance_to_resistance >= 0.2:
            breakout_score = 8
        elif distance_to_resistance >= 0:
            breakout_score = 7
        elif distance_to_resistance >= -0.25:
            breakout_score = 5
        else:
            breakout_score = 3

        score += breakout_score

        # ----------------------------------------------------
        # CANDLE / 10
        # ----------------------------------------------------

        if bullish and body_ratio >= 0.80:
            candle_score = 10
        elif bullish and body_ratio >= 0.65:
            candle_score = 9
        elif bullish and body_ratio >= 0.50:
            candle_score = 8
        elif bullish and body_ratio >= 0.35:
            candle_score = 6
        elif bullish:
            candle_score = 5
        else:
            candle_score = 3

        score += candle_score

        score = min(
            round(score),
            100
        )

        technical_candidates += 1

        # ====================================================
        # CANDIDATE
        # ====================================================

        candidate = {
            "symbol": symbol,
            "score": score,
            "rsi": round(rsi, 1),
            "vol": round(volume_ratio, 2),
            "adx": round(adx, 1),
            "ema_distance": round(ema_distance, 2),
            "breakout": round(distance_to_resistance, 2),
            "entry": entry,
            "stop": stop,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3
        }

        candidates.append(candidate)

    except Exception as e:
        continue

    if i % 100 == 0:
        print(
            f"Scanned: {i}/{len(pairs)}"
        )


# ============================================================
# RESULTS
# ============================================================

candidates = sorted(
    candidates,
    key=lambda x: x["score"],
    reverse=True
)

strong_candidates = [
    x for x in candidates
    if x["score"] >= MIN_SCORE
]

print()
print(
    f"Technical candidates: {technical_candidates}"
)

print(
    f"Signals >= {MIN_SCORE}: "
    f"{len(strong_candidates)}"
)


# ============================================================
# TOP 10
# ============================================================

if candidates:

    print()
    print("=" * 65)
    print("TOP 10 CANDIDATES")
    print("=" * 65)

    for x in candidates[:10]:

        print(
            f"{x['symbol']} | "
            f"Score {x['score']} | "
            f"RSI {x['rsi']} | "
            f"Vol x{x['vol']} | "
            f"ADX {x['adx']} | "
            f"EMA {x['ema_distance']}%"
        )

else:

    print()
    print("No technical candidates found.")


# ============================================================
# TELEGRAM
# ============================================================

if not TOKEN:

    print()
    print("❌ Missing TELEGRAM_BOT_TOKEN")

elif not CHAT_ID:

    print()
    print("❌ Missing TELEGRAM_CHAT_ID")

elif not strong_candidates:

    print()
    print(
        f"No signal above minimum score {MIN_SCORE}."
    )

else:

    # ========================================================
    # STRONGEST SIGNAL
    # ========================================================

    signal = strong_candidates[0]

    now = time.time()

    last_sent = history.get(
        signal["symbol"],
        0
    )

    # ========================================================
    # COOLDOWN
    # ========================================================

    if now - last_sent < COOLDOWN:

        remaining = int(
            (
                COOLDOWN
                - (now - last_sent)
            ) / 60
        )

        print()
        print(
            f"⏳ {signal['symbol']} "
            f"is still in cooldown."
        )

        print(
            f"Remaining: {remaining} minutes"
        )

    else:

        # ====================================================
        # SIGNAL LEVEL
        # ====================================================

        if signal["score"] >= 90:
            level = "🔥 VERY STRONG"

        elif signal["score"] >= 85:
            level = "🚀 STRONG"

        elif signal["score"] >= 80:
            level = "⚡ GOOD"

        else:
            level = "📊 SIGNAL"

        # ====================================================
        # MESSAGE
        # ====================================================

        message = (
            f"{level} BINANCE AI SIGNAL\n\n"
            f"Pair: {signal['symbol']}\n"
            f"Score: {signal['score']}/100\n"
            f"RSI: {signal['rsi']}\n"
            f"Volume: x{signal['vol']}\n"
            f"ADX: {signal['adx']}\n"
            f"EMA Trend: +{signal['ema_distance']}%\n\n"
            f"Entry: {signal['entry']:.8f}\n"
            f"Stop: {signal['stop']:.8f}\n"
            f"TP1: {signal['tp1']:.8f}\n"
            f"TP2: {signal['tp2']:.8f}\n"
            f"TP3: {signal['tp3']:.8f}\n\n"
            f"Timeframe: 15m\n"
            f"Spot only"
        )

        # ====================================================
        # SEND TELEGRAM
        # ====================================================

        try:

            telegram_response = requests.post(
                f"https://api.telegram.org/"
                f"bot{TOKEN}/sendMessage",
                data={
                    "chat_id": CHAT_ID,
                    "text": message
                },
                timeout=20
            )

            print()
            print(
                "Telegram API:",
                telegram_response.status_code
            )

            if telegram_response.status_code == 200:

                print(
                    "✅ Telegram signal sent."
                )

                history[signal["symbol"]] = now

                with open(
                    HISTORY_FILE,
                    "w"
                ) as f:

                    json.dump(
                        history,
                        f,
                        indent=2
                    )

            else:

                print(
                    "❌ Telegram Error:"
                )

                print(
                    telegram_response.text
                )

        except Exception as e:

            print(
                "❌ Telegram Exception:",
                e
            )


import os
import json
import time
import requests
from chart import save_chart

# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BASE = "https://data-api.binance.vision"

INTERVAL = "5m"
LIMIT = 150

MIN_SCORE = 70
MAX_SIGNALS = 3
COOLDOWN = 3600

session = requests.Session()


# =========================================================
# TELEGRAM
# =========================================================

def send_photo(photo_path, caption):
    try:
        with open(photo_path, "rb") as img:
            response = session.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                data={
                    "chat_id": CHAT_ID,
                    "caption": caption
                },
                files={
                    "photo": img
                },
                timeout=30
            )

        if response.ok:
            print("Telegram message sent")
        else:
            print("Telegram error:", response.text)

    except Exception as e:
        print("Telegram exception:", e)


# =========================================================
# BINANCE
# =========================================================

def get_json(endpoint, params=None):
    try:
        response = session.get(
            BASE + endpoint,
            params=params,
            timeout=20
        )

        response.raise_for_status()

        return response.json()

    except Exception as e:
        print("Binance error:", e)
        return None


# =========================================================
# SIGNAL MEMORY
# =========================================================

def load_signals():
    try:
        with open("signals.json", "r") as file:
            return json.load(file)
    except Exception:
        return {}


def save_signals(data):
    try:
        with open("signals.json", "w") as file:
            json.dump(data, file)
    except Exception as e:
        print("signals.json error:", e)


# =========================================================
# INDICATORS
# =========================================================

def ema(values, period):
    if len(values) < period:
        return None

    value = sum(values[:period]) / period
    multiplier = 2 / (period + 1)

    for price in values[period:]:
        value = (
            (price - value) * multiplier
            + value
        )

    return value


def rsi(values, period=14):
    if len(values) <= period:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]

        if change >= 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (
            avg_gain * (period - 1)
            + gains[i]
        ) / period

        avg_loss = (
            avg_loss * (period - 1)
            + losses[i]
        ) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def atr(klines, period=14):
    if len(klines) < period + 1:
        return None

    trs = []

    for i in range(1, len(klines)):
        high = float(klines[i][2])
        low = float(klines[i][3])
        previous_close = float(klines[i - 1][4])

        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

        trs.append(tr)

    return sum(trs[-period:]) / period


# =========================================================
# MULTI TIMEFRAME TREND
# =========================================================

def timeframe_trend(symbol, interval):
    try:
        klines = get_json(
            "/api/v3/klines",
            {
                "symbol": symbol,
                "interval": interval,
                "limit": 100
            }
        )

        if not klines or len(klines) < 60:
            return False

        closes = [
            float(k[4])
            for k in klines
        ]

        price = closes[-1]

        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)

        if ema20 is None or ema50 is None:
            return False

        return (
            price > ema20
            and ema20 > ema50
        )

    except Exception:
        return False


# =========================================================
# BTC FILTER
# =========================================================

def btc_market_ok():
    try:
        klines = get_json(
            "/api/v3/klines",
            {
                "symbol": "BTCUSDT",
                "interval": "15m",
                "limit": 100
            }
        )

        if not klines:
            return False

        closes = [
            float(k[4])
            for k in klines
        ]

        e20 = ema(closes, 20)
        e50 = ema(closes, 50)
        r = rsi(closes)

        if e20 is None or e50 is None or r is None:
            return False

        return (
            closes[-1] > e20
            and e20 > e50
            and r >= 50
        )

    except Exception as e:
        print("BTC filter error:", e)
        return False


# =========================================================
# ORDER BOOK
# =========================================================

def order_book_analysis(symbol):
    try:
        data = get_json(
            "/api/v3/depth",
            {
                "symbol": symbol,
                "limit": 100
            }
        )

        if not data:
            return None

        bids = data.get("bids", [])
        asks = data.get("asks", [])

        if not bids or not asks:
            return None

        bid_volume = sum(
            float(x[1])
            for x in bids
        )

        ask_volume = sum(
            float(x[1])
            for x in asks
        )

        if ask_volume <= 0:
            return None

        ratio = bid_volume / ask_volume

        return ratio

    except Exception:
        return None


# =========================================================
# MAIN SCANNER
# =========================================================

def main():

    print("========================================")
    print("BINANCE AI SCANNER PRO MAX STARTED")
    print("========================================")

    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials missing")
        return

    btc_ok = btc_market_ok()

    print(
        "BTC Market:",
        "BULLISH" if btc_ok else "WEAK"
    )

    exchange = get_json(
        "/api/v3/exchangeInfo"
    )

    if not exchange:
        print("Exchange information unavailable")
        return

    symbols = []

    for item in exchange.get("symbols", []):

        if item.get("status") != "TRADING":
            continue

        if item.get("quoteAsset") != "USDT":
            continue

        if item.get("isSpotTradingAllowed") is not True:
            continue

        symbol = item.get("symbol")

        if symbol:
            symbols.append(symbol)

    print(
        f"USDT Spot pairs: {len(symbols)}"
    )

    old_signals = load_signals()

    candidates = []

    for number, symbol in enumerate(symbols, 1):

        print(
            f"[{number}/{len(symbols)}] {symbol}"
        )

        try:

            # -----------------------------------------
            # 5M DATA
            # -----------------------------------------

            klines = get_json(
                "/api/v3/klines",
                {
                    "symbol": symbol,
                    "interval": INTERVAL,
                    "limit": LIMIT
                }
            )

            if not klines or len(klines) < 100:
                continue

            closes = [
                float(k[4])
                for k in klines
            ]

            highs = [
                float(k[2])
                for k in klines
            ]

            lows = [
                float(k[3])
                for k in klines
            ]

            volumes = [
                float(k[5])
                for k in klines
            ]

            price = closes[-1]

            # -----------------------------------------
            # INDICATORS
            # -----------------------------------------

            ema20 = ema(closes, 20)
            ema50 = ema(closes, 50)
            ema200 = ema(closes, 100)

            r = rsi(closes, 14)
            current_atr = atr(klines, 14)

            if (
                ema20 is None
                or ema50 is None
                or ema200 is None
                or r is None
                or current_atr is None
            ):
                continue

            score = 0
            reasons = []

            # -----------------------------------------
            # PRICE / EMA
            # -----------------------------------------

            if price > ema20:

                score += 10

                reasons.append(
                    "Price above EMA20"
                )

            else:
                continue

            if ema20 > ema50:

                score += 10

                reasons.append(
                    "EMA20 above EMA50"
                )

            else:
                continue

            if price > ema200:

                score += 10

                reasons.append(
                    "Price above long-term EMA"
                )

            # -----------------------------------------
            # RSI
            # -----------------------------------------

            if 50 <= r <= 65:

                score += 15

                reasons.append(
                    f"Perfect RSI {r:.1f}"
                )

            elif 65 < r <= 70:

                score += 8

                reasons.append(
                    f"High RSI {r:.1f}"
                )

            else:
                continue

            # -----------------------------------------
            # VOLUME
            # -----------------------------------------

            average_volume = (
                sum(volumes[-21:-1])
                / 20
            )

            if average_volume <= 0:
                continue

            volume_ratio = (
                volumes[-1]
                / average_volume
            )

            if volume_ratio >= 3:

                score += 15

                reasons.append(
                    f"Extreme volume x{volume_ratio:.2f}"
                )

            elif volume_ratio >= 2:

                score += 12

                reasons.append(
                    f"Strong volume x{volume_ratio:.2f}"
                )

            elif volume_ratio >= 1.5:

                score += 7

                reasons.append(
                    f"Good volume x{volume_ratio:.2f}"
                )

            else:
                continue

            # -----------------------------------------
            # BREAKOUT
            # -----------------------------------------

            previous_high = max(
                highs[-21:-1]
            )

            breakout_percent = (
                (price - previous_high)
                / previous_high
            ) * 100

            if price > previous_high:

                score += 10

                reasons.append(
                    f"Breakout +{breakout_percent:.2f}%"
                )

            else:
                continue

            # -----------------------------------------
            # MOMENTUM
            # -----------------------------------------

            momentum = (
                (price / closes[-6])
                - 1
            ) * 100

            if 0.5 <= momentum <= 4:

                score += 8

                reasons.append(
                    f"Momentum +{momentum:.2f}%"
                )

            else:
                continue

            # -----------------------------------------
            # ATR / VOLATILITY
            # -----------------------------------------

            atr_percent = (
                current_atr / price
            ) * 100

            if 0.3 <= atr_percent <= 6:

                score += 5

                reasons.append(
                    f"Healthy volatility {atr_percent:.2f}%"
                )

            else:
                continue

            # -----------------------------------------
            # ORDER BOOK
            # -----------------------------------------

            book_ratio = order_book_analysis(
                symbol
            )

            if book_ratio is None:
                continue

            if book_ratio >= 1.30:

                score += 10

                reasons.append(
                    f"Buy pressure x{book_ratio:.2f}"
                )

            elif book_ratio >= 1.10:

                score += 5

                reasons.append(
                    f"Positive order book x{book_ratio:.2f}"
                )

            else:
                continue

            # -----------------------------------------
            # MULTI TIMEFRAME
            # -----------------------------------------

            trend_15m = timeframe_trend(
                symbol,
                "15m"
            )

            trend_1h = timeframe_trend(
                symbol,
                "1h"
            )

            if trend_15m:

                score += 5

                reasons.append(
                    "15m trend confirmed"
                )

            else:
                continue

            if trend_1h:

                score += 5

                reasons.append(
                    "1h trend confirmed"
                )

            # -----------------------------------------
            # BTC FILTER
            # -----------------------------------------

            if btc_ok:

                score += 5

                reasons.append(
                    "BTC market supportive"
                )

            else:

                score -= 10

                reasons.append(
                    "BTC market weak"
                )

            # -----------------------------------------
            # STOP / TAKE PROFITS
            # -----------------------------------------

            stop_distance = max(
                current_atr * 1.2,
                price * 0.01
            )

            stop = price - stop_distance

            if stop <= 0:
                continue

            risk = price - stop

            tp1 = price + risk * 1.5
            tp2 = price + risk * 2
            tp3 = price + risk * 3

            rr1 = (
                (tp1 - price)
                / risk
            )

            rr2 = (
                (tp2 - price)
                / risk
            )

            rr3 = (
                (tp3 - price)
                / risk
            )

            # -----------------------------------------
            # MINIMUM SCORE
            # -----------------------------------------

            if score < MIN_SCORE:
                continue

            candidates.append(
                {
                    "symbol": symbol,
                    "price": price,
                    "score": min(score, 100),
                    "rsi": r,
                    "volume": volume_ratio,
                    "momentum": momentum,
                    "atr": atr_percent,
                    "book_ratio": book_ratio,
                    "stop": stop,
                    "tp1": tp1,
                    "tp2": tp2,
                    "tp3": tp3,
                    "rr1": rr1,
                    "rr2": rr2,
                    "rr3": rr3,
                    "klines": klines,
                    "reasons": reasons
                }
            )

        except Exception as e:

            print(
                f"Analysis error {symbol}: {e}"
            )

        time.sleep(0.05)

    # =====================================================
    # SORT
    # =====================================================

    candidates.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    print(
        f"Qualified signals: {len(candidates)}"
    )

    # =====================================================
    # SEND
    # =====================================================

    now = int(time.time())

    sent_count = 0

    for signal in candidates:

        if sent_count >= MAX_SIGNALS:
            break

        symbol = signal["symbol"]

        last_time = old_signals.get(
            symbol,
            0
        )

        if (
            now - last_time
            < COOLDOWN
        ):
            print(
                f"Cooldown: {symbol}"
            )
            continue

        # ---------------------------------------------
        # LABEL
        # ---------------------------------------------

        if signal["score"] >= 90:

            label = "🟢 STRONG SETUP"

        elif signal["score"] >= 80:

            label = "🟢 HIGH QUALITY"

        else:

            label = "🟡 GOOD SETUP"

        # ---------------------------------------------
        # CHART
        # ---------------------------------------------

        filename = f"{symbol}.png"

        try:

            save_chart(
                signal,
                signal["klines"],
                filename
            )

        except Exception as e:

            print(
                f"Chart error {symbol}: {e}"
            )
            continue

        # ---------------------------------------------
        # REASONS
        # ---------------------------------------------

        reasons_text = "\n".join(
            "✅ " + reason
            for reason in signal["reasons"]
        )

        # ---------------------------------------------
        # TELEGRAM
        # ---------------------------------------------

        caption = (
            f"{label}\n\n"
            f"🪙 {symbol}\n"
            f"💰 Price: {signal['price']:g}\n"
            f"📊 Score: {signal['score']}/100\n"
            f"📈 RSI: {signal['rsi']:.1f}\n"
            f"📊 Volume: x{signal['volume']:.2f}\n"
            f"🔥 Momentum: +{signal['momentum']:.2f}%\n"
            f"📐 ATR: {signal['atr']:.2f}%\n"
            f"📚 Order Book: x{signal['book_ratio']:.2f}\n\n"
            f"🛑 Stop: {signal['stop']:g}\n"
            f"🎯 TP1: {signal['tp1']:g}\n"
            f"🎯 TP2: {signal['tp2']:g}\n"
            f"🎯 TP3: {signal['tp3']:g}\n\n"
            f"⚖️ RR TP1: 1:{signal['rr1']:.2f}\n"
            f"⚖️ RR TP2: 1:{signal['rr2']:.2f}\n"
            f"⚖️ RR TP3: 1:{signal['rr3']:.2f}\n\n"
            f"📌 Reasons:\n"
            f"{reasons_text}\n\n"
            f"⚠️ SPOT\n"
            f"Technical analysis only."
        )

        send_photo(
            filename,
            caption
        )

        old_signals[symbol] = now

        sent_count += 1

        print(
            f"Signal sent: {symbol}"
        )

    save_signals(old_signals)

    print("========================================")
    print("SCAN COMPLETED")
    print("========================================")


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()

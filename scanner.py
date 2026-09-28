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
                timeout=20
            )

        if response.ok:
            print("Telegram message sent")
        else:
            print("Telegram error:", response.text)

    except Exception as e:
        print("Telegram exception:", e)


def get_json(endpoint, params=None):
    try:
        response = session.get(
            BASE + endpoint,
            params=params,
            timeout=15
        )

        response.raise_for_status()

        return response.json()

    except Exception as e:
        print("Binance error:", e)
        return None


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

    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        average_gain = (
            (average_gain * (period - 1))
            + gains[i]
        ) / period

        average_loss = (
            (average_loss * (period - 1))
            + losses[i]
        ) / period

    if average_loss == 0:
        return 100

    relative_strength = average_gain / average_loss

    return 100 - (
        100 / (1 + relative_strength)
    )


def confirm_trend(symbol):
    try:
        klines = get_json(
            "/api/v3/klines",
            {
                "symbol": symbol,
                "interval": CONFIRM_INTERVAL,
                "limit": 60
            }
        )

        if not klines:
            return False

        closes = [
            float(kline[4])
            for kline in klines
        ]

        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)
        r = rsi(closes)

        if (
            ema20 is None
            or ema50 is None
            or r is None
        ):
            return False

        return (
            closes[-1] > ema20
            and ema20 > ema50
            and r > 50
        )

    except Exception as e:
        print(
            f"Trend error {symbol}:",
            e
        )
        return False


def btc_market_ok():
    try:
        klines = get_json(
            "/api/v3/klines",
            {
                "symbol": "BTCUSDT",
                "interval": "15m",
                "limit": 60
            }
        )

        if not klines:
            return True

        closes = [
            float(kline[4])
            for kline in klines
        ]

        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)
        r = rsi(closes)

        if (
            ema20 is None
            or ema50 is None
            or r is None
        ):
            return True

        return (
            closes[-1] > ema20
            and ema20 > ema50
            and r > 50
        )

    except Exception as e:
        print("BTC error:", e)
        return True


def main():

    print(
        "BINANCE AI SCANNER PRO 2.2 STARTED"
    )

    if not BOT_TOKEN:
        print("BOT_TOKEN missing")
        return

    if not CHAT_ID:
        print("CHAT_ID missing")
        return

    market_ok = btc_market_ok()

    print(
        "BTC market:",
        "OK" if market_ok else "WEAK"
    )

    data = get_json(
        "/api/v3/exchangeInfo"
    )

    if not data:
        print("Could not get Binance symbols")
        return

    symbols = []

    for item in data.get("symbols", []):

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

    sent = load_signals()

    signals = []

    for index, symbol in enumerate(
        symbols,
        1
    ):

        print(
            f"[{index}/{len(symbols)}] {symbol}"
        )

        try:

            klines = get_json(
                "/api/v3/klines",
                {
                    "symbol": symbol,
                    "interval": INTERVAL,
                    "limit": LIMIT
                }
            )

            if not klines:
                continue

            if len(klines) < 60:
                continue

            closes = [
                float(kline[4])
                for kline in klines
            ]

            highs = [
                float(kline[2])
                for kline in klines
            ]

            lows = [
                float(kline[3])
                for kline in klines
            ]

            volumes = [
                float(kline[5])
                for kline in klines
            ]

            price = closes[-1]

            ema20 = ema(
                closes,
                20
            )

            ema50 = ema(
                closes,
                50
            )

            r = rsi(
                closes,
                14
            )

            if (
                ema20 is None
                or ema50 is None
                or r is None
            ):
                continue

            score = 0
            reasons = []

            # EMA20
            if price > ema20:

                score += 20

                reasons.append(
                    "Price above EMA20"
                )

            # EMA50
            if ema20 > ema50:

                score += 20

                reasons.append(
                    "EMA20 above EMA50"
                )

            # RSI FILTER
            if 50 <= r <= 65:

                score += 20

                reasons.append(
                    f"Perfect RSI {r:.1f}"
                )

            elif 65 < r <= 70:

                score += 10

                reasons.append(
                    f"High RSI {r:.1f}"
                )

            else:

                continue

            # VOLUME
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

            if volume_ratio >= 2.0:

                score += 25

                reasons.append(
                    f"Strong volume x{volume_ratio:.2f}"
                )

            elif volume_ratio >= 1.5:

                score += 15

                reasons.append(
                    f"Good volume x{volume_ratio:.2f}"
                )

            else:

                continue

            # BREAKOUT
            previous_high = max(
                highs[-21:-1]
            )

            if price > previous_high:

                score += 20

                reasons.append(
                    "Breakout"
                )

            # MOMENTUM
            momentum = (
                (price / closes[-6])
                - 1
            ) * 100

            if 0.5 <= momentum <= 4:

                score += 15

                reasons.append(
                    f"Strong momentum "
                    f"+{momentum:.2f}%"
                )

            else:

                continue

            # BTC MARKET
            if not market_ok:

                score -= 20

                reasons.append(
                    "BTC market weak"
                )

            # STOP LOSS
            stop = min(
                lows[-20:]
            )

            risk = price - stop

            if risk <= 0:
                continue

            # TAKE PROFITS
            tp1 = price + (
                risk * 1.5
            )

            tp2 = price + (
                risk * 2
            )

            tp3 = price + (
                risk * 3
            )

            # TP1 MUST BE AT LEAST 2%
            reward_percent = (
                (tp1 - price)
                / price
            ) * 100

            if reward_percent < 2:
                continue

            # SCORE
            if score < MIN_SCORE:
                continue

            # 15M CONFIRMATION
            if not confirm_trend(symbol):
                continue

            signals.append(
                {
                    "symbol": symbol,
                    "price": price,
                    "score": min(
                        score,
                        100
                    ),
                    "rsi": r,
                    "volume": volume_ratio,
                    "momentum": momentum,
                    "stop": stop,
                    "tp1": tp1,
                    "tp2": tp2,
                    "tp3": tp3,
                    "klines": klines,
                    "reasons": reasons
                }
            )

        except Exception as e:

            print(
                f"Analysis error "
                f"{symbol}: {e}"
            )

        time.sleep(0.05)

    signals.sort(
        key=lambda signal:
        signal["score"],
        reverse=True
    )

    print(
        f"Signals found: "
        f"{len(signals)}"
    )

    now = int(
        time.time()
    )

    sent_count = 0

    for signal in signals:

        if sent_count >= MAX_SIGNALS:
            break

        symbol = signal["symbol"]

        last_sent = sent.get(
            symbol,
            0
        )

        if (
            now - last_sent
            < COOLDOWN
        ):
            continue

        risk_value = (
            signal["price"]
            - signal["stop"]
        )

        reward_value = (
            signal["tp1"]
            - signal["price"]
        )

        if risk_value <= 0:
            continue

        rr = (
            reward_value
            / risk_value
        )

        if rr >= 2:

            label = (
                "🟢 STRONG BUY"
            )

        elif rr >= 1.5:

            label = (
                "🟡 GOOD SETUP"
            )

        else:

            continue

        filename = (
            f"{symbol}.png"
        )

        try:

            save_chart(
                signal,
                signal["klines"],
                filename
            )

        except Exception as e:

            print(
                f"Chart error "
                f"{symbol}: {e}"
            )

            continue

        reasons_text = "\n".join(
            "✅ " + reason
            for reason
            in signal["reasons"]
        )

        caption = (
            f"{label}\n\n"
            f"🪙 {symbol}\n"
            f"💰 Price: "
            f"{signal['price']:g}\n"
            f"📊 Score: "
            f"{signal['score']}/100\n"
            f"📈 RSI: "
            f"{signal['rsi']:.1f}\n"
            f"📊 Volume: "
            f"x{signal['volume']:.2f}\n"
            f"🔥 Momentum: "
            f"{signal['momentum']:+.2f}%\n\n"
            f"🛑 Stop: "
            f"{signal['stop']:g}\n"
            f"🎯 TP1: "
            f"{signal['tp1']:g}\n"
            f"🎯 TP2: "
            f"{signal['tp2']:g}\n"
            f"🎯 TP3: "
            f"{signal['tp3']:g}\n"
            f"⚖️ Risk/Reward: "
            f"1:{rr:.2f}\n\n"
            f"📌 Reasons:\n"
            f"{reasons_text}\n\n"
            f"⚠️ SPOT\n"
            f"Technical analysis only."
        )

        send_photo(
            filename,
            caption
        )

        sent[symbol] = now

        sent_count += 1

        print(
            f"Signal sent: "
            f"{symbol}"
        )

    save_signals(sent)

    print(
        "SCAN COMPLETED"
    )


if __name__ == "__main__":
    main()

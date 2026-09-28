import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

import time
import requests
from telegram_bot import send
from signal_engine import analyze

BINANCE_BASE = "https://data-api.binance.vision"
INTERVAL = "5m"
KLINE_LIMIT = 120
MAX_SIGNALS = 3

session = requests.Session()


def get(endpoint, params=None):
    try:
        r = session.get(
            BINANCE_BASE + endpoint,
            params=params,
            timeout=15
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("Binance:", e)
        return None


def get_symbols():
    data = get("/api/v3/exchangeInfo")
    if not data:
        return []

    return [
        s["symbol"]
        for s in data["symbols"]
        if s["status"] == "TRADING"
        and s["quoteAsset"] == "USDT"
        and s["isSpotTradingAllowed"]
    ]


def message(sig):
    reasons = "\n".join("✅ " + r for r in sig["reasons"])

    return (
        "🚨 BINANCE SPOT SIGNAL 🚨\n\n"
        f"🪙 Coin: {sig['symbol']}\n"
        f"💰 Price: {sig['price']:g}\n"
        f"📊 Score: {sig['score']}/100\n"
        f"📈 RSI: {sig['rsi']:.1f}\n"
        f"📊 Volume: x{sig['volume']:.2f}\n"
        f"🔥 Momentum: {sig['momentum']:+.2f}%\n\n"
        "🎯 TRADE PLAN\n"
        f"🟢 Entry: {sig['entry_low']:g}-{sig['entry_high']:g}\n"
        f"🛑 Stop: {sig['stop']:g}\n"
        f"🎯 TP1: {sig['tp1']:g}\n"
        f"🎯 TP2: {sig['tp2']:g}\n"
        f"🎯 TP3: {sig['tp3']:g}\n\n"
        "📌 Reasons:\n"
        f"{reasons}"
    )


def main():
    print("BINANCE AI SCANNER PRO STARTED")

    symbols = get_symbols()
    print(f"Pairs: {len(symbols)}")

    signals = []

    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] {symbol}")

        klines = get(
            "/api/v3/klines",
            {
                "symbol": symbol,
                "interval": INTERVAL,
                "limit": KLINE_LIMIT
            }
        )

        if not klines:
            continue

        signal = analyze(symbol, klines)

        if signal:
            signals.append(signal)

        time.sleep(0.05)

    signals.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    print(f"Signals: {len(signals)}")

    for signal in signals[:MAX_SIGNALS]:
        send(message(signal))
        print(f"Sent: {signal['symbol']}")


if __name__ == "__main__":
    main()

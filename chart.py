import pandas as pd
import mplfinance as mpf

def save_chart(signal, klines, filename):
    df = pd.DataFrame(klines, columns=[
        "time","open","high","low","close","volume",
        "ct","qv","n","tb","tq","x"
    ])

    df["time"] = pd.to_datetime(df["time"], unit="ms")
    df.set_index("time", inplace=True)

    for c in ["open","high","low","close","volume"]:
        df[c] = df[c].astype(float)

    price = signal["price"]

    ap = [
        mpf.make_addplot([price]*len(df), color="lime"),
        mpf.make_addplot([signal["stop"]]*len(df), color="red"),
        mpf.make_addplot([signal["tp1"]]*len(df), color="green"),
        mpf.make_addplot([signal["tp2"]]*len(df), color="green"),
        mpf.make_addplot([signal["tp3"]]*len(df), color="green"),
    ]

    mpf.plot(
        df,
        type="candle",
        style="charles",
        volume=True,
        addplot=ap,
        title=signal["symbol"],
        savefig=filename
    )

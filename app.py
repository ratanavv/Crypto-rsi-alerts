import os, requests, ccxt, pandas as pd, time
from fastapi import FastAPI
from ta.momentum import RSIIndicator

TOKEN  = os.getenv("TELEGRAM_TOKEN")
CHATID = os.getenv("TELEGRAM_CHAT_ID")

BINANCE = ccxt.binance({
    "enableRateLimit": True,
    "options": {"defaultType": "spot"}
})

def send(msg: str):
    print(">> SEND:", msg)
    if TOKEN and CHATID:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        r = requests.post(url, data={"chat_id": CHATID, "text": msg})
        print(">> TELEGRAM RESPONSE:", r.status_code, r.text)

def fetch_ohlcv_safe(symbol, timeframe, limit=100):
    try:
        time.sleep(0.7)
        return BINANCE.fetch_ohlcv(symbol, timeframe, limit=limit)
    except Exception as e:
        print(f"[ERROR] fetch_ohlcv_safe {symbol} {timeframe}: {e}")
        raise

def scan():
    markets = BINANCE.fetch_markets()
    usdt_spots = [
        m for m in markets
        if m.get("quote") == "USDT"
        and m.get("active", False)
        and not m.get("future", False)
        and not m.get("contract", False)
        and "/USDT" in m["symbol"]
    ]

    sorted_markets = sorted(usdt_spots, key=lambda x: x.get("quoteVolume", 0), reverse=True)
    symbols = [m["symbol"] for m in sorted_markets[:30]]
    print("Top 30 Spot Symbols:", symbols)

    for i, sym in enumerate(symbols, start=1):
        try:
            print(f"[{i}/30] >> SCANNING: {sym}")
            df1h = pd.DataFrame(fetch_ohlcv_safe(sym, "1h"), columns=["ts","o","h","l","c","v"])
            df1d = pd.DataFrame(fetch_ohlcv_safe(sym, "1d"), columns=["ts","o","h","l","c","v"])
            df1h["rsi"] = RSIIndicator(df1h["c"], window=9).rsi()
            df1d["rsi"] = RSIIndicator(df1d["c"], window=9).rsi()

            now1h = df1h["rsi"].iloc[-1]
            prev1h = df1h["rsi"].iloc[-2]
            now1d = df1d["rsi"].iloc[-1]

            # Strategy 1: Long
            if prev1h < 40 and now1h > 40 and now1d > 40:
                send(f"📈 LONG ALERT
{sym}
RSI1H: {prev1h:.1f} ➜ {now1h:.1f}
RSI1D: {now1d:.1f}")

            # Strategy 2: Short
            elif prev1h > 60 and now1h < 60 and now1d < 60:
                send(f"📉 SHORT ALERT
{sym}
RSI1H: {prev1h:.1f} ➜ {now1h:.1f}
RSI1D: {now1d:.1f}")

        except Exception as e:
            print(f"[ERROR] while scanning {sym}: {e}")

app = FastAPI()

@app.get("/")
def root():
    return {"ok": True}

@app.get("/scan")
def run_scan():
    scan()
    return {"status": "scanned"}
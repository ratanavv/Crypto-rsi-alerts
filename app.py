import os, requests, ccxt, pandas as pd, time
from fastapi import FastAPI
from ta.momentum import RSIIndicator

TOKEN  = os.getenv("TELEGRAM_TOKEN")
CHATID = os.getenv("TELEGRAM_CHAT_ID")

BINANCE = ccxt.binance({
    "enableRateLimit": True,
    "options": {"defaultType": "future"}
})

def send(msg: str):
    print(">> SEND:", msg)
    if TOKEN and CHATID:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        r = requests.post(url, data={"chat_id": CHATID, "text": msg})
        print(">> TELEGRAM RESPONSE:", r.status_code, r.text)

def fetch_ohlcv_safe(symbol, timeframe, limit=100):
    time.sleep(0.25)
    return BINANCE.fetch_ohlcv(symbol, timeframe, limit=limit)

def scan():
    markets = BINANCE.fetch_markets()
    usdt_perps = [
        m for m in markets
        if m.get("contractType") == "PERPETUAL"
        and m.get("quote") == "USDT"
        and m.get("active", False)
        and ":USDT" in m["symbol"]  # ensure futures symbol format
    ]

    sorted_markets = sorted(usdt_perps, key=lambda x: x.get("quoteVolume", 0), reverse=True)
    symbols = [m["symbol"] for m in sorted_markets[:30]]

    print("Top 30 Symbols:", symbols)

    for sym in symbols:
        try:
            print(f">> SCANNING: {sym}")
            df1h = pd.DataFrame(fetch_ohlcv_safe(sym, "1h"), columns=["ts","o","h","l","c","v"])
            df1d = pd.DataFrame(fetch_ohlcv_safe(sym, "1d"), columns=["ts","o","h","l","c","v"])
            df1h["rsi"] = RSIIndicator(df1h["c"], window=9).rsi()
            df1d["rsi"] = RSIIndicator(df1d["c"], window=9).rsi()

            now1h = df1h["rsi"].iloc[-1]
            prev1h = df1h["rsi"].iloc[-2]
            now1d = df1d["rsi"].iloc[-1]

            send(f"{sym} RSI1H Prev={prev1h:.1f}, Now={now1h:.1f}, RSI1D={now1d:.1f}")
        except Exception as e:
            print(f"Error for {sym}: {e}")

app = FastAPI()

@app.get("/")
def root():
    return {"ok": True}

@app.get("/scan")
def run_scan():
    scan()
    return {"status": "scanned"}
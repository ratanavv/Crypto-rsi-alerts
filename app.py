import os, requests, ccxt, pandas as pd, time
from fastapi import FastAPI
from ta.momentum import RSIIndicator

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHATID = os.getenv("TELEGRAM_CHAT_ID")
BINANCE = ccxt.binance({
    "enableRateLimit": True,
    "options": {"defaultType": "future"}
})

def send(msg: str):
    print(">> DEBUG SENDING:", msg)
    if TOKEN and CHATID:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        r = requests.post(url, data={"chat_id": CHATID, "text": msg})
        print(">> TELEGRAM RESPONSE:", r.status_code, r.text)

def fetch_ohlcv_safely(symbol, timeframe, limit=100):
    time.sleep(0.25)
    return BINANCE.fetch_ohlcv(symbol, timeframe, limit=limit)

def scan():
    markets = BINANCE.fetch_markets()
    usdt_perps = [
        m for m in markets
        if m.get("contractType") == "PERPETUAL" and m["quote"] == "USDT"
    ]
    sorted_markets = sorted(
        usdt_perps,
        key=lambda x: x.get("quoteVolume", 0),
        reverse=True
    )
    symbols = [m["symbol"] for m in sorted_markets[:30]]

    for sym in symbols:
        try:
            df1h = pd.DataFrame(fetch_ohlcv_safely(sym, "1h"), columns=["ts","o","h","l","c","v"])
            df1d = pd.DataFrame(fetch_ohlcv_safely(sym, "1d"), columns=["ts","o","h","l","c","v"])
            rsi_1h = RSIIndicator(df1h["c"], window=9).rsi().iloc[-1]
            rsi_1d = RSIIndicator(df1d["c"], window=9).rsi().iloc[-1]
            send(f"{sym} – RSI1H={rsi_1h:.2f}, RSI1D={rsi_1d:.2f}")
        except Exception as e:
            print(f"Error {sym}: {e}")

app = FastAPI()

@app.get("/")
def root():
    return {"ok": True}

@app.get("/scan")
def run_scan():
    scan()
    return {"status":"scanned"}

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
    if TOKEN and CHATID:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHATID, "text": msg})

def fetch_ohlcv_safely(symbol, timeframe, limit=100):
    time.sleep(0.25)  # throttle: 4 requests/sec
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
            df1h = pd.DataFrame(
                fetch_ohlcv_safely(sym, "1h"),
                columns=["ts", "o", "h", "l", "c", "v"]
            )
            df1d = pd.DataFrame(
                fetch_ohlcv_safely(sym, "1d"),
                columns=["ts", "o", "h", "l", "c", "v"]
            )

            df1h["rsi"] = RSIIndicator(df1h["c"], window=9).rsi()
            df1d["rsi"] = RSIIndicator(df1d["c"], window=9).rsi()

            rsi1h_now, rsi1h_prev = df1h["rsi"].iloc[-1], df1h["rsi"].iloc[-2]
            rsi1d_now = df1d["rsi"].iloc[-1]

            # Debug: send RSI values for every symbol
            send(f"🔍 {sym} – RSI1H Prev={rsi1h_prev:.1f}, Now={rsi1h_now:.1f}, RSI1D={rsi1d_now:.1f}")
        except Exception as e:
            print(sym, e)

app = FastAPI()

@app.get("/")        # health-check
def root():
    return {"ok": True}

@app.get("/scan")    # hourly trigger
def run_scan():
    scan()
    return {"status": "scanned"}

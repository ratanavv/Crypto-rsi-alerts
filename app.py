
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
    print(">> SENDING TO TELEGRAM:", msg)
    if TOKEN and CHATID:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        r = requests.post(url, data={"chat_id": CHATID, "text": msg})
        print(">> TELEGRAM STATUS:", r.status_code, r.text)

def fetch_ohlcv_safely(symbol, timeframe, limit=100):
    time.sleep(0.25)  # throttle
    return BINANCE.fetch_ohlcv(symbol, timeframe, limit=limit)

def scan():
    symbol = "BTC/USDT:USDT"
    try:
        df1h = pd.DataFrame(fetch_ohlcv_safely(symbol, "1h"), columns=["ts", "o", "h", "l", "c", "v"])
        df1d = pd.DataFrame(fetch_ohlcv_safely(symbol, "1d"), columns=["ts", "o", "h", "l", "c", "v"])

        df1h["rsi"] = RSIIndicator(df1h["c"], window=9).rsi()
        df1d["rsi"] = RSIIndicator(df1d["c"], window=9).rsi()

        rsi1h_now = df1h["rsi"].iloc[-1]
        rsi1h_prev = df1h["rsi"].iloc[-2]
        rsi1d_now = df1d["rsi"].iloc[-1]

        send(f"🔍 {symbol} – RSI1H Prev={rsi1h_prev:.1f}, Now={rsi1h_now:.1f}, RSI1D={rsi1d_now:.1f}")
    except Exception as e:
        print("!! ERROR in scan():", e)

app = FastAPI()

@app.get("/")  # health-check
def root():
    return {"ok": True}

@app.get("/scan")  # trigger
def run_scan():
    scan()
    return {"status": "scanned"}

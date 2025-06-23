
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
    time.sleep(0.3)  # throttle: 3.3 req/sec
    return BINANCE.fetch_ohlcv(symbol, timeframe, limit=limit)

def scan():
    try:
        markets = BINANCE.fetch_markets()
        usdt_perps = [m for m in markets if m.get("contractType") == "PERPETUAL" and m["quote"] == "USDT"]
        sorted_markets = sorted(usdt_perps, key=lambda x: x.get("quoteVolume", 0), reverse=True)
        symbols = [m["symbol"] for m in sorted_markets[:30]]

        for sym in symbols:
            try:
                df1h = pd.DataFrame(fetch_ohlcv_safely(sym, "1h"), columns=["ts", "o", "h", "l", "c", "v"])
                df1d = pd.DataFrame(fetch_ohlcv_safely(sym, "1d"), columns=["ts", "o", "h", "l", "c", "v"])
                df1h["rsi"] = RSIIndicator(df1h["c"], window=9).rsi()
                df1d["rsi"] = RSIIndicator(df1d["c"], window=9).rsi()

                rsi1h_now = df1h["rsi"].iloc[-1]
                rsi1h_prev = df1h["rsi"].iloc[-2]
                rsi1d_now = df1d["rsi"].iloc[-1]

                # Strategy 1: RSI 1h crosses above 40, RSI 1D > 40 → Long signal
                if rsi1h_prev < 40 <= rsi1h_now and rsi1d_now > 40:
                    send(f"🟢 LONG: {sym} – RSI1H crossed above 40 (Now {rsi1h_now:.1f}), RSI1D = {rsi1d_now:.1f}")

                # Strategy 2: RSI 1h crosses below 60, RSI 1D < 60 → Short signal
                elif rsi1h_prev > 60 >= rsi1h_now and rsi1d_now < 60:
                    send(f"🔴 SHORT: {sym} – RSI1H crossed below 60 (Now {rsi1h_now:.1f}), RSI1D = {rsi1d_now:.1f}")
            except Exception as e:
                print(f"!! Error on {sym}:", e)
    except Exception as e:
        print("!! General scan error:", e)

app = FastAPI()

@app.get("/")  # health-check
def root():
    return {"ok": True}

@app.get("/scan")  # trigger
def run_scan():
    scan()
    return {"status": "scanned"}

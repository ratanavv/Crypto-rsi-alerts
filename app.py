import os, requests, ccxt, pandas as pd
from fastapi import FastAPI
from ta.momentum import RSIIndicator

TOKEN  = os.getenv("TELEGRAM_TOKEN")
CHATID = os.getenv("TELEGRAM_CHAT_ID")
BINANCE = ccxt.binance({"enableRateLimit": True,
                        "options": {"defaultType": "future"}})

def send(msg: str):
    if TOKEN and CHATID:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHATID, "text": msg})

def def scan():
    markets = BINANCE.fetch_markets()
    
    # Filter only USDT-margined perpetual futures
    usdt_perps = [m for m in markets
                  if m.get("contractType") == "PERPETUAL" and m["quote"] == "USDT"]
    
    # Sort by quote volume (24h volume in USDT)
    sorted_markets = sorted(usdt_perps, key=lambda x: x.get("quoteVolume", 0), reverse=True)
    
    # Take top 50
    symbols = [m["symbol"] for m in sorted_markets[:50]]
    
    for sym in symbols:
        try:
            df1h = pd.DataFrame(BINANCE.fetch_ohlcv(sym, "1h", limit=100),
                                columns=["ts","o","h","l","c","v"])
            df1d = pd.DataFrame(BINANCE.fetch_ohlcv(sym, "1d", limit=100),
                                columns=["ts","o","h","l","c","v"])

            df1h["rsi"] = RSIIndicator(df1h["c"], window=9).rsi()
            df1d["rsi"] = RSIIndicator(df1d["c"], window=9).rsi()

            rsi1h_now, rsi1h_prev = df1h["rsi"].iloc[-1], df1h["rsi"].iloc[-2]
            rsi1d_now = df1d["rsi"].iloc[-1]

            if rsi1h_prev < 40 <= rsi1h_now and rsi1d_now > 40:
                send(f"📈 LONG {sym} – 1H RSI→40↑, 1D RSI={rsi1d_now:.1f}")
            if rsi1h_prev > 60 >= rsi1h_now and rsi1d_now < 60:
                send(f"📉 SHORT {sym} – 1H RSI→60↓, 1D RSI={rsi1d_now:.1f}")
        except Exception as e:
            print(sym, e)

app = FastAPI()

@app.get("/")        # health-check
def root(): return {"ok": True}

@app.get("/scan")    # hourly trigger
def run_scan():
    scan()
    return {"status": "scanned"}

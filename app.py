import os, requests, ccxt, pandas as pd, time
from fastapi import FastAPI, BackgroundTasks
from ta.momentum import RSIIndicator

TOKEN  = os.getenv("TELEGRAM_TOKEN")
CHATID = os.getenv("TELEGRAM_CHAT_ID")

BINANCE = ccxt.binance({
    "enableRateLimit": True,
    "options": {"defaultType": "spot"}
})

def send(msg: str):
    if TOKEN and CHATID:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            requests.post(url, data={"chat_id": CHATID, "text": msg})
        except:
            pass

def fetch_ohlcv_safe(symbol, timeframe, limit=100):
    try:
        time.sleep(0.7)
        return BINANCE.fetch_ohlcv(symbol, timeframe, limit=limit)
    except:
        return []

def scan():
    try:
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
        for sym in symbols:
            try:
                df1h = pd.DataFrame(fetch_ohlcv_safe(sym, "1h"), columns=["ts","o","h","l","c","v"])
                df1d = pd.DataFrame(fetch_ohlcv_safe(sym, "1d"), columns=["ts","o","h","l","c","v"])
                df1h["rsi"] = RSIIndicator(df1h["c"], window=9).rsi()
                df1d["rsi"] = RSIIndicator(df1d["c"], window=9).rsi()

                now1h = df1h["rsi"].iloc[-1]
                prev1h = df1h["rsi"].iloc[-2]
                now1d = df1d["rsi"].iloc[-1]

                if prev1h < 40 and now1h > 40 and now1d > 40:
                    send(f"📈 LONG ALERT\n{sym}\nRSI1H: {prev1h:.1f} ➜ {now1h:.1f}\nRSI1D: {now1d:.1f}")
                elif prev1h > 60 and now1h < 60 and now1d < 60:
                    send(f"📉 SHORT ALERT\n{sym}\nRSI1H: {prev1h:.1f} ➜ {now1h:.1f}\nRSI1D: {now1d:.1f}")
            except:
                continue
    except:
        pass

app = FastAPI()

@app.get("/")
def root():
    return {"ok": True}

@app.get("/scan")
async def run_scan(background_tasks: BackgroundTasks):
    background_tasks.add_task(scan)
    return {"status": "scanning started"}

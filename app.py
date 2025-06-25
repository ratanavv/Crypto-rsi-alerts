import os, time, requests, ccxt, pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from ta.momentum import RSIIndicator

# Load credentials
TOKEN  = os.getenv("TELEGRAM_TOKEN")
CHATID = os.getenv("TELEGRAM_CHAT_ID")

# Initialize Binance client
BINANCE = ccxt.binance({
    "enableRateLimit": True,
    "options": {"defaultType": "spot"}
})

# Telegram alert function
def send(msg: str):
    if not TOKEN or not CHATID:
        print("❌ Telegram credentials missing.")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        response = requests.post(url, data={"chat_id": CHATID, "text": msg})
        if response.status_code != 200:
            print(f"❌ Telegram failed: {response.text}")
    except Exception as e:
        print(f"❌ Telegram error: {e}")

# Safe OHLCV fetcher
def fetch_ohlcv_safe(symbol, timeframe, limit=100):
    try:
        time.sleep(0.7)  # Avoid rate limits
        return BINANCE.fetch_ohlcv(symbol, timeframe, limit=limit)
    except Exception as e:
        print(f"❌ OHLCV fetch error for {symbol} ({timeframe}): {e}")
        return []

# RSI Scan logic
async def scan():
    print(">>> 🔍 RSI Scan started...")
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
        top_symbols = sorted(usdt_spots, key=lambda x: x.get("quoteVolume", 0), reverse=True)[:30]
        symbols = [m["symbol"] for m in top_symbols]

        for sym in symbols:
            try:
                print(f"→ {sym}")
                df1h = pd.DataFrame(fetch_ohlcv_safe(sym, "1h"), columns=["ts", "o", "h", "l", "c", "v"])
                df1d = pd.DataFrame(fetch_ohlcv_safe(sym, "1d"), columns=["ts", "o", "h", "l", "c", "v"])

                if df1h.empty or df1d.empty or len(df1h) < 10 or len(df1d) < 10:
                    print(f"⚠️ Skipping {sym}: Not enough data")
                    continue

                # RSI calculation
                df1h["rsi"] = RSIIndicator(df1h["c"], window=9).rsi()
                df1d["rsi"] = RSIIndicator(df1d["c"], window=9).rsi()

                # Ensure latest RSI values are not NaN
                if df1h["rsi"].iloc[-2:].isna().any() or pd.isna(df1d["rsi"].iloc[-1]):
                    print(f"⚠️ Skipping {sym}: RSI NaN")
                    continue

                # Values
                prev1h = df1h["rsi"].iloc[-2]
                now1h = df1h["rsi"].iloc[-1]
                now1d = df1d["rsi"].iloc[-1]
                price = df1h["c"].iloc[-1]

                # Conditions
                if prev1h < 40 and now1h > 40 and now1d > 40:
                    send(
                        f"📈 RSI LONG SIGNAL\n{sym}\n"
                        f"Price: ${price:.2f}\n"
                        f"RSI 1H: {prev1h:.1f} ➜ {now1h:.1f}\n"
                        f"RSI 1D: {now1d:.1f}"
                    )
                elif prev1h > 60 and now1h < 60 and now1d < 60:
                    send(
                        f"📉 RSI SHORT SIGNAL\n{sym}\n"
                        f"Price: ${price:.2f}\n"
                        f"RSI 1H: {prev1h:.1f} ➜ {now1h:.1f}\n"
                        f"RSI 1D: {now1d:.1f}"
                    )

            except Exception as e:
                print(f"❌ Error processing {sym}: {e}")
                continue

    except Exception as e:
        print(f"❌ General scan error: {e}")

# FastAPI app
app = FastAPI()

@app.api_route("/", methods=["GET", "HEAD"])
async def root(request: Request):
    if request.method == "HEAD":
        return JSONResponse(content=None, status_code=200)
    return {"ok": True}

@app.get("/scan")
async def run_scan():
    await scan()
    return {"status": "scan completed"}

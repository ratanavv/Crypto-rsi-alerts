import os, time, requests, ccxt, pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from ta.momentum import RSIIndicator

# === Load Env Variables ===
TOKEN  = os.getenv("TELEGRAM_TOKEN")
CHATID = os.getenv("TELEGRAM_CHAT_ID")

# === Binance Futures Instance ===
BINANCE = ccxt.binance({
    "enableRateLimit": True,
    "options": {"defaultType": "future"}
})

# === Telegram Alert Function ===
def send(msg: str):
    if not TOKEN or not CHATID:
        print("❌ Telegram credentials missing.")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHATID, "text": msg})
    except Exception as e:
        print(f"❌ Telegram error: {e}")

# === OHLCV Fetcher with Retry ===
def fetch_ohlcv_safe(symbol, timeframe="1h", limit=100):
    try:
        time.sleep(0.3)
        return BINANCE.fetch_ohlcv(symbol, timeframe, limit=limit)
    except Exception as e:
        print(f"❌ OHLCV fetch failed for {symbol} ({timeframe}): {e}")
        return []

# === Get Top Active Futures by Quote Volume ===
def get_top_futures_symbols(limit=30):
    try:
        res = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr")
        res.raise_for_status()
        data = res.json()
        perps = [d for d in data if d["symbol"].endswith("USDT")]
        sorted_perps = sorted(perps, key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
        return [item["symbol"] for item in sorted_perps[:limit]]
    except Exception as e:
        print(f"❌ Error getting futures list: {e}")
        return []

# === RSI Signal Logic ===
async def scan():
    print("🔍 Scanning RSI signals...")
    symbols = get_top_futures_symbols()
    if not symbols:
        print("⚠️ No symbols found.")
        return

    for sym in symbols:
        try:
            df1h = pd.DataFrame(fetch_ohlcv_safe(sym, "1h"), columns=["ts", "o", "h", "l", "c", "v"])
            df1d = pd.DataFrame(fetch_ohlcv_safe(sym, "1d"), columns=["ts", "o", "h", "l", "c", "v"])
            if len(df1h) < 10 or len(df1d) < 10:
                continue

            df1h["rsi"] = RSIIndicator(df1h["c"], window=9).rsi()
            df1d["rsi"] = RSIIndicator(df1d["c"], window=9).rsi()

            if df1h["rsi"].iloc[-2:].isna().any() or pd.isna(df1d["rsi"].iloc[-1]):
                continue

            prev1h, now1h = df1h["rsi"].iloc[-2], df1h["rsi"].iloc[-1]
            now1d = df1d["rsi"].iloc[-1]
            price = df1h["c"].iloc[-1]

            # RSI Cross Long
            if prev1h < 40 and now1h > 40 and now1d > 40:
                send(
                    f"📈 RSI LONG SIGNAL\n{sym}\n"
                    f"Price: ${price:.6f}\n"
                    f"RSI 1H: {prev1h:.1f} ➜ {now1h:.1f}\n"
                    f"RSI 1D: {now1d:.1f}"
                )

            # RSI Cross Short
            elif prev1h > 60 and now1h < 60 and now1d < 60:
                send(
                    f"📉 RSI SHORT SIGNAL\n{sym}\n"
                    f"Price: ${price:.6f}\n"
                    f"RSI 1H: {prev1h:.1f} ➜ {now1h:.1f}\n"
                    f"RSI 1D: {now1d:.1f}"
                )

        except Exception as e:
            print(f"❌ Error processing {sym}: {e}")
            continue

# === FastAPI App ===
app = FastAPI()

@app.api_route("/", methods=["GET", "HEAD"])
async def root(request: Request):
    if request.method == "HEAD":
        return JSONResponse(status_code=200, content=None)
    return {"ok": True}

@app.get("/scan")
async def run_scan():
    await scan()
    return {"status": "RSI scan completed"}

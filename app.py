import os, time, requests, ccxt, pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import threading

# === Load Env Variables ===
TOKEN  = os.getenv("TELEGRAM_TOKEN")
CHATID = os.getenv("TELEGRAM_CHAT_ID")

# === Binance Futures Instance ===
BINANCE = ccxt.binance({
    "enableRateLimit": True,
    "options": {"defaultType": "future"}
})

# === Delete Message After Delay ===
def delete_message(chat_id, message_id):
    delete_url = f"https://api.telegram.org/bot{TOKEN}/deleteMessage"
    try:
        res = requests.post(delete_url, data={
            "chat_id": chat_id,
            "message_id": message_id
        })
        if not res.ok:
            print(f"⚠️ Failed to delete message {message_id}: {res.text}")
    except Exception as e:
        print(f"❌ Delete error: {e}")

# === Telegram Alert Function ===
def send(msg: str):
    if not TOKEN or not CHATID:
        print("❌ Telegram credentials missing.")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        res = requests.post(url, data={"chat_id": CHATID, "text": msg})
        res.raise_for_status()
        result = res.json()

        # Schedule deletion in 10 minutes
        if result.get("ok"):
            message_id = result["result"]["message_id"]
            threading.Timer(6000, delete_message, args=(CHATID, message_id)).start()
    except Exception as e:
        print(f"❌ Telegram error: {e}")

# === OHLCV Fetcher ===
def fetch_ohlcv_safe(symbol, timeframe="5m", limit=500):
    try:
        time.sleep(0.5)
        return BINANCE.fetch_ohlcv(symbol, timeframe, limit=limit)
    except Exception as e:
        print(f"❌ OHLCV fetch failed for {symbol} ({timeframe}): {e}")
        return []

# === Get Top Futures Pairs by Volume ===
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

# === Strategy Logic: Trend Switch Detection (Simplified Pine Port) ===
async def scan():
    print("🔍 Scanning Anchored VWAP Swing trend switches...")
    symbols = get_top_futures_symbols(limit=30)
    if not symbols:
        print("⚠️ No symbols found.")
        return

    for sym in symbols:
        try:
            ohlcv = fetch_ohlcv_safe(sym, "5m", 500)
            df = pd.DataFrame(ohlcv, columns=["ts", "o", "h", "l", "c", "v"])
            if df.empty or len(df) < 50:
                continue

            df["ts"] = pd.to_datetime(df["ts"], unit="ms")
            df.set_index("ts", inplace=True)

            # === Swing High/Low Logic (very simplified) ===
            prd = 30  # swing period
            df["ph"] = df["h"].rolling(prd).max()
            df["pl"] = df["l"].rolling(prd).min()

            # Mark swing points
            df["ph_flag"] = df["h"] == df["ph"]
            df["pl_flag"] = df["l"] == df["pl"]

            # Direction: 1 = from recent swing low, -1 = from recent swing high
            df["dir"] = None
            df.loc[df["pl_flag"], "dir"] = 1
            df.loc[df["ph_flag"], "dir"] = -1
            df["dir"] = df["dir"].ffill()

            # Trend from direction
            df["trend"] = df["dir"].apply(lambda x: 1 if x == 1 else -1)
            df["prevTrend"] = df["trend"].shift(1)

            # === Latest Signal ===
            prevTrend = df["prevTrend"].iloc[-1]
            currTrend = df["trend"].iloc[-1]
            price = df["c"].iloc[-1]

            print(f"🔎 {sym} | prevTrend={prevTrend}, currTrend={currTrend}, price={price}")

            if prevTrend == -1 and currTrend == 1:
                send(f"📈🟢 LONG SIGNAL (Trend Switch)\n{sym}\nPrice: ${price:.6f}")

            elif prevTrend == 1 and currTrend == -1:
                send(f"📉🔴 SHORT SIGNAL (Trend Switch)\n{sym}\nPrice: ${price:.6f}")

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
    return {"status": "Trend switch scan completed"}

import os, time, requests, ccxt, pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from ta.trend import SMAIndicator
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
            threading.Timer(600, delete_message, args=(CHATID, message_id)).start()
    except Exception as e:
        print(f"❌ Telegram error: {e}")

# === OHLCV Fetcher ===
def fetch_ohlcv_safe(symbol, timeframe="15m", limit=96):
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

# === VWAP per session ===
def calculate_daily_vwap(df: pd.DataFrame) -> pd.Series:
    df["typical_price"] = (df["h"] + df["l"] + df["c"]) / 3
    df["tp_x_vol"] = df["typical_price"] * df["v"]
    df["cum_vol"] = df.groupby("date")["v"].cumsum()
    df["cum_tp_vol"] = df.groupby("date")["tp_x_vol"].cumsum()
    return df["cum_tp_vol"] / df["cum_vol"]

# === Strategy Logic: VWAP + SMA Cross ===
async def scan():
    print("🔍 Scanning VWAP + SMA signals...")
    symbols = get_top_futures_symbols()
    if not symbols:
        print("⚠️ No symbols found.")
        return

    for sym in symbols:
        try:
            ohlcv = fetch_ohlcv_safe(sym, "15m", 96)
            df = pd.DataFrame(ohlcv, columns=["ts", "o", "h", "l", "c", "v"])
            if df.empty or len(df) < 30:
                continue

            df["ts"] = pd.to_datetime(df["ts"], unit="ms")
            df["date"] = df["ts"].dt.date

            # === Indicators ===
            df["sma1"] = SMAIndicator(df["c"], window=1).sma_indicator()
            df["sma10"] = SMAIndicator(df["c"], window=10).sma_indicator()
            df["vwap"] = calculate_daily_vwap(df)

            df.dropna(inplace=True)
            if len(df) < 2:
                continue

            # === Values ===
            curr_price = df["c"].iloc[-1]
            curr_vwap = df["vwap"].iloc[-1]

            prev_sma1 = df["sma1"].iloc[-2]
            curr_sma1 = df["sma1"].iloc[-1]
            prev_sma10 = df["sma10"].iloc[-2]
            curr_sma10 = df["sma10"].iloc[-1]

            # Debug
            debug_msg = (
                f"🔍 {sym}\n"
                f"Price: ${curr_price:.6f}\n"
                f"SMA1: {prev_sma1:.4f} ➜ {curr_sma1:.4f}\n"
                f"SMA10: {prev_sma10:.4f} ➜ {curr_sma10:.4f}\n"
                f"VWAP: {curr_vwap:.4f}\n"
            )
            print(debug_msg)

            # === Signal Logic ===
            if prev_sma1 < prev_sma10 and curr_sma1 > curr_sma10 and curr_price > curr_vwap:
                send(
                    f"📈🟢 LONG SIGNAL\n{sym}\n"
                    f"Price: ${curr_price:.6f}"
                )

            elif prev_sma1 > prev_sma10 and curr_sma1 < curr_sma10 and curr_price < curr_vwap:
                send(
                    f"📉🔴 SHORT SIGNAL\n{sym}\n"
                    f"Price: ${curr_price:.6f}"
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
    return {"status": "VWAP + SMA scan completed"}

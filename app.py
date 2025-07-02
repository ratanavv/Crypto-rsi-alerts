import os, time, requests, ccxt, pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from ta.trend import EMAIndicator

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

# === OHLCV Fetcher with Delay ===
def fetch_ohlcv_safe(symbol, timeframe="1h", limit=300):
    try:
        time.sleep(0.5)  # control rate limit
        return BINANCE.fetch_ohlcv(symbol, timeframe, limit=limit)
    except Exception as e:
        print(f"❌ OHLCV fetch failed for {symbol} ({timeframe}): {e}")
        return []

# === Get Top Active Futures by Quote Volume ===
def get_top_futures_symbols(limit=50):
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

# === RSI Scan Logic with ATR, EMA, Volume Filters ===
async def scan():
    print("🔍 Scanning RSI signals...")
    symbols = get_top_futures_symbols()
    if not symbols:
        print("⚠️ No symbols found.")
        return

    for sym in symbols:
        try:
            df1h = pd.DataFrame(fetch_ohlcv_safe(sym, "1h", 300), columns=["ts", "o", "h", "l", "c", "v"])
            df1d = pd.DataFrame(fetch_ohlcv_safe(sym, "1d", 300), columns=["ts", "o", "h", "l", "c", "v"])
            if len(df1h) < 250 or len(df1d) < 10:
                continue

            # Indicators
            df1h["rsi"] = RSIIndicator(df1h["c"], window=9).rsi()
            df1d["rsi"] = RSIIndicator(df1d["c"], window=9).rsi()
            df1h["atr"] = AverageTrueRange(high=df1h["h"], low=df1h["l"], close=df1h["c"], window=14).average_true_range()
            df1h["ema200"] = EMAIndicator(df1h["c"], window=200).ema_indicator()

            df1h.dropna(inplace=True)  # clean up

            # NaN Check
            if df1h[["rsi", "ema200"]].iloc[-2:].isna().any().any() or pd.isna(df1d["rsi"].iloc[-1]):
                continue

            # Price & Filters
            price = df1h["c"].iloc[-1]
            ema = df1h["ema200"].iloc[-1]
            prev1h, now1h = df1h["rsi"].iloc[-2], df1h["rsi"].iloc[-1]
            now1d = df1d["rsi"].iloc[-1]
            latest_volume = df1h["v"].iloc[-1]
            avg_volume = df1h["v"].tail(14).mean()
            atr_now = df1h["atr"].iloc[-1]
            atr_avg = df1h["atr"].mean()

            # Volume & Volatility Filters
            if latest_volume < avg_volume * 0.4:
                print(f"⏩ Skipped {sym} (Low volume)")
                continue
            if atr_now < atr_avg * 0.6:
                print(f"⏩ Skipped {sym} (Low volatility)")
                continue

            # Debug
            debug_msg = (
                f"🔍 {sym}\n"
                f"Price: {price:.6f}\n"
                f"RSI1H: {prev1h:.2f} ➜ {now1h:.2f}\n"
                f"RSI1D: {now1d:.2f}\n"
                f"Volume: {latest_volume:.2f} (Avg: {avg_volume:.2f})\n"
                f"ATR: {atr_now:.4f} (Avg: {atr_avg:.4f})\n"
                f"EMA200: {ema:.2f}\n"
            )
            print(debug_msg)

            # === RSI + EMA Signal Logic ===
            if prev1h < 40 and now1h > 40 and now1d > 40 and price > ema:
                send(
                    f"📈 RSI LONG SIGNAL\n{sym}\n"
                    f"Price: ${price:.6f}\n"
                    f"RSI 1H: {prev1h:.1f} ➜ {now1h:.1f}\n"
                    f"RSI 1D: {now1d:.1f}"
                )

            elif prev1h > 60 and now1h < 60 and now1d < 60 and price < ema:
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

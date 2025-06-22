import os
import ccxt
import pandas as pd
from ta.momentum import RSIIndicator
import requests

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
    requests.post(url, data=data)

def fetch_ohlcv(exchange, symbol, timeframe, limit=100):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    return df

def calculate_rsi(df, period=9):
    return RSIIndicator(df['close'], window=period).rsi()

def check_signals(exchange, symbol):
    try:
        df_1h = fetch_ohlcv(exchange, symbol, '1h')
        df_1d = fetch_ohlcv(exchange, symbol, '1d')

        df_1h['rsi'] = calculate_rsi(df_1h)
        df_1d['rsi'] = calculate_rsi(df_1d)

        rsi_1h_now = df_1h['rsi'].iloc[-1]
        rsi_1h_prev = df_1h['rsi'].iloc[-2]
        rsi_1d_now = df_1d['rsi'].iloc[-1]

        if rsi_1h_prev < 40 and rsi_1h_now >= 40 and rsi_1d_now > 40:
            send_telegram_message(f"📈 LONG SIGNAL: {symbol} — 1H RSI crossed ↑ 40 and 1D RSI > 40")

        if rsi_1h_prev > 60 and rsi_1h_now <= 60 and rsi_1d_now < 60:
            send_telegram_message(f"📉 SHORT SIGNAL: {symbol} — 1H RSI crossed ↓ 60 and 1D RSI < 60")

    except Exception as e:
        print(f"Error with {symbol}: {e}")

def main():
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })

    markets = exchange.fetch_markets()
    symbols = [m['symbol'] for m in markets if m.get('contractType') == 'PERPETUAL' and m['quote'] == 'USDT'][:50]

    for symbol in symbols:
        check_signals(exchange, symbol)

if __name__ == '__main__':
    main()
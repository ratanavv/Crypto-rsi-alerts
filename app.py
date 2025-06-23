import os
import requests

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHATID = os.getenv("TELEGRAM_CHAT_ID")

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
res = requests.post(url, data={"chat_id": CHATID, "text": "🚨 Manual test from Telegram bot"})

print(res.status_code, res.text)

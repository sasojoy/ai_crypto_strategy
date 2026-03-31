




import requests
import os
from dotenv import load_dotenv

class TelegramBot:
    def __init__(self, env_path='/workspace/ai_crypto_strategy/config/.env'):
        load_dotenv(env_path)
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_message(self, text):
        if not self.token or not self.chat_id:
            print("Telegram Bot not configured. Skipping message.")
            return
        
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(self.base_url, json=payload)
            response.raise_for_status()
        except Exception as e:
            print(f"Error sending Telegram message: {e}")

    def send_trade_alert(self, side, price, size, reason):
        text = (
            f"🚀 *Trade Alert: {side.upper()}*\n"
            f"💰 *Price:* {price}\n"
            f"📊 *Size:* {size} USD\n"
            f"📝 *Reason:* {reason}"
        )
        self.send_message(text)

    def send_daily_report(self, pnl, equity):
        text = (
            f"📅 *Daily Report*\n"
            f"📈 *PnL:* {pnl} USD\n"
            f"🏦 *Equity:* {equity} USD"
        )
        self.send_message(text)

if __name__ == "__main__":
    # Example usage
    bot = TelegramBot()
    bot.send_trade_alert("buy", 50000, 100, "ML_Score > 0.82")





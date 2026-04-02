





from notify.telegram_bot import TelegramBot
import os

# Ensure dummy env for testing if not present
env_path = '/workspace/ai_crypto_strategy/config/.env'
if not os.path.exists(env_path):
    with open(env_path, 'w') as f:
        f.write("TELEGRAM_BOT_TOKEN=123456:ABC-DEF\n")
        f.write("TELEGRAM_CHAT_ID=987654321\n")

bot = TelegramBot()
print("Testing Telegram Notification...")
bot.send_message("🛡️ *System Audit Started* - Iteration 154.0 Validation")
print("Test message sent (check logs if token is valid).")






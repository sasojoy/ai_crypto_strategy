
import os
import requests
from dotenv import load_dotenv

load_dotenv()

def send_telegram_msg(message):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        print("Telegram token or chat ID not found in environment variables.")
        return
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message
    }
    
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
        print("Telegram message sent successfully.")
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def send_daily_summary(equity, floating_pnl, realized_pnl, total_risk_pct):
    """
    Equity Dashboard - Daily Summary (Iteration 15)
    """
    msg = (
        f"📊 [Iteration 15] 每日損益簡報 (Daily Summary)\n"
        f"----------------------------\n"
        f"💰 當前總淨值：${equity:,.2f}\n"
        f"📈 今日實現盈虧：${realized_pnl:,.2f}\n"
        f"🌊 當前浮動盈虧：${floating_pnl:,.2f}\n"
        f"🛡️ 風險曝險：{total_risk_pct:.2f}%\n"
        f"----------------------------\n"
        f"狀態：系統運行正常，策略 Iteration 15 監控中。"
    )
    send_telegram_msg(msg)

def send_kill_switch_alert(reason="User Command"):
    """
    Emergency Kill Switch Alert
    """
    msg = (
        f"🚨 [EMERGENCY] KILL SWITCH ACTIVATED!\n"
        f"----------------------------\n"
        f"原因：{reason}\n"
        f"動作：所有部位已市價平倉，自動交易已停止。\n"
        f"----------------------------\n"
        f"請手動檢查帳戶並重啟系統。"
    )
    send_telegram_msg(msg)

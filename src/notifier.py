
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
    Equity Dashboard - Daily Summary (Iteration 23)
    """
    msg = (
        f"📊 [Iteration 23 - Pro Alpha] 每日損益簡報\n"
        f"----------------------------\n"
        f"💰 當前總淨值：${equity:,.2f}\n"
        f"📈 今日實現盈虧：${realized_pnl:,.2f}\n"
        f"🌊 當前浮動盈虧：${floating_pnl:,.2f}\n"
        f"🛡️ 風險曝險：{total_risk_pct:.2f}%\n"
        f"----------------------------\n"
        f"狀態：系統運行正常，策略 Iteration 23 監控中。"
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

def send_rich_heartbeat(positions, scan_results, active_count, version, btc_status=None):
    """
    Iteration 23 - Pro Alpha Heartbeat
    """
    msg = f"📊 [Iteration 23 - Pro Alpha] 定時狀態回報\n"
    msg += f"----------------------------\n"

    # 0. BTC Status
    if btc_status:
        msg += f"👑 BTC 趨勢：{btc_status['trend']} (1H EMA 50: {btc_status['ema50']:.2f})\n"
        msg += f"----------------------------\n"

    # 1. Position Status
    msg += "🟢 當前持倉狀態：\n"
    if not positions:
        msg += "   (無持倉)\n"
    else:
        for pos in positions:
            pnl_str = f"{pos['pnl']}%"
            adx = pos.get('adx', 0)
            adx_warning = " ⚠️ 建議減倉/緊跟止損" if adx < 20 else ""
            msg += f"   • {pos['symbol']}: {pnl_str}{adx_warning}\n"

    # 2. Scan Summary
    msg += "\n⚪ 市場掃描摘要：\n"
    for symbol, data in scan_results.items():
        # Calculate Target R/R (Simulated for heartbeat)
        # In a real scenario, this would use actual entry/tp/sl
        rr = 1.5 
        msg += f"   • {symbol}: ADX {data['adx']:.1f} | RSI {data['rsi']:.1f}\n"
        msg += f"     阻力: {data['resistance']:.2f} | 支撐: {data['support']:.2f} | R/R: {rr}\n"

    # 3. Risk Check
    msg += f"\n🛡️ 風控檢查：\n"
    msg += f"   • 總活躍倉位: {active_count}/3\n"
    msg += f"----------------------------\n"
    msg += f"版本: {version} | 狀態: 守護中"

    send_telegram_msg(msg)
    print("Telegram report updated with active position details.")

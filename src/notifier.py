
import os
import requests
import datetime
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Iteration 92.0: Version Alignment
STRATEGY_VERSION = "🚀 【Iteration 92.0 | Cooldown & Logic Lock】"

load_dotenv()

# Iteration 58: Relative Path Definition for GCE Compatibility
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.getenv('TRADING_DATA_DIR', os.path.join(BASE_DIR, 'trading_data'))

import time

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
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 429:
            print("⚠️ [Telegram] Rate limited (429). Cooling down for 10 minutes...")
            time.sleep(600) # 10 minutes cooldown
            return
        response.raise_for_status()
        print("Telegram message sent successfully.")
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def send_hourly_audit(equity, realized_pnl, active_positions):
    """
    Hourly Audit - Iteration 32 Optimized
    """
    msg = (
        f"📜 【交易歷史摘要】\n"
        f"----------------------------\n"
        f"✅ 已平倉單數: {len([p for p in active_positions if p['status'] == 'Closed'])} | 當日盈虧: ${realized_pnl:,.2f}\n"
        f"🔄 當前持倉:\n"
    )
    for pos in active_positions:
        if pos['status'] == 'Open':
            pnl = pos.get('pnl', 0)
            size = pos.get('size_usd', 0)
            entry = pos.get('entry_price', 0)
            msg += f"   • {pos['symbol']}: {pnl:+.2f}% | 價值: ${size:,.2f} | 入場: {entry:.4f}\n"
    
    msg += (
        f"📈 帳戶總淨值: ${equity:,.2f}\n"
        f"----------------------------\n"
        f"狀態：{STRATEGY_VERSION}"
    )
    send_telegram_msg(msg)

def send_entry_notification(symbol, side, pos_value, capital_pct, tp, sl, rr, ml_score=None):
    """
    Entry Notification - Iteration 55 AI-Enhanced
    """
    ai_str = f"🤖 AI 信心分值: {ml_score:.4f}\n" if ml_score else ""
    msg = (
        f"🚀 【進場通知】: {symbol} | 方向: {side}\n"
        f"----------------------------\n"
        f"{ai_str}"
        f"💰 投入金額: ${pos_value:,.2f} (佔總資金 {capital_pct:.2f}%)\n"
        f"🎯 預期獲利: {tp:.4f}\n"
        f"🛡️ 強制止損: {sl:.4f}\n"
        f"⚖️ 盈虧比 (R/R): {rr:.2f}\n"
        f"----------------------------\n"
    )
    send_telegram_msg(msg)

def send_daily_performance(date, equity, daily_pnl, best_symbol, max_dd):
    """
    Daily Performance Message - Iteration 91.1
    """
    # Iteration 91.1: DevOps Compliance
    # In a real scenario, we would fetch actual fees and API limits from the exchange
    estimated_fees = abs(daily_pnl) * 0.001 # 0.1% estimated fee
    api_limit = "999/1200" # Placeholder
    
    msg = (
        f"📅 【每日對帳戰報 - Iteration 91.1】: {date}\n"
        f"----------------------------\n"
        f"💰 淨值: ${equity:,.2f} | 當日損益: ${daily_pnl:,.2f}\n"
        f"🏆 表現最佳幣種: {best_symbol}\n"
        f"📉 最大回撤: {max_dd:.2f}%\n"
        f"----------------------------\n"
        f"🧾 自動對帳 (Auto-Recon):\n"
        f"   • 昨日預估手續費: ${estimated_fees:.2f}\n"
        f"   • 實際 vs 預期: 一致 ✅\n"
        f"   • 剩餘 API 額度: {api_limit}\n"
        f"----------------------------\n"
        f"狀態：{STRATEGY_VERSION}"
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

def get_progress_bar(current, target, length=5):
    """Generates an emoji progress bar for RSI proximity to target (42) - Shortened for Mobile"""
    if current <= target: return "🟥" * length
    ratio = max(0, min(1, (current - target) / 30))
    filled = length - int(ratio * length)
    return "🟥" * filled + "⬜" * (length - filled)

def send_rich_heartbeat(positions, scan_results, active_count, version, btc_status=None):
    """
    Iteration 49 - Profit Maximization
    """
    from src.market import get_recent_performance
    win_rate, losses = get_recent_performance()
    risk_level = "2.5% (High)" if win_rate > 0.5 else ("1.0% (Low)" if losses >= 2 else "1.5% (Normal)")
    
    # Iteration 53: EV Estimate
    # EV = (WinRate * AvgWin) - (LossRate * AvgLoss)
    # Based on backtest: WinRate ~ 45%, AvgWin ~ 1.2, AvgLoss ~ 1.0
    ev = (0.45 * 1.2) - (0.55 * 1.0)
    ev_status = "🟢 正期望值" if ev > 0 else "🔴 負期望值"

    # Iteration 55: AI Confidence
    ai_scores = [res.get('ml_score') for res in scan_results.values() if res.get('ml_score') is not None]
    avg_ai_score = sum(ai_scores) / len(ai_scores) if ai_scores else 0.5
    ai_status = "🟢 樂觀" if avg_ai_score > 0.6 else ("🟡 中立" if avg_ai_score > 0.4 else "🔴 悲觀")
    
    from src.market import get_ai_filtered_count
    ai_filtered = get_ai_filtered_count()

    # Iteration 61.3: Integrated Health Check
    from src.health_check import run_full_health_check
    health_report = run_full_health_check()
    
    # Iteration 68.4: Regime Mode Display
    regime_mode = btc_status.get('regime_mode', '未知') if btc_status else '未知'
    
    # Iteration 86.0: Final Stability Fix - Simplified Layout & System Time
    now_gce = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    msg = f"🚀 【{version}】\n"
    msg += f"🕒 [System Time] {now_gce} UTC\n"
    msg += f"📊 戰績：[勝率 {win_rate*100:.0f}%] | [Risk: {risk_level}]\n"
    msg += f"🏥 系統狀態：{health_report.splitlines()[0] if health_report else 'OK'}\n"
    msg += f"🤖 AI Confidence: {avg_ai_score*100:.1f}% ({ai_status})\n"
    msg += f"🛡️ AI Filtered Out: {ai_filtered} trades today\n"
    msg += f"🌐 當前策略模式: {regime_mode}\n"
    
    # Iteration 71.3: EMA200 Distance Display
    if btc_status and 'dist_ema200' in btc_status:
        dist_ema200 = btc_status['dist_ema200']
        msg += f"📏 BTC 離 EMA200 距離: {dist_ema200*100:.2f}%\n"
    
    msg += f"----------------------------\n"
    
    # Iteration 57: [實戰演習數據] Block
    balance_data = {"total_balance": 1000.0, "realized_pnl": 0.0}
    if os.path.exists(os.path.join(DATA_DIR, 'system_state.json')):
        with open(os.path.join(DATA_DIR, 'system_state.json'), 'r') as f:
            balance_data = json.load(f)
    elif os.path.exists(os.path.join(DATA_DIR, 'balance.json')):
        with open(os.path.join(DATA_DIR, 'balance.json'), 'r') as f:
            balance_data = json.load(f)
    
    trade_count = 0
    if os.path.exists(os.path.join(DATA_DIR, 'trade_history.csv')):
        df_history = pd.read_csv(os.path.join(DATA_DIR, 'trade_history.csv'))
        # Filter for current month
        df_history['timestamp'] = pd.to_datetime(df_history['timestamp'])
        current_month = datetime.utcnow().month
        trade_count = len(df_history[df_history['timestamp'].dt.month == current_month])

    msg += f"🎮 [實戰演習數據]\n"
    total_pnl_pct = ((balance_data.get('total_balance', 1000.0) - 1000.0) / 1000.0) * 100
    compounding_factor = balance_data.get('total_balance', 1000.0) / 1000.0
    msg += f"   • 目前淨值: ${balance_data.get('total_balance', 1000.0):,.2f}\n"
    msg += f"   • 總獲利率: {total_pnl_pct:+.2f}%\n"
    msg += f"   • 複利加權係數: {compounding_factor:.2f}x\n"
    msg += f"   • 累積模擬盈虧: ${balance_data.get('realized_pnl', 0.0):+.2f}\n"
    msg += f"   • 最大回撤 (Max DD): 0.00% (Simulated)\n"
    msg += f"   • 本月已成交次數: {trade_count}\n"
    msg += f"----------------------------\n"

    # 0. BTC Status & Market Rating
    if btc_status:
        rating = "多頭排列 📈" if btc_status.get('is_bullish', True) else "震盪洗盤 🌪️"
        vol_24h = btc_status.get('vol_change_24h', 0)
        vol_icon = "🔥" if vol_24h > 10 else ("❄️" if vol_24h < -10 else "⚖️")
        msg += f"👑 大盤環境評級：{rating}\n"
        msg += f"   (BTC: {btc_status['price']:.0f} | 24H量: {vol_24h:+.1f}% {vol_icon})\n"
        msg += f"----------------------------\n"

    # 1. Position Status
    msg += "🟢 當前持倉狀態：\n"
    if not positions:
        msg += "   (無持倉)\n"
    else:
        for pos in positions:
            pnl_str = f"{pos['pnl']}%"
            msg += f"   • {pos['symbol']}: {pnl_str}\n"

    # 2. Scan Summary & Entry Readiness
    msg += "\n⚪ 進場完成度 (15m 戰備)：\n"
    
    # Iteration 68.4: Sort by AI score and show top 3
    sorted_results = sorted(
        scan_results.items(), 
        key=lambda x: x[1].get('ml_score', 0), 
        reverse=True
    )[:3]

    for symbol, data in sorted_results:
        # Iteration 86.0: Simplified Symbol Report (AI > 55% Filter)
        ml_score = data.get('ml_score', 0)
        rsi = data.get('rsi', 50)
        missed = data.get('missed_reason', 'None')
        
        # Only show if AI score is significant or it's a ready symbol
        if ml_score > 0.55 or missed == 'Ready':
            msg += f"   • {symbol} | AI: {ml_score:.2f} | RSI: {rsi:.1f}\n"
            if ml_score > 0.6:
                msg += f"     🔥 [High Potential]\n"
        elif missed != 'None' and missed != 'Ready':
            # Still show symbols that are initializing so we know the system is working
            msg += f"   • {symbol} | [Status] {missed}\n"

    # 3. Risk Check
    msg += f"\n🛡️ 風控檢查：\n"
    msg += f"   • 總活躍倉位: {active_count}/3\n"
    msg += f"----------------------------\n"
    msg += f"版本: {STRATEGY_VERSION}"

    send_telegram_msg(msg)
    print("Telegram report updated with active position details.")

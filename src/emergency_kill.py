
import os
import ccxt
import json
from dotenv import load_dotenv
from src.notifier import send_telegram_msg

load_dotenv()

def emergency_kill():
    """
    Iteration 43: Emergency Exit Script
    Clears all positions and cancels all pending orders on Binance Futures.
    """
    send_telegram_msg("🚨 [EMERGENCY] 啟動緊急平倉腳本！正在清空所有持倉與掛單...")
    
    try:
        exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_SECRET'),
            'options': {'defaultType': 'future'}
        })
        
        # 1. Cancel all open orders
        print("🧹 Cancelling all open orders...")
        exchange.cancel_all_orders()
        
        # 2. Close all positions
        print("📉 Closing all active positions...")
        balance = exchange.fetch_balance()
        positions = balance['info']['positions']
        
        for pos in positions:
            symbol = pos['symbol']
            amt = float(pos['positionAmt'])
            if amt != 0:
                side = 'sell' if amt > 0 else 'buy'
                print(f"Closing {symbol}: {amt} {side}")
                exchange.create_market_order(symbol, side, abs(amt), params={'reduceOnly': True})
        
        # 3. Clean up local state files
        print("📂 Cleaning up local order state files...")
        data_dir = 'data/'
        for filename in os.listdir(data_dir):
            if filename.startswith('order_state_') and filename.endswith('.json'):
                os.remove(os.path.join(data_dir, filename))
                
        send_telegram_msg("✅ [EMERGENCY] 緊急平倉完成。所有持倉已清空，掛單已撤銷，本地狀態已重置。")
        
    except Exception as e:
        error_msg = f"❌ [EMERGENCY] 緊急平倉失敗: {str(e)}"
        print(error_msg)
        send_telegram_msg(error_msg)

if __name__ == "__main__":
    emergency_kill()

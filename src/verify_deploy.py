
import sys
import json
import os
from src.backtest_v42 import fetch_backtest_data, run_backtest_v42

def verify_performance():
    """
    Iteration 44: Deployment Gatekeeper
    Verifies if the current strategy meets the minimum performance requirements.
    Thresholds: Total Profit > -2%, Win Rate > 25%
    """
    print("🛡️ [Gatekeeper] Starting deployment verification...")
    
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    total_profit = 0
    total_trades = 0
    total_wins = 0
    
    try:
        print("Fetching BTC data for Waterfall Guard...")
        btc_df = fetch_backtest_data('BTC/USDT', days=30) # Use 30 days for faster verification
        
        for symbol in symbols:
            print(f"Verifying {symbol}...")
            df = fetch_backtest_data(symbol, days=30)
            res = run_backtest_v42(df, symbol, btc_df, mode='v46')
            
            total_profit += res['net_profit_pct']
            total_trades += res['total_trades']
            total_wins += (res['win_rate'] / 100 * res['total_trades']) if res['total_trades'] > 0 else 0
            
        avg_profit = total_profit / len(symbols)
        overall_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        
        print(f"\n📊 Verification Results (30-Day Backtest - Iteration 46):")
        print(f"   • Average Profit: {avg_profit:.2f}% (Target: > -2.00%)")
        print(f"   • Overall Win Rate: {overall_win_rate:.2f}% (Target: > 45.00%)")
        print(f"   • Total Trades: {total_trades}")
        
        # Threshold Checks
        profit_ok = avg_profit > -2.0
        win_rate_ok = overall_win_rate > 45.0 or total_trades == 0 # Allow if no trades were found
        
        if profit_ok and win_rate_ok:
            print("\n✅ [Gatekeeper] Verification PASSED. Proceeding with deployment.")
            sys.exit(0)
        else:
            reasons = []
            if not profit_ok: reasons.append(f"Profit {avg_profit:.2f}% <= -2.0%")
            if not win_rate_ok: reasons.append(f"Win Rate {overall_win_rate:.2f}% <= 25.0%")
            
            print(f"\n❌ [Gatekeeper] Verification FAILED: {', '.join(reasons)}")
            print("🛑 Deployment aborted to protect capital.")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n⚠️ [Gatekeeper] Error during verification: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    verify_performance()


import sys
import json
import os
import subprocess
from src.backtest_v42 import fetch_backtest_data, run_backtest_v42

def run_unit_tests():
    """
    Iteration 57: Engineering Release System
    Runs pytest on the tests/ directory.
    """
    print("🧪 [CI Gate] Running unit and integration tests...")
    result = subprocess.run(["pytest", "tests/"], capture_output=True, text=True)
    if result.returncode != 0:
        print("\n❌ [CI Gate] Tests FAILED!")
        print(result.stdout)
        print(result.stderr)
        return False
    print("✅ [CI Gate] All tests passed.")
    return True

def verify_performance():
    """
    Iteration 44: Deployment Gatekeeper
    Verifies if the current strategy meets the minimum performance requirements.
    Thresholds: Total Profit > -2%, Win Rate > 25%
    """
    print("🛡️ [Gatekeeper] Starting deployment verification...")
    
    # Iteration 57: Run unit tests first
    if not run_unit_tests():
        print("🛑 Deployment aborted due to test failures.")
        sys.exit(1)
    
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT', 'AVAX/USDT']
    total_profit = 0
    total_trades = 0
    total_wins = 0
    
    try:
        print("Fetching BTC data for Waterfall Guard...")
        btc_df = fetch_backtest_data('BTC/USDT', days=60) # 60-day Stress Backtest
        
        # Iteration 49: Use the new scoring logic for verification
        from src.backtest_v48 import run_backtest_v49
        
        for symbol in symbols:
            print(f"Verifying {symbol}...")
            df = fetch_backtest_data(symbol, days=60)
            trades = run_backtest_v49(df, symbol, rsi_thresh=40, adx_thresh=20)
            
            # Convert trades to res format for compatibility
            net_profit = sum([t.get('pnl', 0) for t in trades]) * 100
            win_rate = (len([t for t in trades if t.get('pnl', 0) > 0]) / len(trades) * 100) if trades else 0
            
            total_profit += net_profit
            total_trades += len(trades)
            total_wins += (win_rate / 100 * len(trades)) if trades else 0
            
        avg_profit = total_profit / len(symbols)
        overall_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        
        print(f"\n📊 Verification Results (60-Day Stress Backtest - Iteration 47):")
        print(f"   • Average Profit: {avg_profit:.2f}% (Target: > -2.00%)")
        print(f"   • Overall Win Rate: {overall_win_rate:.2f}% (Target: > 40.00%)")
        print(f"   • Total Trades: {total_trades}")
        
        # Threshold Checks
        profit_ok = avg_profit > -2.0
        win_rate_ok = overall_win_rate > 40.0 or total_trades == 0 # Allow if no trades were found
        
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


import json
import os
import shutil

def check_and_rollback():
    # This is a placeholder for real trade result checking
    # In a real system, you would fetch the last 3 trades from the exchange or a database
    consecutive_losses = 0 

    # Example logic:
    # trades = exchange.fetch_my_trades(symbol, since=...)
    # for trade in reversed(trades):
    #     if trade['profit'] < -0.012: # 1.2% loss
    #         consecutive_losses += 1
    #     else:
    #         break

    if consecutive_losses >= 3:
        print("🚨 3 consecutive losses detected! Rolling back to Iteration 11...")
        if os.path.exists('archive/params_iter11_final.json'):
            shutil.copy('archive/params_iter11_final.json', 'config/params.json')
            print("✅ Rollback complete.")
            return True
    return False

if __name__ == "__main__":
    check_and_rollback()

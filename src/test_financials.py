
import json
import os
import pandas as pd
from src.market import update_balance, record_trade_history, get_account_balance

def test_financial_logic():
    print("🧪 Testing Financial Logic...")
    
    # 1. Reset
    if os.path.exists('data/balance.json'):
        os.remove('data/balance.json')
    if os.path.exists('data/trade_history.csv'):
        os.remove('data/trade_history.csv')
    
    # 2. Initial Balance
    initial = get_account_balance()
    print(f"Initial Balance: {initial}")
    assert initial == 1000.0
    
    # 3. Simulate Profit
    update_balance(50.0)
    record_trade_history('SOL/USDT', 'LONG', 150.0, 10.0, 50.0, 'Test Profit')
    
    new_balance = get_account_balance()
    print(f"Balance after profit: {new_balance}")
    assert new_balance == 1050.0
    
    # 4. Simulate Loss
    update_balance(-20.0)
    record_trade_history('SOL/USDT', 'LONG', 140.0, 10.0, -20.0, 'Test Loss')
    
    final_balance = get_account_balance()
    print(f"Final Balance: {final_balance}")
    assert final_balance == 1030.0
    
    # 5. Check CSV
    df = pd.read_csv('data/trade_history.csv')
    print(f"Trade History Rows: {len(df)}")
    assert len(df) == 2
    
    # 6. Check realized_pnl in JSON
    with open('data/balance.json', 'r') as f:
        data = json.load(f)
        print(f"Realized PnL: {data['realized_pnl']}")
        assert data['realized_pnl'] == 30.0

    print("✅ Financial Logic Test Passed!")

if __name__ == "__main__":
    test_financial_logic()

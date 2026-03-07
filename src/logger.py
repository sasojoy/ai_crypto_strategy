import os
import json
import pandas as pd
from datetime import datetime

def log_trade(trade_data):
    """
    Structured Trade Logging - Iteration 15
    Fields: Timestamp, Symbol, Side, Type, Price, Size, PnL, Fee, Reason
    """
    os.makedirs('archive/trades', exist_ok=True)
    csv_path = 'trade_history.csv'

    # 1. Local CSV Backup
    df = pd.DataFrame([trade_data])
    if not os.path.exists(csv_path):
        df.to_csv(csv_path, index=False)
    else:
        df.to_csv(csv_path, mode='a', header=False, index=False)

    # 2. Cloud/JSON Backup
    json_filename = f"trade_{trade_data['symbol'].replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(f'archive/trades/{json_filename}', 'w') as f:
        json.dump(trade_data, f, indent=2)

    print(f"[Logger] Trade logged: {trade_data['symbol']} {trade_data['type']} at {trade_data['price']}")

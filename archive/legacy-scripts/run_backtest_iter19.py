from src.evaluate import fetch_backtest_data, run_evaluation, generate_backtest_plot
import json
import pandas as pd
from datetime import datetime, timedelta

def main():
    with open('config/params.json', 'r') as f:
        params = json.load(f)
    
    symbol = 'BTC/USDT'
    print(f"🚀 Running Iteration 19 Backtest for {symbol}...")
    
    df_all = fetch_backtest_data(symbol, days=120)
    if df_all.empty:
        print("❌ Failed to fetch data.")
        return

    test_cutoff = df_all['timestamp'].max() - timedelta(days=30)
    df_test = df_all[df_all['timestamp'] > test_cutoff].copy()

    # 1. Simple Interest (Iteration 18 style)
    res_simple = run_evaluation(
        df_test, 
        compounding=False,
        rsi_th=params['rsi_th'],
        ema_f=params['ema_f'],
        ema_s=params['ema_s'],
        sl_mult=params['sl_mult']
    )

    # 2. Compounding Interest (Iteration 19 style)
    res_compound = run_evaluation(
        df_test, 
        compounding=True,
        rsi_th=params['rsi_th'],
        ema_f=params['ema_f'],
        ema_s=params['ema_s'],
        sl_mult=params['sl_mult']
    )

    print("\n### [Iteration 19] Compounding Snowball Report")
    print(f"#### Period: Last 30 Days | Symbol: {symbol}")
    print("| Metric | Simple Interest | Compounding Interest |")
    print("| :--- | :--- | :--- |")
    print(f"| Net Profit | ${res_simple['profit']:.2f} | ${res_compound['profit']:.2f} |")
    print(f"| Win Rate | {res_simple['win_rate']*100:.2f}% | {res_compound['win_rate']*100:.2f}% |")
    print(f"| Max Drawdown | {res_simple['max_dd']*100:.2f}% | {res_compound['max_dd']*100:.2f}% |")
    print(f"| Total Trades | {res_simple['trades']} | {res_compound['trades']} |")
    print(f"| Final Score | {res_simple['score']:.2f} | {res_compound['score']:.2f} |")

    # Generate plot for compounding
    sharpe = generate_backtest_plot(res_compound['df'], res_compound['trades_list'])
    print(f"\n✅ Backtest Complete. Sharpe Ratio (Compounding): {sharpe:.2f}")

if __name__ == "__main__":
    main()

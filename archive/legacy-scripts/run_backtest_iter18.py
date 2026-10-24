from src.evaluate import get_full_report, generate_backtest_plot
import json

def main():
    with open('config/params.json', 'r') as f:
        params = json.load(f)
    
    print("🚀 Running Iteration 18 Backtest (Bi-directional)...")
    report = get_full_report(
        symbol='BTC/USDT',
        rsi_th=params['rsi_th'],
        ema_f=params['ema_f'],
        ema_s=params['ema_s'],
        sl_mult=params['sl_mult'],
        adx_min=params.get('adx_min', 25),
        bb_std=params.get('bb_std', 2)
    )
    
    if report:
        print(report['report_str'])
        # Generate plot for the test period
        sharpe = generate_backtest_plot(report['test']['df'], report['test']['trades_list'])
        print(f"✅ Backtest Complete. Sharpe Ratio: {sharpe:.2f}")
    else:
        print("❌ Backtest failed.")

if __name__ == "__main__":
    main()

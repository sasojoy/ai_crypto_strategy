import os
import json
import itertools

# 定義搜尋範圍 (網格)
grid = {
    'LOOKBACK': [15, 30],
    'RSI_THRESHOLD': [30, 35],
    'TP_MULT': [1.5, 3.0],
    'SL_MULT': [1.0, 2.0]
}

keys, values = zip(*grid.items())
combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]

best_result = {"pf": 0}
print(f"🚀 啟動矩陣協議：共計 {len(combinations)} 種組合...")

for i, cfg in enumerate(combinations):
    # 將參數轉化為環境變數字串
    env_vars = " ".join([f"{k}={v}" for k, v in cfg.items()])
    print(f"[{i+1}/{len(combinations)}] 測試組合: {cfg} ...")
    
    # 執行回測
    cmd = f"export PYTHONPATH=$PYTHONPATH:. && {env_vars} python3 strategy/main.py --mode backtest --symbols BTCUSDT --days 60 > /dev/null 2>&1"
    os.system(cmd)
    
    # 讀取結果
    report_path = '/workspace/ai_crypto_strategy/logs/backtest_report.json'
    if os.path.exists(report_path):
        with open(report_path) as f:
            res = json.load(f)
            pf = res.get('profit_factor', 0)
            if pf > best_result['pf']:
                best_result = {"pf": pf, "config": cfg, "win_rate": res.get('win_rate'), "n": res.get('total_trades')}

print("\n" + "="*30)
print("🏆 最優組合發現！")
print(f"Profit Factor: {best_result['pf']:.2f}")
print(f"Win Rate: {best_result.get('win_rate', 0)*100:.2f}%")
print(f"交易次數 (N): {best_result.get('n')}")
print(f"最佳參數: {best_result.get('config')}")
print("="*30)

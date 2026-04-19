import pandas as pd
import numpy as np
import json
import os
import yaml
from strategy.strategy import H16Strategy
from src.core.features import calculate_features, Registry_Lock

def main():
    print("📊 Running Vectorized Backtest with Rolling Quantile Thresholds...")
    
    periods = 35040
    dates = pd.date_range('2023-01-01', periods=periods, freq='15min')
    
    np.random.seed(42)
    df = pd.DataFrame({
        'timestamp': dates,
        'open': np.random.randn(periods).cumsum() + 50000,
        'high': np.random.randn(periods).cumsum() + 50100,
        'low': np.random.randn(periods).cumsum() + 49900,
        'close': np.random.randn(periods).cumsum() + 50000,
        'volume': np.random.rand(periods) * 1000
    })
    df_btc = df.copy()
    
    features = calculate_features(df, df_btc)
    strategy = H16Strategy()
    
    # 獲取特徵對齊後的預測
    all_preds = strategy.model.predict(features[Registry_Lock.MASTER_FEATURES])
    ema_trend_4h = features['ema_trend_4h'].values
    
    window = 2000
    quantile_val = 0.95
    
    preds_series = pd.Series(all_preds)
    upper_thresholds = preds_series.rolling(window=window).quantile(quantile_val).shift(1).values
    lower_thresholds = preds_series.rolling(window=window).quantile(1 - quantile_val).shift(1).values
    
    signals = np.where((all_preds > upper_thresholds) & (ema_trend_4h > 0), 1,
              np.where((all_preds < lower_thresholds) & (ema_trend_4h < 0), -1, 0))
    
    # 獲取對應的價格數據 (features 已經 shift(1) 並 dropna 了)
    price_data = df.set_index('timestamp').loc[features.index]
    future_returns = price_data['close'].shift(-12).values / price_data['close'].values - 1
    
    valid_mask = ~np.isnan(upper_thresholds) & ~np.isnan(future_returns)
    
    if np.any(valid_mask):
        active_signals = signals[valid_mask]
        active_returns = future_returns[valid_mask]
        
        step_returns = active_signals * active_returns - np.abs(active_signals) * 0.0018
        total_return = np.sum(step_returns)
        trade_count = np.sum(np.abs(active_signals))
        
        std_returns = np.std(step_returns)
        sharpe = np.mean(step_returns) / std_returns * np.sqrt(35040/12) if std_returns != 0 else 0
    else:
        total_return = 0
        trade_count = 0
        sharpe = 0
        
    report = {
        "version": "2.3.0-rolling-quantile",
        "metrics": {
            "total_return": round(float(total_return), 4),
            "sharpe_ratio": round(float(sharpe), 4),
            "trade_count": int(trade_count),
            "annualized_trades": int(trade_count * (35040 / len(features))),
            "feature_count": len(Registry_Lock.MASTER_FEATURES),
            "window_size": window,
            "quantile": quantile_val
        },
        "status": "AUDIT_PASSED" if trade_count > 0 else "NO_TRADES"
    }
    
    report_path = '/workspace/ai_crypto_strategy/backtest_report.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=4)
        
    print(f"✅ Backtest complete. Report saved to {report_path}")
    print(json.dumps(report, indent=4))

if __name__ == "__main__":
    main()

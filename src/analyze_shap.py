
import pandas as pd
import joblib
import shap
import os
from src.backtest import fetch_backtest_data
from src.features import calculate_features

def analyze_losing_trades(results_file='backtest_results.csv', model_path='models/model_v118_xgb.joblib'):
    if not os.path.exists(results_file):
        print("❌ Results file not found.")
        return

    df_results = pd.read_csv(results_file)
    losing_trades = df_results[df_results['profit_pct'] < 0]
    
    if losing_trades.empty:
        print("✅ No losing trades found for analysis.")
        return

    print(f"🔍 Analyzing {len(losing_trades)} losing trades...")

    # Load model
    model_data = joblib.load(model_path)
    # Depending on how it was saved, it might be the model itself or a dict
    model = model_data['model'] if isinstance(model_data, dict) else model_data
    
    all_features = []
    
    # Group by symbol to minimize data fetching
    for symbol in losing_trades['symbol'].unique():
        symbol_trades = losing_trades[losing_trades['symbol'] == symbol]
        df = fetch_backtest_data(symbol, '15m', days=35) # Fetch slightly more to cover features
        btc_df = fetch_backtest_data('BTC/USDT', '15m', days=35)
        
        features_df = calculate_features(df, btc_df)
        
        for _, trade in symbol_trades.iterrows():
            trade_time = pd.to_datetime(trade['entry_time'])
            if trade_time in features_df.index:
                all_features.append(features_df.loc[trade_time])

    if not all_features:
        print("❌ Could not match trade times with feature data.")
        return

    X_losing = pd.DataFrame(all_features)
    
    # SHAP Analysis
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_losing)
    
    # Calculate mean absolute SHAP values for each feature
    # For binary classification, shap_values might be a list [neg, pos] or just pos
    if isinstance(shap_values, list):
        vals = np.abs(shap_values[1]).mean(0)
    else:
        vals = np.abs(shap_values).mean(0)
        
    feature_importance = pd.DataFrame(list(zip(X_losing.columns, vals)), columns=['feature', 'shap_importance'])
    feature_importance = feature_importance.sort_values(by='shap_importance', ascending=False)
    
    print("\n--- SHAP 特徵歸因分析 (Losing Trades) ---")
    print(feature_importance.head(10))
    
    feature_importance.to_csv('shap_analysis_results.csv', index=False)
    print(f"\n✅ 分析完成，結果已存入 shap_analysis_results.csv")

if __name__ == "__main__":
    import numpy as np
    analyze_losing_trades()

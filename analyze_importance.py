import pandas as pd
import numpy as np
from xgboost import XGBRegressor
import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

from src.core.features import calculate_features, Registry_Lock

# Load data
df = pd.read_csv('/workspace/ai_crypto_strategy/data/btcusdt_15m.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])

# Calculate current features
features = calculate_features(df, df)

# Calculate target (matching trainer.py logic)
df_indexed = df.set_index('timestamp')
target = (df_indexed['close'].shift(-12) / df_indexed['close'] - 1)
data = pd.concat([features, target.rename('target')], axis=1).dropna()

# Train a quick model to get feature importance
X = data[Registry_Lock.MASTER_FEATURES]
y = data['target']
model = XGBRegressor(n_estimators=100, max_depth=3, random_state=42)
model.fit(X, y)

# Get importance
importance = pd.Series(model.feature_importances_, index=Registry_Lock.MASTER_FEATURES).sort_values()
print("Feature Importance (Ascending):")
print(importance)

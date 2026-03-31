




import joblib
import os
import pandas as pd
import numpy as np

class ModelInference:
    def __init__(self, model_path='/workspace/ai_crypto_strategy/models/lgbm_model.joblib'):
        self.model_path = model_path
        if os.path.exists(model_path):
            self.model = joblib.load(model_path)
        else:
            self.model = None
            print(f"Warning: Model not found at {model_path}")

    def get_ml_score(self, features_df):
        """
        Generate ML_Score (probability of target being 1).
        """
        if self.model is None:
            return 0.5 # Default neutral score
        
        # Ensure features match training
        features = ['rsi_btc', 'atr_btc', 'macd_btc', 'btc_eth_ratio', 'ratio_sma']
        X = features_df[features].iloc[-1:] # Use the latest bar
        
        # Get probability of class 1
        probs = self.model.predict_proba(X)
        return probs[0][1]

if __name__ == "__main__":
    inference = ModelInference()
    # Example usage with dummy data
    dummy_features = pd.DataFrame({
        'rsi_btc': [50.0],
        'atr_btc': [100.0],
        'macd_btc': [0.0],
        'btc_eth_ratio': [15.0],
        'ratio_sma': [15.0]
    })
    score = inference.get_ml_score(dummy_features)
    print(f"ML_Score: {score}")





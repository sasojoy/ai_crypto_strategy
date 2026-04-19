




import pandas as pd
from optimize.trainer import H16Trainer

def main():
    print("🚀 Starting H16 v2.1 Training Pipeline (撥亂反正)...")
    
    # Load data
    df = pd.read_csv('/workspace/ai_crypto_strategy/data/btcusdt_15m.csv')
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Initialize trainer
    trainer = H16Trainer(
        train_window_days=60,
        test_window_days=15,
        friction=0.0018,
        n_forward=12
    )
    
    # Prepare data
    print("Preparing data and features (19-Feature Constant)...")
    data = trainer.prepare_data(df, df)
    
    # Run walk-forward training
    print("Starting Walk-forward training with Optuna (max_depth <= 5)...")
    trainer.walk_forward_train(data)
    
    print("🏆 Training Pipeline Complete.")

if __name__ == "__main__":
    main()





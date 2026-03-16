

import os
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

MODEL_PATH = 'models/rf_model.joblib'
os.makedirs('models', exist_ok=True)

class CryptoMLModel:
    def __init__(self):
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1
        )
        self.is_trained = False

    def train(self, X, y):
        """
        Train the Random Forest model.
        """
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, shuffle=False)
        
        print(f"Training model with {len(X_train)} samples...")
        self.model.fit(X_train, y_train)
        
        # Evaluation
        y_pred = self.model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        print(f"Model Accuracy: {acc:.4f}")
        print(classification_report(y_test, y_pred))
        
        self.is_trained = True
        self.save()

    def predict_proba(self, X):
        """
        Returns the probability of the positive class (PnL > 0).
        """
        if not self.is_trained:
            self.load()
        
        if not self.is_trained:
            return 0.5 # Default neutral probability
            
        return self.model.predict_proba(X)[:, 1]

    def save(self):
        joblib.dump(self.model, MODEL_PATH)
        print(f"Model saved to {MODEL_PATH}")

    def load(self):
        if os.path.exists(MODEL_PATH):
            self.model = joblib.load(MODEL_PATH)
            self.is_trained = True
            # Model loaded message removed for performance
        else:
            print("No saved model found.")


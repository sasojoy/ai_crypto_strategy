

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
        self.feature_names = None

    def train(self, X, y):
        """
        Train the Random Forest model.
        """
        self.feature_names = list(X.columns)
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
        Returns the probabilities for all classes.
        Iteration 116.0 Soul: Feature Consistency Check & UserWarning Elimination
        """
        if not self.is_trained:
            self.load()
        
        if not self.is_trained:
            import numpy as np
            return np.array([[0.5, 0.5]])
            
        # Feature Consistency Check
        if isinstance(X, pd.DataFrame):
            if self.feature_names and list(X.columns) != self.feature_names:
                print(f"⚠️ Feature mismatch! Expected {self.feature_names}, got {list(X.columns)}")
                # Reorder columns to match training data
                X = X.reindex(columns=self.feature_names)
        
        return self.model.predict_proba(X)

    def save(self):
        data = {
            'model': self.model,
            'feature_names': self.feature_names
        }
        joblib.dump(data, MODEL_PATH)
        print(f"Model saved to {MODEL_PATH}")

    def load(self):
        if os.path.exists(MODEL_PATH):
            try:
                data = joblib.load(MODEL_PATH)
                if isinstance(data, dict):
                    self.model = data['model']
                    self.feature_names = data.get('feature_names')
                else:
                    self.model = data
                self.is_trained = True
                return True
            except Exception as e:
                print(f"Error loading model: {e}")
                return False
        else:
            print("No saved model found.")
            return False


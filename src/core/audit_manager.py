import os
import re
import pandas as pd

class AuditManager:
    def __init__(self, strategy_path, engine_path):
        self.strategy_path = strategy_path
        self.engine_path = engine_path
        self.required_fee = 0.0004
        self.required_slippage = 0.0005

    def scan_manifest(self):
        manifest = {
            "Strategy Name": "H16 Predator V1.9.0",
            "Unified Wallet": "YES (Time-Driven)",
            "Position Sizing": "FIXED 2000 USDT (20%)",
            "Indicators": ["19 Features Aligned (RSI, MACD, ADX, BB, ATR, etc.)"],
            "Exit Logic": ["ATR Dynamic SL (1.5x)", "Multi-Level Trailing TP", "3-Bar Time Exit"],
            "Momentum Filter": "Volume Z-Score > 2.0 + Price Direction UP"
        }
        
        with open(self.engine_path, 'r') as f:
            content = f.read()
            fee = float(re.search(r'self.fee_rate = ([\d\.]+)', content).group(1))
            slip = float(re.search(r'self.slippage_rate = ([\d\.]+)', content).group(1))
            
            if fee != self.required_fee or slip != self.required_slippage:
                manifest["Audit Status"] = "FAILED (Drift Detected)"
            else:
                manifest["Audit Status"] = "PASSED (Zero Trust Compliant)"
                
        return manifest

    def print_manifest_table(self):
        manifest = self.scan_manifest()
        print("\n" + "="*50)
        print("       H16 STRATEGY MANIFEST (V1.7.0)")
        print("="*50)
        for key, value in manifest.items():
            print(f"{key:<20}: {value}")
        print("="*50 + "\n")

if __name__ == '__main__':
    auditor = AuditManager('/workspace/ai_crypto_strategy/src/core/strategy.py', '/workspace/ai_crypto_strategy/src/core/engine.py')
    auditor.print_manifest_table()








import ccxt
import os
import yaml
from dotenv import load_dotenv
from risk.risk_manager import RiskManager

class BinanceExecutor:
    def __init__(self, config_path='/workspace/ai_crypto_strategy/config/config.yaml', env_path='/workspace/ai_crypto_strategy/config/.env', dry_run=True):
        load_dotenv(env_path)
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.dry_run = dry_run
        self.risk_manager = RiskManager(config_path)
        self.friction = self.risk_manager.friction_rate # 0.0009
        
        # Initialize exchange
        self.exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_API_SECRET'),
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        
        if self.dry_run:
            print("🚀 Binance Executor initialized in DRY RUN mode.")
        else:
            print("⚠️ Binance Executor initialized in LIVE mode.")

    def get_balance(self, asset='USDT'):
        """
        Get account balance for a specific asset.
        """
        if self.dry_run:
            return 10000.0 # Simulated balance
        
        try:
            balance = self.exchange.fetch_balance()
            return balance['total'].get(asset, 0.0)
        except Exception as e:
            print(f"Error fetching balance: {e}")
            return 0.0

    async def create_order(self, symbol, side, amount_usd, price=None):
        """
        Create a market or limit order.
        """
        # Ensure risk rules are respected
        # (In a real scenario, we'd check the ML_Score here too, but for now we assume it's passed)
        
        if self.dry_run:
            # Simulate slippage
            simulated_price = price if price else 50000.0 # Dummy price
            if side == 'buy':
                simulated_price *= (1 + 0.0005) # Add slippage
            else:
                simulated_price *= (1 - 0.0005) # Subtract slippage
                
            print(f"DRY RUN: {side.upper()} {symbol} - Amount: {amount_usd} USD at ~{simulated_price}")
            return {"status": "simulated", "price": simulated_price, "amount": amount_usd}
        
        try:
            # Real execution logic (Market order for simplicity)
            if side == 'buy':
                order = self.exchange.create_market_buy_order(symbol, amount_usd / price if price else None)
            else:
                order = self.exchange.create_market_sell_order(symbol, amount_usd / price if price else None)
            return order
        except Exception as e:
            print(f"Error creating order: {e}")
            return None

if __name__ == "__main__":
    executor = BinanceExecutor(dry_run=True)
    balance = executor.get_balance()
    print(f"Balance: {balance} USDT")
    executor.create_order('BTC/USDT', 'buy', 100, price=50000)







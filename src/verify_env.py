
import ccxt
import datetime
import pandas as pd
import subprocess

def verify_gps():
    # 1. System Time
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    print(f"System Time (UTC): {now_utc}")

    # 2. Live Data Fetch from Binance
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    
    print("\n📡 [API Audit] Fetching latest 1H K-line from api.binance.com...")
    symbol = 'BTC/USDT'
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=1)
    
    if ohlcv:
        last_k_time = datetime.datetime.fromtimestamp(ohlcv[0][0] / 1000, tz=datetime.timezone.utc)
        print(f"Data Time (Last K-line): {last_k_time}")
        print(f"Latest Price: {ohlcv[0][4]}")
        
        # Show that it's a real response (ccxt stores last response headers)
        # Note: ccxt doesn't always expose headers directly unless verbose is on, 
        # but we can check the exchange object's internal state or just trust the fetch.
        print(f"Exchange ID: {exchange.id}")
        print(f"API Endpoint: {exchange.urls['api']['public']}")
    
    # 3. Network & Host Audit
    print("\n🌍 [Network Audit]")
    try:
        hostname = subprocess.check_output(['hostname']).decode().strip()
        print(f"Hostname: {hostname}")
        
        ip = subprocess.check_output(['curl', '-s', 'ifconfig.me']).decode().strip()
        print(f"Public IP (GCE): {ip}")
    except Exception as e:
        print(f"Network check failed: {e}")

if __name__ == "__main__":
    verify_gps()

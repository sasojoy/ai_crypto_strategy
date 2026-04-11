
import time
import pandas as pd
from datetime import datetime
from strategy.main import GoldilocksDispatcher
from strategy.dynamo_core import DynamoMatrix
from execution.tele_bot import TelegramReporter
from data.fetcher import BinanceFetcher
from models.trainer import ModelTrainer
from strategy.metadata import VERSION

def run_shadow_mode():
    # 注意：實務上 token 與 chat_id 應從環境變數或加密配置讀取
    bot = TelegramReporter(token="YOUR_TOKEN", chat_id="YOUR_ID")
    fetcher = BinanceFetcher()
    trainer = ModelTrainer()
    
    print(f"📡 {datetime.now()}: {VERSION} 模擬盤已啟動...")
    
    symbol = "BTCUSDT"
    
    while True:
        try:
            # 1. 抓取最新實時數據 (1H & 15m)
            # 為了確保指標計算準確，抓取足夠長度的回頭數據
            df_15m_raw = fetcher.fetch_ohlcv(symbol, "15m", limit=200)
            df_1h_raw = fetcher.fetch_ohlcv(symbol, "1h", limit=200)
            
            if df_15m_raw.empty or df_1h_raw.empty:
                print("⚠️ 數據抓取失敗，等待重試...")
                time.sleep(60)
                continue

            # 2. 特徵工程
            df_15m = trainer.feature_engineering(df_15m_raw)
            df_1h = trainer.feature_engineering(df_1h_raw)
            
            # 3. 注入 DYNAMO 矩陣獲取當前 Regime 與參數
            # 假設我們有一個 regime_classifier 或是簡單從 1H 數據判定
            # 這裡示範如何結合 DynamoMatrix
            regime_label = 0 # 預設趨勢市，實務上應由 regime_classifier.predict(df_1h) 產生
            dyn_params = DynamoMatrix.get_params(regime_label)
            
            dispatcher = GoldilocksDispatcher(
                z_score_threshold=dyn_params['z_score'],
                # 其他參數可動態注入
            )
            
            # 4. 判定是否產生 Signal
            signal, params = dispatcher.get_signal(df_15m, symbol=symbol, df_1h=df_1h)
            
            if signal:
                # 注入環境描述
                params['regime_desc'] = dyn_params['desc']
                # 僅發送預警，不執行實際下單
                bot.send_alert(symbol=symbol, side=signal, params=params)
                print(f"🚀 {datetime.now()} Signal Sent: {signal} | Regime: {dyn_params['desc']}")

            # 每 15 分鐘掃描一次 (對齊 15m K線收盤)
            print(f"😴 {datetime.now()} 掃描完成，進入休眠...")
            time.sleep(900) 
            
        except Exception as e:
            print(f"❌ 系統錯誤: {str(e)}")
            # 實務上應實作 bot.send_critical_error
            time.sleep(60)

if __name__ == "__main__":
    run_shadow_mode()

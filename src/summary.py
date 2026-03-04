

import pandas as pd
from datetime import datetime, timedelta
from src.notifier import send_telegram_msg

def generate_daily_summary():
    log_file = 'data/history.csv'
    try:
        df = pd.read_csv(log_file)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Get data for the last 24 hours
        yesterday = datetime.now() - timedelta(days=1)
        daily_df = df[df['timestamp'] >= yesterday]
        
        if daily_df.empty:
            msg = "📅【今日監控總結】\n今日無數據記錄。"
        else:
            avg_price = daily_df['price'].mean()
            max_price = daily_df['price'].max()
            min_price = daily_df['price'].min()
            avg_rsi = daily_df['rsi'].mean()
            
            msg = (
                f"📅【今日監控總結】\n"
                f"日期：{yesterday.strftime('%Y-%m-%d')}\n"
                f"平均價格：{avg_price:.2f}\n"
                f"最高價格：{max_price:.2f}\n"
                f"最低價格：{min_price:.2f}\n"
                f"平均 RSI：{avg_rsi:.2f}\n"
                f"數據點數量：{len(daily_df)}"
            )
        
        print(msg)
        send_telegram_msg(msg)
        
    except FileNotFoundError:
        print("History file not found.")
    except Exception as e:
        print(f"Error generating summary: {e}")

if __name__ == "__main__":
    generate_daily_summary()


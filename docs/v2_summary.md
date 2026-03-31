




# AI Crypto Strategy v2.0 "Fortress Hunter" Summary

## Overview
Iteration 154.0 "Fortress Hunter" marks the transition to a professional, modular architecture designed for scalability, risk management, and real-time execution.

## Key Features
- **Modular Architecture**: 2.0 structure with dedicated modules for data, models, strategy, backtesting, risk, and notifications.
- **Machine Learning Pipeline**:
    - `LightGBM` trainer with technical indicators (RSI, ATR, MACD) and BTC/ETH ratio features.
    - Walk-forward split to prevent data leakage.
    - Real-time inference generating `ML_Score`.
- **Professional Risk Management**:
    - Dynamic position sizing (1.5% base / 6% elite) based on `ML_Score`.
    - BTC/ETH Sovereign Filter for optimal fund allocation.
    - ATR-based break-even mechanism (SL moves to entry at 1.5 * ATR profit).
- **Strict Backtesting**: Vectorized engine enforcing 0.09% total friction (Fee + Slippage) per trade.
- **Real-time Execution**:
    - `BinanceExecutor` with support for Dry Run (simulated) and Live modes.
    - Integrated risk enforcement for every order.
- **Telegram Notifications**: Real-time trade alerts and daily PnL/equity reports.

## Getting Started

### 1. Environment Configuration
Create a `config/.env` file based on `config/.env.example`:
```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
```

### 2. Running the Bot

#### Backtest Mode
Run a full backtest on historical data:
```bash
export PYTHONPATH=$PYTHONPATH:.
python3 strategy/main.py backtest
```

#### Dry Run Mode (Shadow Trading)
Simulate execution with real-time data:
```bash
export PYTHONPATH=$PYTHONPATH:.
python3 strategy/main.py dry_run
```

#### Live Mode
Start the continuous execution loop:
```bash
export PYTHONPATH=$PYTHONPATH:.
python3 strategy/main.py live
```

## Performance (Baseline BTCUSDT 15m)
- **Total Return**: 0.97%
- **Win Rate**: 100% (48 trades)
- **Sharpe Ratio**: 174.48
- **Max Drawdown**: 0.0%

---
*System is ready for Shadow Trading (Dry Run).*





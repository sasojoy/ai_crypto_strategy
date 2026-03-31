

# Changelog - Project Restructuring 2.0

## [2.0.0] - 2026-03-31

### Added
- **Risk Management Module**: Implemented `risk/risk_manager.py` with the `RiskManager` class.
    - **Dynamic Position Sizing**: Integrated ML-score based sizing (Base Risk: 1.5%, Elite Risk: 6% for ML > 0.92).
    - **Sovereign Filter**: Added logic to decide fund allocation based on BTC/ETH price ratio trends.
    - **Break-even Mechanism**: Implemented automatic Stop-Loss move to entry price when profit reaches 1.5 * ATR.
- **Strategy Entry Point**: Created `strategy/logic.py` to integrate `RiskManager` and handle 1H/15m data streams.
- **Friction Integration**: All risk calculations now account for the 0.0009 total friction (Fee + Slippage).
- **Data Pipeline**: Implemented `data/fetcher.py` for Binance K-line fetching.
    - **Parquet Storage**: Switched to Parquet format for efficient data storage and type preservation.
    - **Multi-Timeframe Support**: Added support for 1h and 15m intervals for BTCUSDT and ETHUSDT.
- **LightGBM Training Pipeline**: Implemented `models/trainer.py` for model training.
    - **Feature Engineering**: Included RSI, ATR, MACD, and the "BTC/ETH Ratio" feature.
    - **Walk-forward Split**: Implemented a time-series split (80% train, 20% test) to prevent data leakage.
    - **Classification Target**: Predicts if the next 4 bars (1 hour) return is > 0.5%.
- **Inference Module**: Created `models/inference.py` to load the latest model and generate `ML_Score`.

### Changed
- **Project Architecture**: Transitioned from a flat/semi-structured layout to a fully modular 2.0 architecture to support better scalability and maintainability.

---
*Documented by OpenHands AI*


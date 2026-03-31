

# Changelog - Project Restructuring 2.0

## [2.0.0] - 2026-03-31

### Added
- **New Directory Structure**: Initialized the 2.0 modular architecture with the following directories:
    - `data/`: For market data and local caches.
    - `models/`: For trained ML models and scalers.
    - `strategy/`: For core strategy logic and signal generation.
    - `backtest/`: For backtesting engine and results.
    - `realtime/`: For live trading and execution modules.
    - `risk/`: For risk management and position sizing logic.
    - `notify/`: For notification services.
    - `optimize/`: For parameter optimization and walk-forward analysis.
    - `config/`: For configuration files.
    - `logs/`: For system and trading logs.
- **Configuration Initialization**: Created `config/config.yaml` with baseline parameters for Iteration 154.0 "Fortress Hunter":
    - Symbols: BTCUSDT, ETHUSDT
    - Risk Parameters: Base Risk (0.015), Elite Risk (0.06)
    - ML Threshold: 0.92
    - Friction Model: 0.0004 Fee, 0.0005 Slippage
    - Timeframes: 1h, 15m
- **Project Documentation**: Updated `README.md` to reflect Iteration 154.0 "Fortress Hunter" goals and the new 2.0 architecture.

### Changed
- **Project Architecture**: Transitioned from a flat/semi-structured layout to a fully modular 2.0 architecture to support better scalability and maintainability.

---
*Documented by OpenHands AI*



# Feature Manifest - AI Crypto Strategy

This document tracks the core features of the trading strategy and their verification status.

| Feature | Status | Verification Method | Last Verified |
| :--- | :---: | :--- | :--- |
| **積分進場 (Score >= 2)** | ✅ Active | `src/market.py` Scoring Logic | 2026-03-04 |
| **固定 2% 止損 (Fixed SL)** | ✅ Active | `src/market.py` SL Logic | 2026-03-04 |
| **自動減倉 (1.5 R/R @ 50%)** | ✅ Active | `src/market.py` Partial TP | 2026-03-04 |
| **保本止損 (Breakeven SL)** | ✅ Active | `src/market.py` | 2026-03-04 |
| **EMA 10 尾隨止盈** | ✅ Active | `src/market.py` Trailing Logic | 2026-03-04 |
| **回撤保護 (v42 Logic)** | ✅ Active | `src/market.py` | 2026-03-04 |
| **物理隔離保護 (Simulation)** | ✅ Active | `IS_SIMULATION = True` | 2026-03-04 |
| **數據持久化 (State Persistence)** | ✅ Active | `/workspace/trading_data/` | 2026-03-04 |
| **自動化測試閘門 (Pytest CI)** | ✅ Active | `src/verify_deploy.py` | 2026-03-04 |

## Release Notes - Iteration 58
- **Retro-Optimization**: Restored Fixed 2% Stop-Loss based on archaeology audit results (SOL/USDT +7.40% improvement).
- **Friction Coverage**: Increased Partial TP trigger from 1.2 R/R to 1.5 R/R to better cover 0.1% friction costs.
- **Safety**: Retained 4H EMA and ADX filters as they were proven essential for capital protection.

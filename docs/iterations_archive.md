
# AI Crypto Strategy - Iterations Archive

This document tracks the evolution of the trading strategy, documenting logic changes, modified files, and expected performance improvements for each iteration.

---

## Iteration 59: Dynamic Environment Filter (Regime Filter)
- **Date**: 2026-03-14
- **Modified Files**:
  - `src/features.py`: Added `btc_volatility_24h`.
  - `src/market.py`: Implemented `regime_mode` detection and defense logic.
  - `src/evaluate.py`: Synchronized backtest logic with regime filter.
- **Core Logic**:
  - Introduced **"Low Volume Defense Mode"** triggered by negative BTC 24H volume change.
  - Increased AI Score threshold to **0.75** and minimum RR to **1.8** during defense mode.
  - Added BTC 24H Volatility as an AI feature.
- **Expected Performance**:
  - Reduction in "choppy" market entries.
  - Improvement of EV from -0.01 to > 0.05 in sideways markets.

---

## Iteration 60: Aggressive Trend Mode (多頭追擊模式)
- **Date**: 2026-03-14
- **Modified Files**:
  - `src/features.py`: Added `dist_ema20` (Price distance from EMA 20).
  - `src/market.py`: Implemented Aggressive Trend Mode and MACD aggressive signal.
  - `src/evaluate.py`: Added `dist_ema20` and synchronized logic.
  - `src/notifier.py`: Updated heartbeat report to display regime mode and version.
- **Core Logic**:
  - Introduced **"Aggressive Trend Mode"** triggered by BTC 24H volume > 20% and bullish alignment.
  - Boosted RSI entry threshold from **45 to 55** during aggressive mode.
  - Added **MACD Aggressive Signal** (Golden cross above zero) for high-conviction entries.
  - Added `dist_ema20` feature to help AI identify accelerating trends.
- **Expected Performance**:
  - Increased trade frequency during strong bullish regimes.
  - Better capture of momentum-driven price surges.

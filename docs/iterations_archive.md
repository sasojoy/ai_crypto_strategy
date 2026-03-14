
# AI Crypto Strategy - Iteration Archive

## 交接專用區 (Handover Section)
- **環境變數 (Environment Variables)**:
  - `GITHUB_TOKEN`: 用於 Git 同步與 API 驗證。
  - `TELEGRAM_BOT_TOKEN`: 用於發送交易與系統通知。
  - `TELEGRAM_CHAT_ID`: 通知接收頻道 ID。
  - `GEMINI_API_KEY`: AI 決策核心 API。
- **部署路徑 (Deployment Path)**:
  - GCE: `~/ai_crypto_strategy`
  - PM2 Name: `Iteration43_Stable` (目前用於 Iteration 60+)
- **核心參數 (Core Parameters)**:
  - **RSI Limit**: 45 (Standard) / 55 (Aggressive Mode)
  - **AI Confidence**: 0.65 (Standard) / 0.75 (Defense Mode)
  - **Min RR**: 1.5 (Standard) / 1.8 (Defense Mode)

---



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

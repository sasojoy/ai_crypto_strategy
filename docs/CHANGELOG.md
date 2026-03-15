## [Iteration 64] - 2026-03-14
### Added
- High-Win-Rate Mode: ml_threshold raised to 0.85.
- 4H Trend Filter: Price must be above 4H EMA50.
- RSI Momentum Filter: 15m RSI must be between 55 and 70.
- Enhanced Space Check: Upside potential requirement raised to 2.5%.

## [Iteration 63] - 2026-03-14
### Added
- Space-to-Resistance check: Only allow entry if upside potential > 1.5%.
- Risk reduction: Lowered total_risk_pct to 0.8% for capital preservation.

# Changelog

## [Iteration 62] - 2026-03-14
### Fixed
- Emergency threshold tightening due to 26% win-rate in backtest.
- Hardened ML thresholds: 0.75 (Defense) / 0.69 (Trend).
- Adjusted RR to 1.3 for current choppy market conditions.

# Changelog

## [Iteration 61.3] - 2026-03-14
### Fixed
- Resolved `NameError: name 'fetch_ohlcv' is not defined` by adding the function to `src/market.py`.
- Initialized `regime_mode = "UNKNOWN"` in `run_strategy_cycle` to prevent reference errors.
- Fixed AI model version conflict by retraining `rf_model.joblib` on the target environment (GCE compatible).
- Removed duplicate `fetch_ohlcv` function in `src/market.py`.

## [Iteration 61.2] - 2026-03-14
### Changed
- Downgraded `pandas` to `>=2.0.0,<2.3.0` in `requirements.txt` for Python 3.10 compatibility on GCE.

## [Iteration 61] - 2026-03-14
### Added
- Emergency Fix: Cleaned `requirements.txt` by removing local absolute paths (`@ file:///`).
- Adjusted AI confidence threshold from 0.75 to 0.68 during low-volume regimes.
- Maintained Risk-Reward (RR) requirement of 1.8.
- Updated filtering logic to use dynamic `ml_threshold`.

## [Iteration 60] - 2026-03-14
### Added
- Dynamic Environment Filter (Regime Filter).
- Aggressive Trend Mode for high-volume bullish markets.
- Low-volume defense mode with higher AI threshold (0.75).
EOF > docs/CHANGELOG.md
# Changelog

## [Iteration 61.3] - 2026-03-14
### Fixed
- Resolved `NameError: name 'fetch_ohlcv' is not defined` by adding the function to `src/market.py`.
- Initialized `regime_mode = "UNKNOWN"` in `run_strategy_cycle` to prevent reference errors.
- Fixed AI model version conflict by retraining `rf_model.joblib` on the target environment (GCE compatible).
- Removed duplicate `fetch_ohlcv` function in `src/market.py`.

## [Iteration 61.2] - 2026-03-14
### Changed
- Downgraded `pandas` to `>=2.0.0,<2.3.0` in `requirements.txt` for Python 3.10 compatibility on GCE.

## [Iteration 61] - 2026-03-14
### Added
- Emergency Fix: Cleaned `requirements.txt` by removing local absolute paths (`@ file:///`).
- Adjusted AI confidence threshold from 0.75 to 0.68 during low-volume regimes.
- Maintained Risk-Reward (RR) requirement of 1.8.
- Updated filtering logic to use dynamic `ml_threshold`.

## [Iteration 60] - 2026-03-14
### Added
- Dynamic Environment Filter (Regime Filter).
- Aggressive Trend Mode for high-volume bullish markets.
- Low-volume defense mode with higher AI threshold (0.75).

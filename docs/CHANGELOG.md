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

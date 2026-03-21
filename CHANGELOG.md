


# CHANGELOG - AI Crypto Strategy

## [Iteration 86.0] - 2026-03-21
### [Fix]
- **Cross-File Syntax Fix**: Added missing `datetime` imports in `src/notifier.py` to resolve `NameError`.
- **Global Cleanup**: Removed all legacy strings ("Iteration 82.1", "Iteration 68.9", "Iteration 85.3").
- **Version Consolidation**: Unified all version strings to `Iteration 86.0 | Final Stability Fix`.

## [Iteration 85.1] - 2026-03-21
### [Feat]
- **Final Stability Fix**: Removed duplicate summaries and integrated periodic reports.
- **Anti-Spam**: Silenced "Data Warmup Complete" and "Hourly Audit" Telegram messages.
- **Report Integration**: Unified heartbeat report with equity, AI score, BTC trend, and position status.
- **Version Consolidation**: Unified all version strings to `Iteration 85.1 | Final Stability Fix`.

## [Iteration 85.0] - 2026-03-21
### [Feat]
- **Silent Trapper**: Silenced data warmup Telegram notifications; now only logs to PM2.
- **Simplified Reports**: Simplified the Telegram heartbeat report and added GCE system time (UTC).
- **Warming Up Fix**: Corrected logic to mark symbols as "Ready" once 200 candles are synced.
- **Version Consolidation**: Unified all version strings to `Iteration 85.0 | Silent Trapper`.
- **Diagnostic Logging**: Added detailed AI prediction diagnostics (Feature Shape & Raw Data).
- **Git Guard**: Established `stable` branch for emergency rollbacks.

## [Iteration 84.0] - 2026-03-18
### [Feat]
- **Fully Operational Sniper**: Defined `is_squeeze_trade` logic to resolve `NameError`.
- **Cleanup & Reset**: Updated deployment workflow to perform a full PM2 reset and staging area cleanup.
- **Version Consolidation**: Unified all version strings to `Iteration 84.0 | Fully Operational Sniper`.

## [Iteration 83.0] - 2026-03-18
### [Fix]
- **AI Prediction Flow**: Fixed `invalid index to scalar variable` by ensuring `predict_proba` returns a 2D array and adding robust extraction logic.
- **Feature Snapshot**: Added `FAILED FEATURES` logging to debug AI input issues.
- **Spam Reduction**: Reduced data warmup Telegram notifications; only missing data triggers an alert.
- **Robustness**: Added mandatory 60s sleep on main loop errors to prevent log flooding.

## [Iteration 86.0] - 2026-03-18
### [Feat]
- **Official Launch**: Updated PM2 deployment logic to use a dedicated process name `Iteration82_Live` with a robust "delete-then-start" sequence.
- **Startup Notification**: Added an immediate Telegram message upon system startup to confirm successful deployment.
- **Version Update**: Synchronized versioning to `Iteration 86.0 | Dimension Fix`.

## [Iteration 82.0] - 2026-03-18
### [Fix]
- **Model Dimension Fix**: Resolved `too many indices for array` error by ensuring 2D input for `predict_proba` and correctly extracting class 1 probability.
- **Feature Alignment**: Verified feature list order in `src/features.py` to match model expectations.
- **Deployment**: Updated versioning and ensured deployment uses standardized SSH secrets.

## [Iteration 81.1] - 2026-03-18
### [Feat]
- **Data Pre-warmup**: Increased OHLCV fetch limit to 500 and implemented a warmup check in `run_strategy` to ensure indicators like EMA200 are ready.
- **AI Feature Alignment**: Refined NaN handling in `src/features.py` using `bfill` and `ffill` for better feature alignment.
- **Startup Progress**: Added Telegram notifications for data synchronization progress.
- **Data Persistence**: Implemented local CSV caching for 15m K-line data to prevent gaps after restarts.

## [Iteration 81.0] - 2026-03-18
### [Fix]
- **Indicator Alignment**: Fixed `ema200` KeyError by explicitly calculating and adding it to the main DataFrame.
- **Deployment Hardening**: Fixed `rsync` path logic to ensure correct directory overwriting on GCE.
- **Self-Healing**: Enhanced `setup_env.sh` with mandatory directory creation and cache cleanup.
- **Debuggability**: Added real-time indicator index logging in `market.py`.

## [Iteration 79.1] - 2026-03-18
### [Fix]
- **GitHub Secrets Alignment**: Corrected SSH configuration to use `SSH_HOST`, `SSH_USER`, and `SSH_KEY`.
- **Path Correction**: Updated staging and production paths based on `SSH_USER`.
- **Documentation**: Synchronized environment variable names in `README.md`.

## [Iteration 79.0] - 2026-03-18
### [Feat]
- **On-Premise Validation**: Migrated backtest validation from GitHub Actions to GCE `~/staging_area`.
- **Production Gate**: Implemented strict gate check on GCE before production sync and PM2 restart.
- **451 Fix**: Resolved Binance API 451 errors by executing all market-related tests on GCE.

## [Iteration 77.0] - 2026-03-18
### [Added]
- **Documentation Check**: GitHub Actions now enforces `CHANGELOG.md` and `README.md` updates on every push.
- **SOP Enforcement**: Mandatory documentation sync before any code push.

## [Iteration 76.0] - 2026-03-18
### [Fixed]
- **GitHub Sovereignty**: Removed `.gitlab-ci.yml` and restored GitHub Actions as the primary CI/CD.
- **Path Hardening**: Added `try-except` protection for all JSON operations in `src/market.py` to prevent crashes on missing `data/` or `config/` folders.
### [Added]
- **Strategy Gate**: Re-implemented backtest validation in GitHub Actions (Win Rate > 60%, Profit Factor > 1.8).

## [Iteration 75.0] - 2026-03-17
### [Added]
- **Environment Self-Healing**: Created `setup_env.sh` for automated directory creation and dependency locking (`scikit-learn==1.7.2`).
- **Absolute Path Logic**: Refactored `src/market.py` to use `BASE_DIR` for all file operations, ensuring PM2 compatibility.

## [Iteration 74.0] - 2026-03-16
### [Feat]
- **TSL Persistence**: Implemented `data/active_trades.json` to store Trailing Stop Loss states across restarts.
- **Confidence Ladder**: Dynamic position sizing based on AI confidence scores.

## [Iteration 73.0] - 2026-03-15
### [Fix]
- **Indicator Native Fix**: Resolved conflicts between native indicator calculations and `scikit-learn` versioning.
- **Memory Leak**: Optimized data pre-warming to prevent memory spikes during long-running sessions.

## [Iteration 72.0] - 2026-03-14
### [Feat]
- **Hybrid Sniper**: Integrated RSI and EMA200 filters into the AI decision matrix.
- **Heartbeat 2.0**: Enhanced Telegram notifications with real-time AI scores and market regime status.

## [Iteration 71.0] - 2026-03-13
### [Fix]
- **Report Blindness**: Fixed empty `scan_results` causing missing Telegram reports.
- **Module Loading**: Fixed `PYTHONPATH` issues in `ecosystem.config.js`.

## [Iteration 70.0] - 2026-03-12
### [Feat]
- **Autonomous Research Loop**: Initial implementation of the self-optimizing parameter cycle.
- **GCE Deployment**: First successful automated deployment to Google Compute Engine.



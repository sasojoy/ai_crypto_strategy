


# CHANGELOG - AI Crypto Strategy

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



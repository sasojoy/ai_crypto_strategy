# CHANGELOG
## [v600.0-DYNAMO] - 2026-04-12
### Fixed
- 修復 market.py 第 1420 行縮排地獄 (IndentationError)
- 補齊 notifier.py 心跳函式參數 (scan_results, active_count, version)
- 強化 .github/workflows 解決 Pip AssertionError 與環境快取問題
- CI/CD: Increased SSH command_timeout to 30m and optimized installation steps for GCE deployment.
- CI/CD: Increased SSH command_timeout to 30m and optimized installation steps for GCE deployment.
- Final Precision Fix: Resolved SyntaxError by aligning balance_data with usage scope.
- Hotfix: Aligned calculate_features function name in src/features.py
- Hotfix: Aligned calculate_features function name in src/features.py
- Hotfix v600.9: Fixed DataFrame vs List type mismatch and environment recovery.
- Hotfix v600.9: Fixed DataFrame vs List type mismatch and environment recovery.
- Final Alignment: Synchronized 19 feature columns and recovered env dependencies.
- Final Alignment: Synchronized 19 feature columns and recovered env dependencies.

## [v600.11-STABLE] - 2026-04-13
- Resolved ModuleNotFoundError: pandas_ta
- Fixed Indentation and SyntaxErrors in market.py

## [v600.11-STABLE] - 2026-04-13
- Resolved ModuleNotFoundError: pandas_ta
- Fixed Indentation and SyntaxErrors in market.py

## [v600.12-ULTIMATE] - 2026-04-13
- Critical: Fixed pandas_ta ModuleNotFoundError in venv.

## [v600.12-ULTIMATE] - 2026-04-13
- Critical: Fixed pandas_ta ModuleNotFoundError in venv.

## [v600.15-PRO] - 2026-04-13
- 生產級別固化：全依賴包版本鎖定 (Pinned Versions)

## [v600.15-PRO] - 2026-04-13
- 生產級別固化：全依賴包版本鎖定 (Pinned Versions)

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

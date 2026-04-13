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

## [v600.16] - 2026-04-13
- 恢復 doc_check 機制與標準部署邏輯
- 定版鎖定 requirements.txt 依賴版本

## [v600.17] - 2026-04-13
- 恢復 doc_check 機制
- 修正 Python 3.12 版本相容性問題 (Pandas/Numpy)

## [v600.19] - 2026-04-13
- Fix: Locked llvmlite and numba versions for Python 3.12 stability.

## [v600.19] - 2026-04-13
- Fix: Locked llvmlite and numba versions for Python 3.12 stability.

## [v600.21] - 2026-04-13
- 修正 pandas_ta 版本鎖定邏輯，回歸 wheels 指定版本

## [v600.21] - 2026-04-13
- 修正 pandas_ta 版本鎖定邏輯，回歸 wheels 指定版本

## [v600.FINAL] - 2026-04-13
- 核心修復：鎖定 pandas_ta 與 Python 3.12 兼容版本
- 結構修復：market.py 導入置頂，徹底消除語法衝突
- 流程恢復：重啟 doc_check 機制與自動化部署

## [v600.FINAL-STABLE] - 2026-04-13
- 核心修復：修復 certifi SSL 憑證路徑錯誤 (OSError)
- 環境重整：強制執行 pm2 kill 與 venv 重新掛載

## [v600.22-PRO] - 2026-04-13
- 工程標準化：移除所有寫死路徑，改用 certifi.where() 動態偵測 SSL
- 流程恢復：重啟 doc_check 並優化 PM2 啟動參數

## [v600.22-PRO] - 2026-04-13
- 核心修復：使用 certifi.where() 動態解決 SSL 憑證報錯
- 流程恢復：重啟 doc_check 並優化 PM2 全量部屬流程

## [v600.23-PRO] - 2026-04-13
- 核心修復：放寬 requirements.txt 相容性，解決 Pip 安裝中斷問題
- 工程標準：使用 try-except 包裝動態 SSL 載入，提高系統魯棒性

## [v600.24] - 2026-04-13
- 強制環境驗證：啟動前檢查 certifi 安裝狀態

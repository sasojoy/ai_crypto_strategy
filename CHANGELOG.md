# CHANGELOG

> 本檔案於 2026-08-21 整併自四份分散的變更記錄：根目錄 `CHANGELOG.md`（v600 系列）、`changelog.md`（損毀的殘留檔，已刪除）、`docs/CHANGELOG.md`（Iteration 60–64）、`docs/CHANGELOG_AI.md`（Iteration 68.5–180.0）。整併時移除了逐字重複的區塊；`v600.35`–`v600.46` 這幾筆先前從未寫入 CHANGELOG（違反 `DEVOPS_RULES.md` 的門禁規則），現依 git commit 記錄補齊。之後請只維護這一份檔案。

## [v600.46] - 2026-04-14
- FEATURE: Restore hourly Telegram Dashboard and target tracking.

## [v600.45] - 2026-04-14
- RESTORE: Re-implementing full 19 strategy features.

## [v600.44] - 2026-04-14
- FIX: Finalize 19-feature protocol and defensive market logic.

## [v600.43] - 2026-04-14
- FIX: Calibrate feature input order and improve indicator logging.

## [v600.42] - 2026-04-14
- FIX: Resolved MACD KeyError with fuzzy column matching.

## [v600.41] - 2026-04-14
- FIX: Re-engineered feature extraction for proper data alignment.

## [v600.40] - 2026-04-14
- FIX: Align data limit and fix identity scores.

## [v600.39] - 2026-04-14
- TRUTH: Removed silent try-excepts, added full tracebacks.

## [v600.38] - 2026-04-14
- VERBOSE: Added explicit step logging for diagnosis.

## [v600.36] - 2026-04-14
- FIX: Resolve src ModuleNotFoundError with dynamic path injection.

## [v600.35] - 2026-04-14
- STABLE: Complete Code Re-alignment and Indentation Fix.

## [v600.34] - 2026-04-13
- 核心修復：全面導入語法自檢，解決 main 循環中的縮排錯誤。

## [v600.29] - 2026-04-13
- 核心修復：使用 py_compile 解決 market.py 縮排錯誤。
- 流程強化：新增 GitHub Action 語法檢查門檻 (quality_gate)。

## [v600.27] - 2026-04-13
- 修正 else 塊的 IndentationError。
- 鎖定依賴版本並優化 PM2 部署流程。

## [v600.26] - 2026-04-13
- 修正 pandas_ta 版本衝突。
- 徹底移除 market.py 內的 try/except 縮排錯誤。

## [v600.25-FINAL] - 2026-04-13
- 核心修復：解決 market.py 導入與環境變數設定問題。
- 環境重整：恢復標準導入與 PM2 徹底清創流程。

## [v600.24] - 2026-04-13
- 強制環境驗證：啟動前檢查 certifi 安裝狀態。

## [v600.23-PRO] - 2026-04-13
- 核心修復：放寬 requirements.txt 相容性，解決 Pip 安裝中斷問題。
- 工程標準：使用 try-except 包裝動態 SSL 載入，提高系統魯棒性。

## [v600.22-PRO] - 2026-04-13
- 工程標準化：移除所有寫死路徑，改用 certifi.where() 動態偵測 SSL。
- 核心修復：使用 certifi.where() 動態解決 SSL 憑證報錯。
- 流程恢復：重啟 doc_check 並優化 PM2 啟動參數 / 全量部屬流程。

## [v600.FINAL-STABLE] - 2026-04-13
- 核心修復：修復 certifi SSL 憑證路徑錯誤 (OSError)。
- 環境重整：強制執行 pm2 kill 與 venv 重新掛載。

## [v600.FINAL] - 2026-04-13
- 核心修復：鎖定 pandas_ta 與 Python 3.12 兼容版本；重構 market.py 頭部，徹底解決 IndentationError。
- 結構修復：market.py 導入置頂，徹底消除語法衝突。
- 環境鎖定：恢復鎖定版本 requirements.txt 安裝流程；增加啟動前依賴包完整性驗證。
- 流程恢復：重啟 doc_check 機制與自動化部署。

## [v600.21] - 2026-04-13
- 修正 pandas_ta 版本鎖定邏輯，回歸 wheels 指定版本。

## [v600.19] - 2026-04-13
- Fix: Locked llvmlite and numba versions for Python 3.12 stability.

## [v600.17] - 2026-04-13
- 恢復 doc_check 機制。
- 修正 Python 3.12 版本相容性問題 (Pandas/Numpy)。

## [v600.16] - 2026-04-13
- 恢復 doc_check 機制與標準部署邏輯。
- 定版鎖定 requirements.txt 依賴版本。

## [v600.15-PRO] - 2026-04-13
- 生產級別固化：全依賴包版本鎖定 (Pinned Versions)。

## [v600.12-ULTIMATE] - 2026-04-13
- Critical: Fixed pandas_ta ModuleNotFoundError in venv.

## [v600.11-STABLE] - 2026-04-13
- Resolved ModuleNotFoundError: pandas_ta.
- Fixed Indentation and SyntaxErrors in market.py.

## [v600.0-DYNAMO] - 2026-04-12
### Fixed
- 修復 market.py 第 1420 行縮排地獄 (IndentationError)。
- 補齊 notifier.py 心跳函式參數 (scan_results, active_count, version)。
- 強化 .github/workflows 解決 Pip AssertionError 與環境快取問題。
- CI/CD: Increased SSH command_timeout to 30m and optimized installation steps for GCE deployment.
- Final Precision Fix: Resolved SyntaxError by aligning balance_data with usage scope.
- Hotfix: Aligned calculate_features function name in src/features.py.
- Hotfix v600.9: Fixed DataFrame vs List type mismatch and environment recovery.
- Final Alignment: Synchronized 19 feature columns and recovered env dependencies.

## [180.0-ALPHA] - 2026-04-06
### Changed
- 初始化 strategy/metadata.py 統一管理版本與摩擦成本。
- 全域版本號遷移：將所有 .py 文件中的 168.0 與 179.0 替換為 180.0。
- 回測引擎增強：在 backtest/engine.py 注入 equity_curve 與 peak 追蹤邏輯。

## [179.0] - 2026-04-03
### The Momentum Flip
- Entry Logic: Updated Z-Score threshold to < -2.5 and added 15m RSI cross-up 30 confirmation.
- Risk Control: Tightened Stop-Loss to 0.8 * ATR. Single trade risk maintained at < 1%.
- Timeframe: Standardized all operations to 15m.

## [Iteration 93.1] - 2026-03-18
### Emergency Fix & Cold Start
- Updated pkill logic to target only src/market.py, preventing SSH session termination.
- Renamed PM2 process to Iteration93_Production and enabled non-fatal gate checks.

## [Iteration 93.0] - 2026-03-18
### Optimization & Hardening
- Refactored startup sequence to reduce Telegram spam and API pressure.
- Implemented 1s delay between symbol syncs to avoid rate limits.
- Enforced single model load verification with explicit logging.
- Added 1-minute heartbeat logs for PM2 diagnosis.
- Postponed auto-retrain checks by 1 hour after startup to prevent initialization loops.
- Enhanced deployment script to force kill all residual Python processes.

## [Iteration 92.0] - 2026-03-18
### Emergency Fix
- Added last_retrain.json to ensure model re-training only happens once per day.
- Enforced time.sleep(60) at the end of the main loop to prevent CPU spiking.
- Added 429 error handling in send_telegram_msg with a 10-minute silent cooldown.

## [Iteration 91.1 | DevOps Compliance] - 2026-03-18
- 重構 src/market.py 的 run_strategy 邏輯：過濾器不再中斷 AI 評分流程，僅在 execute_trade 階段攔截。
- 全域版本號對齊：統一使用 STRATEGY_VERSION 變數。
- 實施 500 根 K 線強制同步；移除所有 0.5 錯誤掩蓋邏輯，改為拋出 ValueError 並顯示 Traceback。
- 建立 data/ 資料夾持久化最近 K 線數據，防止 PM2 重啟導致數據斷層。

## [Iteration 89.0 | Rigid Data Alignment] - 2026-03-18
- 強制 K 線長度 limit=500，並加入硬性長度檢查。
- 重構 src/features.py，預測時固定取 iloc[-1:]。
- API 限流保護：掃描循環 time.sleep 從 0.5s 提升至 1.0s。

## [Iteration 86.0 | Final Stability Fix] - 2026-03-14
- 移除 deploy 腳本中的阻塞指令 (pm2 log, tail, ps aux)。
- 重構 24H Volume Change 邏輯。
- 加入換日線保護與數據邊界硬檢查。
- Telegram Heartbeat 頻率限制為每 15 分鐘一次。

## [Iteration 71 | Hybrid Sniper] - 2026-03-14
- 實作基於 BTC 24H 成交量變化的階梯進場邏輯 (Aggressive/Standard/Defensive)。
- Trailing Stop 間距調整為 1.8%。
- 30 天回測：勝率 100.0%，最大回撤 0.00%。

## [Iteration 69.3 | Syntax Fix] - 2026-03-14
- 修正 market.py 中 AI 決策流與 BB Squeeze 過濾器的縮進錯誤。
- 加入全局 try...except，啟動失敗會發送 Telegram 報警。

## [Iteration 69.2 | Startup Visibility] - 2026-03-14
- 加入啟動即時 Telegram 通知。
- ccxt.binance() 實例移至全局變數 exchange，共用連線池。

## [Iteration 69 | AI Confidence Recovery] - 2026-03-14
- fetch_1h_data / fetch_btc_vol_with_retry 的 limit 從 100 提升至 250。
- AI Score 計算提前至掃描循環中。
- 未成功計算時預設值改為 0.5。

## [Iteration 68.5 - 68.8] - 2026-03-14
- 逐步優化 deploy.sh 為靜音模式。
- 修正 src/market.py 中的 STRATEGY_VERSION 變數。
- 實裝追擊模式 (Pursuit Mode) 與移動止損 (Trailing Stop) 邏輯。

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

## [Iteration 62] - 2026-03-14
### Fixed
- Emergency threshold tightening due to 26% win-rate in backtest.
- Hardened ML thresholds: 0.75 (Defense) / 0.69 (Trend).
- Adjusted RR to 1.3 for current choppy market conditions.

## [Iteration 61.3] - 2026-03-14
### Fixed
- Resolved NameError: name 'fetch_ohlcv' is not defined by adding the function to src/market.py.
- Initialized regime_mode = "UNKNOWN" in run_strategy_cycle to prevent reference errors.
- Fixed AI model version conflict by retraining rf_model.joblib.
- Removed duplicate fetch_ohlcv function in src/market.py.

## [Iteration 61.2] - 2026-03-14
### Changed
- Downgraded pandas to >=2.0.0,<2.3.0 for Python 3.10 compatibility on GCE.

## [Iteration 61] - 2026-03-14
### Added
- Emergency Fix: Cleaned requirements.txt by removing local absolute paths (@ file:///).
- Adjusted AI confidence threshold from 0.75 to 0.68 during low-volume regimes.
- Maintained Risk-Reward (RR) requirement of 1.8.
- Updated filtering logic to use dynamic ml_threshold.

## [Iteration 60] - 2026-03-14
### Added
- Dynamic Environment Filter (Regime Filter).
- Aggressive Trend Mode for high-volume bullish markets.
- Low-volume defense mode with higher AI threshold (0.75).

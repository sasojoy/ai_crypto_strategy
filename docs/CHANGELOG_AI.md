

# 📜 AI 策略變更日誌 (CHANGELOG_AI)

本文件紀錄 AI 策略系統的每一次迭代與優化，確保策略演進路徑可追溯。

---

## [Iteration 68.9 | Final Sniper] - 2026-03-14
### 觸發原因
*   GitHub Actions 部署超時 (Timeout) 導致 CI/CD 流程中斷。
*   成交量計算邏輯在換日線附近出現異常波動。

### 具體修改
1.  **部署優化**：徹底移除 `.github/workflows/deploy.yml` 與 `deploy.sh` 中的阻塞指令 (`pm2 log`, `tail`, `ps aux`)。
2.  **量能修正**：重構 24H Volume Change 邏輯，改為「過去 24H 總量 vs. 前一個 24H 總量」。
3.  **異常檢測**：實裝「換日線保護」與「數據邊界硬檢查」，若跌幅 > 80% 自動歸零並發出警告。
4.  **頻率控制**：將 Telegram Heartbeat 頻率限制為每 15 分鐘一次，提升 Loop 效率。
5.  **版本同步**：全系統更新為 `Iteration 68.9 | Final Sniper`。

### 預期指標
*   GitHub Actions 部署成功率：100% (綠色勾勾)。
*   量能判定準確率：提升 30% 以上。
*   系統 Loop 延遲：降低 15%。

---

## [Iteration 68.5 - 68.8] - 2026-03-14
### 觸發原因
*   部署腳本掛起與版本號不一致。

### 具體修改
*   逐步優化 `deploy.sh` 為靜音模式。
*   修正 `src/market.py` 中的 `STRATEGY_VERSION` 變數。
*   實裝「追擊模式 (Pursuit Mode)」與「移動止損 (Trailing Stop)」邏輯。

---
*本文件由 OpenHands AI 維護，紀錄每一代 AI 的智慧結晶。*



# 🛠️ AI Crypto Strategy - DevOps Rules

為了確保系統穩定性與開發透明度，所有開發者（包括 AI 助手）必須嚴格遵守以下規則：

## 1. 📝 門禁規則 (Gatekeeping Rules)
- **CHANGELOG 優先**：每次 Push 之前，必須更新 `CHANGELOG.md`，記錄當前 Iteration 的變更。
- **版本同步**：`README.md` 的標題與狀態區塊必須與 `CHANGELOG.md` 的最新版本號 100% 一致。
- **代碼標籤**：`src/market.py` 與 `src/notifier.py` 中的 `STRATEGY_VERSION` 必須同步更新。

## 2. 🚀 部署規則 (Deployment Rules)
- **物理清場**：在 GCE 部署時，必須執行 `pm2 delete all` 以清除舊版本的幽靈進程。
- **暫存區清理**：部署前必須清空 `~/staging_area/*`，確保代碼為最新狀態。
- **門禁檢查**：只有當 GCE 實地回測達標 (Win Rate > 60%, PF > 1.8) 時，才允許同步至生產目錄。

## 3. 🤖 AI 診斷規則 (AI Diagnostic Rules)
- **嚴禁盲目預設**：AI 預測邏輯若發生錯誤，必須拋出異常 (Raise Error) 並記錄真實原因，嚴禁直接回傳 `0.5` 掩蓋問題。
- **特徵對齊**：`extract_features` 必須使用嚴格的 `reindex` 確保特徵順序與模型訓練一致。

## 4. 🧪 驗證規則 (Verification Rules)
- **日誌審計**：部署後必須檢查 `pm2 logs`，確認沒有 `CRITICAL ERROR` 且 AI 分數正常變動。
- **Telegram 驗證**：確認戰報中的版本號與 AI Confidence 顯示正確。

---
*最後更新：2026-03-21 (Iteration 87.1)*

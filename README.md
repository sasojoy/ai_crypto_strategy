# AI Crypto Strategy - 🚀 【Iteration 71.2 | Hybrid Sniper | 核心修復】

這是一個基於 AI 驅動的加密貨幣量化交易系統，具備 **「自主研究循環 (Autonomous Research Loop)」** 與 **「進化記憶 (Evolutionary Memory)」** 機制。系統利用 Google Gemini API 分析市場數據，自動優化策略參數，並透過 GitHub Actions 與 PM2 實現無縫部署至 Google Compute Engine (GCE)。

## 🌟 當前策略狀態 (Iteration 71.2 | Hybrid Sniper | 核心修復)

### 1. 核心邏輯：階梯進攻 (Laddered Sniper)
- **動態門檻參數**：
    - **A (極強趨勢)**: 0.72
    - **B (穩健趨勢)**: 0.68
    - **C (震盪修復)**: 0.65
- **核心修復 (71.2)**：
    - 解決 `scan_results` 為空導致的報表失明問題。
    - 即使在縮量禁止進場期間，仍保持基礎數據輸出至 Heartbeat。
    - 固化 `PYTHONPATH` 於 `ecosystem.config.js`，確保模組加載穩定。

### 2. 品質保證 (Quality Assurance)
- **Unit Test Base**: 已建立 `tests/` 目錄。
- **指標驗證**: `tests/test_indicators.py` 通過 RSI, EMA, ATR 計算驗證。
- **狀態**: Unit Tests Passed ✅

### 3. 數據邊界保護
- **換日線保護**：UTC 00:00 - 00:30 自動跳過量能檢查，避免數據缺失導致的異常判定。
- **異常值 Clip**：若檢測到量能跌幅 > 80%，系統強制歸零並發出警告，防止數據錯誤。

## 🛠️ 快速診斷手冊 (Quick Diagnosis)

| 症狀 | 可能原因 | 檢查動作 |
| :--- | :--- | :--- |
| **GitHub Actions Timeout** | 部署腳本包含阻塞指令 | 檢查 `deploy.sh` 是否有 `pm2 log` 或 `tail` |
| **不進場 (No Trades)** | AI 分數未達標 | 查看 `logs/trading.log` 中的 `Score: 0.xx` |
| **量能顯示 -97%** | 交易所 API 換日數據缺失 | 系統會自動觸發「軍規四」保護，無需人工干預 |
| **Telegram 無心跳** | 進程崩潰或 API 限制 | 執行 `pm2 status` 檢查，確認心跳頻率為 15min |

## 🚀 運維軍規
本專案嚴格遵守 [docs/DEVOPS_RULES.md](./docs/DEVOPS_RULES.md) 中的「六大軍規」，確保系統穩定性。

## 📂 目錄結構
```text
ai_crypto_strategy/
├── docs/
│   ├── DEVOPS_RULES.md     # 最高運維軍規
│   └── CHANGELOG_AI.md     # AI 策略變更日誌
├── config/
│   └── params.json         # 策略參數
├── models/
│   └── rf_model.joblib     # 訓練好的 AI 模型
├── src/
│   ├── market.py           # 核心交易執行器
│   ├── train_model.py      # 模型訓練腳本
│   └── notifier.py         # 通知與標籤管理
└── requirements.txt        # 淨化後的依賴清單
```

---
*Last Updated: 2026-03-14*

# AI Crypto Strategy - 🚀 【Iteration 133.9 | Profit Recovery Plan】

這是一個基於 AI 驅動的加密貨幣量化交易系統，具備 **「自主研究循環 (Autonomous Research Loop)」** 與 **「進化記憶 (Evolutionary Memory)」** 機制。系統利用 Google Gemini API 分析市場數據，自動優化策略參數，並透過 GitHub Actions 與 PM2 實現無縫部署至 Google Compute Engine (GCE)。

## 🌟 當前策略狀態 (Iteration 133.9 | Profit Recovery Plan)

### 1. 核心架構：利潤奪還計畫 (Profit Recovery Plan)
- **1H EMA200 趨勢過濾**：價格在 EMA200 上方僅做多，下方僅做空，確保與大趨勢同步。
- **動態 AI 門檻**：基礎門檻 0.82，高波動幣種 (FET/AVAX/SOL) 門檻 0.88。
- **獲利空間過濾**：進場點與止盈點之間必須具備 > 1.5% 的淨獲利空間。
- **保本移動止損 (Trailing Stop)**：獲利達到 2.0 * ATR 後，止損自動移至保本點。
- **ATR 參數優化**：止損 2.5 * ATR / 止盈 5.0 * ATR。

### 2. 品質保證 (Quality Assurance)
- **環境自癒 (Self-Healing)**：透過 `setup_env.sh` 自動修復目錄結構與依賴版本 (`scikit-learn==1.7.2`)。
- **路徑硬化 (Path Hardening)**：全系統採用絕對路徑，並具備 `❌ [JSON PATH ERROR]` 異常捕獲機制。
- **狀態**: Unit Tests & Backtest Gate Passed ✅

### 3. 數據與文件規範
- **文件同步 (Doc Sync)**：強制要求每次 Push 必須更新 `CHANGELOG.md` 與 `README.md` 版本號。
- **異常值 Clip**：若檢測到量能跌幅 > 80%，系統強制歸零並發出警告，防止數據錯誤。

## ⚙️ 安裝與部署 (Installation)

### 1. 環境變數配置 (GitHub Secrets)
請在 GitHub Repository 的 `Settings > Secrets and variables > Actions` 中配置以下變數：
- `SSH_HOST`: GCE 實例的外部 IP。
- `SSH_USER`: SSH 登入用戶名。
- `SSH_KEY`: SSH 私鑰內容。
- `GEMINI_API_KEY`: Google Gemini API 金鑰。
- `TELEGRAM_BOT_TOKEN`: Telegram Bot Token。
- `TELEGRAM_CHAT_ID`: Telegram 頻道或群組 ID。

### 2. 環境初始化
在 GCE 或本地環境執行：
```bash
git clone https://github.com/sasojoy/ai_crypto_strategy.git
cd ai_crypto_strategy
bash setup_env.sh
```

### 3. 啟動系統
```bash
pm2 start ecosystem.config.js
```

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
*Last Updated: 2026-03-30*

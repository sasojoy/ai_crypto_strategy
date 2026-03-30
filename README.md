# AI Crypto Strategy - 🚀 【Iteration 133.8 | Environment Isolation】

這是一個基於 AI 驅動的加密貨幣量化交易系統，具備 **「自主研究循環 (Autonomous Research Loop)」** 與 **「進化記憶 (Evolutionary Memory)」** 機制。系統利用 Google Gemini API 分析市場數據，自動優化策略參數，並透過 GitHub Actions 與 PM2 實現無縫部署至 Google Compute Engine (GCE)。

## 🌟 當前策略狀態 (Iteration 133.8 | Environment Isolation)

### 1. 核心架構：環境物理隔離 (Environment Isolation)
- **絕對路徑啟動 (Absolute Path Execution)**：
    - PM2 啟動腳本強制使用 `$(pwd)/venv/bin/python` 絕對路徑，徹底繞過 GCE 環境變數失效問題。
- **離線依賴注入 (Offline Dependency Injection)**：
    - 內置 `wheels/` 資料夾並包含 `pandas_ta-0.4.71b0-py3-none-any.whl`，實現 100% 離線安裝。
- **策略戰術止損 (Tactical Stop Loss)**：
    - **1H 週期統一**：全幣種回歸 1H 週期，大幅減少高摩擦磨損。
    - **ATR 盈虧比優化**：止損 2.2x ATR / 止盈 5.5x ATR。
    - **高勝率門檻**：AI Score >= 0.85 且價格必須在 1H EMA200 之上才准進場。

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

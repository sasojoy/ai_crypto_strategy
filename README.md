
# AI Crypto Strategy - Iteration 15 (Towards $5M)

這是一個基於 AI 驅動的加密貨幣量化交易系統，具備 **「自主研究循環 (Autonomous Research Loop)」** 與 **「進化記憶 (Evolutionary Memory)」** 機制。系統利用 Google Gemini API 分析市場數據，自動優化策略參數，並透過 GitHub Actions 與 PM2 實現無縫部署至 Google Compute Engine (GCE)。

## 🌟 核心邏輯 (Iteration 15)

### 1. 進場策略 (Entry Logic)
- **趨勢過濾**：ADX > 25 確保市場具備足夠動能。
- **均線確認**：價格必須位於 EMA 趨勢線之上。
- **動能確認**：MACD Histogram 必須為正且持續增長。

### 2. 倉位管理 (Position Sizing)
- **風險控制**：每筆交易嚴格限制為總資產的 **1% Risk**。
- **波動調整**：根據 ATR (Average True Range) 自動計算倉位大小，確保在不同波動率下風險一致。

### 3. 出場與獲利管理 (Exit & Profit Management)
- **分批減倉**：觸及 Bollinger Band Upper 時自動減倉 50%，並將止損移至保本價 (Breakeven)。
- **追蹤止損**：剩餘 50% 倉位啟動 **EMA 20 追蹤止損**，最大化趨勢利潤。

## 🚀 技術堆棧 (Tech Stack)
- **語言**：Python 3.10+
- **交易所對接**：CCXT (Binance)
- **進程管理**：PM2 (Process Manager 2)
- **AI 研究員**：Google Gemini API (Strategy Researcher)
- **基礎設施**：Google Compute Engine (GCE) & GitHub Actions

## 🛠️ 操作說明

### 1. 啟動交易機器人
```bash
pm2 start "python3 -u -m src.market" --name "Iteration15_Bot"
```

### 2. 監控與日誌
- **即時日誌**：`pm2 logs Iteration15_Bot`
- **儀表板**：透過 Telegram `/dashboard` 指令查看每日損益簡報。

### 3. 啟動自主研究循環
如果您想讓 AI 開始分析並優化策略，請執行：
```bash
python3 src/autonomous_research.py
```

## 🛡️ 風控宣告 (Risk Guardrails)
- **最大持倉**：系統同時最多僅持有 3 個交易對。
- **風險標準化**：所有進場均經過 1% Risk-normalized 處理，嚴禁過度槓桿。

---

## 📂 目錄結構

```text
ai_crypto_strategy/
├── .github/workflows/      # GitHub Actions 自動化部署配置
├── archive/                # 舊版策略代碼備份
├── config/
│   └── params.json         # 當前運行的策略參數 (由 AI 自動更新)
├── logs/                   # 系統運行與 AI 研究日誌
├── src/
│   ├── __init__.py
│   ├── market.py           # 核心交易執行器
│   ├── autonomous_research.py # AI 自主研究員模組
│   ├── evaluate.py         # 策略回測與評分引擎
│   ├── report.py           # 策略表現報告生成
│   └── summary.py          # 每日盈虧總結
├── STRATEGY_RELEASE_NOTES.md # 策略進化歷史帳本
├── requirements.txt        # 項目依賴
└── .env                    # 環境變數 (API Keys, Token)
```

---

## 🛠️ 快速上手

### 1. 環境設定
在 `.env` 檔案中配置以下金鑰：
```env
GEMINI_API_KEY=your_google_gemini_api_key
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 2. 啟動自主研究循環
如果您想讓 AI 開始分析並優化策略，請執行：
```bash
export PYTHONPATH=$PYTHONPATH:.
python3 src/autonomous_research.py
```

### 3. 手動啟動交易監控
```bash
python3 -u -m src.market
```

---

## 🛡️ 安全機制
- **API 異常處理**：當 Gemini API 達到速率限制或失效時，系統會自動回退至上一代穩定參數。
- **OOS (Out-of-Sample) 驗證**：AI 建議的參數必須在未見過的測試數據上表現正向，否則拒絕部署。
- **進程保護**：部署腳本具備自我保護邏輯，確保在更新過程中不會殺死部署進程本身。

---

## 📈 策略演進紀錄
所有的優化細節都會自動記錄在 [STRATEGY_RELEASE_NOTES.md](./STRATEGY_RELEASE_NOTES.md)。

---
*Last Updated: 2026-03-05*
\n\n## 🛡️ Security Notice\n**IMPORTANT**: When configuring your Binance API keys, ensure that only **'Enable Spot & Margin Trading'** is checked. **DO NOT** enable 'Enable Withdrawals'. This project only requires trading permissions.
## 📊 Backtest Results (Iteration 15)
- **Period**: Last 120 days (BTC/USDT)
- **Net Profit**: +$10.44
- **Win Rate**: 50.00%
- **Max Drawdown**: 0.11%
- **Sharpe Ratio**: 0.11
- **Total Trades**: 4

### Performance Visualization
![Backtest Result](backtest_result.png)

*Note: The strategy is currently optimized for high capital preservation (low drawdown) and is undergoing further parameter tuning.*

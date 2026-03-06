
# 🚀 AI Crypto Strategy: Evolutionary Memory & Autonomous Research

這是一個基於 AI 驅動的加密貨幣量化交易系統，具備 **「自主研究循環 (Autonomous Research Loop)」** 與 **「進化記憶 (Evolutionary Memory)」** 機制。系統利用 Google Gemini API 分析市場數據，自動優化策略參數，並透過 GitHub Actions 實現無縫部署至 Google Compute Engine (GCE)。

## 🌟 核心功能

### 1. 自主研究循環 (Autonomous Research Loop)
系統不再依賴人工調整參數，而是透過 `src/autonomous_research.py` 實現自動演進：
- **數據驅動分析**：自動抓取 BTC、ETH、SOL 等多幣種的歷史 K 線數據。
- **AI 決策優化**：整合 **Gemini 2.0 / 1.5 Flash** 模型，分析前一輪策略的盈虧、勝率及回撤，並給出下一代的優化建議。
- **自動回測驗證**：AI 提出的參數必須通過 Train/Test 數據集的雙重驗證。
- **物理護欄 (Safety Guardrails)**：強制執行參數限制（如 RSI 必須在 20-50 之間，止損必須在 1-5% 之間），防止 AI 產生極端風險。

### 2. 進化記憶機制 (Evolutionary Memory)
系統會記錄每一次的失敗與成功，確保策略持續進化：
- **策略帳本 (`STRATEGY_RELEASE_NOTES.md`)**：自動記錄每一代 (Iteration) 的邏輯變更、參數設定及回測表現。
- **版本化備份**：在每次參數更新前，自動將舊版 `market.py` 備份至 `archive/` 目錄。
- **參數中心化**：所有策略參數統一由 `config/params.json` 管理，實現代碼與配置分離。

### 3. 多幣種量化策略
核心交易邏輯位於 `src/market.py`，具備以下特性：
- **多指標融合**：結合 MACD 趨勢確認、RSI 超賣買入、以及 EMA (20/100/200) 長期趨勢過濾。
- **動態風險管理**：支持每筆交易固定風險百分比 (Risk Per Trade)。
- **異步監控**：支持同時監控多個交易對，並即時執行信號。

### 4. 自動化 CI/CD 部署
透過 `.github/workflows/deploy.yml` 實現高度自動化的運維：
- **安全部署 (Safe-Kill)**：優化後的腳本可精確重啟進程，避免傳統 `pkill` 導致的部署中斷 (143 錯誤)。
- **環境自動構建**：自動同步代碼、安裝依賴、並根據 GitHub Secrets 生成 `.env` 配置文件。
- **自動重啟機制**：整合 Crontab 監控，確保 `market.py` 在崩潰後能自動重啟。
- **定時任務**：每日 00:00 (台北時間) 自動執行 `src.summary` 生成每日盈虧報告。

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
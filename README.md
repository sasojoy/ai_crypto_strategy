# AI Crypto Strategy - Iteration 61.3 (GCE Optimized)

這是一個基於 AI 驅動的加密貨幣量化交易系統，具備 **「自主研究循環 (Autonomous Research Loop)」** 與 **「進化記憶 (Evolutionary Memory)」** 機制。系統利用 Google Gemini API 分析市場數據，自動優化策略參數，並透過 GitHub Actions 與 PM2 實現無縫部署至 Google Compute Engine (GCE)。

## 🌟 核心邏輯 (Iteration 61.3)

### 1. 動態環境過濾 (Regime Filter)
- **多頭追擊**：BTC 24H 量能增長 > 20% 且處於多頭排列時，啟動激進模式。
- **震盪防禦**：量能萎縮時，AI 門檻下修至 **0.68**，並嚴格執行 **1.8 RR** 過濾。
- **趨勢擴張**：標準模式下使用 0.65 AI 門檻。

### 2. AI 決策系統
- **隨機森林模型**：整合 RSI, ADX, ATR 與量能增長特徵進行即時預測。
- **動態門檻**：根據市場環境自動調整 AI 信心門檻 (0.65 - 0.75)。

### 3. 風險管理
- **RR 門檻**：防禦模式下強制要求 Risk-Reward Ratio >= 1.8。
- **倉位控制**：基於 ATR 的波動率調整倉位，單筆風險控制在 1.5%。

## 🚀 [System Health] 依賴版本
- **Python**: 3.10 (GCE Compatible)
- **Pandas**: >=2.0.0, <2.3.0
- **Scikit-Learn**: >=1.0.0 (Local Retrained)
- **CCXT**: >=4.0.0

## 🛠️ 操作說明

### 1. 啟動交易機器人
```bash
pm2 start "python3 -u -m src.market" --name "AI_Strategy_Bot"
```

### 2. 監控與日誌
- **即時日誌**：`pm2 logs AI_Strategy_Bot`
- **更版紀錄**：查看 [docs/CHANGELOG.md](./docs/CHANGELOG.md)

---

## 📂 目錄結構
```text
ai_crypto_strategy/
├── docs/
│   └── CHANGELOG.md        # 版本演進詳細紀錄
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
EOF > README.md
# AI Crypto Strategy - Iteration 61.3 (GCE Optimized)

這是一個基於 AI 驅動的加密貨幣量化交易系統，具備 **「自主研究循環 (Autonomous Research Loop)」** 與 **「進化記憶 (Evolutionary Memory)」** 機制。系統利用 Google Gemini API 分析市場數據，自動優化策略參數，並透過 GitHub Actions 與 PM2 實現無縫部署至 Google Compute Engine (GCE)。

## 🌟 核心邏輯 (Iteration 61.3)

### 1. 動態環境過濾 (Regime Filter)
- **多頭追擊**：BTC 24H 量能增長 > 20% 且處於多頭排列時，啟動激進模式。
- **震盪防禦**：量能萎縮時，AI 門檻下修至 **0.68**，並嚴格執行 **1.8 RR** 過濾。
- **趨勢擴張**：標準模式下使用 0.65 AI 門檻。

### 2. AI 決策系統
- **隨機森林模型**：整合 RSI, ADX, ATR 與量能增長特徵進行即時預測。
- **動態門檻**：根據市場環境自動調整 AI 信心門檻 (0.65 - 0.75)。

### 3. 風險管理
- **RR 門檻**：防禦模式下強制要求 Risk-Reward Ratio >= 1.8。
- **倉位控制**：基於 ATR 的波動率調整倉位，單筆風險控制在 1.5%。

## 🚀 [System Health] 依賴版本
- **Python**: 3.10 (GCE Compatible)
- **Pandas**: >=2.0.0, <2.3.0
- **Scikit-Learn**: >=1.0.0 (Local Retrained)
- **CCXT**: >=4.0.0

## 🛠️ 操作說明

### 1. 啟動交易機器人
```bash
pm2 start "python3 -u -m src.market" --name "AI_Strategy_Bot"
```

### 2. 監控與日誌
- **即時日誌**：`pm2 logs AI_Strategy_Bot`
- **更版紀錄**：查看 [docs/CHANGELOG.md](./docs/CHANGELOG.md)

---

## 📂 目錄結構
```text
ai_crypto_strategy/
├── docs/
│   └── CHANGELOG.md        # 版本演進詳細紀錄
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

# Session 交接報告（2026-09-28 ～ 2026-10-01）

> 給下一個 session：請先讀這份，再視需要查 `RESEARCH_FINDINGS.md`（完整研究紀錄）。
> 使用者偏好：**全程用繁體中文回覆**（含簡短進度說明）；小資金、希望以小搏大，但同意「先確認有優勢再加碼」。

---

## 1. 系統現況

### 實盤／模擬盤
| 項目 | 狀態 |
|---|---|
| 實盤 v7（Binance **testnet**，非真錢） | 正常運作。2026-09-21 起 8 筆、1 勝 7 敗，正好落在 v7 的 2026 Q3 低潮期（見第 3 節），不是系統問題 |
| WS 即時訊號偵測 daemon（`LiveTrading-WsEntryDetector`） | 正常運作，心跳正常，偶有全幣種同時斷線後自動重連（屬正常） |
| 模擬盤 v1 / v7 / v8 | 正常；截至 9/29：v1 -11.29%、v7 +5.43%、v8 +5.94% |
| 健康檢查 | `cd live_trading; ..\venv\Scripts\python.exe health_check.py`（**必須用 venv 的 python**，系統 python 沒有 ccxt） |

### 排程工作（Windows Task Scheduler）
- 全部用 `pythonw.exe`（不跳視窗）。
- **2026-09-29 修正**：`paper_trading/watchdog.py` 每 15 分鐘呼叫 PowerShell 會跳出一堆 cmd 視窗 → 已加 `CREATE_NO_WINDOW`（commit 8adb820）。
- **新增** `PaperTrading-ForwardReport`：每週一 09:00 跑 `scripts/forward_weekly_report.py`，把三個前瞻追蹤器的結果用中文傳到 Telegram，並附加到 `data/forward/weekly_report.log`。第一次自動執行：2026-10-05。

### ⚠️ 待使用者確認的事項
- **WS daemon 開機觸發器沒有作用**：9/27 重開機後，daemon 是看門狗 10 分鐘後救回來的。原因推定是任務為「只在使用者登入時執行」(InteractiveToken)，開機觸發在登入前發生就被跳過。建議改成「登入時」觸發（auto mode 擋住，需使用者自己執行）：
  ```powershell
  Set-ScheduledTask -TaskName LiveTrading-WsEntryDetector -Trigger (New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME")
  ```
  套用後同步修改 `live_trading/register_ws_task.ps1` 第 17 行。

---

## 2. 研究方法論（這兩天建立，之後沿用）

1. **事先登記**：假設、規則、通過標準先寫進 `RESEARCH_FINDINGS.md` 並 commit，之後才跑測試；不通過就結案，不換參數重測。
2. **樣本**：
   - **15 幣籃**：BTC ETH SOL NEAR AVAX ＋ BNB XRP DOGE ADA LINK LTC DOT BCH TRX UNI（設計用）
   - **35 新幣**：45 幣宇宙中不在 15 幣籃的幣（獨立驗證用）
   - 開發區 2020～2025 再切 2020-23（發現）／2024-25（確認）
3. **封存區（2026）**：**已被幾乎所有策略家族用過**（v7 系列、空方擁擠、BRK4H、XS7、新幣做空）。之後任何新想法，乾淨的驗證只剩**前瞻追蹤**（使用者已表示可以不在意這點繼續找，但要記得結果帶有偏差）。
4. **常見陷阱**：小樣本運氣（杯柄 16 筆 → 45 幣上被推翻）、事後挑最好的參數、絕對門檻遇到市場水準漂移（資金費率）。

---

## 3. 最重要的結論

### v7 在 2026 年的真實表現（實盤設定：5 幣、1 分鐘提前進場、ADX 風險）
| | n | 勝率 | 平均R | PF | 權益（ADX 風險，逐筆加總） |
|---|---|---|---|---|---|
| 2026Q1 | 193 | 44% | +0.17 | 1.43 | +59% |
| 2026Q2 | 198 | 41% | +0.05 | 1.10 | +17% |
| 2026Q3 | 185 | 29% | **-0.12** | 0.80 | **-41%** |
| 全年 | 576 | 38% | +0.04 | 1.08 | +36% |
- **v7 整體在 2026 仍是賺的，虧損集中在 Q3**。歷史上約 1/3 的季度會虧，這次是最深的之一。
- 先前一度說「v7 從 4 月起就在虧」，那是**陽春代理版**（1H 收盤進場、無 ADX、50 幣）的結論，已更正（commit b0cd86b）。
- **1 分鐘提前進場在每一季都明顯優於收盤進場** → 進場速度非常重要。

### 其他關鍵發現
- **v7 優勢不能推廣到其他幣**：45 個新幣上 +0.015R（原 5 幣 +0.141R）；用過去表現挑幣也幾乎沒用。
- **v7 的利潤幾乎全來自「進場後立刻噴、不回頭」的單**：沒回踩 0.5 ATR 的訊號勝率 70%（+1.03R），有回踩的 29%（-0.20R）→ 回踩掛單、分批停利、提早出場都會砍到贏單，全部無效。
- **2026 年市場對方向性與動能類策略都不友善**：波動率降到三年低點、橫截面「動能」轉為「反轉」。
- **以小搏大的槓桿模擬**：以 2020-25 歷史，每筆押 1～2% 合理（兩年中位數 2.6～4.9 倍）；押 5% 以上爆倉機率急升；以 2026 Q3 那種行情，押多少都虧。

---

## 4. 本期所有研究結果一覽

| 研究 | 結果 | 腳本 |
|---|---|---|
| 外部樞軸點共振策略 | ❌ 停損太窄，成本吃掉 0.63R/筆 | `dev_pivot_confluence.py` |
| 找「必定失敗」的進場模板 | ❌ 101 格，0 格兩期成立 | `dev_momentum_loss_templates.py` |
| 進場前後量能 | ⚠️ 進場後量能能分辨輸贏但不能當出場規則；進場前量能堆積有小效果但與 ADX 重疊 | `dev_momentum_volume_profile.py`、`dev_momentum_volume_scaled_risk.py` |
| 斐波那契回檔位 | ❌ 94,287 次碰線，跟普通比例無差別 | `dev_fib_reaction_grid.py` |
| 杯柄型態 | ❌ 原 5 幣 16 筆漂亮，45 新幣 112 筆被推翻 | `dev_cup_handle.py` |
| v7 套到 45 新幣 | ❌ 優勢不推廣 | `dev_momentum_universe.py` |
| 依幣「性格」配策略 | ❌ 性格指標本身不穩定 | `dev_coin_personality.py` |
| 滾動式挑幣 | ❌ 幾乎無增益 | `dev_coin_selection_walkforward.py` |
| 回踩掛單進場 | ❌ 極端逆選擇 | `dev_momentum_pullback_entry.py` |
| 分批停利 | ❌ 勝率↑回撤↓但少賺 | `dev_momentum_partial_tp.py` |
| 空方擁擠（資金費率）風險重分配 | ✅ 35 新幣事先登記通過（p=0.0003）→ ❌ 2026 封存區失敗（資金費率整體水準下移，門檻失效） | `prereg_short_crowding.py`、`dev_short_crowding_risk.py`、`holdout_short_crowding.py` |
| 低波動／逆 BTC 月趨勢 減碼 | ❌ 兩個假設在 2020-25 都不成立 | `prereg_vol_trend.py` |
| 新策略：波動收斂突破 | ❌ 收斂無附加價值 | `prereg_squeeze_breakout.py` |
| 新策略：BRK4H（4H 突破＋區間中點停損＋3R） | 開發區四格皆正 → ❌ 2026 封存區失敗；已進前瞻追蹤 | `brk4h.py` |
| 新策略：日線趨勢跟隨 | ❌ 靠 2020-21 大多頭，隨機進場同出場也 +0.50R | `prereg_daily_trend.py` |
| 新策略：橫截面動能（28 天／7 天） | ❌ 2024-25 很強，2026 崩跌（7 天版 -60%/年） | `prereg_xs_momentum.py`、`holdout_xs7.py` |
| 新策略：做空新上市永續 | 開發區「新幣跑輸大盤 11～19%」很穩 → ❌ 2025H2-26 上市的新幣效應消失 | `fetch_listings.py`、`prereg_listing_short.py` |
| **策略切換器** | ✅ **探索性：2021～2026 每一年都不虧**（見下） | `dev_regime_switch.py` |

### 策略切換器（目前唯一的曙光）
- 6 個子策略：V7（陽春版）、BRK4H、XSM7、XSR7、XSM28、XSR28（橫截面動能／反轉），每週損益依過去 26 週波動正規化到每週約 1%。
- 規則 POSEW：持有「過去 L 週平均 > 0」的子策略、等權；全部 ≤ 0 就空手。
- L = 26～39 週形成穩定平台；**L=30、L=39 在 2021～2026 每年 Sharpe 都 > 0**。槓桿到年化波動 20%：L=30 年化 +12.8%、最大回撤 23%；L=39 年化 +15.7%、回撤 20%。
- 限制：用全部歷史找出、無乾淨驗證資料；切換有約半年延遲（2026 Q1、Q2 也是虧的，Q3 才賺回）；執行複雜（6 策略 × 50 幣）。
- 登記當下（2026-10-01）兩個版本都持有 XSR7、XSR28（橫截面反轉）。

---

## 5. 前瞻追蹤（規則凍結，**不可修改**）

| 追蹤器 | 腳本 | 最終判定條件 | 預計時間 |
|---|---|---|---|
| v7 訊號（50 幣，收盤進場代理） | `scripts/forward_tracker.py`（門檻凍結在 `forward_frozen_cutoffs.json`） | ≥1,500 筆已結束、平均 R>0 且單尾 p<0.05 | 約半年 |
| BRK4H（50 幣） | `scripts/brk4h.py forward` | ≥5,000 筆、同上 | 約一年 |
| 策略切換器（L=30、L=39） | `scripts/forward_switcher.py`（歷史凍結在 `regime_switch_raw_frozen.csv`） | ≥52 個「確定週」後才看 Sharpe>0 | 約一年 |

- 都只統計 2026-10-01（切換器為 2026-10-04 週）之後的訊號；期中只回報、不判定。
- 每週一 09:00 自動傳 Telegram；手動：`.\venv\Scripts\python.exe scripts\forward_weekly_report.py`。

---

## 6. 資料位置
- `data/backtest_cache/`：5 幣 1H/1m 開發區快取、`universe_1h/`、`universe_4h/`（45 幣）、`funding_basket/`、`funding_universe/`、`holdout_2026/`（50 幣 2025-10 起 1H＋資金費率）、`listings/dev|holdout/`
- `data/forward/`：前瞻追蹤用的最新 1H 資料與輸出 CSV

---

## 7. 建議的下一步
1. **不要把任何策略轉成真錢**，直到前瞻追蹤給出正面結果；實盤繼續在 testnet 跑。
2. 每週看 Telegram 週報；特別留意 v7 能否從 Q3 低潮恢復、切換器的實際持倉與表現。
3. 若繼續找策略：沿用「事先登記 → 15 幣設計 → 35 幣驗證 → 前瞻追蹤」流程；切換器這個方向（讓近期表現決定用哪個策略）是目前最有希望的研究主軸，可考慮把**實盤設定的 v7**（1 分鐘進場＋ADX）加入成為新的子策略版本（需另外登記，現有凍結的切換器不改）。
4. 處理 WS daemon 觸發器（第 1 節）。

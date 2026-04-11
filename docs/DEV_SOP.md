# 量化開發輸出規範 (SOP v1.0)

## 第一階段：代碼透明化 (Code Transparency)
在執行任何回測前，必須先使用 grep 打印出核心邏輯（TP/SL/Z-Score/Timeframe）。

## 第二階段：原始執行 (Raw Execution)
必須完整顯示 Terminal 的執行日誌，禁止隱藏 Warning 或 Error。

## 第三階段：標準化審計表 (Standard Audit Table)
所有任務結尾必須包含以下表格中的所有數據：

[FINAL_AUDIT_REPORT]
| 指標 | 數值 |
| :--- | :--- |
| 策略版本 | {version} |
| 總交易數 (N) | {n} |
| 勝率 (WinRate) | {wr}% |
| 期望值 (Expectancy) | {exp}% |
| 最大回撤 (MaxDD) | {dd}% |
| 盈虧比 (PF) | {pf} |
| 結束類型 | {sl/tp/be 分佈} |
[END_OF_REPORT]

## 禁令
1. 禁止在未提供數據前說「已驗證」。
2. 禁止提供「摘要式」的虛假成功報告。
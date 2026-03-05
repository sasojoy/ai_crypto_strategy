


# Strategy Release Notes

## Iteration 11 - Triple Threat Optimized
- **Date**: 2026-03-05
- **Logic**: The previous iteration yielded almost zero trades, indicating the RSI 30 threshold coupled with a slow trend filter (50/200) is too restrictive. Raising RSI to 45 allows entries on shallower pullbacks during medium-term trends (EMA 20/100).
- **Parameters**: RSI=45, EMA_F=20, EMA_S=100, SL=2.5, MACD=True
- **Performance**:
### BTC/USDT
| Period | Score | Net Profit | Win Rate | Max Drawdown | Trades |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Train (30d)** | -894.65 | $-234.77 | 30.00% | 7.87% | 10 |
| **Test (30d)** | -1291.99 | $-1512.50 | 14.29% | 16.72% | 14 |

### ETH/USDT
| Period | Score | Net Profit | Win Rate | Max Drawdown | Trades |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Train (30d)** | 911.70 | $326.34 | 36.84% | 13.19% | 19 |
| **Test (30d)** | -970.67 | $-1152.06 | 11.11% | 13.19% | 9 |

### SOL/USDT
| Period | Score | Net Profit | Win Rate | Max Drawdown | Trades |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Train (30d)** | 652.44 | $143.82 | 35.71% | 7.87% | 14 |
| **Test (30d)** | -0.00 | $-1992.69 | 0.00% | 18.29% | 11 |


This file tracks the evolution of the AI Crypto Strategy.

## Iteration 9 - MACD Enhanced (Baseline)
- **Date**: 2026-03-04
- **Logic**: Added MACD Histogram confirmation (Hist > 0 and increasing).
- **Status**: Deployed as baseline for Phase 2.



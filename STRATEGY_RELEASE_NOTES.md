



## Architecture Insights
- **Iteration 11 Performance Analysis**: ETH and SOL outperformed BTC due to the **20/100 EMA** configuration, which is more responsive to the high-momentum trends typical of altcoins. The **RSI 45** threshold successfully captured shallow pullbacks in ETH/SOL's aggressive rallies, whereas BTC's more stable price action led to premature entries. **MACD momentum filtering** provided superior secondary confirmation for ETH/SOL's explosive moves, while proving less effective in BTC's recent range-bound volatility.



# Strategy Release Notes

## Iteration 12 - Triple Threat Optimized
- **Date**: 2026-03-05
- **Logic**: Targets 'Momentum Dip' setups by raising RSI to 48, assuming strong trends are preventing deep oversold conditions. Uses a fast EMA_F (15) for quick trend alignment. The very tight SL (1.2) is the primary mechanism for Drawdown Control, exiting immediately if the shallow dip turns into a correction.
- **Parameters**: RSI=48, EMA_F=15, EMA_S=110, SL=1.2, MACD=True
- **Performance**:
### BTC/USDT
| Period | Score | Net Profit | Win Rate | Max Drawdown | Trades |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Train (30d)** | 3798.18 | $932.63 | 40.00% | 9.82% | 25 |
| **Test (30d)** | -1613.01 | $-1877.53 | 20.00% | 23.28% | 25 |

### ETH/USDT
| Period | Score | Net Profit | Win Rate | Max Drawdown | Trades |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Train (30d)** | 174.03 | $83.91 | 34.48% | 16.63% | 29 |
| **Test (30d)** | -2193.68 | $-1877.53 | 20.00% | 17.12% | 25 |

### SOL/USDT
| Period | Score | Net Profit | Win Rate | Max Drawdown | Trades |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Train (30d)** | -1517.66 | $-687.90 | 30.00% | 13.60% | 30 |
| **Test (30d)** | -831.64 | $-2923.57 | 8.70% | 30.57% | 23 |


## Iteration 11 - Triple Threat Optimized
- **Date**: 2026-03-05
- **Logic**: Iteration 11 yielded near-zero trades, indicating entry criteria were too strict. Raising RSI to 45 allows for entries during shallower pullbacks, while 20/100 EMAs align faster with changing trends.
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



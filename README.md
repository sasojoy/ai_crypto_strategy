

# AI Crypto Strategy 2.0 - Fortress Hunter

## Iteration 154.0: Fortress Hunter (Predator Real-Edge)

This iteration focuses on extreme stability and professional-grade risk management, transitioning the project to the 2.0 architecture.

### Core Goals & Features

- **Conservative Kelly Risk Management**: Transitioned from aggressive 30% sizing to a normalized risk model.
    - **Max Risk**: 8% (for ML confidence > 0.92)
    - **Standard Risk**: 2%
- **1.5 * ATR Break-even Mechanism**: Implementation of an automatic Stop-Loss (SL) move to entry price once profit reaches 1.5 * ATR, ensuring principal protection.
- **Multi-Timeframe Quality Filter**: High-precision entry logic combining:
    - **1H Trend**: EMA200 guard.
    - **15m RSI**: Oversold/Overbought filtering.
- **Realistic Friction Model**: High-fidelity backtesting with enforced 0.09% total friction (0.04% Fee + 0.05% Slippage).
- **Stability & Performance**:
    - **MDD Reduction**: Successfully reduced Max Drawdown from 30%+ to 3.42% in a 180-day multi-currency audit.
    - **Expanded Asset Audit**: Verified performance across BTC, ETH, SOL, FET, and AVAX.

### Project Structure 2.0

The project has been restructured into a modular architecture:
- `config/`: Configuration files (YAML/JSON).
- `data/`: Market data and local caches.
- `models/`: Trained ML models and scalers.
- `strategy/`: Core strategy logic and signal generation.
- `backtest/`: Backtesting engine and results.
- `realtime/`: Live trading and execution modules.
- `risk/`: Risk management and position sizing logic.
- `notify/`: Notification services (Telegram, etc.).
- `optimize/`: Parameter optimization and walk-forward analysis.
- `logs/`: System and trading logs.

---
*Iteration 154.0 - "Fortress Hunter" - 2026-03-27*



# v600.0-STABLE-STABLE-RECOVERY-RECOVERY-DYNAMO "Adaptive Matrix"

## Goals
- Implement GMM-based Adaptive Market Regime Switching.
- Production-ready infrastructure (venv, Systemd, Telegram alerts).
- Extreme friction resilience (0.14% total cost).
- CI/CD Governance with automated GCE validation.

## Key Parameters
- Symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT"]
- Market Regimes: 0 (Trend Hunter), 1 (Mean Reversion), 2 (Stay Out)
- Base Risk: 0.02
- ML Threshold: 0.85
- Friction:
    - Fee: 0.0004
    - Slippage: 0.0010 (Total 0.14%)
- Timeframes: ["1h", "15m"]

# 2.0 Architecture (archived 2026-08-21)

This is the modular "Project Restructuring 2.0" rewrite (`strategy/main.py`,
`strategy/logic.py`, `backtest/engine.py`, `realtime/binance_executor.py`,
`data/fetcher.py`, `config/config.yaml`) that read its parameters from
`config.yaml` via `risk/risk_manager.py`.

It was last touched on 2026-04-11, the same day `src/market.py` took over as
the actively developed, PM2-deployed entry point (see `ecosystem.config.js`).
Everything after that (the `v600.x` series in `CHANGELOG.md`) evolved
`src/market.py` directly, with its parameters hardcoded rather than read from
`config.yaml`. Nothing in `src/` ever imported from this tree.

Moved here instead of deleted so the history and design are still available
for reference. Note: `scripts/trace_optimizer.py`, `optimizer_v2/v3/v4_robust.py`,
`oos_stealth_validator.py`, `oos_validator.py`, `friction_test.py`,
`models/trainer.py`, and `execution/live_dry_run.py` still import from the
original paths and will now fail — they were already tied to this
abandoned architecture and hardcoded to a GCE path
(`/workspace/ai_crypto_strategy/...`), so they were not runnable as-is either
way.

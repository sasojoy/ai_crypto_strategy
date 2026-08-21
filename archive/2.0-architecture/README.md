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
for reference. `scripts/optimizer.py`, `optimizer_v2/v3/v4_robust.py`,
`trace_optimizer.py`, `oos_stealth_validator.py`, `oos_validator.py`,
`friction_test.py`, and `final_audit_runner.py` all imported from this tree
and were archived alongside it into `scripts/` here — they were already
hardcoded to a GCE path (`/workspace/ai_crypto_strategy/...`), so they were
not runnable as-is on this machine either way.

`models/trainer.py` and `execution/live_dry_run.py` also import from this
tree but were left in place — they weren't purely 2.0-architecture code, so
removing them needs a closer look first.

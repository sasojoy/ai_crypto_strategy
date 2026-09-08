# Paper-Trading Monitors

Two standalone, read-only monitors for the two research-validated candidates (see `RESEARCH_FINDINGS.md`, `DEPLOYMENT_RISK_ASSESSMENT.md`). **Neither ever places a real order** — they only fetch public market data and simulate trades on paper, logging results and sending Telegram notifications so you can decide whether to replicate a signal manually with real capital.

- `momentum_monitor.py` — RSI(14) oversold/overbought momentum-continuation + volume-tercile confirmation (locked spec, `dev_momentum_continuation.py`).
- `funding_monitor.py` — delta-neutral funding-rate carry, conditional variant (locked spec, `dev_funding_carry.py`), BTC + ETH only per the deployment risk assessment's recommendation.

## Setup

1. **Telegram (optional but recommended):** create a `.env` file at the project root (copy `config/.env.example`) with `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Without it, both monitors still run and log to the console / CSV files, they just won't message you.
2. **Calibration (momentum monitor only):** `momentum_monitor.py`/`momentum_monitor_v2.py` need `thresholds.json` -- a PER-SYMBOL volume-ratio top-tercile cutoff for each of the 5 symbols (2026-09-08 fix: a single pooled cutoff was found to screen BTC far more leniently than the altcoins, since BTC's volume-ratio distribution runs structurally higher -- see `RESEARCH_FINDINGS.md`), plus the 5x5 daily-return correlation matrix used by the risk-budget position cap below. It's already generated from data through today; re-run `calibrate_momentum_threshold.py` every few months to keep both current as the market structure drifts.
3. First run of each monitor establishes a baseline (no backlog of historical signals is treated as "new" — see the scripts' docstrings) and won't open any paper positions or fire toggle notifications; from the second run onward it reacts to genuinely new signals.

## Scheduling (Windows Task Scheduler)

`momentum_monitor.py` should run roughly hourly (matches the 1H bar granularity). `funding_monitor.py` should run roughly every 8 hours (matches the funding settlement cadence), though running it hourly too is harmless — it just finds nothing new most of the time.

Example (PowerShell, run once to register the tasks):

```powershell
$python = "C:\Users\User\Documents\ai_crypto_strategy\venv\Scripts\python.exe"
$repo = "C:\Users\User\Documents\ai_crypto_strategy\paper_trading"

$actionMomentum = New-ScheduledTaskAction -Execute $python -Argument "momentum_monitor.py" -WorkingDirectory $repo
$triggerMomentum = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "PaperTrading-MomentumMonitor" -Action $actionMomentum -Trigger $triggerMomentum

$actionFunding = New-ScheduledTaskAction -Execute $python -Argument "funding_monitor.py" -WorkingDirectory $repo
$triggerFunding = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 8) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "PaperTrading-FundingMonitor" -Action $actionFunding -Trigger $triggerFunding
```

Not registered automatically — run this yourself (or ask to have it done) once you're ready for these to run unattended on a schedule.

## State files (`state/`)

- `momentum_state.json` / `funding_state.json` — current open paper positions / on-off status and cumulative paper P&L. Safe to delete to reset (loses paper track record).
- `momentum_trades_log.csv` / `funding_events_log.csv` — append-only history of every simulated close / regime toggle.

## Position sizing / risk cap

Momentum monitor sizing is fixed-notional (2% of a fixed reference capital per trade) per the correction in `scripts/dev_momentum_fixed_notional.py` — not the original backtest's compounding number. New signals are gated by a correlation-aware portfolio-risk budget (`RISK_BUDGET = 3.0`, see `scripts/dev_momentum_portfolio_risk.py`) instead of a flat headcount cap: same-direction positions in correlated symbols (the 5 symbols' daily returns run 0.55-0.80 correlated) count for more than one slot each, opposite-direction ("hedging") positions count for less. A flat `MAX_CONCURRENT(_GROUPS) = 5` is still kept as an absolute backstop underneath the risk budget.

## Known limitations (carried over from `DEPLOYMENT_RISK_ASSESSMENT.md`)

- Neither monitor simulates margin/liquidation, execution slippage, or exchange/counterparty risk — see the risk assessment for what real deployment still needs to account for.
- Funding monitor's paper P&L doesn't include the resimulated fixed-notional sizing work — it directly sums the raw funding-rate percentages exactly as `dev_funding_carry.py`'s conditional() variant does.
- BTC exclusion was considered (dev-window backtests showed it as a drag) but shelved: it contradicted the actual holdout run, where BTC was the single best-performing symbol. That contradiction turned out to be explained by the per-symbol tercile fix above, not a reason to exclude BTC — see `RESEARCH_FINDINGS.md`'s 2026-09-08 audit section for the full account.

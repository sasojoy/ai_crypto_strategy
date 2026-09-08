# Paper-Trading Monitors

Two standalone, read-only monitors for the two research-validated candidates (see `RESEARCH_FINDINGS.md`, `DEPLOYMENT_RISK_ASSESSMENT.md`). **Neither ever places a real order** — they only fetch public market data and simulate trades on paper, logging results and sending Telegram notifications so you can decide whether to replicate a signal manually with real capital.

- `momentum_monitor.py` — RSI(14) oversold/overbought momentum-continuation + volume-tercile confirmation (locked spec, `dev_momentum_continuation.py`).
- `momentum_monitor_v2.py` — same locked entry/exit rules, plus two EXPERIMENTAL, never-holdout-validated additions: 1-minute SL/TP polling and a trend-following pyramid add. Its own separate state files, doesn't affect v1's track record.
- `funding_monitor.py` — delta-neutral funding-rate carry, conditional variant (locked spec, `dev_funding_carry.py`), BTC + ETH only per the deployment risk assessment's recommendation.

## Bootstrapping this on a NEW machine (e.g. to run 24/7 somewhere other than where this was developed)

This code lives on the `paper-trading-monitors` git branch, not `main`. On the new machine:

```powershell
git clone https://github.com/sasojoy/ai_crypto_strategy.git
cd ai_crypto_strategy
git checkout paper-trading-monitors

python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

Then, before running anything:
1. **Create a `.env` file at the repo root** (same folder as `requirements.txt`, NOT inside `paper_trading/`) with `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. This file is intentionally not in git (it's a credential); copy it over from wherever it already exists (the machine this was developed on), don't retype it from memory, and never commit it. Without it, both monitors still run and log to the console / CSV files, they just won't message you.
2. Run each monitor once by hand from inside `paper_trading/` (`..\venv\Scripts\python.exe momentum_monitor.py`, then `momentum_monitor_v2.py`, then `funding_monitor.py`) to confirm they complete with no errors and print "Run complete". The very first run on a fresh machine has no prior state, so each will print a "first run, baseline set" message and won't open any paper positions yet or send a Telegram message — that's expected, not a bug; state accumulates fresh on this machine from here on (it's not shared with any other machine already running these).
3. Only after that, register the scheduled tasks -- see "Scheduling" below.

## Calibration

`momentum_monitor.py`/`momentum_monitor_v2.py` need `thresholds.json` (already committed, generated from data through 2026-09-08) -- a PER-SYMBOL volume-ratio top-tercile cutoff for each of the 5 symbols (a single pooled cutoff was found to screen BTC far more leniently than the altcoins, since BTC's volume-ratio distribution runs structurally higher -- see `RESEARCH_FINDINGS.md`'s 2026-09-08 audit section), plus the 5x5 daily-return correlation matrix used by the risk-budget position cap below. Re-run `calibrate_momentum_threshold.py` every few months to keep both current as the market structure drifts (needs `data/backtest_cache/*_1h_full.csv`, which isn't in git -- regenerate it with `scripts/fetch_holdout_data.py` first if this machine doesn't already have it cached).

## Scheduling (Windows Task Scheduler)

`momentum_monitor.py` should run roughly hourly (matches the 1H bar granularity). `momentum_monitor_v2.py` should run every 1-5 minutes (its whole point is faster SL/TP reaction). `funding_monitor.py` should run roughly every 8 hours (matches the funding settlement cadence), though running it hourly too is harmless — it just finds nothing new most of the time.

Example (PowerShell, run once per machine to register the tasks -- adjust `$repo` to wherever you actually cloned this):

```powershell
$repo = "C:\Users\User\Documents\ai_crypto_strategy\paper_trading"
$python = (Resolve-Path "$repo\..\venv\Scripts\python.exe").Path

$a1 = New-ScheduledTaskAction -Execute $python -Argument "momentum_monitor.py" -WorkingDirectory $repo
$t1 = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "PaperTrading-MomentumV1" -Action $a1 -Trigger $t1

$a2 = New-ScheduledTaskAction -Execute $python -Argument "momentum_monitor_v2.py" -WorkingDirectory $repo
$t2 = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "PaperTrading-MomentumV2" -Action $a2 -Trigger $t2

$a3 = New-ScheduledTaskAction -Execute $python -Argument "funding_monitor.py" -WorkingDirectory $repo
$t3 = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "PaperTrading-Funding" -Action $a3 -Trigger $t3
```

Not registered automatically — run this (or have it run) once the manual test runs above all completed cleanly.

## State files (`state/`, gitignored)

- `momentum_state.json` / `momentum_v2_state.json` / `funding_state.json` — current open paper positions / on-off status and cumulative paper P&L, one file per monitor (v1 and v2 track completely independent records). Safe to delete to reset (loses that monitor's paper track record).
- `momentum_trades_log.csv` / `momentum_v2_trades_log.csv` / `funding_events_log.csv` — append-only history of every simulated close / regime toggle.
- Not in git, so a freshly-cloned machine starts with empty state (see "Bootstrapping" above) -- it does not inherit any other machine's paper-trading history.

## Position sizing / risk cap

Momentum monitor sizing is fixed-notional (2% of a fixed reference capital per trade) per the correction in `scripts/dev_momentum_fixed_notional.py` — not the original backtest's compounding number. New signals are gated by a correlation-aware portfolio-risk budget (`RISK_BUDGET = 3.0`, see `scripts/dev_momentum_portfolio_risk.py`) instead of a flat headcount cap: same-direction positions in correlated symbols (the 5 symbols' daily returns run 0.55-0.80 correlated) count for more than one slot each, opposite-direction ("hedging") positions count for less. A flat `MAX_CONCURRENT(_GROUPS) = 5` is still kept as an absolute backstop underneath the risk budget.

## Known limitations (carried over from `DEPLOYMENT_RISK_ASSESSMENT.md`)

- Neither monitor simulates margin/liquidation, execution slippage, or exchange/counterparty risk — see the risk assessment for what real deployment still needs to account for.
- Funding monitor's paper P&L doesn't include the resimulated fixed-notional sizing work — it directly sums the raw funding-rate percentages exactly as `dev_funding_carry.py`'s conditional() variant does.
- BTC exclusion was considered (dev-window backtests showed it as a drag) but shelved: it contradicted the actual holdout run, where BTC was the single best-performing symbol. That contradiction turned out to be explained by the per-symbol tercile fix above, not a reason to exclude BTC — see `RESEARCH_FINDINGS.md`'s 2026-09-08 audit section for the full account.

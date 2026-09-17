# Paper-Trading Monitors

Standalone, read-only monitors built on the research-validated candidates (see `RESEARCH_FINDINGS.md`, `DEPLOYMENT_RISK_ASSESSMENT.md`). **None of them ever places a real order** — they only fetch public market data and simulate trades on paper (or, for `threshold_report.py`, just report status), logging results and sending Telegram notifications so you can decide whether to replicate a signal manually with real capital.

- `momentum_monitor.py` — RSI(14) oversold/overbought momentum-continuation + volume-tercile confirmation (locked spec, `dev_momentum_continuation.py`).
- `momentum_monitor_v2.py` — same locked entry/exit rules, plus two EXPERIMENTAL, never-holdout-validated additions: 1-minute SL/TP polling and a trend-following pyramid add. Its own separate state files, doesn't affect v1's track record.
- `momentum_monitor_v3.py` — same locked entry/exit rules, replaces "wait for the hour to close" with a real-time ANTICIPATORY ENTRY: solves for the RSI-cross threshold price from the last closed bar's Wilder state, polls 1-minute bars, and enters the instant price touches it AND a real-time volume projection clears a separately-calibrated causal cutoff (`thresholds.json`'s `..._causal_by_symbol`). Once the entry hour actually closes, re-checks the REAL volume ratio against the existing (non-causal) cutoff and immediately closes the position if it doesn't hold up (`VOL_UNCONFIRMED`). Dev-window backtested (six rounds of bug-hunting — two look-ahead bugs and a volume-cutoff calibration mismatch found and fixed along the way): n=6,139, PF 1.51, +387.23%/yr vs v1's +79.79%/yr. **HOLDOUT-VALIDATED (2026-09-17)**: on the 2026 holdout window, scored n=741 (3.5x a same-window v1-style baseline's n=213) with win_rate 47.5%/PF 1.39 vs the baseline's 37.6%/1.05, all 5 symbols net positive — see `RESEARCH_FINDINGS.md`. A separate real-time early-volume-rejection refinement was tested and found dev-window neutral (not implemented — see v3's own docstring). No pyramid add (kept isolated from v2's experiment so results can be attributed to one mechanism at a time). Its own state files, doesn't affect v1/v2's track records.
- `funding_monitor.py` — delta-neutral funding-rate carry, conditional variant (locked spec, `dev_funding_carry.py`), BTC + ETH only per the deployment risk assessment's recommendation.
- `momentum_monitor_v4.py` — EXPERIMENTAL, added 2026-09-11. Same locked entry/exit rules and same "wait for the bar to close" timing as v1 (no pyramid, no anticipatory entry) — the ONLY change is wider SL/TP: 2.5x/5.0xATR instead of v1's locked 2.0x/4.0xATR, same 2:1 reward:risk ratio. Motivated by the user asking about the locked spec's low (~40%) win rate: dev-window testing (`RESEARCH_FINDINGS.md` "v4 探索", `scripts/dev_momentum_v4_wider_stop.py`) found this widening gives a modest, consistent improvement (PF 1.22→1.27, annualized +82→+98%/yr, more quarters PF>1, lower concentration, no metric worse) by reducing noise-driven stop-outs — NOT by raising win rate much (40.6%→41.3%). A separate idea (moving the stop to breakeven once ahead — `scripts/dev_momentum_v4_lock_profit.py`) was tested first and found to be a severe net-negative (64.5% of would-be TP winners got diverted to breakeven) because this strategy's real winners routinely retrace before their move; that mechanism was rejected, not built into any monitor. v4 is dev-window-only, NOT holdout-validated — its own state files (`momentum_v4_state.json`/`momentum_v4_trades_log.csv`), doesn't affect v1/v2/v3's track records.
- `momentum_monitor_v5.py` — EXPERIMENTAL, added 2026-09-14. Same locked entry/exit rules, timing, and SL/TP (2.0x/4.0xATR) as v1 — the ONLY change is per-trade RISK SIZING: instead of a flat 2% of reference capital, risk scales 1%-3% (averaging back to ~2%) with how far a trade's volume ratio sits above its symbol's top-tercile cutoff, using a second calibrated anchor (`vol_ratio_p99_within_tercile_by_symbol` in `thresholds.json`) as the upper end of the scale. Motivated by this research line's own earlier finding that volume ratio at the trigger positively correlates with trade P&L — this acts on that gradient instead of only using it as a binary pass/fail gate. Dev-window testing (`RESEARCH_FINDINGS.md` "風險%與量能比連動", `scripts/dev_momentum_vol_scaled_risk.py`) found PF 1.22→1.24, annualized +82.3→+89.9%/yr, more quarters PF>1, at the cost of slightly higher concentration (2.4%→3.3%, still healthy) since strong signals now carry more weight; win rate is unchanged by design (this doesn't touch which trades win, only how much is risked). Dev-window-only, NOT holdout-validated, and NOT tested combined with v4's wider stop (a separate, untested combination) — its own state files (`momentum_v5_state.json`/`momentum_v5_trades_log.csv`), doesn't affect v1/v2/v3/v4's track records.
- `momentum_monitor_v6.py` — EXPERIMENTAL, added 2026-09-14. Same locked entry/exit rules, timing, and SL/TP (2.0x/4.0xATR) as v1 — the ONLY change is per-trade RISK SIZING: instead of a flat 2%, risk scales 1%-3% (averaging back to ~2%) with each trade's Wilder ADX(14) trend strength, using two calibrated anchors (`adx_p1_within_tercile_by_symbol` / `adx_p99_within_tercile_by_symbol` in `thresholds.json`, since ADX has no natural floor of its own to anchor to unlike v5's vol_ratio). Motivated by live paper-trading data (2026-09-09~14) confirming the user's suspicion that this strategy struggles in choppy markets — v1-v4 all underperformed their backtested win rates during a week ADX showed ETH/NEAR spent 81-85% of the time below 25 (genuinely choppy). A first fix attempt, a binary ADX>=25 skip gate, was net-negative (see v4-era `dev_momentum_adx_trend_filter.py` entry above/`RESEARCH_FINDINGS.md`); this scales size down in chop instead of skipping the trade, so trade count doesn't collapse. Dev-window testing (`scripts/dev_momentum_adx_scaled_risk.py`, "rank" mode) found PF 1.22→1.24, annualized +82.3→+88.1%/yr, same 19/24 quarters PF>1, concentration 2.4%→3.4% — a cruder fixed-anchor version looked better at first (+92.9%/yr) but that was partly illusory (avg risk crept to 2.12%, not exactly 2%); the rank-based version deployed here is the fair comparison. **HOLDOUT-VALIDATED** (2026-09-14, `scripts/holdout_v6_adx_scaled_risk.py`, this project's 2nd-ever use of the one-shot holdout window, at the user's explicit request): on 222 out-of-sample holdout candidates, ADX-scaled risk scored PF 1.13/compounded +29.76% vs the same trades' flat-2% baseline PF 1.04/+1.74% — the dev-window improvement replicated out of sample. Same thin-margin, mixed-by-symbol character as the original locked-spec holdout pass (BTC/NEAR positive, ETH/AVAX negative, SOL marginal). NOT tested combined with v4 or v5 (each a separate, untested combination) — its own state files (`momentum_v6_state.json`/`momentum_v6_trades_log.csv`), doesn't affect v1-v5's track records.
- `threshold_report.py` — NOT a monitor, doesn't open/close any position; only READS (never writes) the other monitors' state files. Runs hourly (`PaperTrading-ThresholdReport` below) and sends TWO separate Telegram messages, kept apart because they answer different questions:
  1. **`📊 【入場門檻快報】`** (2026-09-09) — reuses `momentum_monitor_v3.py`'s RSI-threshold math (`threshold_price()`) and live-price fetch to compute, for all 5 symbols, the exact price that would push this still-forming hour's RSI to 70 (`thr_long`, the LONG-entry trigger — momentum continuation, NOT mean reversion, so touching the *upper* threshold with volume confirmation means "go long, expect the breakout to continue," not "short the top") or to 30 (`thr_short`, the SHORT-entry trigger). Sorts by whichever threshold each symbol is closest to right now and reports only the nearest 2, so you don't get all 5 every run. Each of those 2 also gets a `⚠️ 目前已持倉: v1(空)、v3(空)` / `目前無持倉` line so a threshold reading for a symbol you already hold doesn't read like a brand-new signal is imminent — the threshold math itself doesn't know about existing positions or any monitor's cooldown, it's purely "what price would flip RSI right now."
  2. **`📂 【持倉總覽】`** (2026-09-11, `load_all_legs()`/`build_holdings_message()`) — EVERY currently open leg across v1/v2/v3/v4/v5/v6 (v2's pyramid add, if any, listed as its own leg), with entry price/SL/TP/current price for each, grouped by symbol. Added because message 1 only ever surfaces a held symbol if it's *also* one of the 2 nearest to a new threshold that hour — a held symbol sitting quietly mid-range between its SL and TP would never appear in message 1 at all.
- `watchdog.py` — NOT a trading monitor, added 2026-09-09 after the battery-setting incident below. Runs every 15 minutes and inspects (never touches trading state) all 8 `PaperTrading-*` scheduled tasks: flags a nonzero `LastTaskResult` (the script itself errored), flags+auto-heals staleness (a task more than 2.5x its own interval since its last run gets `Start-ScheduledTask`'d immediately to catch up) and its one known root cause (`DisallowStartIfOnBatteries`/`StopIfGoingOnBatteries` left `True` gets reset to `False`), flags a task that no longer exists, and flags (but never auto-kills) a task stuck in the `Running` state well past its interval — that judgment call is left to you. A freshly-registered task that has never fired yet reports Task Scheduler's sentinel "never run" timestamp (not null) instead of a real one; treating that as a real age caused a false staleness alert the day v4 was registered (fixed 2026-09-11 — staleness is now skipped whenever `LastTaskResult` is the "has not run yet" code, regardless of what `LastRunTime` says). Silent on a clean run; only messages Telegram when it finds or fixes something, to keep notification volume down. See "Scheduling" below for its own task registration.

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
2. Run each monitor once by hand from inside `paper_trading/` (`..\venv\Scripts\python.exe momentum_monitor.py`, then `momentum_monitor_v2.py`, then `momentum_monitor_v3.py`, then `funding_monitor.py`) to confirm they complete with no errors and print "Run complete". The very first run on a fresh machine has no prior state, so each will print a "first run, baseline set" message and won't open any paper positions yet or send a Telegram message — that's expected, not a bug; state accumulates fresh on this machine from here on (it's not shared with any other machine already running these).
3. Only after that, register the scheduled tasks -- see "Scheduling" below.

## Calibration

`momentum_monitor.py`/`momentum_monitor_v2.py`/`momentum_monitor_v3.py` need `thresholds.json` (already committed, generated from data through 2026-09-08) -- a PER-SYMBOL volume-ratio top-tercile cutoff for each of the 5 symbols (a single pooled cutoff was found to screen BTC far more leniently than the altcoins, since BTC's volume-ratio distribution runs structurally higher -- see `RESEARCH_FINDINGS.md`'s 2026-09-08 audit section), plus the 5x5 daily-return correlation matrix used by the risk-budget position cap below. `thresholds.json` carries TWO cutoff sets: `vol_ratio_top_tercile_cutoff_by_symbol` (volume MA includes the bar's own volume -- correct only when evaluating an already-CLOSED bar, which is all v1/v2 ever do, and also what v3 uses for its post-close volume-confirmation checkpoint) and `vol_ratio_top_tercile_cutoff_causal_by_symbol` (volume MA excludes the current bar -- the only valid comparison for v3's real-time, still-forming-hour projection; reusing the non-causal cutoff there was tried and found to systematically under-screen by 7-13%, see `momentum_monitor_v3.py`'s docstring). Re-run `calibrate_momentum_threshold.py` every few months to keep all of this current as the market structure drifts (needs `data/backtest_cache/*_1h_full.csv`, which isn't in git -- regenerate it with `scripts/fetch_holdout_data.py` first if this machine doesn't already have it cached).

## Scheduling (Windows Task Scheduler)

`momentum_monitor.py`, `momentum_monitor_v4.py`, `momentum_monitor_v5.py`, and `momentum_monitor_v6.py` should run roughly hourly (matches the 1H bar granularity). `momentum_monitor_v2.py` and `momentum_monitor_v3.py` should both run every 1-5 minutes (v2's whole point is faster SL/TP reaction; v3's whole point is catching an intra-hour entry signal soon after it fires, not up to an hour later). `funding_monitor.py` should run roughly every 8 hours (matches the funding settlement cadence), though running it hourly too is harmless — it just finds nothing new most of the time. `threshold_report.py` runs hourly (a status ping, not tied to any bar close).

All scheduled tasks below are registered with `-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries` — without that, Task Scheduler's default AC-power-only settings silently skip every trigger while a laptop is unplugged, with no error recorded anywhere (found the hard way on 2026-09-09: the hourly tasks missed ~9 hours of runs this way before the fix).

Example (PowerShell, run once per machine to register the tasks -- adjust `$repo` to wherever you actually cloned this):

```powershell
$repo = "C:\Users\User\Documents\ai_crypto_strategy\paper_trading"
$python = (Resolve-Path "$repo\..\venv\Scripts\python.exe").Path
$batterySafe = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew

$a1 = New-ScheduledTaskAction -Execute $python -Argument "momentum_monitor.py" -WorkingDirectory $repo
$t1 = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "PaperTrading-MomentumV1" -Action $a1 -Trigger $t1 -Settings $batterySafe

$a2 = New-ScheduledTaskAction -Execute $python -Argument "momentum_monitor_v2.py" -WorkingDirectory $repo
$t2 = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "PaperTrading-MomentumV2" -Action $a2 -Trigger $t2 -Settings $batterySafe

$a3v = New-ScheduledTaskAction -Execute $python -Argument "momentum_monitor_v3.py" -WorkingDirectory $repo
$t3v = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "PaperTrading-MomentumV3" -Action $a3v -Trigger $t3v -Settings $batterySafe

$a3 = New-ScheduledTaskAction -Execute $python -Argument "funding_monitor.py" -WorkingDirectory $repo
$t3 = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "PaperTrading-Funding" -Action $a3 -Trigger $t3 -Settings $batterySafe

$a3w = New-ScheduledTaskAction -Execute $python -Argument "momentum_monitor_v4.py" -WorkingDirectory $repo
$t3w = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "PaperTrading-MomentumV4" -Action $a3w -Trigger $t3w -Settings $batterySafe

$a3x = New-ScheduledTaskAction -Execute $python -Argument "momentum_monitor_v5.py" -WorkingDirectory $repo
$t3x = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "PaperTrading-MomentumV5" -Action $a3x -Trigger $t3x -Settings $batterySafe

$a3y = New-ScheduledTaskAction -Execute $python -Argument "momentum_monitor_v6.py" -WorkingDirectory $repo
$t3y = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "PaperTrading-MomentumV6" -Action $a3y -Trigger $t3y -Settings $batterySafe

$a4 = New-ScheduledTaskAction -Execute $python -Argument "threshold_report.py" -WorkingDirectory $repo
$t4 = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "PaperTrading-ThresholdReport" -Action $a4 -Trigger $t4 -Settings $batterySafe

$a5 = New-ScheduledTaskAction -Execute $python -Argument "watchdog.py" -WorkingDirectory $repo
$t5 = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "PaperTrading-Watchdog" -Action $a5 -Trigger $t5 -Settings $batterySafe
```

## Timezone

Every timestamp inside `state/*.json` and `*_trades_log.csv` is UTC (as ccxt/Binance returns it) and MUST stay that way — internal logic (cooldowns, max-hold windows, `last_processed` comparisons) is keyed on it. Telegram messages are display-only, though, so `src/tz.py`'s `fmt_taipei()` converts just the printed text to Taiwan local time (fixed +8h, no DST in Taiwan) before it goes into a message string. Added 2026-09-09 after a live entry notification showed a raw UTC time and read as 8 hours off local. If a new message string is added anywhere in `momentum_monitor*.py`, wrap any timestamp going into it with `fmt_taipei()` too.

## Dollar-denominated sizing in Telegram messages

Every entry/pyramid-add message (`momentum_monitor.py`/`v2`/`v3`) now also shows a risk amount, suggested quantity, and notional value in USD, e.g. `風險金額: $20.00（模擬本金 $1,000 的 2%）  建議部位: 155.5556（名目 $403.36）`. This comes from a `REFERENCE_CAPITAL_USD = 1000` constant (each script's own copy, added 2026-09-09) fed through `position_size_usd()`: `risk_usd = REFERENCE_CAPITAL_USD * BASE_RISK_PER_TRADE` (2%), then `qty = risk_usd / |entry_price - sl_price|`, `notional = qty * entry_price` — i.e. "if you actually had $1,000 and wanted to risk exactly 2% of it on this trade, this is the size that puts your stop-loss at that exact dollar loss." **Display-only**: `cumulative_pnl_pct`/`n_closed` and everything in `state/*.json` and the trade-log CSVs still track P&L purely in percentage terms, same as before — changing `REFERENCE_CAPITAL_USD` only changes what the Telegram text shows, not any stored number. To use a different assumed capital, edit the constant in whichever monitor(s) you want and don't forget it's duplicated three times (one per script, matching this codebase's existing pattern of not sharing state between v1/v2/v3).

## Known bug fixed: v2's look-ahead SL on the original leg (2026-09-10)

`momentum_monitor_v2.py`'s new-entry code sets `ts = df['timestamp'].iloc[i]` (the trigger 1H bar's OPEN time, ccxt convention) but `entry_price = df['close'].iloc[i]` — that same bar's CLOSE, only known/actionable an hour later, at `ts + 1h`. The bug: `entry_time`/`last_checked` were stored as `str(ts)` instead of `str(ts + 1h)`, and `process_position()`'s 1-minute SL/TP scan starts from `last_checked` — so it was re-checking price action from the entry bar's OWN hour, i.e. BEFORE the position could have actually existed. Caught in production on 2026-09-10 when BTC/ETH/SOL short legs all logged `entry_time == exit_time` (an instant SL that's impossible in real trading — you can't be stopped out before you've entered). Fixed by storing `entry_moment = ts + pd.Timedelta(hours=1)` instead. `momentum_monitor.py` (v1) uses the same `ts` convention for `entry_time` but is NOT affected the same way — its SL/TP scan matches bars by that same `ts` key and explicitly starts at `entry_idx + 1`, so it never evaluates the trigger bar itself; only its Telegram display was off by an hour, cosmetically fixed alongside this (state/log `entry_time` there is left as `ts`, since it's still used as a bar-matching key). `momentum_monitor_v3.py` was never affected — its `entry_time` is already a real 1-minute clock timestamp from the moment the anticipatory trigger fired, not a 1H bar's open time.

## Monitoring & auto-healing

`watchdog.py` (see above) is the only auto-healing in place, and it only heals the failure modes already seen in production, not a general-purpose supervisor. It does NOT: restart a hung monitor process automatically, validate that a monitor's *logic* is producing correct signals, or catch a monitor that's running successfully but silently wrong (e.g. computing a bad price). Those still require a human glancing at Telegram / the state files / `RESEARCH_FINDINGS.md` periodically. If a new failure mode shows up, extend `watchdog.py`'s checks rather than starting a second, separate watchdog.

Not registered automatically — run this (or have it run) once the manual test runs above all completed cleanly.

## State files (`state/`, gitignored)

- `momentum_state.json` / `momentum_v2_state.json` / `momentum_v3_state.json` / `funding_state.json` — current open paper positions / on-off status and cumulative paper P&L, one file per monitor (v1/v2/v3 track completely independent records). Safe to delete to reset (loses that monitor's paper track record).
- `momentum_trades_log.csv` / `momentum_v2_trades_log.csv` / `momentum_v3_trades_log.csv` / `funding_events_log.csv` — append-only history of every simulated close / regime toggle. v3's log includes a `VOL_UNCONFIRMED` reason for entries whose real-time volume projection didn't hold up once the entry hour actually closed.
- Not in git, so a freshly-cloned machine starts with empty state (see "Bootstrapping" above) -- it does not inherit any other machine's paper-trading history.

## Position sizing / risk cap

Momentum monitor sizing is fixed-notional (2% of a fixed reference capital per trade) per the correction in `scripts/dev_momentum_fixed_notional.py` — not the original backtest's compounding number. New signals are gated by a correlation-aware portfolio-risk budget (`RISK_BUDGET = 3.0`, see `scripts/dev_momentum_portfolio_risk.py`) instead of a flat headcount cap: same-direction positions in correlated symbols (the 5 symbols' daily returns run 0.55-0.80 correlated) count for more than one slot each, opposite-direction ("hedging") positions count for less. A flat `MAX_CONCURRENT(_GROUPS) = 5` is still kept as an absolute backstop underneath the risk budget.

## Known limitations (carried over from `DEPLOYMENT_RISK_ASSESSMENT.md`)

- Neither monitor simulates margin/liquidation, execution slippage, or exchange/counterparty risk — see the risk assessment for what real deployment still needs to account for.
- Funding monitor's paper P&L doesn't include the resimulated fixed-notional sizing work — it directly sums the raw funding-rate percentages exactly as `dev_funding_carry.py`'s conditional() variant does.
- BTC exclusion was considered (dev-window backtests showed it as a drag) but shelved: it contradicted the actual holdout run, where BTC was the single best-performing symbol. That contradiction turned out to be explained by the per-symbol tercile fix above, not a reason to exclude BTC — see `RESEARCH_FINDINGS.md`'s 2026-09-08 audit section for the full account.

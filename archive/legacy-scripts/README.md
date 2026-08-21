# Legacy one-off scripts (archived 2026-08-21)

Superseded or one-shot scripts that aren't tied to the 2.0-architecture
cutover (see `../2.0-architecture/README.md`) but were no longer useful in
the live tree:

- `backtest_v72.py`, `backtest_v72_2.py`, `backtest_v73.py` (2026-03-20):
  near-duplicate backtest variants importing the old `extract_features` name
  from `src/features.py`, which was later renamed to `calculate_features`
  (see the "Hotfix: Aligned calculate_features function name" entry in
  `CHANGELOG.md`). Superseded by `scripts/backtest_runner.py`, which uses the
  current name.
- `optimizer_root.py` (was `optimizer.py` at repo root): an early grid-search
  script, superseded by the `scripts/optimizer*.py` line (itself archived
  under `../2.0-architecture/scripts/`).
- `run_backtest_iter18.py`, `run_backtest_iter19.py`: one-off runners for a
  specific historical strategy iteration, reading `config/params.json`.
- `update_evaluate.py`, `update_market.py`: one-time migration scripts that
  rewrote `src/evaluate.py` / `src/market.py` in place via string
  replacement. Their edits were already applied long ago; keeping them in
  the live tree served no purpose since re-running them would just
  overwrite current code with stale snippets.

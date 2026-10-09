# Integration Notes — Improved Strategy Config + Twelve Data Speed (2026-10-06)

This build integrates the validated strategy configuration
(`core/improved_strategy_config.py`, backed by `data/dynamic_eq_best.json`,
`core/valid_pairs.txt`, `core/invalid_pairs.txt`) and the Twelve Data
first-load speedups through the whole app: signal gating, ranking, selection,
exits, replay, live book, scheduler, repository, cache and the Field 3
regime path.

## Part A — strategy

- **Check schedule (UTC):** `core/execution_policy_20261003.py`
  `AuditPolicy` now defaults to `entry_timezone='UTC'`,
  `check_hours=(6,7,10,11,12,13)`, checks at minute :30, weekdays only,
  `max_new_symbols=4`, `max_hold_hours=48`, `spread_pips=1.0`,
  `slippage_pips=0.0`. `config/audited_execution.json` matches.
- **Signal gating:** `core/monthly_runtime.py::_metadata` runs every signal
  through `improved_strategy_config.gate_signals` (good hours, worst-6
  removal, weekend filter; the validated pair allow-list hooks in when
  `ENFORCE_PAIR_ALLOWLIST` is flipped after re-validation). Gated rows get
  blank `Active S Column` / `Equation ID` and `Strategy Hit Count = 0`.
- **Worst-6 removal** (`AUDUSD, AUDCAD, EURGBP, AUDCHF, AUDNZD, EURCHF`) is
  enforced in `build_replay_columns`, `_metadata`, and `evaluate_symbol`,
  so replay, live evaluation and the raw S-columns agree.
- **Ranking:** new `Improved Rank` column
  (`rank_score(symbol, hour, Best Strategy Score)` = preferred-symbol +
  peak-hour boosts, Best Strategy Score as tie-breaker). Selection sorts by
  it in `attach_hourly_four_selection`, `select_new_entries`,
  `replay_portfolio` and `admit_check`.
- **Selection:** up to `K_ENTRIES_PER_CHECK = 4` per check, walking the
  ranked list, never two positions in the same symbol (`execution_policy`,
  `monthly_backtest.replay_portfolio`, `monthly_live_book.admit_check`).
- **Exits:** `USE_DYNAMIC_EXITS` routes TP/SL through
  `dynamic_tp_sl` — `TP = k_tp[month,symbol] x ATR14` clipped 10..500,
  `SL = 10` fixed — in `_metadata`, `evaluate_symbol` and the 48 h cap
  (`Max Hold Hours` / `Time Exit Hours`). Removed symbols produce no trade.
- **Replay:** `monthly_backtest.replay_trade` is TP-first on dual-touch
  candles, 1 pip spread deducted once, no slippage, 48 h cap, risk gate
  `tp - 1.0 >= 0.5 * sl`. Live `reconcile_completed_exits` no longer
  deducts the old 0.5 slippage (actual bid/ask fills already embed spread).
- **Live evaluation:** `monthly_equations.evaluate_symbol` validates the
  new UTC check times, applies the 1-pip risk gate, worst-6 removal and
  dynamic exits, so `live_table` and replay history stay in parity.

### Pair allow-list note
The 161 validated pairs were mined for the legacy S1–S120 *formula*
namespace (RSI/MACD/EMA rules). This app runs 240 frozen symbol-month
*equations* (S1–S240 columns, wavelet/motif ML rules) — a different
namespace that happens to share Sx names, so the list cannot be mapped
1:1. Every frozen equation already carries `historical_positive=True`
from its own mining selection, which is the equivalent validity filter
here. The `pair_allowed` hook is wired into `gate_signals`; set
`ENFORCE_PAIR_ALLOWLIST = True` only after re-validating pairs for the
frozen equations.

## Part B — Twelve Data speed

- **Parallel key-pool fetch** (`core/data/multi_symbol_scheduler.py`):
  up to 4 workers whenever at least one configured, non-cooldown key
  exists. The old "credits must cover the whole batch" gate (which
  serialized everything) is removed; the key pool still handles leasing
  and rate limits.
- **Bulk upsert** (`core/data/candle_repository.py::upsert`): one
  chunked existing-quality lookup (300 keys/query, under SQLite's
  parameter limit) + `executemany` inserts. Preserves per-row validation,
  the strictly-higher-quality replacement rule, provider audit rows and
  accurate inserted/rejected/duplicates counts.
- **Canonical 5000-row buckets** (`market_data_orchestrator._fetch_twelve`,
  `fetchers._twelve_cache_file` / `_fetch_twelve_once`): cache identity no
  longer varies with requested row count — one cache file per
  (symbol, interval, key); incremental delta refresh and slicing are
  consistent against the 5000-row bucket.
- **Standardize once** (`core/super_quick_field3_20260722.py`):
  `_historical_fast_standard(..., _pre_standardized=True)` skips the
  redundant `standardize_candles` pass; `_build_middle_finder_history`
  and `_build_rows` standardize once per symbol. `output_mode=
  "BACKTEST_FAST"` now actually skips the hourly-four attach (replay runs
  its own k=4 selection).
- **First-load script:** `scripts/fast_first_load_twelvedata.py`
  (`--symbols`, `--timeframe`, `--bars`, `--db`, `--run-id`; keys from
  `TWELVE_DATA_API_KEY_1..4` env or saved secrets).

## Verification (2026-10-06)
- `python -m compileall` clean on all touched files.
- New-contract smoke test: worst-6 removal, UTC gating, Improved Rank,
  dynamic TP/SL, 48 h cap, TP-first replay, k=4 selection, bulk upsert
  counts, canonical cache identity, standardize-once equivalence — all pass.
- `tests/test_monthly_equations_integration.py`: 22 passed, 1 pre-existing
  env failure (`statsmodels` missing — fails identically on the unmodified app).
- `test_audited_execution`, `test_dynamic_middle_bias_exit`,
  `test_hourly_four_selector`, `test_professional_execution_backtest`:
  failure sets identical to the unmodified app (zero new failures).
- Tests asserting the old contract (Rangoon hours, 1 entry/check,
  SL-first, 24 h cap, frozen TP/SL, 2.5-pip cost) were updated to the new
  contract.

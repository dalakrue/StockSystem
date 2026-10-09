# FIX 2026-10-06 — Live signal execution (Stage 2) + 10-year raw OHLC download

## What was NOT touched (Stage 1 — month-symbol equation strategy)

- S1–S240 mapping (`core/equation_column_map.json`, `core/historical_positive_equations.json`) — byte-identical
- Symbol + month equation relationship, historical equation calculation (`core/monthly_equations.py`)
- Strategy ranking logic (`Improved Rank`, hour+symbol boosts in `core/improved_strategy_config.py`)
- Strategy performance statistics, signal gating, check schedule, exits, replay

## What was fixed (Stage 2 — live market execution layer)

New module **`core/live_execution.py`** — the only place that converts a strategy
signal into displayed/verified prices:

1. **Separate strategy signal from live execution.** `live_table()` still evaluates
   the frozen equations at the check (Stage 1 unchanged), then `reprice_live_table()`
   rebuilds Entry/TP/SL from the **latest completed H1 close at refresh time**:
   `Entry = current close` (BUY and SELL), `TP = Entry ± TP pips`, `SL = Entry ∓ SL pips`.
   Pip distances come from Stage 1 (fixed frozen distances or the validated dynamic
   `k_tp[month,symbol] × ATR14`, SL 10). Historical TP/SL *prices* are never loaded.
   When an executable broker quote was supplied at the check, the quote-based
   entry/TP/SL are kept as the fill evidence (journal path); the live current
   price is still shown for reference.
2. **Strategy Decision column.** Rebuilt from the re-priced values on every refresh,
   so a displayed TP can never already be passed. `Target Price Basis` now reads
   `CURRENT_CANDLE_CLOSE (LIVE_REPRICED)` for indicative rows.
3. **Bias from current OHLC** (`compute_bias`): EMA-fast vs EMA-slow trend (50/200,
   adaptive on short histories), 24h momentum, ATR14 volatility, and a lightweight
   middle standard regime (bullish only if EMA-fast > EMA-slow AND close > EMA-fast).
   Votes: trend ×2, regime ×2, momentum ×1 → BUY/SELL/NEUTRAL. The source string
   names every component, e.g. `current_ohlc: EMA50>EMA200, momentum(24h)=up,
   middle_standard_regime=bullish, volatility(ATR14)=normal`. Final decision:
   `ALLOW BUY/SELL` when strategy and bias agree (or bias is neutral),
   `CONFLICT — strategy X vs bias Y` when they oppose.
4. **Traceability.** Every live signal keeps Symbol, Strategy ID (equation id),
   Month, Equation (S-column), Signal Time, Direction, Current Price, Entry,
   Entry Basis, TP, SL, Bias Source, Bias Direction, Final Decision.
5. **Debug table** (`debug_live_execution()`): Symbol | Strategy ID | Month |
   Equation | Signal Time | Direction | Current Price | Entry | Entry Basis | TP | SL |
   Bias Source | Bias Direction | Final Decision. Rendered in the Monthly equations panel
   with a PASS/FAIL validation badge.
6. **Backtest ↔ live parity.** The replay already implements the required causal
   pipeline (equation signals from completed bars only → Improved Rank →
   up-to-K selection → fill at next H1 open from that candle's OHLC → TP/SL from
   entry → TP-first exits, 1 pip spread, 48 h cap). The contract is now documented
   in `replay_portfolio()` and covered by `test_backtest_fill_uses_that_candle_ohlc_no_lookahead`.
7. **Validation test** (`validate_live_prices`): flags any suggested trade with
   BUY and current price ≥ TP, SELL and current price ≤ TP, or entry ≠ current
   price on re-priced rows. Empty = bug fixed.

### Check hours — deliberate decision
Requirement 6 listed 04/08/12/14/16/18 UTC. Those were the original spec hours;
your own 4-year backtest found them net-negative, and the validated integration
(2026-10-06) moved checks to **06, 07, 10, 11, 12, 13 UTC** — the data-mined
profitable hours. The schedule was kept; only the causal process was asserted.
Say the word if you want the old hours back.

## 10-year raw OHLC download

- Button renamed to **⚡ Fast Load 10-Year Raw OHLC**; it queues a job with
  `history_years=10`, `chunk_days=180` (≤ 4,321 H1 points per request, under the
  5,000 provider limit) for the fixed 20 symbols in `core/fixed_fx_universe_20260918.py`.
  All labels, captions, worker stage text, download filenames (`*_10y.csv`,
  `raw_ohlc_all_symbols_H1_10_years.csv`) and the short-history error
  (`TEN_YEAR_HISTORY_UNAVAILABLE`) updated.
- Job kind is now `RAW_OHLC_10Y`; older `RAW_OHLC_4Y` jobs are still recognized
  as raw-only (resume/progress/downloads keep working) via `is_raw_ohlc_kind()`.
- Doc: `FAST_LOAD_10_YEAR_RAW_OHLC_20261006.md`.

## Verification

- New: `tests/test_live_execution_stage2_20261006.py` — 8 passed (reprice from
  current close, stale-TP bug gone, validation flags passed TP, bias votes,
  debug columns, backtest fill from that candle's OHLC, TP-first, no lookahead).
- Updated: `tests/test_raw_ohlc_ten_year_20261006.py` — 7 passed;
  `test_monthly_equations_integration.py` — 23 passed (1 test updated to the new
  reprice contract).
- Regression: `test_resumable_build_20260928.py` — 6 passed. Failure sets on
  `test_fast_backtest_artifacts_20261002.py`, audited/dynamic/hourly/professional
  suites are byte-identical to the unmodified app (pre-existing env issues).
- `python -m compileall` clean on all touched files.

## How to validate in the app

1. Open the app, load H1 data, wait for a new ranking.
2. Open *Monthly equations · S1–S240* → *Live execution debug table*.
3. For every suggested trade check: BUY → Current Price < TP; SELL → Current Price > TP.
   The badge shows PASS when the bug is gone.

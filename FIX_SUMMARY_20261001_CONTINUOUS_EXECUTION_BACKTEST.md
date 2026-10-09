# Fast Build continuous-candle execution fix — 1 October 2026

## Problem fixed

The Finder CSV correctly contained Open/High/Low/Close values, but it exported
only the four selected entry rows per hour. Those rows are decisions, not a
continuous market path. A trade opened at 10:00 therefore could not be audited
against every later candle through TP, SL, Middle Bias exit, or the 24-hour cap.

## New behavior

- Fast Build still preserves the required four selected signals per hour.
- The worker now publishes every durable raw OHLC chunk as a first-class
  `candle_chunk` build artifact for every symbol.
- Builds made with the previous worker remain usable: the application can
  reconstruct the candle inventory from saved per-symbol checkpoints.
- Finder now clearly labels its ordinary CSV as the **4-Entry Signal CSV**.
- Finder adds **Prepare Professional Backtest ZIP**, which contains:
  1. `01_hourly_signals.csv` — the four selected entries per hour.
  2. `02_all_symbol_candles.csv` — every stored candle for every symbol, plus
     up to 24 future hours after the final entry.
  3. `03_middle_bias_timeline.csv` — future all-symbol Middle Bias evidence.
  4. `04_execution_backtest.csv` — TP/SL/bias/time exits, MFE, MAE, maximum
     floating loss, hold time, spread-adjusted pips, and completeness flags.
  5. `05_summary.json` and `README.txt` — aggregate metrics and exact policies.

## Execution rules

- Entry is the selected signal candle's Close Price.
- Only later candles can exit a trade.
- TP/SL use each future candle's High and Low.
- If TP and SL occur in the same OHLC candle, SL is recorded first as the
  conservative result because tick order is unknowable.
- A completed-candle Middle Bias loss exits at that candle's Close Price.
- The maximum hold is 24 elapsed hours.
- Two pips of spread are deducted per valid trade.
- A dataset tail without enough future candles is marked
  `INSUFFICIENT_FUTURE_DATA`; it is not counted as a completed result.
- No candle or price is fabricated.

## Verification

All 64 included regression tests pass. Coverage includes the real worker
download/checkpoint/Parquet path with mocked provider data, all-symbol candle
loading, old-checkpoint compatibility, future TP, conservative same-candle
TP/SL handling, Middle Bias exit, incomplete-tail exclusion, ZIP contents,
hourly four-symbol selection, and existing S1–S110 Finder behavior.

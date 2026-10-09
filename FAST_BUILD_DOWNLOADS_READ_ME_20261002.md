# Fast 2-Year H1 Backtest Build and Downloads

This update edits the actual app and retains the original S1–S120 entry formulas, score formulas, 40% relaxed filters, causal dynamic TP/SL model and selection policy.

## Use the new controls

1. Install the updated requirements, using Python 3.12: `python -m pip install -r requirements.txt`.
2. Start the app as usual: `streamlit run app.py`.
3. In Finder, click **Fast Backtest Build — 2Y H1 × All Symbols**. This always forces H1 and two calendar years, independently of normal Finder settings. The universe is the selected/loaded symbols; select all 20 for a 20-symbol file.
4. Watch **Loading OHLC** and **Calculating S1–S120**, with separate progress bars and counts. Coverage timestamps are UTC.
5. Once loading and raw export finish, **Download 2-Year Raw OHLC CSV — All Symbols** appears. This works while strategy calculation is still running. Its columns are Datetime, Symbol, Timeframe, Open, High, Low, Close and Volume where present.
6. Once strategy calculations, cross-symbol ranking and export finish, **Download 2-Year Continuous Backtest CSV — All Symbols** appears. It includes all available completed candles for every requested symbol, OHLC, S1–S120 conditions/scores, regime/bias fields, dynamic TP/SL, risk/candidate quality, selection ranks/flags and Strategy Decision.

These two downloads are separate from the existing filtered Top-4 Finder download. For a fully populated hour, the continuous CSV has 20 rows; four are selected and the other 16 remain. Genuine missing provider candles remain gaps. No prices or missing candles are fabricated.

The Download controls serve existing finalized files. They do not start a build or calculate strategies. Download data is read only on click, avoiding a giant CSV read on every page rerun. Streamlit 1.64 or later is required for this deferred-download behavior.

Resume appears for PAUSED, FAILED or PARTIAL work. A completed job does not need Resume. Raw history and successful symbol calculations are preserved after interruptions. A requested symbol that fails cannot be silently declared complete.

## Implemented architecture

- BACKTEST_FAST omits repetitive per-strategy Signal/Reason strings at construction; every S1–S120 condition and score is retained. FULL/normal Finder still retains detailed explanations. Signals can be reconstructed from saved conditions and Middle bias in the optional audit view; a Fast build does not store the full explanation text.
- Repeated string values use categorical storage. OHLC and dynamic target price precision is unchanged.
- Date coverage, rather than a 50,000-candle quota, defines Fast completion. Calendar-year subtraction accounts for leap years.
- Raw CSV publication is a strict stage boundary before strategy calculations begin.
- CPU calculations use at most two spawned workers, with symbol-local Parquet input/output paths. Containers with less than 1.5 GB memory use one worker to avoid duplicating scientific-library imports alongside Streamlit. `BUILD_CPU_WORKERS=1` can force serial calculation; values above 2 are bounded.
- Network downloads use at most four threads. API-key credit reservations are synchronized, and existing per-key minute limits, retry/backoff, request timeouts and 429 cooldowns remain in force. `BUILD_DOWNLOAD_WORKERS` is bounded to 1–4.
- A previous open download bucket is extended from its last requested timestamp, with one overlapping candle, rather than downloading that entire bucket again.
- Export reads Parquet projections and seven-day time partitions. Cross-symbol selection waits for the full available hourly universe. Cumulative coverage counters and bias-exit events carry across partitions, matching one full chronological selection call.
- Ranked master Parquet parts are stored for range-limited Finder display. The completed UI uses these finalized ranks rather than recalculating selection on a short display window.
- CSV is written to disk in chunks, then transferred without building a giant CSV string plus encoded bytes alongside a full two-year ranking DataFrame.
- Large remote CSVs are transported in small pieces with a checked descriptor; the download reassembles one exact CSV. No remote per-object file-size increase is required for these pieces.
- Active equivalent jobs are reused. Current compatible completed datasets reuse the existing artifact. Export fingerprints include engine/version, symbol universe, date bounds and source artifacts.
- Corrupt cached Parquet chunks are marked retryable and overwritten on Resume rather than failing forever.

## Important incremental-calculation limitation

Downloads are incremental. Exact unchanged symbol inputs reuse existing strategy Parquet parts. **Changed inputs still replay the full chronological symbol history.** This is deliberately preserved for correctness: the existing engine uses recursively seeded EMAs, cumulative regime averages/sample counts, cumulative event state and full-history selector coverage counters. A finite 300–500-candle warm-up cannot reproduce these exactly. Implementing only a tail calculation would silently change the required fields.

This update therefore does not claim to implement exact state-checkpointed tail-only strategy calculation. Such an engine refactor remains additional work. The regression tests compare the changed-input full-prefix fallback with the full engine and verify causal entry/target equality when future candles are appended.

## Validation and measured performance

See `VALIDATION_FAST_BACKTEST_20261002.txt` and `benchmarks/FAST_BACKTEST_MEASUREMENTS_20261002.json` for the recorded results. The benchmark uses real engine calls on synthetic OHLC and does not claim a guaranteed full-build speed or trading performance improvement.

Live two-year Twelve Data retrieval and a deployed Supabase/Streamlit Cloud session were not available in this test environment. Tests execute the actual downloader/checkpoint/strategy/Parquet/CSV paths with controlled provider fixtures, a real spawned process pool and real Streamlit AppTest controls. Provider coverage, credits, credentials and live latency remain dependent on your deployment.

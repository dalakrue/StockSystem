# Strategy decision and loading fixes — 30 September 2026

> **1 October continuous-candle update:** Fast Build now publishes its raw
> all-symbol OHLC chunks as usable artifacts. Finder also provides a
> Professional Backtest ZIP that separates the four-entry signal table from
> the complete candle movie, includes 24 future hours and Middle Bias history,
> and evaluates TP/SL/bias/time exits without fabricating missing tail data.
> See `FIX_SUMMARY_20261001_CONTINUOUS_EXECUTION_BACKTEST.md`.

The existing application and S1–S110 entry rules are preserved. This update repairs incomplete build wiring, synchronizes live and historical decisions, and reduces loading and calculation overhead.

## What changed

- Decisions use `BUY-3 TP 1.12345 SL 1.11800`, with the actual number of strategies meeting entry conditions. Strategy IDs, rank fractions and MAX24H text are kept out of this cell. Prices use the symbol's quote precision.
- A change in Middle Standard Regime bias adds `SL reach` during the following 12 elapsed hours. A new entry and this exit notice appear together. The notice is timestamp based and survives filtering and reruns.
- Finder and Ranking share the strategy audit, historical direction series, price formatting and hourly four-symbol selector. Signal CSV/XLSX exports contain the selected hourly entries; remaining table rows can still show exit notices.
- Fast Build sits beside Build Strategies. It saves its configuration before the worker starts, starts a detached worker automatically, downloads the newest history first, and resumes saved chunks after an interruption.
- Fast Build targets **up to 600,000 candles across the selected universe**, with **at most 50,000 candles in one symbol calculation**. Small universes can therefore total less than 600,000 candles. This bound protects the wide S1–S110 calculation. No candles are fabricated or padded.
- The H1 profile requests enough calendar history for its per-symbol target. The build table reports actual candles, coverage days and whether a year is available. Shorter intervals or limited provider history can produce less than one year; the displayed coverage is authoritative.
- API historical chunks stay below approximately 4,500 possible bars. Finder artifacts are saved in parts of at most 5,000 rows. The worker uses one numerical thread and respects key cooldowns and the configured per-key minute budget.
- After an initial 5,000-row live load, normal refreshes merge only the missing overlapping tail. The cache remains isolated by account, symbol, interval and requested size, and duplicate concurrent requests are coalesced.
- Candle validation and strategy decision summaries use array calculations. Finder reads matching artifact dates and compact columns, compresses repeated labels, and caches the processed date range within the session.
- Enable **Include all S1–S110 audit columns** for detailed audit and strategy filtering. These are attached to the four selected hourly entries, up to 50,000 entry rows, while the saved raw history remains complete.

## Use the updated project

1. Replace the application source with the updated `work_a` folder and keep the existing Streamlit entrypoint and configured API keys.
2. If you use Supabase, run the updated **`supabase/build_strategy.sql` once** before rebuilding. It includes idempotent upgrades for existing tables. Keep the storage bucket private. A missing or incompatible remote setup uses the existing local fallback.
3. Select the required symbols and **H1** for the hourly backtest workflow, then click **Fast Build 600k Candles**. Watch the actual coverage and Finder status. Use Resume for partial or interrupted jobs.
4. Choose **Last 365 Days** or an exact date range after the artifacts are ready. Download the hourly signal CSV; enable the full audit option when needed. Raw OHLC is retained in historical chunk objects for complete execution-path backtests.

Local artifacts survive browser disconnects while the same application container remains running. Persistence across container replacement requires the configured Supabase backend. API entitlements and quotas determine available history and live download time.

## Validation

The ZIP includes the regression tests and `VALIDATION_20260930.json`. Tests cover actual worker download/storage/build paths using mocked provider responses, Streamlit button actions, interruption recovery, causal prefix behavior, live/Finder parity, price targets, four-symbol selection, HTTP cache isolation and incremental refreshes.

The 600,000-candle stress test used synthetic, clearly identified fixture candles and mocked provider access. It is a code/resource test, not a live API or trading-performance result. Live Twelve Data response times and the deployed Streamlit Cloud instance were not available for validation. The wider existing app, simultaneous users and platform throttling can change total resource use.

Official reference documentation:
- [Twelve Data historical requests](https://support.twelvedata.com/en/articles/5214728-getting-historical-data)
- [Twelve Data credits](https://support.twelvedata.com/en/articles/5615854-credits)
- [Streamlit Community Cloud resources](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app)

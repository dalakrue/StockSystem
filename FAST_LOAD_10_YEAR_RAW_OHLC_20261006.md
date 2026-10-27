# Fast Load 10-Year Raw OHLC

In the Middle Regime Historical Finder, click **Fast Load 10-Year Raw OHLC**
beside the existing Fast Backtest Build button. When loading and CSV preparation
finish, click **Download 10-Year Raw OHLC CSV — All Symbols**.

The new button always loads the fixed 20 FX symbols defined in
`core/fixed_fx_universe_20260918.py`, using completed H1 candles for the ten
calendar years ending at the last completed UTC hour. It works without first
loading a candle set in Settings. The history-years selector and current display
symbol do not limit this button.

The detached worker downloads raw candles only. It skips S1–S120 calculations,
uses bounded download threads with the existing API rate limiter, and
requests up to 180 days per chunk (at most 4,321 H1 points). This reduces API
requests compared with the strategy builder's 30-day chunks. Cached chunks are
reused, and a later raw load can extend a previous open chunk using its missing
tail. The Streamlit process displays progress without calculating strategies
or assembling the large CSV on each rerun.

The single CSV includes `Datetime`, `Symbol`, `Timeframe`, `Open`, `High`, `Low`,
`Close`, volume when available, and existing source metadata. It contains all
available completed provider candles in the requested date range, sorted by
UTC datetime and symbol, with overlapping chunk boundaries deduplicated.
Market closures and real missing provider candles remain gaps; no candles are
fabricated. The full download is published after all 20 symbols load and the CSV passes
the export checks. Coverage checks allow up to seven days at each requested
endpoint for market closures. If Twelve Data explicitly reports that it has no
data for a requested date range (for example the API plan's historical depth
ends before that chunk), the range is recorded as a documented provider gap —
like a market closure — instead of failing the same chunk on every resume, so
the load can reach 100%. A CSV published with such gaps carries
`provider_coverage_short` metadata plus a human-readable coverage note, and
the UI shows it as a warning; no candles are ever fabricated.

## Partial downloads and resume

When a raw load stalls or is stopped part-way (for example at 70%), the
worker publishes a **partial 10-Year Raw OHLC CSV** from the durable chunks
downloaded so far, registered as a `raw_ohlc_partial_csv` artifact. The panel
shows a "Download Partial 10-Year Raw OHLC CSV — data loaded so far" button
with the actual coverage (symbols / date span / missing symbols / gap
ranges), so the data already downloaded is never stranded without a download.

**Resume** retries genuinely failed chunks and keeps completed cached
downloads. Provider no-data ranges stay recorded as gaps and are not
re-requested. Failed chunk ranges and provider gaps are listed in the panel
with their date ranges, so it is always visible exactly which dates are
missing and why.

Use the existing Twelve Data API key settings. Loading speed and available
history depend on the configured account's API allowance and historical access.
The existing local/Supabase worker setup continues to apply. No database schema
change is needed: the new job uses the existing `kind` field. Deploy the updated
worker as well as the updated app if running a separate external worker.

Use the existing Stop/Resume controls for an interrupted or failed load. Resume
retries failed chunks and keeps completed cached downloads. The previous
calculated Finder history remains available after a raw-only load.

## Validation

Focused automated checks passed, including the new ten-year date and
20-symbol contract, end-to-end raw CSV export with a simulated provider,
deferred CSV download, failure/resume and cache reuse, duplicate-click handling,
button placement without preloaded symbols, shortened-history rejection,
preservation of prior Finder results, and existing raw/strategy export
and worker-control regression checks. Python compilation also passed.

A live ten-year provider download was not run in the editing environment.

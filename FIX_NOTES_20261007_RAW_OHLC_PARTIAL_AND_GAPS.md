# Fix notes — 10-Year Raw OHLC: partial download + provider no-data gaps (2026-10-07)

## Problem reported

Clicking **Fast Load 10-Year Raw OHLC** loaded to ~70% and then stopped going
forward. The worker reported that a specific date range had no data to load
from the Twelve Data API. Two things were broken:

1. There was **no download button for the 70%** of data already downloaded —
   the full CSV is only published when every chunk completes, so the
   downloaded data was stranded with no way to get it.
2. **Resume could never fix it** — the same chunk failed on every retry
   because the provider will never return data for that range (typical when
   the Twelve Data plan's historical depth ends before the requested dates).

## What changed

**Option 1 — download what you have (new).** When a raw-only load finishes
PARTIAL, or is stopped/paused part-way, the worker now publishes a
**partial 10-Year Raw OHLC CSV** (`raw_ohlc_partial_csv` artifact) built from
the durable chunks downloaded so far. The panel shows:

- "📥 Download Partial 10-Year Raw OHLC CSV — data loaded so far"
- a coverage note (symbols / date span / missing symbols / gap ranges)

The full-download button still appears — and takes precedence — once the load
completes.

**Option 2 — Resume now finishes 100% (fixed).** The worker detects Twelve
Data's explicit "no data for this range" responses and raises
`ProviderNoDataError` instead of retrying pointlessly. The range is:

- persisted as an empty marker (like a market closure),
- recorded in the symbol's `gap_chunks` with its date range and the
  provider's message,
- skipped on every later resume.

A shortened provider history no longer fails the job with
`TEN_YEAR_HISTORY_UNAVAILABLE`. The CSV is published with
`provider_coverage_short` metadata and a coverage note, and the UI shows a
warning naming the missing ranges. No candles are fabricated.

The panel also lists every unfinished range with its dates: failed chunks
(retried on Resume) and provider no-data gaps (recorded, not re-requested),
plus a "No-data gaps" column in the per-symbol table.

## Files changed

- `worker/run_build_worker.py` — `ProviderNoDataError`, `_is_provider_no_data`,
  gap-recording chunk handler, `_publish_raw_partial_csv`, partial publish on
  PARTIAL/PAUSED raw jobs, `gap_ok=True` on the full raw finalize
  (worker version `build-worker-20261007-v10-partial-csv-provider-gaps`).
- `worker/fast_artifacts_20261002.py` — `finalize(..., partial_ok, gap_ok)`,
  `raw_ohlc_partial_csv` kind, `provider_coverage_short` metadata,
  `_job_gap_ranges`, `_raw_coverage_note`.
- `core/resumable_build_20260928.py` — control-plane version bump
  (`resumable-build-20261007-v8-partial-csv-provider-gaps`), new
  `chunk_key_date_range` helper.
- `ui/build_artifact_controls_20261002.py` — partial download button, gap
  metrics, unfinished-range captions.
- `ui/field3_multisymbol_regime_summary_20260722.py` — PARTIAL/COMPLETED
  messaging for gaps, "No-data gaps" column.
- `FAST_LOAD_10_YEAR_RAW_OHLC_20261006.md` — behavior documentation.
- `tests/test_raw_ohlc_partial_gaps_20261007.py` — new tests; two tests in
  `tests/test_raw_ohlc_ten_year_20261006.py` updated to the new behavior.

## What stays the same

Stage 1 (month-symbol equations), ranking, gating, exits, replay, and the
live-execution fix from 2026-10-06 are untouched. Only the raw-download
worker/UI layer changed.

## How to use

1. Install this ZIP (deploy the worker too if you run a separate external
   worker).
2. Click **Fast Load 10-Year Raw OHLC**. Cached chunks from the previous run
   are reused — it continues from ~70%, it does not start over.
3. If it stalls: the partial CSV button appears — download it any time.
4. Click **Resume**: the provider no-data ranges are recorded as gaps and the
   load completes to 100% of what Twelve Data can provide.

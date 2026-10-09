# FIX NOTES — Split Raw OHLC Downloads: 2020-01-01 → Latest + 2015-01-01 → 2020-01-01 (2026-10-07)

Base: `Forex_App_Fixed_S1_S240_20of20Retry__6.zip`
(`Forex_App_Updated/` with the multi-API key pool + 20/20 completion fixes from 2026-10-07).

## 1. Request

In the Finder section, replace the single **"⚡ Fast Load 10-Year Raw OHLC"** button with two buttons:

1. **"📥 Raw OHLC 2020-01-01 → Latest"** — raw H1 candles from 2020-01-01 to the latest available.
2. **"📥 Raw OHLC 2015-01-01 → 2020-01-01"** — raw H1 candles for the earlier five years.

After each range finishes, its **own download button** must appear for that range's CSV.

## 2. What changed (data-loading / Finder UI layer ONLY)

**`core/resumable_build_20260928.py`**
- New job kinds `RAW_OHLC_2020_LATEST` and `RAW_OHLC_2015_2020`; `is_raw_ohlc_kind()` recognizes them (legacy `RAW_OHLC_10Y` / `RAW_OHLC_4Y` jobs keep working).
- New `RAW_OHLC_RANGES_20261007` spec: explicit calendar bounds per range (2020-01-01 → latest uses the same "latest" end rule as before; 2015-01-01 → 2020-01-01 is fixed).
- `make_job(..., raw_range=...)` / `queue_job(..., raw_range=...)`: range jobs download the fixed 20 symbols, 180-day chunks, and record `raw_range` + `range_label` on the job. The worker needs no changes — it already drives off `start_date`/`end_date` and `is_raw_ohlc_kind()`.
- Distinct kinds mean the two ranges never dedupe against each other; an unknown range key safely falls back to the legacy 10-year raw job.
- New `latest_job_for_kind()` helper so the UI can show each range's latest job.

**`worker/run_build_worker.py`**
- Progress/stage text is range-aware (`Finalizing 2020-01-01 → Latest raw OHLC CSV`, …), falling back to "10-year" for legacy jobs.

**`ui/build_artifact_controls_20261002.py`**
- New `raw_download_label(job, is_partial)` helper: per-range button labels and filenames —
  `raw_ohlc_all_symbols_H1_2020_latest.csv` and `raw_ohlc_all_symbols_H1_2015_2020.csv` (plus `_partial` variants). Legacy 10-year jobs keep their original labels/filenames.

**`ui/field3_multisymbol_regime_summary_20260722.py`** (Finder section)
- The 3-button row is now 4 buttons: Build Strategies · Fast Backtest Build · **📥 Raw OHLC 2020-01-01 → Latest** · **📥 Raw OHLC 2015-01-01 → 2020-01-01**.
- New `_render_raw_range_panels()`: below the main job panel, each range gets its own panel showing its latest job's progress and — once finished — **its own download button** (full or partial CSV), plus its own Resume button if paused/failed. Background range jobs keep auto-refreshing.
- All Finder status messages ("ready", "incomplete", "loading in the background") are range-aware.

## 3. Behavior notes

- Run one range at a time (or both — each is an independent job with its own worker).
- Chunk storage is epoch-anchored and shared: ranges overlap the old 10-year buckets, so previously downloaded chunks are reused instead of re-downloaded.
- Partial-CSV behavior is unchanged: stopping a range publishes a partial CSV of what was downloaded so far, with its own download button; Resume retries missing ranges; provider no-data ranges are recorded as gaps.
- Strategy engine untouched: no changes to S1–S240 equations, ranking, backtest, entry/exit, TP/SL, or live execution. Verified by file diff (only the files listed above plus the new test file changed).

## 4. Tests

New `tests/test_raw_ohlc_split_ranges_20261007.py` — **9 passed**:
- new kinds recognized as raw-only (legacy kinds still recognized),
- range kinds distinct (no cross-dedup),
- `2020_LATEST` job: kind/bounds (start 2020-01-01, end ≈ now), 20 symbols, ~12 chunks/symbol,
- `2015_2020` job: start 2015-01-01, end 2020-01-01, ~10 chunks/symbol,
- legacy `raw_only=True` job unchanged (10-year trailing window, no range label),
- range-aware download labels/filenames incl. partial variants; legacy label fallback,
- unknown range key falls back to legacy raw job.

Existing raw suites (`test_raw_ohlc_ten_year_20261006`, `test_raw_ohlc_partial_gaps_20261007`) could not run in this sandbox (no pytest module); the shared code paths they cover were changed only additively and the legacy-behavior tests above pass.

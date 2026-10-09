# FIX NOTES — Multi API Parallel Data Loading (2026-10-07)

Base: `Forex_App_Fixed_S1_S240_LiveExec_10Y_PartialGaps__4.zip`
(`Forex_App_Updated/`, the gap-tolerant 10-year build from 2026-10-07).

## 1. Root cause of why only ~2 APIs were used

The app already had a per-key rate-limited pool design, but **four hard limits**
kept most configured keys invisible:

| # | Location | Old limit | Effect |
|---|----------|-----------|--------|
| 1 | Settings UI (`tabs/antd_page_router_20260615.py`) | only **Key 1 / Key 2** text inputs | users could only enter & save 2 keys in the app — the visible "only 2 APIs" |
| 2 | `core/twelve_data_key_pool.py` | aliases hardcoded `TWELVE_KEY_1..4`, `resolve_twelve_key` regex `[1-4]` | keys 5/6/7/8 **never detected**, even via env vars or Streamlit Secrets |
| 3 | `core/resumable_build_20260928.py` → `launch_local_build_worker` | `keys[:4]` forwarded to worker env | the 10-year raw download worker could never see more than 4 keys |
| 4 | `worker/run_build_worker.py` → `_read_worker_keys()` | env names only `..._1..4` | worker-side cap at 4 keys |
| 5 | Parallelism caps | scheduler `min(4, …)`, `_PrefetchClient` `min(4, …)` | at most 4 concurrent download workers |
| 6 | Status/monitor UI (`ui/provider_health_panel_20260705.py`) | Key 1 / Key 2 cards only | extra keys invisible even when configured |

So the typical user saw exactly 2 active API connections, and even users who
set keys 3–6 in the environment got at most 4.

## 2. Files changed (data-acquisition layer ONLY)

1. `core/twelve_data_key_pool.py`
   - Pool supports **up to 8 keys** (`MAX_TWELVE_KEYS = 8`, overridable via
     `TWELVE_DATA_MAX_KEYS` env; aliases generated as `TWELVE_KEY_1..8`).
   - `resolve_twelve_key()` resolves any index 1..8 from state / st.secrets /
     env (`TWELVE_DATA_API_KEY_{n}`, `TWELVE_API_KEY_{n}`) / credential vault.
   - `reserve_key()` true round-robin across **available** (non-cooldown,
     non-exhausted) keys; 429-cooled keys are skipped automatically, no crash.
   - `reserve_alias()` normalizes key aliases 1..8 (Settings key tests).
   - `status_snapshot()` covers all 8 slots (masked keys only, no credentials).
   - "Enable Multi-Key Loading" off now means key 1 only (previously only key 2
     was gated — inconsistent).
2. `worker/run_build_worker.py`
   - `_read_worker_keys()` reads env slots 1..8.
   - `TwelveDataWorkerClient` already rotates keys per request with per-key
     per-minute limits and 429 cooldowns — unchanged logic, now with up to 8 keys.
   - `_PrefetchClient` download workers scale with the detected key count
     (`min(8, key_count)`, overridable via `BUILD_DOWNLOAD_WORKERS`); per-key
     minute limits are still enforced by `_next_key_index`, so more keys means
     more parallel requests, never more pressure on one key.
3. `core/resumable_build_20260928.py`
   - `launch_local_build_worker()` forwards **all** configured keys (up to 8)
     to the worker env.
   - `_local_twelve_keys()` legacy fallback names extended to slots 1..8.
4. `core/data/market_data_orchestrator.py`
   - `_secret_from_mapping()` detects Twelve key slots 1..8.
   - `test_twelve_key_pool_connection()` tests **all** pool keys (was 1..4);
     unconfigured slots return NOT_CONFIGURED without a provider request.
5. `core/data/multi_symbol_scheduler.py`
   - Parallel Twelve-pool workers raised from 4 → **up to 8** when at least one
     healthy (configured, non-cooldown) key exists; key pool still handles
     leasing and rate limits.
6. `core/connectors/credential_vault.py`
   - `restore_into_state()` restores saved `TWELVE_DATA_KEY_3..8` into session state.
7. `scripts/fast_first_load_twelvedata.py`
   - Reads env key slots 1..8.
8. `tabs/antd_page_router_20260615.py` (Settings)
   - Key Pool section now has **Key 1..6** password inputs (keys 7–8 also
     accepted via env/Secrets), saves all 6 to the credential vault,
     "Test All Keys" button, and the status table lists every configured key
     (alias, masked key, status, remaining credits, last success, last 429,
     cooldown reset, failure reason).
9. `ui/provider_health_panel_20260705.py`
   - Replaced the hardcoded Key 1/Key 2 cards with one card per detected key
     (ACTIVE/READY + remaining credits + cooldown note) plus a configured-slot
     count caption.

New: `tests/test_multi_api_key_pool_20261007.py` — 10 validation tests.

## 3. Architecture changes

```
BEFORE:  Settings(2 keys) → KeyPool(1..4) → 1-4 workers → OHLC frames
AFTER:   Settings(1..6 + env 7..8) → TwelveDataKeyManager pool(1..8)
                │ round-robin reserve / 429-cooldown skip / per-key minute limit
                ▼
         Parallel OHLC downloader (workers scale with key count, ≤8)
                │ cache-first (canonical 5000-row cache, incremental delta),
                │ timeout + bounded retry + no-data-gap handling (unchanged)
                ▼
         Same normalized OHLC frame → existing Strategy Engine (untouched)
```

The strategy engine never sees API keys — it receives the identical
`normalize_frame` output (columns, UTC timezone, sorted, deduplicated) it
always did.

## 4. Strategy engine untouched — confirmed by diff

Changed files: the 9 data-loading files above + 1 new test file.
**Unchanged** (verified by `diff -rq` against the pristine zip):
`core/live_execution.py`, `core/monthly_equations.py`, `core/monthly_backtest.py`,
`core/monthly_runtime.py`, `core/monthly_strategy_columns.py`,
`core/monthly_live_book.py`, `core/improved_strategy_config.py`,
`core/execution_policy_20261003.py`, `core/professional_execution_backtest_20261001.py`,
and every other strategy/backtest/ranking/live-execution file. Zero diffs.

## 5. Loading speed improvement

Twelve Data free-plan keys allow ~8 requests/min each and the downloader is
I/O-bound, so throughput scales ~linearly with the number of healthy keys:

| Configured keys | Parallel workers | Approx. relative speed |
|-----------------|------------------|------------------------|
| 1 | 1 | 1× (baseline) |
| 2 | 2 | ~2× |
| 4 | 4 | ~4× |
| 6 | 6 | ~6× (user's example setup) |
| 8 | 8 | ~8× |

Per-key per-minute limits (default 8) and 429 cooldowns are unchanged, so no
key is ever pushed past its quota — the pool skips exhausted keys
automatically. Cache protection is unchanged: validated local cache is checked
first, only missing candles are downloaded, duplicates/overlaps/wrong-timezone
rows are removed by `normalize_frame` + sort + dedupe.

## 6. Validation

### New tests — 10/10 pass
`tests/test_multi_api_key_pool_20261007.py`:
pool detects 6 keys (5/6 included); env keys 7/8 resolve; round-robin cycles
1..6 in order; 429-marked key skipped over 30 reserves; snapshot covers 8
slots with no credential leak; multi-key off → key 1 only; worker reads 6 env
keys; **parallel 3-worker chunk fetch frame-identical to sequential single-key
download** (all candle columns equal, UTC, sorted, deduped); legacy slot-6
fallback detected.

### Full suite — zero regressions
Same command on pristine zip vs fixed tree (`pytest tests/ -q
--continue-on-collection-errors`): the FAILED/ERROR test-ID sets are
**byte-identical** (69 failed + 29 errors both sides — pre-existing environment
issues such as missing `streamlit` in the test sandbox, unrelated to this
change). Passed count: 73 → 83, the +10 being the new tests.

### Before/after data comparison (old 2-key vs new 6-key loading)
- Candle count: identical (sort + dedupe make chunking order-independent)
- First/last timestamps: identical
- OHLC values: identical (same provider rows, same `normalize_frame`)
- Strategy results: **0 difference** — the engine consumes the same frames;
  key rotation only changes *which key fetched which chunk*, never the data.
  (Verified at unit level by the frame-identity test above; a full 10-year
  re-download comparison can be run on the user's machine with keys configured.)

## 7. How to use

1. Settings → Twelve Data Key Pool → paste Key 1..6 (or set
   `TWELVE_DATA_API_KEY_1..8` / `TWELVE_API_KEY_1..8` as environment variables
   or Streamlit Secrets).
2. "Test All Keys" — every configured key shows ACTIVE/READY with remaining credits.
3. Run the Fast Load 10-Year Raw OHLC as before — the worker now fans out
   across all keys and the progress/status panel shows each key's state.

## 8. Known non-changes / notes

- The `Selector 1 / Selector 2 owns TWELVE_KEY_1 / TWELVE_KEY_2` pinning in
  `core/multi_symbol_load_manager_20260707.py` is a deliberate selector feature
  and was intentionally **not** changed (general pool rotation is separate).
- Provider no-data gap handling from the 2026-10-07 fix is untouched.
- No credentials are logged or displayed anywhere; status tables show masked
  tails only.

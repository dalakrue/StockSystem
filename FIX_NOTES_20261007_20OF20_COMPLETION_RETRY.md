# FIX NOTES — Canonical 20/20 Load Completion + Retry Failed Symbols (2026-10-07)

Base: `Forex_App_Fixed_S1_S240_MultiApiKeys__5.zip`
(`Forex_App_Updated/` with the multi-API key pool fix from 2026-10-07).

## 1. Problem reported

After the multi-API fix, the Middle Standard regime ranking table load
frequently completed with only **13–16 of the 20** canonical symbols. The user
requires:
1. **All 20 symbols load, no matter what** — the Middle Standard ranking table
   is only produced from a complete 20/20 universe, never a partial table.
2. A **🔁 Retry Failed Symbols** button at the top of Settings, beside
   ⚡ Super Quick Run — clicking it reloads only the symbols that failed the
   Twelve Data load.

## 2. Root cause

- The selector-owned loader assigns Selector 1 → Key 1 only, Selector 2 →
  Key 2 only, Selector 3 → shared pool. Each selector load runs a **single**
  scheduler round (`multi_symbol_fetch_rounds = 1`); a transient failure
  (timeout, 429, quota) in that round leaves the symbol failed.
- The built-in automatic recovery (other key → pool) also runs single rounds
  with no wait for key-credit windows, so bursty failures survive it.
- The ranking calculation then ran on whatever subset loaded (13–16 symbols),
  silently producing a partial Middle Standard ranking table.

## 3. Files changed (data-loading layer ONLY)

1. `core/multi_symbol_load_manager_20260707.py`
   - New `ensure_complete_canonical_load()`: after any explicit load, retries
     still-failed symbols through the **FULL** Twelve Data key pool
     (round-robin across every configured key), with a bounded wait for key
     credits between rounds (up to ~75s per round), stale circuit-breaker
     clearing, and up to 5 rounds. Successful rows are **never re-fetched**.
     Per-round trace stored in `state["canonical_completion_loop_trace_20261007"]`.
   - `load_all_selectors_safely(..., ensure_complete=True)` (new keyword,
     default on): runs the completion loop after the selector-owned passes.
     Pass `ensure_complete=False` to keep the old stop-at-partial behavior.
2. `tabs/antd_page_router_20260615.py`
   - Quick Actions row is now 3 columns: added **🔁 Retry Failed Symbols**
     button → sets `settings_top_retry_failed_requested_20261007`.
   - Manual ⚡ Super Quick Run is now gated: it only calculates when the
     canonical universe is complete (≥20 loaded, 0 failed); otherwise it shows
     exactly how many symbols are missing and points at the Retry button.
3. `ui/multi_symbol_settings_20260701.py`
   - Consumes the top retry flag: runs `load_all_selectors_safely(...,
     retry_failed_only=True, force_retry_failed=True)` (failed-only, then the
     completion loop drives to 20/20).
   - The automatic ranking calculation after a load is now gated: it only
     publishes the Middle Standard ranking table at 20/20. On partial loads it
     names the missing symbols and directs the user to 🔁 Retry Failed Symbols
     instead of silently publishing a 13–16 symbol table.

New: `tests/test_canonical_20of20_completion_20261007.py` — 9 tests.

## 4. Strategy engine untouched — confirmed by diff

`diff -rq` against the pristine `__4` zip shows changes ONLY in the 11
data-loading files listed above (+ 2 new test files). **Zero differences** in:
`core/live_execution.py`, `core/monthly_equations.py`,
`core/monthly_backtest.py`, `core/monthly_runtime.py`,
`core/monthly_strategy_columns.py`, `core/monthly_live_book.py`,
`core/improved_strategy_config.py`, `core/super_quick_field3_20260722.py`
(the ranking *calculation* itself is unchanged — only its trigger now
requires a complete 20/20 universe), and every other strategy/backtest/
ranking/exit/TP-SL file.

## 5. Behavior changes (what the user will see)

- Pressing **📥 Load All Selected** now ends at 20/20 (or reports exactly
  which symbols could not load after 5 pool rounds, with per-round trace).
- **🔁 Retry Failed Symbols** (top Quick Actions, beside ⚡ Super Quick Run):
  reloads only failed symbols through the full key pool, then completes to
  20/20. Existing READY rows are preserved.
- The Middle Standard ranking table is published **only at 20/20**. Partial
  states show: which symbols are missing + "press 🔁 Retry Failed Symbols".
- The per-key minute limits, 429 cooldowns, cache-first policy, and all
  provider fallback behavior are unchanged — the loop only adds *persistence*,
  never extra pressure on a single key.

## 6. Validation

### New tests — 9/9 pass
`tests/test_canonical_20of20_completion_20261007.py`: pool capacity snapshot
(usable keys / none configured); quota wait returns immediately with credits;
completion loop retries failed-only through `TWELVE_DATA_KEY_POOL` and reaches
20/20; stops after max rounds on hard failure; no-op when already complete;
`load_all_selectors_safely` runs/skips the loop via `ensure_complete`;
top-retry state-flag contract.

### Full suite — zero regressions
Same command on pristine `__4` zip vs this tree
(`pytest tests/ -q --continue-on-collection-errors`): the FAILED/ERROR test-ID
sets are **byte-identical** (69 failed + 29 errors both sides — pre-existing
environment issues such as missing `streamlit` in the test sandbox, unrelated
to this change). Passed: 73 → 92 (+19 new tests).

### Data identity
Unchanged from the `__5` fix: parallel multi-key chunk fetch is frame-identical
to sequential single-key download (same columns, UTC, sorted, deduplicated), so
backtest/live results have **0 difference**.

## 7. How to use

1. Settings → Quick Actions → **📥 Load All Selected** — loads to 20/20
   automatically (completion loop included).
2. If any symbol still shows failed, press **🔁 Retry Failed Symbols** (top,
   beside ⚡ Super Quick Run) — only failed symbols reload via the full key pool.
3. The Middle Standard ranking table appears once all 20 are READY; the
   provider board shows per-symbol status, provider, and failure reasons.

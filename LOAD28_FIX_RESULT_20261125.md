# Load-28 fix — result (2026-11-25, user order in the app-fix side chat)

User report: the app said **20 symbols loaded** in both the sidebar and the
main dashboard; he ordered it fixed to load **28**.

## What was proven first

- The fixed universe is 28 (FIRST 10 + SECOND 10 + THIRD 8) and the loader
  cap is already 28 (`MAX_CANONICAL_SYMBOLS = 28`, raised 2026-10-29).
- The repo-shipped cache snapshot (`data/cache_parts`, built 2026-11-25
  10:54 UTC) was reassembled locally and inspected: **all 28 symbols hold
  ~750 H1 bars each** (H1 21,043 / M15 82,789 / M5 50,341 rows).
- Reproduction against that exact snapshot, no Twelve key: the selector
  load admitted **28/28 from local cache in ~27 s**. So the data and the
  basic load path were never the problem — three gates around them were.

## The three defects fixed

1. **Boot restore accepted any non-empty store.** `core/data/cache_boot.py`
   treated a candle store with ANY rows as "populated", so a store holding
   only part of the universe (the 20-symbol shape) blocked the snapshot
   restore forever. Now the store is compared against the manifest's
   per-timeframe counts: below the snapshot → restore; at/above (a
   live-freshened store) → never replaced.
2. **A failed provider record masked a valid cache frame.**
   In `merge_selector_load_results` (`core/multi_symbol_load_manager_20260707.py`)
   the cache-only validation ran only when NO load record existed for a
   symbol; a failed record (e.g. a rate-limited Twelve run) kept the symbol
   failed even with a valid frame in the store. Now a valid exact-symbol
   cache frame wins over any failed record, from any selector.
3. **Auto-load demanded a Twelve Data key.** `maybe_auto_load_field3`
   (`core/auto_load_startup_20261019.py`) returned before loading whenever
   no key was configured or its pool was momentarily empty — the exact
   state of every fresh redeploy, whose in-app key vault is wiped. The key
   is now used when present but is no longer a gate: on open, the app loads
   all 28 from the local store and spends credits only on symbols the store
   cannot cover.

Also: the user-facing "only published at 20/20" ranking message and the
stale "20/20" comments now use the real symbol count
(`ui/multi_symbol_settings_20260701.py`, load manager comments).

No cycle maths, registry, check times, sizing, or signal logic changed.
The 20-symbol evaluation floor in the combined panels (a readiness floor,
not a load cap) is untouched.

## Verification (local, against the shipped snapshot)

- Merge rescue test: failed records seeded for all 8 THIRD crosses →
  merged board **28 loaded, 0 failed** (before the fix this is the 20/28
  the user saw). PASS
- Regression: plain selector load on the snapshot → **28/28 from cache**.
  PASS
- Boot restore: partial store restores; at/above-manifest store untouched;
  empty placeholder restores. PASS (3/3)
- Auto-load with **no Twelve key at all**: attempted, ok,
  **symbols = 28** (`auto_load_complete_via_local_cache_no_key`). PASS
- `py_compile` on all four changed code files. PASS

## Limits

- The live app could not be screen-verified from here (the checking
  browser is not signed into Streamlit; the app answers "no access").
  The user's open of the app is the final proof: the sidebar line should
  read **Symbols loaded: 28 / 28**.
- This push redeploys the app, so a Twelve key pasted inside the app is
  wiped again (expected; loading no longer needs it — the durable home
  for the key remains Streamlit Secrets `[api_keys] second_api`, used by
  the ranking table's fresh fetches).

# Forex App — Research Fix __9 (2026-10-09)

**Read me first.** This release adds research/backtest integrity tooling to the
app (exit registry, honest cost/ambiguity handling, validation states, replay
wrapper, cache versioning, export builders, new Streamlit page). It does **not**
change entry equations, check hours, providers, or any existing behavior.

**Rollback** is one step: delete the 13 new `*_20261009` files listed below.

## 1. Install / update

1. **Back up** your current app folder.
2. **Unzip over your existing copy** so folder structure is preserved, OR
   replace the whole folder with this archive — both work; no migration step
   is needed (all new files, nothing overwritten).
3. Start the app the usual way. The new page appears as "research_fix_20261009".

**Nothing else needs to be reconfigured.** Check hours, keys, providers and
defaults are exactly as before.

## 2. Python dependencies

**No new runtime dependencies were added.** The new modules need only what the
app already uses:

- `pandas`, `numpy` — used by the new `core/*_20261009.py` modules (registry,
  replay, metrics, drawdown, cache, exports).
- `streamlit` — **only** for the new `pages/research_fix_20261009.py` UI page.
  The page guards its import: it loads (and the rest of the app runs) even if
  streamlit is missing; the page just won't render until streamlit is present.
- `python-docx` — **only** used by the packaging script that built the release
  Word report; it is **not** needed by the app at runtime.

Dependency changes: **none** — `requirements*.txt` are untouched.

## 3. Rollback

Delete these 13 files (everything else stays as it was):

```
core/exit_registry_20261009.py
core/tpsl_price_calc_20261009.py
core/cost_model_20261009.py
core/replay_fixed_20261009.py
core/validation_states_20261009.py
core/metrics_honest_20261009.py
core/drawdown_20261009.py
core/cache_version_20261009.py
core/exports_20261009.py
config/research_fix_20261009.json
pages/research_fix_20261009.py
data/exit_registry_240.json
tests/test_research_fix_20261009.py
```

After deleting them, the app is byte-equivalent to the pre-fix copy (verified:
existing-suite failure sets were byte-identical before/after the fix).

## 4. How to run the replay + registry page

**Registry page (in the app):** open the Streamlit app and navigate to the
`research_fix_20261009` page. It shows:

- the 240-row exit registry (modes A–E, per-equation TP/SL, validation state,
  DISABLED rows with worst-6 provenance, rejected rows with reason codes);
- validation states (230 INSUFFICIENT SAMPLE / 8 RESEARCH ONLY / 2 FAILED
  DIAGNOSTIC; `Strict_Valid = NO` for all 240 — promotion is blocked until
  fresh data exists);
- config, cost model, and execution policy;
- downloads: registry CSV, active config JSON, validation manifest, trade
  ledger CSV, exit-reason glossary, performance definitions, comparison rows.

**Replay (audited historical evaluation):** the frozen path is unchanged, but
the new replay wrapper (`core/replay_fixed_20261009.py`) runs the same
entries with:

- **SL-first** intrabar priority (the app replay default is TP-first);
- explicit evaluation order per bar: open → Friday close → hold cap →
  bias/danger exits → intrabar barriers;
- per-trade recording of P/L under **both** priorities on ambiguous bars;
- censored trades kept with **unknown (empty) P/L** — never zeroed or invented;
- 1-pip cost deducted exactly once per completed trade.

Reproduction evidence (independent replay of the research "current app"
scenario, 4y data 2022-10-05→2026-10-05): original config reproduced exactly
(5,694 completed / +7,274.91 net / −1,541.75 realized DD); SL-first variant
+1,894.80; 3-pip cost variant −9,493.20. Every row is labelled
"REUSED-TEST DIAGNOSTIC ONLY" — the last year of data is reused, not unseen.

## 5. What changed vs what didn't

**Changed (additive only):** SL-first default for evaluation, one central cost
model, the 240-equation exit registry (modes A–E), one shared target-price
function, honest unknown-outcome handling, validation states, honest
Sharpe/Kelly, realized + floating drawdown reporting, cache versioning,
frequency experiments kept as **config only** (never auto-promoted), new UI
page + export builders.

**NOT changed:** S1–S240 entry equations, strategy ranking, the six check
hours (06:30/07:30/10:30/11:30/12:30/13:30 UTC), data providers, API-key
pool, 20/20 completion retry, or any live default.

**Known limits:** the ranking/Strategy-Decision/Finder table columns were not
patched (the new page carries that display instead); `build_validation_manifest()`
returns "pending — no fresh data"; legacy mode-B `k_tp` lookup uses the UTC
month of the check (documented, not reinterpreted). See
`CHANGELOG_20261009.md` and `FIX_VERIFICATION_20261009.md` for the full
honest accounting.

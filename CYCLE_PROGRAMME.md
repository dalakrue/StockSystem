# CYCLE PROGRAMME — the 12 month cycles

How the 12 month cycles calculate, how their memory is built, what
tests are used, and the verification, validation and replacement
rules. Written 2026-11-28 from the code at commit `b0f8e00`
(`core/signal_mode.py`, the `core/cycle*_best.py` modules,
`core/twelve_memory_section.py`, `core/replay_section.py`,
`core/data/github_saveback.py`, `SIGNAL_LAW.md`).

## 1. The 12 cycles

The registry is `MONTH_SYSTEMS` in `core/signal_mode.py`. Check
slots are Mon–Fri at HH:30 UTC, three per day, at the module's own
`*_CHECK_HOURS`.

| Month | System | Module | Check hours (UTC) |
|---|---|---|---|
| Jan | cycle60k | `core/cycle60k_best.py` | 11, 13, 17 |
| Feb | cycle85s | `core/cycle85s_best.py` | 11, 13, 16 |
| Mar | cycle86o | `core/cycle86o_best.py` | 11, 16, 17 |
| Apr | cycle87p | `core/cycle87p_best.py` | 16, 17, 18 |
| May | cycle88t | `core/cycle88t_best.py` | 0, 16, 18 |
| Jun | cycle89x | `core/cycle89x_best.py` | 1, 15, 18 |
| Jul | cycle78m | `core/cycle78m_best.py` | 15, 17, 18 |
| Aug | cycle67w | `core/cycle67w_best.py` | 1, 16, 17 |
| Sep | cycle91z | `core/cycle91z_best.py` | 1, 11, 18 |
| Oct | cycle92l | `core/cycle92l_best.py` | 15, 17, 18 |
| Nov | cycle93aj | `core/cycle93aj_best.py` | 13, 15, 17 |
| Dec | cycle94t | `core/cycle94t_best.py` | 11, 13, 14 |

## 2. How a cycle calculates

All 12 modules expose the same walker API: `_state()`, `_Form`,
`load_state_form`, `panel_entries`, and `SYMBOLS` (28 symbols).
Eleven also expose a module-level `_STATE`; `cycle87p` does not.

- **Stateful full-way walk.** A month's memory is the cycle's
  state stepped through every check slot in order, Mon–Fri at
  HH:30 UTC. The state is saved after every slot, so a walk
  resumes from its state file and never restarts from slot 1.
  Slots are a memory chain: they cannot be reordered or skipped.
- **Slot timing.** For a check at time T: the signal candle
  closes at T − 30 min, the entry is at T − 30 min, and the M15
  entry bar is the one at T − 15 min. In bar-open terms the
  signal bar opens at T − 1:30 and the entry bar at T − 0:30.
- **The 28/28 gate.** A slot is evaluated only when its data is
  ready for all 28 symbols. Anything less is **DATA ERROR** —
  never NOSIGNAL, never a guessed signal.
- **Precheck.** A precheck is an evaluation on a snapshot clone
  of the walker's in-progress state, with frames cut at the
  signal close (T − 30 min) and the entry candle synthesized.
  It is read at check − 30 and check − 10 and is **never written
  to memory**. Only the check step itself advances the state.
- **Holiday slots.** A slot whose candles do not exist because
  the market was closed (proof: zero H1 rows at signal + entry
  for all symbols, and rows exist after the entry stamp) is
  recorded DATA ERROR and skipped; the walk proceeds from the
  next trading day. Any other shortfall still fails loudly.

## 3. The Signal Law

From `SIGNAL_LAW.md` (user order, 2026-11-23):

1. The main cycle for the current month in this app, together
   with its main memory, is the only source of precheck and
   check signals.
2. The main memory is the cycle's state walked in order from
   the month start, every check slot stepped — the full way.
   A memory with skipped slots is not the main memory.
3. The memory file (`data/walk_ledgers_new8/`) must live in
   this repo, so the app never restarts from empty memory.
4. The app must never show a stale chain feed as current; when
   the feed is stale, the app calculates itself.
5. The same cycle + verified memory is held locally by Muse;
   each check then needs only that check's fresh candles.

## 4. Memory kinds and where they live

- **Live ledgers** — `data/walk_ledgers_new8/<cycle>.json`: the
  current walked state per cycle. At the commit above this
  folder holds 11 ledgers (Jan–Nov); December's `cycle94t`
  ledger is not present.
- **Historical archive** — `data/walk_ledgers_hist/<cycle>_<year>.json`:
  walked month-year memories for past years. At the commit
  above: 110 files plus `index.json`.
- **True-precheck files** — `data/precheck_true/`: the 12
  Novembers' true-precheck results (`precheck_true_nov<year>.json`),
  the 12 walked November states (`walked_nov<year>_cycle93aj.json`)
  and `index.json`.
- **Build progress records** — `data/twelve_memory_progress/<cycle>_<year>.json`:
  the Memory Building section's resumable work record (path
  defined in `core/twelve_memory_section.py`; no record is
  present in the repo at the commit above).
- **App boot cache** — the app-format candle snapshot
  (`cache_parts/`, 859,808 rows) lives in the separate repo
  **dalakrue/fx-data**; `core/data/cache_boot.py` downloads it
  from there on boot when no local copy exists (moved out of
  this repo 2026-11-28, ~157 MB of tree data).
- **Candle data sources** — the Dukascopy 10-year set (28
  symbols, H1/M15/M30/M5, from 2015-01-01) and Twelve Data.
  Every Twelve Data request in this codebase passes
  `timezone=UTC` (`core/replay_section.py`); Twelve bars carry
  provider `TWELVE_DATA` and are never silently mixed with
  Dukascopy bars.

## 5. The build process

**Local full-way builds** (one month-year at a time):

1. Build the unit's own candle store for the window starting
   day 10 of the previous month (H1/M15 from the Dukascopy
   10-year database, M5 from the Set B CSVs).
2. Phase A: walk slots through day 19. Phase B: extend the
   store to the last slot's day and walk to the final slot.
   The true precheck is evaluated before each step (section 2).
3. Assemble the results file, verify processed + skipped ==
   the calendar slot count, and write the completion marker.
   The unit's candle store is kept — it is that month-year's
   cache.

**The app's Twelve Data API Memory Building section**
(`core/twelve_memory_section.py`):

- Downloads the month (H1/M15/M5, 28 symbols + lead-in) from
  the Twelve Data API only, paced under the plan's per-minute
  credit limit, and walks the month's own cycle over it.
- The walk runs on a **throwaway state file in a temp
  directory, started empty**; the app's live ledgers are never
  touched.
- A slot with a data hole is healed first (one fresh Twelve
  re-fetch, then M5→M15 assembly); a slot that still cannot be
  completed is recorded DATA ERROR with its reason and the
  walk **continues in order**. A run finishes only at 100% of
  slots processed (walked + healed + recorded).
- Progress is saved to the progress record (locally and via
  GitHub save-back) as the build goes; the **↻ Recalculate**
  button resumes from it without re-walking finished slots.
- On completion the built state is saved to the historical
  archive **only if that month-year is absent there** (see
  section 10), and the result is downloadable as XLSX
  (Summary / Picks / Slots / Compare).

## 6. Progress — snapshot, 2026-11-28

*This section is a dated snapshot, not a live status.*

- **November true prechecks: complete, 12 of 12 years**
  (2015–2026): 759 slots walked, 641 precheck picks, 118
  no-pick, 147 differing from the check pick
  (`data/precheck_true/index.json`).
- **In this repo:** the 110-file historical archive and the 11
  live ledgers (section 4).
- **Other-months local builds: PAUSED at the user's order**
  (2026-11-28, for the Twelve Data download below). Frozen
  mid-unit: Jan 2024 at 28/45 phase-A slots, Dec 2020 at
  15/42, Dec 2025 at 20/45. No batch unit has a completion
  marker yet. They restart only on the user's explicit order.
- **Twelve Data 5-year download: in progress** — 28 symbols ×
  H1/M15/M5, 2021-01-01 → 2026-11-28, keys rotated, into a
  local database (`fx_data_twelve_5y.db`).

## 7. Tests used

The app changes of 2026-11-27/28 were proven offline (network
stubbed, real store candles) by test scripts held with the
work records; each fails on the defect it guards:

- `test_check_fallback.py` — the check route's Twelve fallback:
  with Dukascopy stubbed to HTTP 503, the 28/28 gate is met
  from fallback bars and the read is labelled fallback.
- `test_twelve_memory_eurusd_gap.py` — Memory Building hole
  healing: a planted EURUSD M15 hole in Nov 2025 heals by
  re-fetch / M5 assembly and the build completes 60/60; a
  permanent hole is recorded, never shown as 100%.
- `test_manual_calculate.py` — sections 1/2 manual Calculate:
  returns the walked pick for the test slot (GBPCHF BUY
  @1.09614) with the compare-with-memory block.
- `test_history_saveback.py` — the precheck day log and the
  eval-history DB push to GitHub and restore exactly on a
  simulated fresh boot.
- `test_persistent_memory_wiring.py` — the persistent-memory
  backbone across all five sections, including Replay's
  historical-archive compare fallback and the dormant
  Finnhub/OpenRouter layer's safe no-op behaviour.
- `test_store_loaded_ohlc.py` — bars loaded from Twelve are
  persisted into the app candle store with INSERT OR IGNORE:
  a pre-existing Dukascopy bar survives, a repeat load inserts
  nothing.
- `test_signal_tpsl_teststatus.py` — every displayed signal
  carries TP/SL and its full-way test verdict; a DATA ERROR
  evaluation records FAIL with its reason.
- `test_replay_twelve.py` — the Twelve-route Replay end to end
  (loader, gates, stateless evaluation, compare-to-past) on
  stubbed Twelve wire format serving real candles.

This repo also carries its own `tests/` folder (25 test files
plus fixtures) from the app's earlier build generations, e.g.
`test_monthly_equations_integration.py`,
`test_check_candle_runtime_20261027.py` and the
`test_raw_ohlc_*` series for the raw-OHLC exports.

## 8. Verification

- **Readiness gates** — every evaluation reports its symbol
  count; only 28/28 evaluates (section 2).
- **Hash-verified transfers** — cache restores are verified
  against the snapshot manifest's sha256 and row counts
  (859,808 rows exact on the fx-data restore test); state
  syncs between working trees are sha256-verified identical;
  the 88-ledger upload of 2026-11-27 was md5-verified 88/88
  on pull.
- **Compare-vs-past** — every build and Replay result is
  compared against the stored past for the same slots and
  reports match / differ counts and a similarity %.
- **DATA ERROR discipline** — an unverifiable slot is
  reported as DATA ERROR with its cause, never replaced by an
  estimate.

## 9. Validation

- **Full-way test before live checks** — at check − 35 min the
  whole signal chain (month cycle + system functions +
  calculation functions) is run end to end; signals are given
  only if it passes, and a failure is reported before the
  check.
- **Gates are locked before a run and never moved after
  results.** A later instruction that conflicts with a locked
  gate stops the run until the user rules which stands.
- **Option B (user decision, 2026-11-26)** — for November the
  gate is data completeness + full-way walk, and the replay
  memory is the reference; the canonical feed is retired as
  November's reference (kept on disk, untouched).

## 10. Replacement rules

- **Historical archive files are written only if absent,
  never overwritten** (`saveback_new_bytes` in
  `core/data/github_saveback.py` returns "exists" and leaves
  the repo file untouched).
- **Candle inserts are INSERT OR IGNORE** — existing bars
  always win. Where both exist, Dukascopy wins over Twelve
  fallback; fallback and M5-assembled bars are always labelled
  as such wherever they are used.
- **Progress records are the one overwritable work record** —
  they exist to be resumed from, and are marked `complete` at
  100%.
- **The Memory Building section never touches the app's live
  ledgers** — it walks a throwaway state and publishes only
  through the only-if-absent archive save.
- **No repo push without the user present** — a push restarts
  the app and wipes any key pasted in-app; keys belong in
  Streamlit Secrets.

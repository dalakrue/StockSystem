# FIX NOTES 2026-10-26 — BRIEF21 (Nov/Dec/Apr C20a) + BRIEF23 (January C20_STACK) app integration

This build removes the two blockers recorded in
`FIX_NOTES_20261026_BRIEF21_INTEGRATION.md` (research folder):
(1) the app had no memory of closed trades, which the C16
re-entry partner is defined on; (2) Nov/Dec's vol veto needs a
384-bar M15 tick-volume window the old live path did not
supply. It also integrates the BRIEF23 January winner
C20_STACK, and fixes the check-time signal delay (see
"Check-time freshness fix" below). Every integration is gated
on an EXACT replay through the app code path against the
validated research ledgers; nothing was approximated.

## User orders applied in this build

- 2026-10-26 ~15:16 MMT (promotion/fallback): for each of
  Nov/Dec/Apr passing exact replay — the new C20a system
  becomes the month's BEST (MONTH_SYSTEMS), and the OLD
  incumbent becomes that month's SECOND priority in the
  combined layer (MONTH_SECOND_BEST[11]=cycle93,
  [12]=cycle94, [4]=cycle87). December special case: cycle274
  stays in the tree as a selectable standalone system (module
  and panel untouched), but December's combined fallback is
  the OLD cycle94, not cycle274. All three months passed, so
  all three applications are in force.
- 2026-10-26 ~16:34 MMT (January joins): BRIEF23 January
  C20_STACK integrated under the same gate; on EXACT,
  MONTH_SYSTEMS[1]=cycle60b and MONTH_SECOND_BEST[1]=cycle60.
  January passed (one documented data-artifact exception,
  below), so the application is in force.
- Standing rules kept: Best N divided by 3 (previous package);
  incumbent modules byte-identical (verified by diff against
  the shipped 2026-10-26 package); no git/GitHub; live signal
  crons untouched.

## What was built

### The stateful walk layer — core/walk_ledger.py

`WalkLedger`: a persisted pick ledger (JSON under
`data/walk_ledgers/<system>.json`). It records picks (check,
symbol, direction + direction stamp, strategy/equation, score,
entry, TP, SL, kind base/dual/reentry) and their simulated
exits (exit_time, exit_reason TP/SL/TIME, exit price, hold_h,
gross pips), and exposes exactly what the re-entry rule needs
at a check: closed trades with exit reasons/times
(`tp_exits()`), full-interval occupancy (`open_symbols_at`,
`live_positions_at`, `symbol_intervals`, `interval_free`).
Exit simulation from M15 frames is research-exact
(`simulate_m15_exit`: gap-through at the open, SL before TP
inside a bar, TIME exit at the capped bar's close; exit_time
is the hour floor of the exit bar start; hold cap 191 M15
bars = 48h). `vol_z_at` implements the C06 statistic exactly
(causal M15 bars strictly before the entry bar, last 1600;
4-bar volume rolling sums over the last 384; z = (last −
median)/IQR; needs ≥387 bars). Batch `reentry_legs` (research
replay) and streaming `due_reentry_legs` / `settle_panel_check`
(live panels) implement C16 identically: triggers are base/
dual TP exits in exit-time order; a leg is placed at the first
grid check strictly after the trigger's exit AND strictly
after the trigger's own check; the candidate is the pool row
for (leg check, trigger symbol) — Nov rule 'max_score',
Dec/Apr rule 'first' (walk order); the leg's full flight
interval must conflict with no recorded interval. Zero-length
flights (exit_time == entry time) never block, so duplicate
legs at one check reproduce (e.g. Dec 2016-12-02 13:30 AUDNZD
×2 in the validated ledger).

### New system modules

- `core/cycle93b_best.py` — November C20a = C93-24 + C06
  vol-shock veto (vol_z > 1.498145894075274, the exact FIT-90th
  percentile) + C16 re-entry (ledger). Panel path =
  `panel_entries` (base pick + ledger-settled legs).
- `core/cycle94b_best.py` — December C20a = C94-23 + C06 veto
  (threshold 1.123626798751949) + C16 re-entry (ledger).
- `core/cycle87b_best.py` — April C20a = C87-24 + C12
  score-gated dual-pick + C16 re-entry (ledger).
  The dual pick replicates `apr_walk` + `sf_score` exactly:
  candidates in reranked walk order; dual = first remaining
  candidate with eq score ≥ 1000.3404785714285 (median
  positive pool score), blocked when ≥3 positions are live
  after the primary. "Live after" is outcome-aware: a primary
  whose exit_time equals its entry time (TP inside the entry
  bar) is not live after and does not block its own symbol,
  so the dual can be a second variant of the primary's
  symbol — this is the rule the first integration attempt
  missed (see April verdict).
- `core/cycle60b_best.py` — January C20_STACK = C60-03 + C10
  (FB breadth veto breadth_m15 > 0.4; FB SL ×0.60; conditional
  24h stall cut on FB trades with pat_score > 0 — an exit rule
  carried on the pick via its pat_score) + C17 score-gated
  dual-pick (score ≥ 971.8205553571429, the exact median
  positive eq score; cap 5 live). No ledger state needed.

Router (`core/signal_mode.py`): the four systems are
registered (set/describe/evaluate/select/check-hours);
MONTH_SYSTEMS[1]=cycle60b, [4]=cycle87b, [11]=cycle93b,
[12]=cycle94b; MONTH_SECOND_BEST = {1: cycle60, 4: cycle87,
9: cycle287, 11: cycle93, 12: cycle94}; Best N (full / ÷3):
60b 83 / 27.666666666666668 (the incumbent's values — no
winner-specific Best N was recorded for C20_STACK), 87b
104 / 34.666666666666664, 93b 83 / 27.666666666666668, 94b
105 / 35.0. The combined layer routes the three ledger
systems through their `panel_entries`. UI: standalone panels
for the four improved systems and COMBINED panels for
January, April, November (December's updated), all appended
at the END of _MONTH_PANEL_ORDER — the original 12 positions
never shift; panel text states the priority order plainly.

## Per-month verdicts (exact-replay gate)

Replay = the app code path (new module + walk ledger) driven
check-by-check over DISC 2016–2023 + AUDIT 2024+2025 on the
research data, compared with the validated C20a / C20_STACK
ledgers: pick keys identical, entry/TP/SL within float
tolerance, segment stats (n / net / leftover @2.5) reproduced.

- **November C20a: INTEGRATED-EXACT.** 536 picks (446 base +
  90 re-entry legs; DISC 436 + AUDIT 100); every key
  (check/symbol/direction/strategy/exit_reason/exit_time)
  identical; entry/exit price max diff 0.0; TP/SL diffs
  ≤ 2.9e-14; DISC net 5128.59 leftover 69.12, AUDIT net
  678.37 leftover 46.39 — reproduced.
- **December C20a: INTEGRATED-EXACT.** 807 picks (620 base +
  187 legs); DISC 650 keys equal, AUDIT 157 keys equal
  (direction compared on the research 'TREND' stamp); entry
  diff 0.0, TP/SL ≤ 1.4e-14; DISC net 4479.75 leftover 66.20,
  AUDIT net 1135.57 leftover 75.39 — reproduced.
- **April C20a: INTEGRATED-EXACT** (after the user's one
  bounded fix attempt). First attempt diverged (DISC app 661
  vs 710): the dual-pick rule was wrong — it required a
  different symbol (October precedent). Probe at the first
  divergence (2016-04-01 18:30) proved the candidate ORDER
  was already exact (engine emission order == pool group
  order, ties included; base pick agreed); the research dual
  is the same-symbol variant 0.3x5.0 because the primary's
  exit_time == its entry time. cycle87b was rebuilt with the
  exact outcome-aware rule and the full replay re-run: base
  690 + legs 207 = 897 picks; DISC n710 keys equal, entry
  diff 0.0, TP/SL ≤ 2.9e-14, net 6033.02 leftover 84.47;
  AUDIT n187 keys equal, net 1971.36 leftover 79.06;
  missing_pool none.
- **January C20_STACK: INTEGRATED-EXACT, with one documented
  data-artifact exception.** 456 picks (DISC 355 + AUDIT
  101, the validated counts; missing_pool 0 in every year).
  Keys, direction stamps, exit reasons/times, hold_h all
  identical; entry/exit diffs 0.0; DISC net 1984.54 win
  95.21%, AUDIT net 550.18 win 96.04% — identical (published
  leftover 64.23 / 67.50 is computed on the sized path from
  the ledger itself, reproduced row-for-row). EXCEPTION:
  one row's sl_pips_used differs — AUDIT 2024-01-26 17:30
  AUDNZD mom_AUDNZD_h17_momS_T1.0_A1.0_0.75x5 (a dual pick):
  app 37.0 vs ledger 34.321429. Proven cause: SL = 5.0 ×
  atr14; the research frame builder (c52_engine, on the raw
  H1 CSV) forward-fills a single missing H1 candle with a
  flat bar — the raw CSV lacks AUDNZD 2024-01-26 15:00, so a
  flat bar sits inside the 14-bar ATR window and the research
  atr14 is 6.8642857 (recomputed exactly from the CSV + fill
  rule) vs 7.4 on any frame containing the real bar. The
  current verified database contains the real bar, so the
  app computes 7.4. Same formula, same system; the pick,
  entry, TP, exit and net are identical.

## Live-feed requirement (November / December veto) — read this

The C06 veto needs vol_z from **at least 387 causal M15 bars
per candidate symbol, including volume** (Dukascopy tick
volume in the research). The improved modules accept the M15
frames as an input (they do not fall back to a ≤200-bar live
fetch for the veto). **If the M15 history provided at a check
is insufficient, the improved system returns NO entries for
that check** and marks its output frame with a status
('insufficient_m15_history…') — it never silently computes a
wrong vol_z and never falls back to an un-vetoed pick: an
un-vetoed pick would be a different system than the one that
was validated. Live use of the November/December improved
systems therefore needs an M15 feed with ≥387 bars incl.
volume per symbol (the panels fetch through the shared
cycle78 path, which serves the repository/provider frames;
the same rule applies there). January's breadth veto follows
the same discipline for FB picks only: if breadth cannot be
computed from the provided 20-symbol M15 set, cycle60b
returns NO FB picks for that check (non-FB picks unaffected)
and marks the status — never an un-vetoed FB pick.

Live caveat for the re-entry legs (Nov/Dec/Apr): legs finalize
from the picks recorded in the ledger so far — a leg appears
only once its trigger trade's exit has been simulated from
arrived bars, and the ledger must be carried forward panel
session to panel session (it persists under
data/walk_ledgers/). A fresh ledger started mid-stream can
only produce legs for triggers recorded after it started.

## Check-time freshness fix (user order 2026-10-26 ~15:46 MMT)

Symptom: signals appeared ~5 minutes after the check time.
Cause: the engine needs the entry candle (the candle starting
at the check hour H:00; it uses only its open). A data cache
with up to a 5-minute lifetime could serve frames fetched
minutes earlier that did not yet contain the H:00 candle, so
at H:00 the panel showed nothing; the signal appeared only
when the cache expired (~H:05). The calculation itself needs
none of those 5 minutes.

Changes (data-freshness behaviour only — no signal
calculation, equation, threshold or selection changed; the
2026-10-19 completed_only=False entry-candle semantics are
kept):
1. `core/connectors/data_parts/fetchers.py` —
   `_read_twelve_cache` fresh-only guard: for intervals
   ≤ 14400 s, if the cached frame's newest candle is older
   than the current bar's open, the cache read is a MISS
   (→ immediate live fetch) instead of serving the stale
   frame until TTL expiry. Self-healing: a still-lagging
   fresh fetch keeps missing the guard, so the next
   evaluation refetches instead of locking in for 300 s.
2. UI `_fetch_c22_frames` (the shared frame fetch for the
   signal panels): the missing-candle refresh trigger changed
   from "≥4 symbols missing" to ANY symbol missing the needed
   candles, and that refresh now forces a live fetch
   (force_live=True).
3. `core/cycle78_best.py` — the shared M15 memo is served
   only when it contains the last completed M15 bar
   (`m15_frames_current` helper); otherwise it refetches.
   (cycle78_best.py is the one incumbent-adjacent file edited,
   and only in its fetch layer — its evaluate/select are
   untouched. The incumbent modules' own private M15 memos
   were NOT touched — they stay byte-identical; their gates
   fail safe on stale data: a missing feature means no veto,
   never a wrong trade.)

Test proof (test_freshness.py, all PASS): A1 stale pickle
cache (fresh mtime, no current candle) is bypassed; A2 a
cache containing the current candle is served (fast path);
B1 a stub repository with exactly ONE stale symbol triggers a
force-live provider fetch for that symbol; B2 the refreshed
frame contains the entry candle; B3 an entry is produced at
the check (the recorded AUDUSD pick); B4 fast path — complete
cache → provider NOT called; B5/C1 bypass-path signals are
identical to signals computed directly from the full frames
(the fix changes no values).

## Notes

- Incumbent modules cycle87/93/94_best.py, their engines
  (cycle63/70/71) and cycle60_best.py are byte-identical to
  the shipped 2026-10-26 package (diff-verified). The
  improved systems reuse the incumbent engines; the exact
  replays above exercise those engines end-to-end.
- The walk ledgers used by the replay harnesses live outside
  the package (research area); the app creates its own under
  data/walk_ledgers/ on first panel use.
- Header note for the record: during this build, the
  work_combined26 source tree's cycle60_best.py was modified
  by a parallel process (an in-place BRIEF23 edit with
  different fallback semantics). This package deliberately
  does NOT contain that edit: this tree is byte-identical to
  the shipped package for every incumbent, and January is
  integrated as the separate cycle60b module exactly as
  ordered (no un-vetoed FB fallback anywhere).

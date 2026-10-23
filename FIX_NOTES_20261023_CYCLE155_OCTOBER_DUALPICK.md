# Fix notes — Cycle 155 (2026-10-23): October dual-pick integrated

User order 2026-10-23: integrate October's VALIDATED dual-pick
(Cycle 155) into the app and upload. OCTOBER ONLY — no other
month's code or behaviour changes.

## 1. What was validated (research record: fx/work_c155)

Candidate = Cycle 152 dual-pick mechanism on the standing
October system C92-24: after the primary pick, take the
walk-ranked second candidate when it is NON-FB, its symbol is
free, and fewer than 3 positions are open (gate 'nonfb',
concurrency cap K=3, full-lot ladder under Best N 83).
Verdict: VALIDATED at the middle standard — EC22-middle
17/18 vs control 15/18; corrected LCT-middle PASS (paired
P 89.23%, own q05 78.80%); audit (2025, unseen) leftover
67.84% vs 62.78%, win 94.74%, 2.478 entries/day; chain
median final 123.89x control; red lines intact.
DISCLOSED with the verdict: chain P(margin call) 36.24% vs
control 8.76%, chain median peak margin 96.28% vs 84.34% —
the candidate grows far faster and runs far hotter; the
user accepted that trade explicitly (and waived the screen
sizing point, discovery path peak margin 60.02% vs the 60%
limit). October's research selection is now this system.

## 2. Changes in this push

- core/cycle92_best.py — select_cycle92_entries now returns
  the primary (frozen C69-07 selection, delegated unchanged)
  PLUS the dual-pick second entry when it fires. New optional
  kwarg open_count (caller's open-position count; default =
  number of distinct open_symbols). New constant
  CYCLE92_DUALPICK_CAP = 3. evaluate_cycle92_signals is
  untouched; the primary path is byte-identical in behaviour.
- core/signal_mode.py — October (cycle92) describe string
  only: now states the dual-pick and its validation numbers.
  Router logic, other months' strings: untouched.
- ui/field3_multisymbol_regime_summary_20260722.py —
  October panel section comment + two October docstrings
  only (text now states primary + dual-pick second). No code
  lines changed in this file; the panel already renders
  multi-row entry frames and calls
  select_cycle92_entries(sig, open_symbols=()).
- This file (new).

## 3. Definition mapping (research walk -> app)

- Candidate pool at a check = evaluate_cycle92_signals rows
  (one per firing C92 equation). Ranking = score descending,
  stable mergesort — identical to the research frame order
  (verified score-descending within all 455 discovery
  checks) and to the existing app selection order.
- 'non-FB' = equation id NOT starting with 'FB_' (research:
  is_fb == strategy.startswith('FB_'), identical test).
- Primary = the frozen top-1 selection (delegated to
  select_cycle69_entries, unchanged).
- Symbol free = not in the caller's open_symbols and not the
  primary's symbol (see deviation for the one refinement the
  research walk applies and the app cannot).
- Cap: second pick only while open positions incl. the
  primary < 3. The app selection API's occupancy input is
  open_symbols; this system never holds two positions on
  one symbol, so the count is len(distinct open symbols)
  unless the caller passes open_count explicitly.
- Sizing: app entry rows carry no lot field; the lot ladder
  is per-system (Best N 83) applied downstream, so the
  second entry — a full entry row — is sized on the same
  ladder as the primary by construction (research likewise
  applies N=83 to every taken trade).

## 4. DOCUMENTED DEVIATION (closest faithful version)

The research walk (work_c152 walk_dual) is sequential: it
prunes open positions by SIMULATED exit times (M15 fill
engine) as it walks checks, and — within a check — it
re-frees the primary's symbol for the second pick whenever
the primary's simulated exit stamp is at/before the entry
moment (fast exits inside the entry bar: the primary is
already gone when the second would enter). The app
evaluates one check at a time, keeps no exit-simulation
state, and evaluates live INSIDE the entry window — before
the entry bar completes, so that information does not
exist yet. The app therefore (a) enforces occupancy/cap
against the open state the caller supplies (panels supply
none today — the same limitation the frozen primary
occupancy has always had in the panels; live occupancy is
applied by the user at order time), and (b) always treats
the primary's symbol as occupied for the second pick.

Measured impact on the research frame (replay, section 5):
primaries identical on both frames; audit second picks
identical 9/9; discovery second picks identical 75/95 — the
20 differing ones are ALL the same-symbol fast-exit form
above (the app takes the next different-symbol second at 8
of those checks, none at 12). Any caller that supplies real
open state gets the full cap/occupancy rule as implemented
in select_cycle92_entries.

Out of scope, verified unchanged: the live signal cron
adapter (fx/live_trader/signals92.py) calls only
evaluate_cycle92_signals and never select_cycle92_entries;
its behaviour is unaffected by this push.

## 5. Verification (app code, Dukascopy H1 frames, research
##    ledgers as ground truth; state driven by each ledger's
##    own exit times exactly as the research walk evolves it)

- Control (pre-change code): discovery 444/444 picks,
  audit 48/48 picks, 0 selection mismatches, 0 signal-set
  mismatches over all 455 + 51 frame checks — the standing
  C92-24 reproduction re-confirmed before any edit.
- Candidate (post-change code): audit 57/57 picks exact
  (48 checks with picks, 0 mismatches). Discovery:
  primaries 444/444; second picks 75/95 identical + 8
  different-symbol substitutes + 12 not taken — every one
  of the 20 differing checks is the documented same-symbol
  fast-exit class (verified: an in-process copy of
  walk_dual reproduces the candidate ledgers sequence-
  exactly, 539 + 57, and all 20 research same-symbol
  seconds have primary exit_time <= entry moment).
- November spot-check (untouched path): all 60 weekday
  checks of Nov 2025 replayed through core/cycle93_best —
  52/52 picks identical to the standing control log.
- Router smoke: all 12 systems set/describe/Best-N OK;
  cycle92 via the router returns primary + second;
  cycle93 returns top-1 only. All edited files compile.

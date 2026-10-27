# Fix notes — Combined Best + Second-Best layer & Best N ÷ 3 (2026-10-26)

User order 2026-10-26 ~14:59–15:02 MMT: change the StockSystem
12-month system so that every month combines its BEST cycle with
its SECOND-BEST cycle — best has priority at check time, and the
second best is shown only when the best cycle cannot meet its
entry condition at that check time and the second best can; also
update the Best N position sizing to N divided by 3 (as simulated
2026-10-25); integrate/migrate cleanly with UI/UX and in-app text;
deliver as a ZIP (the user uploads it himself — nothing was pushed
to GitHub for this package).

## 1. The combined rule (exact)

At any check time, for the month in question:

1. The month's BEST cycle (MONTH_SYSTEMS[month]) is evaluated and
   selected first. If it produces an entry, that entry is shown,
   tagged **BEST**. The second-best cycle is NOT evaluated.
2. ONLY when the best cycle produces NO entry at that check time
   is the month's SECOND-BEST cycle evaluated; if it produces an
   entry, that entry is shown, tagged **SECOND BEST**.
3. If both produce nothing, nothing is shown for that check.
4. Months without an in-app second-best module run best-only
   under the same priority rule (see §4).

Implementation: `core/signal_mode.py` gains
`evaluate_combined_entries(month, frames, check_time_utc,
open_symbols=()) -> (entries_df, source)` plus
`month_combined_info(month)`. It activates each system through
the router's existing global-state pattern and always restores
the caller's active system (try/finally). Returned rows carry
`source_system` and `is_second_best` columns.

## 2. Best N ÷ 3 (position sizing)

`core/signal_mode.py`: `SYSTEM_BEST_N` now holds the divided
values — the exact values of the verified 2026-10-25 div3
prediction simulation. The original values are preserved in the
new `SYSTEM_BEST_N_FULL` (helper `best_n_full_for_system()`).

| Month | System | Full N | N ÷ 3 (active) |
|---|---|---:|---:|
| Jan | cycle60 (C60-03) | 83 | 27.666666666666668 |
| Feb | cycle85 (C85-23) | 104 | 34.666666666666664 |
| Mar | cycle86 (C86-24) | 86 | 28.666666666666668 |
| Apr | cycle87 (C87-24) | 104 | 34.666666666666664 |
| May | cycle88 (C88-03) | 66 | 22.0 |
| Jun | cycle89 (C89-21) | 84 | 28.0 |
| Jul | cycle78 (C78-34) | 103 | 34.333333333333336 |
| Aug | cycle67 (C67-04) | 121 | 40.333333333333336 |
| Sep | cycle91 (C91-15) | 83 | 27.666666666666668 |
| Oct | cycle92 (C92-24) | 83 | 27.666666666666668 |
| Nov | cycle93 (C93-24) | 83 | 27.666666666666668 |
| Dec | cycle94 (C94-23) | 105 | 35.0 |
| Sep 2nd | cycle287 (C287) | 83 | 27.666666666666668 |
| Dec 2nd | cycle274 (C274) | 105 | 35.0 |

Consumers checked by grep across the tree: the only readers of
`best_n_for_system` are the two display spots in
`ui/field3_multisymbol_regime_summary_20260722.py`
(`_best_n_label` and the entry-window banner), which formatted
the value with `str(n)`. Both now format the float Best N with 2
decimals (e.g. "22.00", "27.67", "40.33"). No other code reads
SYSTEM_BEST_N, and nothing casts Best N to int.

## 3. UI/UX + in-app text

`ui/field3_multisymbol_regime_summary_20260722.py`:

- Two new panels APPENDED at the end of `_MONTH_PANEL_ORDER`
  (positions 15–16; the original 12 month positions and the two
  second-best positions never shift — the reminders list is
  month-indexed by position and verified unchanged):
  - "September COMBINED (Best first, Second-Best only when Best
    is silent)" — system id `cycle91combined`
  - "December COMBINED (Best first, Second-Best only when Best
    is silent)" — system id `cycle94combined`
  Both are registered in `_SIGNAL_PANELS` with their own session
  state / age / diag / fail keys and CSV+Excel download buttons,
  and evaluate through `evaluate_combined_entries`.
- Combined picks are visibly labelled: the signals table carries
  a **Source** column ("BEST" / "SECOND BEST"), the Quick-look
  string is prefixed with the source, and a banner line under the
  header states either "🟢 BEST pick — shown from the Best
  system…" or "🟠 SECOND BEST pick — the Best system had NO
  entry at this check, so the Second-Best system pick is shown."
- An info text with the combined rule and the per-month status
  (COMBINED_RULE_TEXT) is shown at the top of the signal panels
  area on every panel, and inside each combined panel.
- The system selector handles the combined ids without touching
  the router default: choosing a combined panel keeps the
  router's active system on that month's BEST system (so the
  banner and check hours stay the best system's) while the panel
  itself applies the combined rule.
- Every incumbent panel, label and default is exactly as before.

## 4. Integrated vs recorded-only — and why

Integrated in app code (exact, replay-verified in earlier rounds):
- All 12 incumbent BEST systems — unchanged.
- September second best: cycle287 (C287 stack).
- December second best: cycle274 (C274 stack).
  (Both integrated 2026-10-25 under the user's chain+DSR waiver;
  see FIX_NOTES_20261025_WAIVER_INTEGRATION.md.)

Recorded-only in `research/combined_20261026/` (NOT integrated,
nothing approximated into code):
- Today's BRIEF21 winners — Nov/Dec/Apr C20a VALIDATED-HUGE —
  blocked for exact app integration: their re-entry partner is
  defined on the base walk's closed-trade ledger (no such state
  in the stateless panels) and Nov/Dec's veto needs Dukascopy
  tick volume over 384 M15 bars (the app's live M15 path is
  ≤200 bars). Proof: FIX_NOTES_20261026_BRIEF21_INTEGRATION.md,
  ROUND_CLOSE_BRIEF21.md.
- Today's BRIEF22 Plan B verdicts: Feb SMALL (C19, not promoted —
  SMALL ≠ the HUGE bar), Jan NO improvement, Mar SMALL (C01),
  May NO improvement (C20a blocked by an arithmetically
  unsatisfiable LCT gate + frequency), and the second-best
  workstream: Nov NO, Dec SMALL (B10, +0.17, cycle274 stands),
  Apr NO.
- Yesterday's designated second bests for the other months
  (SECOND_BEST_ALL12.md): research records only. February's
  H485_veto and July's C407 stack were proven not exactly
  reproducible in-app (FIX_NOTES_20261025_WAIVER_INTEGRATION.md
  §3–§4), so those months — and all months other than Sep/Dec —
  run best-only in the app until an exactly-reproducible second
  best exists.

## 5. What was NOT changed

- `MONTH_SYSTEMS` — still exactly the 12 incumbents (asserted in
  the smoke test).
- Every incumbent evaluator/selector branch and module
  (cycle60/67/78/85/86/87/88/89/91/92/93/94, cycle274, cycle287).
- October's internal C155 dual-pick — untouched.
- The month defaults in every panel and the selector default
  (current month's best system).
- Live signal crons — untouched and unaffected: the cron adapter
  `~/workspace/fx/live_trader/signals92.py` imports
  `core.cycle92_best` directly and never imports
  `core.signal_mode`, so this router change cannot alter the
  live C92-24 signal messages (verified by grep).
- No git / GitHub action was taken for this package; it is
  delivered as a ZIP for the user to upload himself.

## 6. Tests (2026-10-26, on this tree)

- `python -m py_compile` on both changed files: OK.
- Router smoke test: all 14 systems set/describe/Best-N/check-
  hours OK; `MONTH_SYSTEMS` equals the original 12 incumbents;
  every Best N equals the ÷3 table above; full N preserved.
- Combined-logic test (stubbed evaluators): (a) best pick →
  returned tagged BEST and the second-best evaluator is never
  called; (b) best empty in December → cycle274 evaluated, pick
  returned tagged SECOND_BEST; (c) best empty in January → empty
  result tagged BEST, nothing else evaluated; the caller's active
  system is restored after every call.
- UI module import: passes (with Jinja2 available); panels
  `cycle91combined` / `cycle94combined` registered,
  `_MONTH_PANEL_ORDER` first 12 entries unchanged, Best N labels
  render as "22.00" / "35.00" / "40.33". Without Jinja2 the
  import fails inside pandas' Styler import — the identical
  failure occurs on the untouched source tree (pre-existing
  environment gap, unrelated to this change).

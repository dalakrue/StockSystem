# FIX NOTES 2026-10-28 — POSSIBLE (pre-check) panel display

User order (2026-10-28 ~00:32 MMT): add the chat prep/pre-check
function inside the app — before a check time, each panel shows the
MOST POSSIBLE pick for its next check, with a chance % and grade,
using the same method as the chat prep reads.

## Change (one file, insertions only)
- `ui/field3_multisymbol_regime_summary_20260722.py`:
  - New shared helper block (`_precheck_next_check`,
    `_precheck_build_frames`, `_precheck_top`,
    `_compute_precheck_possible`, `_render_precheck_possible`)
    before the panel wiring table.
  - One additive call in `render_multisymbol_regime_summary` after
    the visible panel renders: the POSSIBLE block for that panel's
    month. All 12 month panels covered through the single hook.

## Method (mirrors live_trader/prep_check.py)
- Next check = first check (month's BEST system CHECK_HOURS, :30
  labels, weekends skipped) whose entry candle has not opened yet.
- Evaluate the panel's own combined system via
  `core.signal_mode.evaluate_combined_entries` (the exact path the
  combined panels use; Feb/Mar/Jul run best-only) on frames from
  `_fetch_c22_frames`, with the still-forming signal candle treated
  as final and a synthetic entry bar (open = current price).
- Stress: signal close shifted ±25%/±50% of its range (high/low
  expanded), re-evaluated; same-top-pick count maps to chance:
  4/4 → ~85% (high), 3/4 → ~70% (medium-high), 2/4 → ~55% (medium),
  1/4 → ~45% (low-medium), 0/4 → ~35% (low).
- Display: `POSSIBLE (pre-check — not the final signal): <DIR> <SYM>
  — entry ~px | SL px | TP px — chance ~pct% (grade)`; "none yet"
  when nothing fires; "no data loaded yet" on a cold boot.
- Results are cached in session state against a fingerprint of the
  loaded candles, so re-renders recompute only when data moved.
  M15 feature inputs stay exactly what each cycle module fetches
  itself (the stress shifts only the H1 signal candle, as in the
  chat prep).

## Safety
- Additive display only: no strategy/equation/selection change;
  Feb/Apr layers untouched (February's pre-check is a read-only
  evaluation through the same router the app already uses).
- The whole block is failure-swallowing: any error inside it leaves
  the panel rendering exactly as before.
- Verification: repo test suite failure set identical to the
  pre-change baseline (35 failed / 70 passed / 73 errors in this
  environment, all pre-existing); Streamlit AppTest render of all
  12 panels: 0 exceptions, POSSIBLE line present on every panel;
  real-evaluator smoke on synthetic candles for all 12 months OK.

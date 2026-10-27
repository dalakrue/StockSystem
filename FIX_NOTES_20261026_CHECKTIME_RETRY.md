# FIX 2026-10-26 (evening, user order) — check-time 0/20 "needed candles" error

## Symptom (user screenshot, 2026-10-26 21:33 MMT)
Cycle 92 panel, latest check 21:30 MMT: header said "20/20 symbols loaded"
but the panel showed "Price data incomplete for this window — only 0/20
symbols had the needed candles" and every ranking row "No data".

## Root cause (measured in the code, ui/field3_..._20260722.py)
At the exact check minute, the forming entry candle can be seconds away
on the provider, and every month panel evaluating at once bursts the
per-minute Twelve Data key limit. The shared fetch `_fetch_c22_frames`
made exactly ONE live refresh pass; when that pass came back empty the
window was stored as a data failure — and each panel's fail cooldown
then locked the window for 10 MINUTES, so the 30-second autorefresh
could not recover even after the candle had landed. The dashboard's
"20/20 loaded" counts repository presence, not the evaluation frames,
which is why the two numbers contradicted each other.

## Changes (ui/field3_multisymbol_regime_summary_20260722.py only)
1. `_fetch_c22_frames`: the missing-candle live refresh now runs up to
   3 passes within the same evaluation. After each pass it re-checks
   which symbols still lack a needed candle, waits 20s (then 35s), and
   re-fetches only those, force-live. A successful fetch persists the
   candle to the shared repository, so the remaining panels then read
   it from cache instead of bursting the provider again.
2. Every month panel's fail cooldown: 10 minutes -> 1 minute (all 20
   `_cXX_recent_fail` defaults in the file). A data-failed window now
   retries on the next autorefresh cycle instead of sitting locked.

No evaluator, equation, check-hour, or sizing code changed. Signals are
identical whenever data is present; this only changes how hard the app
works to get the candle at the check minute.

## Verification
- py_compile passes.
- Headless test of the extracted fetch function with a stubbed
  repository (cache missing the entry candle) and a stubbed provider
  chain: (a) first pass rate-limited, second pass OK -> all symbols
  evaluable, exactly 2 passes, one 20s wait; (b) provider down for all
  passes -> bounded at 3 passes, no exception, cached frames kept.
- The same shared fetch + cooldown pattern serves all 12 month panels
  (and the combined B panels), so the fix covers every month, not only
  Cycle 92 / October.

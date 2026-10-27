# FIX 2026-10-26 (night) — surface provider notes in the data-failure message

## Why
Live re-check of the deployed app (22:23-22:29 MMT, after the hang +
M15 fixes in f1d3ef6) verified: the page now finishes loading (~2 min
cold), spinners are transient, no tracebacks — but the Cycle 92 panel
still showed "only 0/20 symbols had the needed candles" for the 21:30
window, with all frames stuck at the last completed candle (14:00 UTC)
~55 minutes after the 15:00 UTC entry candle opened. That is not
provider publication lag: the live refresh is failing in production
for a reason the app already records but never displays (each window
evaluation's fetch diagnostics, including per-symbol live errors,
were discarded whenever a payload was stored).

## Change (ui/field3_multisymbol_regime_summary_20260722.py only)
- All 20 window evaluators now store their fetch diagnostics in the
  payload ("diag": cache/live counts + live_errors).
- All 20 data-failure messages append those provider notes via the
  new _diag_notes() helper, e.g. "Provider notes: EURUSD refresh:
  ALL_TWELVE_KEYS_LIMITED; ..." or "Fetch sources: cache 20/20, live
  0/20" — so the exact production failure (rate limit / key pool not
  configured / empty response) is readable on screen instead of a
  bare 0/20.

No evaluator, equation, fetch, or sizing behaviour changed.

# FIX 2026-10-26 (late evening, user order) — evaluation hang + M15 depth

## Symptoms (user screenshots, 22:09 MMT)
1. After the check-time retry fix (3931c84), the page sat on
   "Evaluating Cycle 92 signals..." for ~15 minutes.
2. The combined B systems (Jan 60B / Apr 87B / Nov 93B / Dec 94B) could
   never produce their validated behaviour live: their M15 data need
   was not being served.

## Root causes (measured in the code)
1. HANG: every month panel on the page calls the shared H1 fetch. The
   retry passes added at 21:5x ran PER PANEL: ~20 panels x up to 3
   passes x 20 provider calls, each provider call with a 15s HTTP
   timeout and internal retries — one page render could stack many
   minutes of fetching and never finish.
2. M15 DEPTH: the shared M15 fetcher (core/cycle78_best.py) loaded and
   fetched only 200 bars per symbol. The November/December vol_z veto
   needs >=387 causal M15 bars and January's breadth uses a causal
   window of up to 1600 bars, so with 200 bars the B evaluators bailed
   out with 'insufficient_m15_history' and returned no entries — the
   combined best cycles were integrated but starved of data. Also,
   explicit symbol sets (what every B system passes) bypassed the
   fetch memo entirely, so each B panel re-fetched from scratch.

## Changes
core/cycle78_best.py (shared M15 path for ALL M15-dependent cycles):
- M15 depth 200 -> 2000 bars, repository load and provider fetch alike
  (same API credit per symbol, more bars per call): vol_z's 387-bar
  prerequisite and January's breadth window are now satisfiable live.
- Memo now also covers explicit symbol sets (keyed by symbol set,
  same 10-minute TTL + currency guard as the default set).
- Provider loop is deadline-bounded (120s): a cold repository plus a
  slow provider can no longer hang a render; what was fetched inside
  the budget is served and the currency guard re-fetches later.

ui/field3_multisymbol_regime_summary_20260722.py (shared H1 fetch):
- Page-level refresh guard: the first panel that needs candles runs
  the live refresh; panels rendering within 60 seconds afterwards
  read the warmed shared repository instead of refreshing again.
- The whole refresh is deadline-bounded (~75s): waits shortened
  (10s/15s), deadline checked before every fetch and every wait, so
  an evaluation always returns and the page always finishes.

No evaluator, equation, check-hour, or sizing code changed.

## Verification
- py_compile passes on both files.
- H1 fetch harness (stubbed repo/provider): first-pass rate-limit
  recovers inside the same evaluation (2 passes, one 10s wait); a
  second panel in the same session makes ZERO new provider calls.
- M15 fetcher harness (cold repo, stubbed provider): all symbols
  return 2000 bars (>=387 vol_z prerequisite met); a repeat fetch for
  the same symbol set is served from the memo with zero provider
  calls; the harness asserts the provider is asked for M15 @ 2000.
- Live-path check of the four B evaluators on real H1 + 2000-bar M15
  frames (research DB): Jan 60B, Nov 93B, Dec 94B, Apr 87B all
  evaluate with NO 'insufficient_m15_history' status — the exact
  silent bailout this fix removes.

## Note on the header the user questioned
The top status reads "cycle92 / Best N 27.67" because October's best
runs through the Cycle 92 panel (C92-24 engine + the C155 dual-pick
selector inside it), and October's own Best N is 83, so the active
÷3 value is 27.67 — the same number as January's by coincidence
(January's N is also 83). Both are their own validated values.

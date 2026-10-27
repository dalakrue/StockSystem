# Check-minute repair verification — 27 October 2026

Verdict: the targeted repair is integrated and locally tested. The complete app
is not certified globally error-free or live-check verified.

## Passed

- 52 focused tests, zero failures/errors (8.18 seconds).
- Continuous controlled 20-symbol direct M15 fetch -> actual Cycle 92 evaluator
  -> Streamlit ENTRY rendering, compared with native-H1 entry/TP/SL results.
- Native versus fallback signal and selection parity over 18 quote-fixture
  check windows, including positive signals and silent windows.
- Exact GBPJPY SELL formatting: entry 210.233, TP 210.133, SL 211.233. This is
  a deterministic test, not a re-verification of the user's historical live trade.
- Missing first quarter, future/invalid opens, historical gaps, quota exhaustion,
  duplicate credentials, request deadline, memo reuse, manual refresh, recovery,
  deep M15 refresh, no-key startup, key replacement priority, and no-trade tables.
- Streamlit app.py startup: zero unhandled exceptions, zero error boxes; one
  expected unavailable-data warning with no credentials configured.
- Python compilation across core/ui/tabs and the app entry files.

## Original legacy suite

The original ZIP's 357 collected tests produced 259 passes, 18 skips, 51 failures,
and 29 setup errors. The updated broad run reproduced exactly the same 80 failed
or errored test IDs; no added failure IDs. Its additional repair tests passed.
One final end-to-end test was added after the broad run and passed in the focused
52-test run. Both comparison and focused result records are included here.

The old failures include removed legacy Finder/UI names, obsolete strategy-count
expectations, execution-contract expectations that disagree with the supplied
build, and unavailable legacy exports. These are outstanding results, not
silently discarded tests. See legacy_failure_comparison.json for every ID.

## Not established

No authenticated deployed-app check was available. These tests cannot prove
Twelve Data publishes the required M15 bar at an exact second, that the deployed
key/plan has spare capacity for all 20 symbols, or that the deployed browser
shows the result inside the real check minute. Real provider outages/late bars
still produce an explicit incomplete calculation and retry; no price is guessed.

The historical strategy validation reports in the supplied ZIP were preserved.
This repair does not independently revalidate all monthly research systems or
establish equality between Twelve Data and Dukascopy/MT5 quote feeds.

Start with READ_FIRST_CHECK_MINUTE_FIX_20261027.md. Run the included read-only
provider verifier at a real check and observe the deployed browser to complete
live acceptance. The verifier intentionally cannot certify browser display.

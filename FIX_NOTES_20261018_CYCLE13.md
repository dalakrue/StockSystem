# Fix notes — Cycle 13 (2026-10-18): 40-process battery, no equation change + sizing recommendation

Base: copy of `Forex_App_Fixed_S1_S240_Cycle12__12.zip` (the uploaded Cycle 12
zip). The uploaded zip was NOT modified. This zip is
`Forex_App_Fixed_S1_S240_Cycle13__13.zip`.

## 1. What changed (and only this)

| File | Change |
|---|---|
| `FIX_NOTES_20261018_CYCLE13.md` | NEW. This file: Cycle 13 verdict + sizing recommendation. |
| `PACKAGE_MANIFEST.json` | Version string + one entry for the new file above. |

**Equations UNCHANGED.** Cycle 13 ran 40 new processes (10 mining cycles ×
4 technique families: indicator-gated, candlestick-pattern,
walk-forward/regime-conditional, optimization-based). 30 of 40 passed the
C13 10-check battery, but **NONE beat C12 BEST** (see §2), so per the
"do not force a winner" rule the app keeps the C12 BEST equations in
`core/cycle12_best.py` verbatim. S1–S240 mapping, equations, ranking,
stats, check hours, and everything else: byte-identical (verified by
`diff -rq` between the base tree and this tree — only the two files
above differ).

## 2. Why no equation change: best C13 vs C12 BEST (same unseen window, same accounting)

| Metric (unseen 2025-10-05→2026-10-05, 1-pip, SL-first) | C12 BEST (in app) | Best C13 (FA-C02) |
|---|---|---|
| Net pips | **+1,164.21** | +490.16 |
| Trades | 163 | 66 |
| RoMAD | **40.39** | 8.99 |
| Sharpe (daily, ann.) | **14.18** | 8.11 |
| Max DD (pips) | −28.82 | −54.52 |
| EV (pips/trade) | 7.14 | **7.43** |
| Win rate | 84.66% | 74.24% |
| Breakeven cost (pips) | 8.14 | 8.42 |
| C13 10-check | PASS | PASS |

FA-C02 (Family A, indicator-gated, cycle 2) is the best of the 40 C13
processes by the stated rule (RoMAD primary, Sharpe second, among
10-check PASS processes). Its only edge over C12 BEST is a slightly
higher unseen EV on far fewer trades (66 vs 163). On every headline
metric — net (+137% for C12 BEST), RoMAD (4.5×), drawdown (shallower) —
C12 BEST wins. Replacing the app's equations with FA-C02 would make the
app worse. Full 40-process table: `~/workspace/fx/work_c13/results/comparison_table.csv`.

## 3. Position sizing (Phase 2): recommendation, app untouched

User-defined rule: lot = 0.01 + 0.01 × floor(cumulative profit $ / N),
N swept $20.00 → $10.00 in $0.01 steps (1001 values), $1,000 start,
base lot 0.01, $0.10/pip per 0.01 lot, sequential over the trade log.

**The app has NO position-sizing parameter/setting** for the C12 BEST
module (verified by grep: `cycle12_best.py` has no sizing; the Kelly /
risk-budget helpers in `core/morning_quant_metrics_20261003.py` are
shadow-only diagnostics with `automatic_position_change: False`). Per the
task, the app's sizing is therefore left untouched and the best N is
reported here as the **recommended setting**:

- **Recommended N = $20.00** (slowest compounding in the swept range) for
  the system in the app (C12 BEST), from the out-of-sample unseen-only
  sweep: final equity $3,807.67 from $1,000, RoMAD 41.86, Sharpe 10.61,
  max DD 2.7%, max lot 1.34.
- **Margin warning:** at N = $20.00 the max margin usage reaches 71.4%
  (1:100 leverage assumed: $1,000 margin per 1.0 lot). N ≤ $17 breaches
  100% on the unseen path (MARGIN-CALL RISK). Do NOT use N below $20
  without a lot cap / margin stop — the backtest replay has no
  margin-call stop.
- For reference, best C13 process FA-C02 unseen-only best N = $18.72
  (equity $1,128.96, RoMAD 17.50, max lot 0.07, margin OK). Not
  recommended for use: FA-C02 underperforms C12 BEST (see §2).
- Full-log (discovery + unseen) sweeps are reported for completeness
  but are NOT tradable: every N in range breaches 100% margin usage,
  and the headline equities ($7.65B for C12 BEST, $2.50M for FA-C02 at
  N = $20) are mechanical compounding artifacts (max lots in the
  millions), not forecasts. The sweep also finds RoMAD rises with N
  (slower compounding = better risk-adjusted return) across the range,
  so $20.00 is "best in range", not a proven interior optimum.

## 4. Verification (all numbers from re-runs, none invented)

- All 40 C13 processes independently re-run from their saved JSON
  equation specs through the shared library (`c13_common`, same
  SL-first engine as C12): **0 mismatches** vs the family workers'
  saved numbers and trade-log CSVs.
- C12 BEST re-run through the same library reproduces the published
  numbers exactly (unseen +1,164.21 / 163 trades).
- Sizing sweep re-ran the user's rule verbatim (1001 N values × 4 logs).
- Tests: Cycle-12 equation tests + monthly-integration + upgrade8
  suites run on this tree — failure set identical to the base tree
  (pre-existing environment gaps only; zero new failures). See the
  Cycle 13 Word report for the test summary.

## 5. Caveats

- FA-C02 was picked by ranking 10-check PASS processes on UNSEEN RoMAD,
  so its 10-check PASS is optimistic to some degree (same caveat as C12
  BEST, which was also ranked on unseen). Fresh forward data / paper
  trading is required before any live use.
- The sizing sweep's full-log paths ignore margin calls, broker lot
  limits, and slippage beyond the 1-pip spread. The unseen-only sweep
  (163 trades, one year) is the decision-relevant one and is still a
  single-year basis.
- The user's separate app-level requests (Myanmar/MetaTrader time +
  check-time/updated flags UI, every-qualifying-entries mode, delete
  14:00 Myanmar check, test 08:00 Myanmar check) were NOT in the Cycle
  13 task scope. Note: C12 already A/B-tested uncapped entries
  (Variant A): it PASSED the 10-check but LOWERED RoMAD (33.97 vs
  40.39), so uncapped stays opt-in, never the default. C12 also tested
  the 08:00 Myanmar check (Variant C, 01:30 UTC equations): the combined
  system FAILED the 10-check (check 8, EURJPY unseen −45.55) with 3.34×
  deeper drawdown and 62% lower RoMAD, so it was NOT recommended.

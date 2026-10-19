# Fix notes — Cycle 14 (2026-10-18): 100-process battery, no equation change + sizing stands

Base: copy of `Forex_App_Fixed_S1_S240_Cycle13__13.zip`.
The Cycle 12 uploaded zip and the Cycle 13 zip were NOT modified. This zip is
`Forex_App_Fixed_S1_S240_Cycle14__14.zip`.

## 1. What changed (and only this)

| File | Change |
|---|---|
| `FIX_NOTES_20261018_CYCLE14.md` | NEW. This file: Cycle 14 verdict + sizing. |
| `PACKAGE_MANIFEST.json` | Version string + one entry for the new file above. |

**Equations UNCHANGED.** Cycle 14 ran 100 new processes (10 mining cycles ×
10 technique families, every technique/indicator new — not used in C12, C13,
__11, or __10). 90 of 100 passed the 10-check battery (10 of the 90 are Family F restatements of C12 BEST, not candidates), but **NONE beat
C12 BEST on RoMAD** (see §2), so per the "do not force a winner" rule the app
keeps the C12 BEST equations in `core/cycle12_best.py` verbatim. S1–S240
mapping, equations, ranking, stats, check hours, and everything else:
byte-identical (verified by `diff -rq` between the base tree and this tree —
only the two files above differ).

## 2. Why no equation change: best C14 vs C12 BEST (same unseen window, same accounting)

| Metric (unseen 2025-10-05→2026-10-05, 1-pip, SL-first) | C12 BEST (in app) | Best C14 (FL-C02) |
|---|---|---|
| Net pips | **+1,164.21** | +2,065.10 |
| Trades | 163 | 298 |
| RoMAD | **40.39** | 35.64 |
| Sharpe | **14.18** | 12.89 |
| Max DD (pips) | **−28.82** | −57.94 |
| EV (pips/trade) | **7.14** | 6.93 |
| C14 10-check | PASS | PASS |

FL-C02 (Family L, Bayesian optimization, cycle 2) beats C12 BEST on raw unseen
net (+2,065 vs +1,164) but loses on the pre-registered primary objective
(RoMAD 35.64 vs 40.39), on Sharpe, and on drawdown depth (−57.9 vs −28.8).
Per the strict upgrade rule (RoMAD primary, no worse drawdown), the app is
NOT upgraded. Forcing FL-C02 in on net pips alone would trade a proven
risk-adjusted edge for a noisier one.

Optimism asymmetry (stated plainly): C12 BEST was selected by ranking on
unseen RoMAD, so its 40.39 is optimistic to some degree; every C14 family's
unseen is fully clean. The true gap may be narrower than it looks — but the
rule was set before mining and is not overridden after seeing the numbers.
Paper trading before any live use, as always.

## 3. The 100 processes (summary)

| Family | Technique | Best process | Unseen net / RoMAD | 10-check |
|---|---|---|---|---|
| E | New oscillators/bands (CCI, Williams %R, Keltner, Donchian, Parabolic SAR, pivots, MFI, CMF, OBV, VWAP) | FE-C02 | +360.2 / 5.43 | 10/10 PASS |
| F | ML classifiers (k-NN, SVM, LogReg, NB, LDA, QDA, MLP, voting) | — | — | 0 adoptions in 10 cycles; all 10 summaries restate C12 BEST (not candidates) |
| G | Cross-symbol/correlation (pair confirmation, DXY-proxy, baskets, spread z-score) | FG-C01 | +975.2 / 9.97 | 10/10 PASS |
| H | Volatility modeling (EWMA forecast, Parkinson, Garman-Klass, RV percentiles, ATR term structure) | FH-C07 | +416.2 / 5.31 | 6/10 PASS (4 fail: <50 unseen trades) |
| I | Event-calendar filters (NFP/FOMC/CPI skip & adjust; dates verified, never invented) | FI-C03 | +929.8 / 24.85 | 10/10 PASS |
| J | Association-rule mining (Apriori/FP-growth) | FJ-C08 | +307.2 / 3.95 | 9/10 PASS (1 fails win-rate stability) |
| K | Genetic programming (evolved condition trees + parsimony penalty) | FK-C06 | +1,851.9 / 10.71 | 10/10 PASS |
| L | Bayesian optimization (GP surrogate + EI/UCB/PI, walk-forward fitness) | FL-C02 | +2,065.1 / 35.64 | 10/10 PASS |
| M | HMM regime-state (2/3-state, Gaussian/Student-t, causal forward-filtered states) | FM-C02 | +768.2 / 20.57 | 6/10 PASS (4 fail: <50 unseen trades) |
| N | Structural variants + the user's calendar idea (exactly one process) | FN-C07 (k=1) | +735.8 / 32.04 | 9/10 PASS (1 fails: 13:30 UTC bad hour) |

Coordinator independently re-ran all 100 processes from their saved equation
specs through the shared library: 0 mismatches vs family workers' numbers and
trade-log CSVs.

Notable honest findings:
- The user's calendar idea (symbol × month × day-of-week, exactly one process:
  FN-C01) FAILED: no calendar cell had ≥30 discovery trades except one exclusion
  that lowered EV; the greedy stacked exclusion that looked good on discovery
  failed validation screening — the overfitting trap working as intended.
- Family K found most of its edge is unconditional 18:30 UTC SELL drift:
  near-unconditional SELLs beat C12 BEST on unseen net but lose badly on RoMAD
  with ~6× deeper drawdown. The 10-check does not protect against drift-regime
  reversal.
- Family F: per-trade win/loss prediction from check-time features is
  near-chance (mean CV AUC 0.545) — structural failure, fully logged.
- Family N: 13:30 UTC is a bad check hour (10-check FAIL); 19:30 UTC has the
  best raw unseen net (+1,327.5) but lower RoMAD (14.45); k=1 gives the best
  unseen RoMAD in the family (32.04); max-2-open-per-symbol does not help.

## 4. Position sizing

Unchanged: **N = $20.00** (lot = 0.01 + 0.01 × floor(cumulative profit $ / N),
$1,000 start, base lot 0.01). No re-run — no new winner. The app has no
position-sizing parameter for the BEST module; sizing remains the reported
recommended setting (margin WARNING at 71% peak on the unseen path).

## 5. Verification

- Tests on the new tree: C12 equation suite passes; monthly-integration +
  upgrade8 suites show only the pre-existing C13 baseline failures (missing
  pyarrow, Rangoon tz alias). Zero new failures.
- Full per-process comparison table (all 100, all 10 checks, overfit verdicts):
  `~/workspace/fx/work_c14/results/comparison_table.csv`.
- Short Word report: `~/workspace/your_files/fx_backtest/Forex_Cycle14_Short_Report_20261018.docx`.

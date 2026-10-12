# S111-S120, Advanced TP/SL, and Two-Year Fast Build Upgrade

## Delivered behavior

- S1-S120 now share the requested exact 40% entry-filter relaxation. Direction agreement, valid completed OHLC, causal calculation, structure alignment, and DMI direction remain mandatory.
- S111-S120 are genuine rescue entries. S111-S119 require no S1-S110 hit; S120 requires no S1-S119 hit and at least four of six independent evidence groups.
- Suggested TP/SL now uses one shared causal structural/multi-horizon pair model in live ranking, Finder, worker output, CSV, selector, and professional execution backtest.
- Strategy Decision no longer publishes `SL reach`. The separate Middle Bias lifetime audit field remains available.
- Finder no longer calculates or downloads a professional backtest ZIP.
- Fast Strategy Build always requests exactly two years of H1 data, stores/reuses large historical chunks, runs S1-S120 once per symbol outside Streamlit, marks the hourly Top-4 entries, and prepares one direct continuous all-symbol CSV download. The CSV retains every symbol row for every exported H1 timestamp.

## S111-S120 definitions

| ID | Entry family |
|---|---|
| S111 | Micro Pullback Resumption |
| S112 | Impulse / Pause / Resume Flag |
| S113 | Inside-Bar Trend Break |
| S114 | NR4/NR7 Narrow-Range Expansion |
| S115 | Failed Countertrend Break / Trap Reclaim |
| S116 | Multi-Wick Absorption |
| S117 | Fair Value Gap / Imbalance Reclaim |
| S118 | Structure Break + First Clean Retest |
| S119 | Contraction to Re-Acceleration |
| S120 | Independent Evidence Consensus Rescue |

## TP/SL model

The model evaluates 4H, 6H, 8H, 12H, 16H, 20H, and 24H horizons from completed historical paths. Forward MFE/MAE values are released only after the relevant horizon has elapsed. It calculates P50/P70/P75/P80/P85/P90 distributions, exact first-touch order, SL-first same-candle ambiguity, post-SL rebound to the original TP, reach times, 2-pip net expectation, reward/risk, ROMAD proxy, and sample coverage.

Structural SL candidates use confirmed swings, sweep extremes, equal-high/equal-low clusters, previous-24H levels, breakout/retest levels, EMA value confluence, historical MAE, historical wick overshoot, noise, ATR, and spread. The adaptive risk ceiling ranges from 2.15 to 2.90 ATR. A stop outside that ceiling is retained as a required structural distance but marked failed/poor instead of being forced inside the invalidation.

TP is selected jointly with SL, prefers the earliest horizon within 93% of the best risk-adjusted utility, is bounded by lagged MFE support, and is placed before strong structural barriers unless breakout evidence passes. Twenty-four hours remains the hard time exit.

## Deterministic before/after professional backtest

The untouched upload and upgraded project were run with identical six-symbol, 1,200-hour deterministic synthetic OHLC data, the same 876-hour entry window, Top-4 selector, Middle Bias exits, 2-pip cost, conservative same-candle rule, and 24H maximum. This is a software regression benchmark, not evidence of live profitability.

| Metric | Before | After |
|---|---:|---:|
| Entry signals | 3,504 | 3,504 |
| Valid trades | 3,179 | 3,229 |
| Strategy-origin trades | 702 | 878 |
| RANK-FILL trades | 2,477 | 2,351 |
| S111-S120 additional trades | 0 | 176 |
| Entries/hour | 4.000 | 4.000 |
| Net pips | -7,644.622 | -11,349.010 |
| Win rate | 28.468% | 54.847% |
| Profit factor | 0.6211 | 0.2887 |
| Max drawdown | -7,824.749 | -11,373.708 |
| ROMAD | -0.9770 | -0.9978 |
| Average hold | 12.482h | 6.055h |
| Median hold | 11.000h | 3.000h |
| P75 hold | 24.000h | 8.000h |
| TP exits / TP-first | 11.293% | 67.637% |
| SL exits / SL-first | 55.363% | 3.964% |
| Middle Bias exits | 8.556% | 25.178% |
| 24H time exits | 24.788% | 3.221% |
| Post-SL rebound to TP | 0.057% (1,760 SL samples) | 0.000% (128 SL samples) |
| Average MFE | 9.543 pips | 4.726 pips |
| Average MAE | 7.537 pips | 7.345 pips |
| Last-30% net pips | -2,014.632 | -3,357.833 |
| Last-30% drawdown | -3,087.281 | -3,501.244 |

The upgrade reduced holding time, SL-first exits, time exits, and observed post-SL rebound events on this fixture, but it did **not** improve net pips, profit factor, or drawdown. No profitability claim is made. The poor aggregate result is driven heavily by mandatory Top-4/RANK-FILL exposure and the synthetic price process; production thresholds should be calibrated on representative out-of-sample market history.

### S111-S120 contribution in the after run

Strategies can overlap with another new-family condition, so per-ID counts are not additive.

| ID | Valid selected trades | Net pips | Win rate |
|---|---:|---:|---:|
| S111 | 4 | 0.81 | 25.00% |
| S112 | 29 | 25.60 | 86.21% |
| S113 | 19 | -54.50 | 63.16% |
| S114 | 13 | -11.48 | 76.92% |
| S115 | 0 | 0.00 | n/a |
| S116 | 78 | -394.11 | 44.87% |
| S117 | 19 | -128.64 | 42.11% |
| S118 | 79 | -234.06 | 49.37% |
| S119 | 1 | 3.65 | 100.00% |
| S120 | 1 | 2.46 | 100.00% |

S115 is proven in separate deterministic BUY and SELL synthetic strategy tests; it simply did not occur in this six-symbol execution fixture.

### Symbol, direction, horizon, and regime breakdown

| Symbol | Before trades | Before net | After trades | After net | After win rate |
|---|---:|---:|---:|---:|---:|
| AUDUSD | 508 | -2,130.34 | 565 | -1,915.88 | 53.45% |
| EURUSD | 531 | -1,003.25 | 575 | -1,550.41 | 55.48% |
| GBPUSD | 523 | -2,516.41 | 467 | -2,306.14 | 51.61% |
| NZDUSD | 561 | 42.38 | 553 | -2,113.84 | 54.97% |
| USDCAD | 550 | -139.86 | 545 | -1,892.06 | 53.94% |
| USDCHF | 506 | -1,897.14 | 524 | -1,570.69 | 59.35% |

| Side / Middle regime | Before trades | Before net | After trades | After net | After win rate |
|---|---:|---:|---:|---:|---:|
| BUY | 1,636 | -2,903.41 | 1,652 | -5,582.03 | 55.27% |
| SELL | 1,543 | -4,741.21 | 1,577 | -5,766.98 | 54.41% |

All 3,229 valid after-upgrade trades selected the discrete 4H horizon on this particular fixture (net -11,349.01; win rate 54.85%). Other deterministic horizon tests selected every supported value from 4H through 24H. The before engine emitted a continuous estimated-hour value rather than one of the new discrete research horizons, so a like-for-like per-horizon category is not available for the legacy run.

## Verification

- Full repository suite: 92 passed, 0 failed.
- New upgrade suite: 27 passed, including all ten new strategies in BUY and SELL direction.
- Two-year-size H1 smoke test: 17,521 rows, 655 output columns, and all S1-S120/TP-SL calculations completed in 3.565 seconds for one symbol on the validation runtime.
- Worker integration test downloads mocked chunks, builds per-symbol Parquet, creates the two-year continuous CSV artifact, reloads it, verifies every requested symbol is present on every exported H1 timestamp, verifies exactly four rows are marked as entries, and confirms completed artifacts/API chunks are reused.
- Professional execution tests confirm exact generated TP/SL prices, future-candle-only exits, 2-pip spread, SL-first same-candle handling, Middle Bias exit, 24H cap/incomplete tails, and realized post-SL rebound auditing.

## Files changed

- `core/advanced_tpsl_engine_20261002.py` (new)
- `core/compact_strategy_decision_20260930.py`
- `core/hourly_four_symbol_selector_20260928.py`
- `core/professional_execution_backtest_20261001.py`
- `core/pullback_engine_s1_s3_upgrade.py`
- `core/resumable_build_20260928.py`
- `core/strategy_audit_20260924.py`
- `core/super_quick_field3_20260722.py`
- `ui/field3_multisymbol_regime_summary_20260722.py`
- `worker/run_build_worker.py`
- `worker/README.md`
- `tests/test_finder_s1_s50_repair_20260924.py`
- `tests/test_loading_and_fast_build_20260930.py`
- `tests/test_professional_execution_backtest_20261001.py`
- `tests/test_s1_s20_finder_upgrade_20260923.py`
- `tests/test_s111_s120_advanced_tpsl_20261002.py` (new)
- `tests/test_strategy_s1_s6_no_wait_20260918.py`
- this report

## Remaining limitations

- No live provider key or user market dataset was supplied, so the before/after result above uses a reproducible synthetic dataset. Run representative walk-forward/out-of-sample market tests before trading or tuning thresholds.
- The first-touch research history is same-symbol and causally rolling. Cross-symbol pooled fallback is not used by the per-symbol worker because that would require a second universe-wide research pass.
- Fast Strategy Build reduces redundant network and calculation work, but its wall-clock duration still depends on provider quota, symbol count, timeframe, and deployment CPU.

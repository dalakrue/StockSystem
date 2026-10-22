# Cycle 116 — September (C91-15) — Two-state HMM regime-persistence ranking bonus

Method as specified: two-state Gaussian HMM on standardized H1 returns + log high–low ranges, fit on discovery, filtered forward. An eligible candidate gets a ranking bonus (the harness's own +400 bonus scale, added in the walk's order_fn) when the filtered probability of its market state has stayed ≥ 0.70 for two consecutive H1 closes before the check (same state at both closes). The standing fallback cuts and X30B stop logic are preserved.

HMM fit: transition matrix [[0.912, 0.088], [0.363, 0.637]], state means [[0.01, -0.29], [-0.03, 1.46]] (standardized [return, log-range]). Candidate rows awarded the bonus during the walks: 1588.

Harness reproduction of the standing system: PASS (walk OFF disc net +2049.2 vs saved +2049.2; audit net +285.1 vs saved +285.1).

## Discovery

| Ledger | Trades | Net pips | Win % | Leftover % | Avg win | Avg loss |
|---|---|---|---|---|---|---|
| OFF | 492 | +2049.2 | 94.11% | 50.51% | 8.2 | 61.0 |
| ON | 491 | +1949.0 | 93.69% | 48.36% | 8.2 | 58.9 |

## 2025 audit

| Ledger | Trades | Net pips | Win % | Leftover % | Avg win | Avg loss |
|---|---|---|---|---|---|---|
| OFF | 58 | +285.1 | 94.83% | 65.26% | 7.5 | 43.1 |
| ON | 58 | +285.1 | 94.83% | 65.26% | 7.5 | 43.1 |

## Verdict: NOT

One-line reason: audit leftover 65.26% -> 65.26%, discovery leftover 50.51% -> 48.36%; no leftover improvement on both ledgers at screening level.

# Cycle 116 — July (C78-34) — Bayesian change-point partial-exit overlay

Method as specified, with the brief-approved lightweight simplification: online Bayesian change-point detection (Adams–MacKay run-length posterior, hazard 1/50, NIG predictive, run-length cap 260) on H1 log returns. 50% partial exit only when P(change within last 4 H1 bars) ≥ 0.60 AND the position is losing AND the original H1 direction is unsupported (last H1 close adverse vs entry). Target stat: the 7.50 cost/loss ratio.

## Discovery

| Ledger | Trades | Net pips | Win % | Leftover % | Avg win | Avg loss |
|---|---|---|---|---|---|---|
| OFF | 527 | +3690.3 | 94.50% | 62.30% | 11.2 | 65.8 |
| ON | 527 | +3665.9 | 92.98% | 61.84% | 11.2 | 49.9 |

Trades triggering the overlay: 18.

## 2025 audit

| Ledger | Trades | Net pips | Win % | Leftover % | Avg win | Avg loss |
|---|---|---|---|---|---|---|
| OFF | 68 | +487.7 | 95.59% | 62.48% | 11.5 | 86.1 |
| ON | 68 | +487.7 | 95.59% | 62.48% | 11.5 | 86.1 |

Trades triggering the overlay: 0.

## Verdict: NOT

One-line reason: audit leftover 62.48% -> 62.48%, discovery leftover 62.30% -> 61.84%, audit avg loss 86.1 -> 86.1 pips; no leftover improvement on both ledgers at screening level.

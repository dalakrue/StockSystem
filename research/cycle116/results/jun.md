# Cycle 116 — June (C89-21) — Rogers–Satchell volatility partial-exit overlay

Method as specified: Rogers–Satchell OHLC volatility over the latest 24 H1 bars is the yardstick. If the current loss ≥ 0.25 × entry H1 ATR and the short-term adverse movement (adverse 4h close move in RS-vol units) exceeds its trailing 90th-percentile threshold, take a one-time 50% partial exit at that H1 open. Target stat: the expensive losing trades behind the 7.78 cost/loss ratio.

## Discovery

| Ledger | Trades | Net pips | Win % | Leftover % | Avg win | Avg loss |
|---|---|---|---|---|---|---|
| OFF | 571 | +3713.3 | 94.75% | 66.59% | 9.8 | 52.3 |
| ON | 571 | +3041.1 | 84.94% | 55.79% | 9.5 | 18.5 |

Trades triggering the overlay: 92.

## 2025 audit

| Ledger | Trades | Net pips | Win % | Leftover % | Avg win | Avg loss |
|---|---|---|---|---|---|---|
| OFF | 63 | +364.0 | 95.24% | 58.20% | 9.9 | 77.2 |
| ON | 63 | +339.9 | 88.89% | 56.97% | 9.5 | 27.2 |

Trades triggering the overlay: 9.

The large audit losses the overlay caught (net pips OFF -> ON):
- 2025-06-11 18:30:00 EURNZD SELL: -102.5 -> -57.7
- 2025-06-23 15:30:00 EURCAD SELL: -102.5 -> -77.0

## Verdict: NOT

One-line reason: audit leftover 58.20% -> 56.97%, discovery leftover 66.59% -> 55.79%, audit avg loss 77.2 -> 27.2 pips; no leftover improvement on both ledgers at screening level.

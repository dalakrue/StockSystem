# Cycle 116 — February (C85-23) — CAViaR-style conditional-tail overlay

Method as specified: rolling 95th-percentile adverse 1h move from M15 returns (trailing 20 trading days, H1 grid). While a trade is open and losing, if the forecast adverse move > 0.35 × entry H1 ATR, close 25% (variant A) / 50% (variant B) at the next H1 open. Screening pass on saved ledgers; partial-exit remainder keeps the original outcome (trigger marks required inside the TP/SL band).

## Discovery

| Ledger | Trades | Net pips | Win % | Leftover % | Avg win | Avg loss |
|---|---|---|---|---|---|---|
| OFF | 433 | +3380.1 | 93.53% | 61.36% | 12.7 | 63.3 |
| A25 | 433 | +2654.1 | 92.84% | 60.44% | 10.1 | 45.9 |
| B50 | 433 | +1928.1 | 79.45% | 47.91% | 9.3 | 14.3 |

Trades triggering the overlay: A 214, B 214 (same trigger set, different fraction).

## 2025 audit

| Ledger | Trades | Net pips | Win % | Leftover % | Avg win | Avg loss |
|---|---|---|---|---|---|---|
| OFF | 49 | +184.2 | 85.71% | 29.35% | 12.8 | 50.5 |
| A25 | 49 | +145.1 | 85.71% | 29.13% | 10.2 | 40.3 |
| B50 | 49 | +106.0 | 75.51% | 24.05% | 9.0 | 18.9 |

Trades triggering the overlay: A 29, B 29 (same trigger set, different fraction).

## Verdict: NOT

One-line reason: best variant (A) moves audit leftover 29.35% -> 29.13% and discovery leftover 61.36% -> 60.44%, audit avg loss 50.5 -> 40.3 pips; no leftover improvement on both ledgers — the tail cuts cost more on the trades that recover than they save on the trades that fail.

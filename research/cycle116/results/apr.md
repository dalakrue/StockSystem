# Cycle 116 — April (C87-24) — Theil–Sen robust-slope ranking bonus

Method as specified: keep the existing top-three ranking and corridor conditions; calculate a robust (Theil–Sen, median pairwise) slope from the preceding 24 H1 closes normalized by H1 ATR; use it as a ranking bonus, not a veto — implemented in the harness's own rerank form: within the post-M18 top-3, candidates with directional slope ≥ 0.015 ATR/bar are promoted to the front (stable order).

Harness reproduction of the standing system: PASS (walk OFF disc net +4357.9 vs saved +4357.9; audit net +633.2 vs saved +633.2).

## Discovery

| Ledger | Trades | Net pips | Win % | Leftover % | Avg win | Avg loss |
|---|---|---|---|---|---|---|
| OFF | 568 | +4357.9 | 96.83% | 78.99% | 9.7 | 54.7 |
| ON | 570 | +2654.8 | 93.51% | 50.84% | 9.2 | 60.2 |

Picks changed by the bonus: trade count itself moved 568 -> 570 (changed picks alter downstream occupancy), so a row-by-row pick count is not meaningful on discovery; on the audit ledger (same count) 14 of 66 picks changed.

## 2025 audit

| Ledger | Trades | Net pips | Win % | Leftover % | Avg win | Avg loss |
|---|---|---|---|---|---|---|
| OFF | 66 | +633.2 | 92.42% | 60.26% | 15.9 | 67.6 |
| ON | 66 | +376.7 | 90.91% | 41.91% | 13.6 | 73.4 |

Picks changed by the bonus: 14.

## Verdict: NOT

One-line reason: audit leftover 60.26% -> 41.91%, discovery leftover 78.99% -> 50.84% with 14 audit picks changed; no leftover improvement on both ledgers at screening level.

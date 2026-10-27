# BRIEF21 NOVEMBER — VALIDATION (2026-10-26)

Incumbent: C93-24 (N=83). Frame A3: DISC 2016–2023 (FIT 2016–2020,
HOLDOUT 2021–2023), AUDIT 2024+2025 (read once, here). Cost @2.5.
Exact raw-price replay only. Gates: BRIEF21.md LOCKED + addendum 1
(middle overfit: PBO not-HIGH passes, DSR report-only) + addendum 2
(partners within incumbent checks + at most one extra; conflict-free
combination, verified below).

Control (A3 battery basis): DISC n 407 net +5069.85 win 89.43
leftover 63.11 | AUDIT n 105 net +604.60 win 85.71 leftover 36.33
epd 2.56. (The brief's book figures — audit win 84.62 / leftover
40.11 — are the V5-book frame; all gate comparisons here are
candidate vs control on the SAME A3 ledgers.)

## WINNER (primary): C20a = C06 + C16
C06: volatility-shock entry veto on C93-24 (drop picks whose
vol_z exceeds the FIT 90th percentile of incumbent picks, 1.50).
C16: win-continuation re-entry partner — after a base trade exits
at TP, re-enter the same symbol/direction at the next grid check
when a same-direction candidate row exists there; partner legs
admitted only if their full flight interval conflicts with no
base/kept trade on the symbol (addendum 2, verified: zero
same-symbol overlaps; max concurrency 5). 90 partner legs (DISC).

- DISC: n 436 net +5128.59 win 92.20 leftover 69.12 (+6.01)
  epd 2.51, account DD 9.51%
- AUDIT: n 100 net +678.37 win 88.00 leftover 46.39 (+10.06 vs
  control) epd 2.44, account DD 18.77%
- LCT-middle: paired P 100.00%, own q05 51.25% — PASS (strict
  also passes)
- EC22-middle: 16 vs 14 (BRIEF21 basis: checks excl. waived 15
  and report-only 20; battery waived basis 17 vs 15, no failed
  checks) — PASS
- Monte Carlo (paired, 2,500 paths, same draws): median final
  ratio 3.2419x control; P(call) 0.0000 vs 0.0000 — PASS
- Materiality: DISC leftover gain +6.01 >= +5 AND audit leftover
  46.39 >= 36.33 — PASS (HUGE)
- Red lines: audit net +678.37 > 0; discovery not collapsed — PASS
- Overfit clause: PBO 0.00% (not HIGH) — PASS; DSR 0.9999
  (report-only)
- Sizing guard (battery): peak margin (1:1000 basis) 6.02%,
  max DD 19.43% — PASS
- Loss clusters: DISC max consecutive losses 2 (control 2),
  worst rolling 5-trade window -111.80 pips (control -179.28),
  worst floating DD 16.38%; AUDIT max consec 2, worst5 -146.08,
  floating DD 21.35%

VERDICT C20a: **VALIDATED-HUGE**

## SECOND VALIDATED SYSTEM: C20b = C13 + C16
C13: quiet-symbol dual-pick partner (second pick at the same
check, different symbol, concurrency cap 3, only on AUDUSD /
GBPUSD / EURAUD / AUDNZD). C16 re-entry stacked on top (104
partner legs DISC). Conflict-free verified; max concurrency 6.

- DISC: n 533 net +6824.82 win 91.56 leftover 68.97 (+5.86)
- AUDIT: n 127 net +928.74 win 88.98 leftover 49.35 (+13.02)
  epd 3.10, account DD 14.33%
- LCT-middle: paired P 93.87%, own q05 58.66% — PASS
- EC22-middle: 15 vs 14 (battery waived basis 16 vs 15; fails
  only 8_weeks, which the incumbent also fails) — PASS
- Monte Carlo (paired): median final ratio >= 1.00x by a wide
  margin (uncapped-chain compounding artifact; identical-method
  comparison only); P(call) 0.0000 vs 0.0000 — PASS
- Materiality: +5.86 DISC and audit 49.35 >= 36.33 — PASS (HUGE)
- PBO 0.00%; DSR 1.0000 (report-only); sizing guard PASS
- Loss clusters: DISC max consec 2, worst5 -128.46, floating
  DD 15.33%; AUDIT max consec 2, worst5 -148.62, floating
  DD 22.68%

VERDICT C20b: **VALIDATED-HUGE**

## NOVEMBER VERDICT: VALIDATED-HUGE (two systems; C20a primary
on the pre-registered finalist rule — highest discovery leftover
— and the stronger LCT). First material November improvement in
the programme's history: every prior round (BRIEF16–20) closed
November with no validated candidate.

Construction note: the first validation pass caught two
re-entry legs (EURNZD, 2019 + 2025) whose flight overlapped a
later incumbent trade on the same symbol; the builder was
corrected to full-interval conflict checking (2 legs dropped,
DISC leftover 69.20 -> 69.12) and both systems were re-validated
from scratch in the corrected form above.

Nothing integrated, nothing pushed (verdict only, per orders;
integration is LOCAL-only and awaits the user's go-ahead).

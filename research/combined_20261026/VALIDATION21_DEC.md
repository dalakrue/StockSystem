# BRIEF21 DECEMBER — VALIDATION (2026-10-26)

Incumbent: C94-23 (N=105). Frame A3: DISC 2016–2023 (FIT
2016–2020, HOLDOUT 2021–2023), AUDIT 2024+2025 (read once, here).
Cost @2.5. Exact raw-price replay only (C196 pools + dec_walk;
setup: base walk reproduces both published control ledgers
exactly; resim probe 629/634 after resolving TREND/FB sides by
the incumbent's own mom24 rule — see STATUS21_DEC.md).
Gates: BRIEF21.md LOCKED + addendum 1 (middle overfit: PBO
not-HIGH passes, DSR report-only) + addendum 2 (partners within
incumbent checks + at most one extra; conflict-free combination,
verified below).

Control (A3 battery basis): DISC n 505 net +2839.75 win 92.87
leftover 52.31 | AUDIT n 129 net +896.87 win 95.35 leftover
70.68 epd 3.00. (The brief's book figures — audit win 95.45 /
leftover 80.81 — are the V5-book frame; all gate comparisons
here are candidate vs control on the SAME A3 ledgers.)

## WINNER (primary): C20a = C06 + C16
C06: volatility-shock entry veto on C94-23 (drop pool rows whose
vol_z exceeds the FIT 90th percentile of incumbent picks, 1.12).
C16: TP-continuation re-entry partner — after a base trade exits
at TP, re-enter the same symbol/side at the next grid check when
a gate-ok candidate row exists there with the same resolved
side; legs admitted only if their full flight interval conflicts
with no base/kept trade on the symbol (addendum 2, verified:
zero same-symbol overlaps; max concurrency 7). 187 partner legs
(full frame; 157 DISC on the 493-trade vetoed base).

- DISC: n 650 net +4479.75 win 94.92 leftover 66.20 (+13.89)
  epd 3.82, account DD 9.39%
- AUDIT: n 157 net +1135.57 win 96.18 leftover 75.39 (+4.71 vs
  control) epd 3.65, account DD 5.42%
- LCT-middle: paired P 100.00%, own q05 54.61% — PASS (strict
  also passes)
- EC22-middle: 16 vs 14 (BRIEF21 basis: checks excl. waived 15
  and report-only 20; candidate fails only 20_dsr, control
  fails 8_weeks + 14_leftover + 20_dsr) — PASS
- Monte Carlo (paired, 2,500 paths, same draws): median final
  ratio 5068x control (uncapped-chain compounding artifact —
  December's pooled nets compound far beyond any real account;
  identical-method comparison only); P(call) 0.0000 vs 0.0000
  — PASS
- Materiality: DISC leftover gain +13.89 >= +5 AND audit
  leftover 75.39 >= 70.68 — PASS (HUGE)
- Red lines: audit net +1135.57 > 0; discovery not collapsed
  — PASS
- Overfit clause: PBO 2.50% (not HIGH) — PASS; DSR 0.0291
  (report-only per addendum 1; the December battery's own
  BRIEF18 formula, which counts DSR, reads False — BRIEF21's
  locked rules govern this round)
- Sizing guard (battery): peak margin (1:1000 basis) 5.81%,
  max DD 5.40% — PASS
- Loss clusters: DISC max consecutive losses 2 (control 2),
  worst rolling 5-trade window -169.24 pips (control -163.05),
  worst floating DD 14.43% (control 17.97%); AUDIT max consec
  1, worst5 -72.50, floating DD 7.85% (control 9.49%)

VERDICT C20a: **VALIDATED-HUGE**

## SECOND VALIDATED SYSTEM: C20b = C12 + C16
C12: score-gated dual-pick partner (second pick at the same
check, different symbol, concurrency cap 3, only rows with eq
score >= the median positive pool score). C16 re-entry stacked
on top (195 partner legs, full frame). Conflict-free verified;
max concurrency 9.

- DISC: n 679 net +4520.03 win 94.40 leftover 62.94 (+10.63)
- AUDIT: n 163 net +1148.64 win 95.71 leftover 73.70 (+3.02)
  epd 3.79, account DD 5.36%
- LCT-middle: paired P 100.00%, own q05 50.49% — PASS (strict
  also passes)
- EC22-middle: 15 vs 14 (fails 8_weeks, which the incumbent
  also fails, + report-only 20_dsr) — PASS
- Monte Carlo (paired): median final ratio 6349x (same
  compounding-artifact caveat); P(call) 0.0000 vs 0.0000 — PASS
- Materiality: +10.63 DISC and audit 73.70 >= 70.68 — PASS
  (HUGE)
- PBO 2.50% (not HIGH); DSR 0.0043 (report-only); sizing guard
  PASS (peak margin 6.65%, max DD 5.89%)
- Loss clusters: DISC max consec 2, worst5 -163.05 (= control),
  floating DD 17.97%; AUDIT max consec 1, worst5 -72.50,
  floating DD 8.08%

VERDICT C20b: **VALIDATED-HUGE**

## DECEMBER VERDICT: VALIDATED-HUGE (two systems; C20a primary
on the pre-registered finalist rule — highest discovery
leftover — and the stronger EC22 count). The November seed
(vol-shock veto + TP-continuation re-entry) transfers to
December in full: C06 was December's ONLY screen-positive
Phase A variant (+5.45) and C16 its strongest partner
(+9.46 alone).

Screen notes for the record: M15/M30 confirmation vetoes are
catastrophic on December (C01 dLO -50.66, C02 -67.08) — the
opposite of a confirmation month; plain dual-pick dilutes
(C11 -15.78), only the score-gated version is mildly positive;
December's incumbent leaves ~no empty checks (C14 found 0
carry legs) and its loss clusters are so thin (max consec 2,
win 92.87%) that the cluster-activated partner never fired on
discovery (C17 = control exactly).

Nothing integrated, nothing pushed (verdict only, per orders).

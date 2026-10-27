# BRIEF21 APRIL — VALIDATION (2026-10-26)

Incumbent: C87-24 (N=104). Frame A3: DISC 2016–2023 (FIT 2016–2020,
HOLDOUT 2021–2023), AUDIT 2024+2025 (read once, here). Cost @2.5.
Exact raw-price replay only (C189 pools + apr_walk; probe:
apr_walk reproduces the C189/C201 control ledgers EXACTLY — 634
rows, keys + gross + exit fields + scores; p2lib resim 633/634
control picks exact, one 2025 EURJPY data-divergence exception).
Gates: BRIEF21.md LOCKED + addendum 1 (middle overfit: PBO
not-HIGH passes, DSR report-only) + addendum 2 (partners within
incumbent checks + at most one extra; conflict-free, verified).

Control (A3 battery basis): DISC n 502 net +3889.03 win 97.01
leftover 78.67 epd 2.97 | AUDIT n 132 net +1102.07 win 93.94
leftover 68.21 epd 3.00. (The brief's book figures — audit win
92.42 / leftover 60.26 — are the V5-book frame; all gate
comparisons here are candidate vs control on the SAME A3
ledgers.) April's control is exceptionally clean: discovery
max consecutive losses 1, worst5 -72.50 — there are no loss
clusters to fix; the cluster objective was to add volume
without creating any.

## WINNER: C20a = C12 + C16 (composition finalist)
C12: dual-pick partner with eq-score gate (second pick at the
same check, different symbol, eq score >= 1000 = median of
positive eq scores, concurrency cap 3). C16 stacked on top:
TP-continuation re-entry partner — after a base trade exits
at TP, re-enter the same symbol/direction at the next grid
check when a same-direction candidate row exists there; full-
interval conflict check (addendum 2, verified: conflict-free,
max concurrency 7). 208 partner legs DISC (46 dual-pick + 162
re-entry), 263 legs total.

- DISC: n 710 net +6033.02 win 97.75 leftover 84.47 (+5.80)
  epd 4.20, account DD 12.90%
- AUDIT: n 187 net +1971.36 win 95.72 leftover 79.06 (+10.85
  vs control) epd 4.25, account DD 5.04%
- LCT-middle: paired P 100.00%, own q05 74.69% — PASS (strict
  also passes)
- EC22-middle: 16 vs 14 (BRIEF21 basis: checks excl. waived 15
  and report-only 20) — the candidate passes ALL 16 counted
  checks, including 8_weeks, which the incumbent itself fails
  (incumbent also fails 14_leftover and 20_dsr) — PASS
- Monte Carlo (paired, 2,500 paths, same draws): median final
  ratio >> 1.00x control (uncapped-chain compounding artifact;
  identical-method comparison only); P(call) 0.0000 vs 0.0000;
  median peak margin 6.73% vs 4.79%; median chain DD 6.04%
  vs 7.62% — PASS
- Materiality: DISC leftover gain +5.80 >= +5 AND audit
  leftover 79.06 >= 68.21 — PASS (HUGE)
- Red lines: audit net +1971.36 > 0; discovery not collapsed
  — PASS
- Overfit clause: PBO 2.50% (not HIGH) — PASS; DSR 0.9052
  (report-only)
- Sizing guard (battery): peak margin (1:1000 basis) 7.68%,
  max DD 5.14% — PASS
- Loss clusters: DISC max consecutive losses 1 (control 1),
  worst rolling 5-trade window -72.50 (control -72.50 — the
  worst window is untouched incumbent trades), floating DD
  14.04% (control 15.71%); AUDIT max consec 1, worst5 -65.40,
  floating DD 35.28% (control 25.95% — the one real cost:
  more concurrent exposure, max concurrency 7)

VERDICT C20a: **VALIDATED-HUGE**

## SECOND SYSTEM: C20b = C16 (re-entry partner alone)
169 partner legs (131 DISC + 38 AUDIT); conflict-free
verified, max concurrency 5.

- DISC: n 633 net +5107.70 win 97.47 leftover 82.21 (+3.54)
  epd 3.75, account DD 13.79%
- AUDIT: n 170 net +1657.02 win 95.29 leftover 76.19 (+7.98)
  epd 3.86, account DD 5.62%
- LCT-middle: paired P 100.00%, own q05 70.87% — PASS (strict
  also passes)
- EC22-middle: 15 vs 14 — PASS
- Monte Carlo (paired): median ratio >> 1.00x; P(call) 0.0000
  vs 0.0000 — PASS
- Materiality: DISC gain +3.54 < +5 — FAIL (audit clause
  passes); this is the ONLY missed gate
- Red lines PASS; PBO 2.50% (not HIGH); DSR 0.8460
  (report-only); sizing guard PASS (peak margin 5.75%,
  max DD 5.57%)
- Loss clusters: DISC max consec 1, worst5 -72.50, floating
  DD 16.88%; AUDIT max consec 1, worst5 -65.40, floating
  DD 26.11%

VERDICT C20b: **SMALL improvement** (all core gates pass;
materiality missed on the discovery clause alone)

## APRIL VERDICT: VALIDATED-HUGE (C20a primary — the C12+C16
stack; C20b SMALL alongside)

Phase A (C01–C10): NO incumbent improvement survived the
discovery screen — April's incumbent is saturated on every
axis tried. The November/December seed veto (C06, vol-shock
fitted on April's own FIT picks) FAILS here (dLO -2.68):
April joins January in rejecting the veto — it has now
worked only in Nov/Dec, the two months whose high-vol_z
picks were actually waste. M15/M30 confirmation vetoes are
again heavily negative (-40.98 / -53.15 — the catastrophic
pattern from Dec/Feb repeats). C04 TP x0.80 is the closest
variant (-0.50); C08's trailing stop never binds (ledger
identical to control); C09 36h cap -9.71; C10: NO CANDIDATE.
Phase B: unfiltered dual-picks dilute (C11 -10.67, C15
-10.58, C18 -10.70, C13 quiet sleeve -22.57, C19 fresh-signal
-40.87); the SCORE GATE is what makes the dual-pick work
(C12 +2.18); C14 produced zero legs (99.0% check coverage)
and C17 zero legs (the >=2-of-last-3-losses trigger can
never fire on a max_consec-1 incumbent) — both vacuous by
construction in April, as the banked lessons predicted.

## For May — reuse notes
1. The winning composition is now the C12+C16 STACK (score-
   gated dual-pick base + TP-continuation re-entry on top):
   April's winner, and January's near-miss was the same stack
   stopped only by January-specific q05/audit-dilution. The
   re-entry partner is positive in 4 of 5 months (Nov, Dec,
   Jan, Apr) — March is the lone rejection. Keep C12/C16/C20
   in their slots.
2. The vol-shock veto is now 2-for-4 (Nov/Dec yes; Jan/Apr
   no): fit per month as always, but expect it only where
   the month's high-vol_z picks are genuinely waste — a
   clean incumbent (April: win 97%, leftover 78.67) has
   nothing for it to remove, and removal designs in such
   months only walk into the frequency trap.
3. When the incumbent has no loss clusters (max_consec 1),
   cluster-activated partners are vacuous and the gain must
   come from gated ADDED volume; watch audit floating DD as
   the price of concurrency (April C20a: 35.28 vs 25.95 at
   max concurrency 7 — chain P(call) still 0, but it is the
   number to keep an eye on if May's stack runs hotter).
4. Audit-leftover dilution did NOT bite in April (79.06 vs
   68.21) because the partner legs' own leftover is high —
   the score gate is doing that work; an ungated base would
   likely have repeated January's failure.

Nothing integrated, nothing pushed (verdict only, per orders;
integration is LOCAL-only and awaits the user's go-ahead).

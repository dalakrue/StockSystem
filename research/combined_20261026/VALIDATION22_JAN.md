# BRIEF22 (Plan B) JANUARY — VALIDATION (2026-10-26)

Incumbent: C60-03 (N=83). Frame A3: DISC 2016–2023 (FIT
2016–2020, HOLDOUT 2021–2023), AUDIT 2024+2025 (read once,
here). Cost @2.5. Exact raw-price replay only. Gates: BRIEF21
LOCKED + addendum 1 (middle overfit) + addendum 2 (partner
check times / conflict-free) + BRIEF22 addendum
(app-expressible designs only — stateless per check, price
features within H1 / 200-bar M15 reach, no tick-volume
statistics, no closed-trade-ledger state). BRIEF21's finalist
was NOT re-run; all 20 Plan B designs are new constructions.

Control (A3 battery basis): DISC n 513 net +1046.61 win 92.20
leftover 24.25 | AUDIT n 132 net +703.87 win 95.45 leftover
67.13 epd 2.87.

Diagnostics that shaped the round (discovery only): the bleed
is the FB fallback layer — walk FIT leftover FB_EURUSD_h11
-87.54, FB_AUDUSD_h13 -42.37, FB_EURGBP_h17 -22.10, while every
scored equation sits at FIT leftover 100. FIT losses are 20
full -102.5 stops + 8 TIME exits, all but one on FB rows.
Control LCT blocks: [25.89, 30.79, -17.85, 23.57, 41.32,
39.28] — block3 (2018–19) is the q05 anchor.

## BEST CANDIDATE: C20_STACK = C04 + C17
C04: FB-only 24h stall cut (exit fallback trades still
net-negative at the first bar at/after 24h, at that bar's
open; scored equations untouched). C17 stacked on top:
dual-pick partner, second pick = best remaining eligible row
on a different symbol with eq score >= 972 (median of the
incumbent's positive eq scores), concurrency cap 5.
10 partner legs (DISC). Conflict-free verified (addendum 2),
max concurrency 4.

- DISC: n 523 net +1490.92 win 90.82 leftover 34.03 (+9.78)
  epd 2.972, account DD 16.54%
- AUDIT: n 135 net +603.31 win 91.85 leftover 56.14
  (control 67.13) epd 2.935, account DD 9.94%
- LCT-middle: paired P 87.29% PASS, own q05 16.56% — FAIL
  (q05 < 20%)
- EC22-middle: 13 vs 14 — FAIL (candidate fails exactly
  {8_weeks, 13_lct, 14_leftover, 20_dsr-report-only}; control
  fails {8_weeks, 14_leftover, 20_dsr} — again the ONLY count
  difference is 13_lct, a direct consequence of the q05 miss)
- Monte Carlo (paired, 2,500 paths): median final ratio
  9.3907x control PASS; P(call) 0.0000 vs 0.0008 — PASS
- Materiality: DISC gain +9.78 >= +5 PASS; audit leftover
  56.14 < incumbent 67.13 — FAIL
- Red lines: audit net +603.31 > 0; discovery not collapsed —
  PASS
- Overfit clause: PBO 2.50% (not HIGH) — PASS; DSR 0.0003
  (report-only)
- Sizing guard (battery): PASS
- Loss clusters: DISC max consecutive losses 3 (control 3),
  worst rolling 5-trade window -200.50 (control -255.61),
  floating DD 17.85% (control 28.09%); AUDIT max consec 2,
  worst5 -64.72, floating DD 14.62% (control 14.62%)

VERDICT C20_STACK: **NOT VALIDATED** (fails LCT-middle q05,
EC22-middle count, and the materiality audit clause)

## FINALIST 2: C04 = FB-only 24h stall cut alone
- DISC: n 513 net +1415.92 win 90.64 leftover 32.88 (+8.63)
  epd 2.915 | FIT leftover 13.61 -> 25.94, HOLDOUT 42.20 ->
  44.66 (no holdout cost — the screen's cleanest Phase A win)
- AUDIT: n 132 net +580.81 win 91.67 leftover 55.20
- LCT-middle: P 81.52%, q05 15.35% — FAIL
- EC22-middle: 13 vs 14 — FAIL (same single-check difference)
- Monte Carlo: ratio 5.0778x PASS; P(call) 0.0000 vs 0.0008
  PASS
- Materiality: DISC PASS; audit leftover 55.20 < 67.13 FAIL
- Red lines PASS; PBO 2.50%; DSR 0.0002 (report-only);
  sizing guard PASS; conflict-free n/a (single system)
- Loss clusters: DISC max consec 3, worst5 -200.50, floating
  DD 17.89%; AUDIT max consec 2, worst5 -64.72, floating DD
  14.75%

VERDICT C04: **NOT VALIDATED** (same three clauses)

FINALIST 3: C10 (Phase A composition of C04 + C05) produced
a ledger IDENTICAL to C04 (the SL x0.60 component is fully
subsumed by the stall cut — stalled trades exit before the
tighter stop binds) and therefore identical validation
numbers on every gate. Recorded as a consistency check, not
a separate candidate. NOT VALIDATED (same three clauses).

## JANUARY PLAN-B VERDICT: NO IMPROVEMENT (at the locked standard)

Plan B found a genuinely different, fully app-expressible
engine — the FB-only stall cut — and it does on discovery
exactly what the brief asked: DISC leftover +8.63 alone,
+9.78 stacked; FIT leftover nearly doubled (13.61 -> 25.94);
Monte Carlo passes both clauses with the best ratios January
has produced; loss clusters improve on every discovery
measure. It is stopped by the same locked clauses as
BRIEF21, through the mirror-image mechanism:

1. **The stall cut transfers value between segments.** On
   discovery it changes 32 trades: -1561.8 -> -1273.9
   (+287.9 rescued from slow bleeders). On audit it changes
   only 7 trades: -57.4 -> -174.1 — five audit trades that
   would have reached TP are cut at 24h while temporarily
   negative (audit TP count 126 -> 121). January's audit
   years are precisely the regime where slow trades recover;
   the rule fitted on FIT behaviour amputates them. Audit
   net falls BELOW control (+580.81 vs +703.87) and audit
   leftover drops 67.13 -> 55.20, failing materiality's
   audit clause by 11.93 pts.
2. **q05 needs every block lifted; the stall cut moves the
   weakness.** Candidate blocks: [44.68, 9.58, 1.29, 56.03,
   43.69, 42.31] vs control [25.89, 30.79, -17.85, 23.57,
   41.32, 39.28]. Block3 is fixed (-17.85 -> +1.29) but
   block2 collapses (30.79 -> 9.58): in 2017–18, trades
   negative at 24h disproportionately recover later. Draws
   pooling blocks 2+3 still land at leftover ~5-15, so
   q05 = 15.35 (C04) / 16.56 (stack) against the 20 line,
   even though paired P passes (81.52 / 87.29).

This is NOT a SMALL verdict either (SMALL requires all core
gates; LCT + EC22 are core). Across BRIEF21 + BRIEF22,
January has now failed the same three clauses by three
different mechanisms (re-entry dilution, score-dual
dilution, exit-rule segment transfer). The month's
discovery-weak segments and its audit segment want opposite
treatment of the same slow fallback trades; no stateless
feature tried in 40 designs separates "bleeder" from
"recoverer" at the decision point (the MFE<0.5R refinement,
C09, was numerically identical to the blunt cut — at 24h
the recoverers have not yet shown 0.5R of favourable
excursion either).

## App-expressibility of the best candidate (C20_STACK)
- C04 stall cut: a per-trade exit rule evaluated on the
  trade's OWN bars since entry — at the first M15 bar
  starting >= 24h after entry, if marked net (previous bar
  close, cost incl.) < 0, exit at that bar's open. Inputs:
  entry time/price + M15 OHLC since entry. No other trade's
  history, no exit_reason of any past trade, no volume.
  "FB-only" scopes it to the three fallback equations —
  static per-month equation identities in the app's config.
- C17 dual-pick: at a check, after the incumbent's pick,
  take the best remaining eligible row on a different symbol
  whose eq score >= 972 (a static config constant: median of
  the incumbent's positive eq scores), only while live
  positions < 5. Inputs: the check's own candidate rows
  (from the incumbent equations' H1/M15 price features) and
  the currently-open symbols/count — exactly the selector
  inputs the app already passes (October dual-pick
  precedent, which integrated faithfully).
- Every feature is computable at a single check from H1
  bars or M15 bars inside a 200-bar window; thresholds are
  FIT-fitted static constants. No tick-volume statistic
  (vol_z never used), no closed-trade-ledger state.

## Screen record (discovery dLO vs control 24.25)
Phase A: C01 FB ADX-skip +0.39 (FIT LO 34.04 but HOLDOUT
9.32 — segment flip, screen-caught) · C02 FB BUY-skip +2.67
(HO -10.21, caught) · C03 FB ATR-mid-skip -4.27 · C04 FB
stall +8.63 POSITIVE · C05 FB SLx0.60 +0.54 POSITIVE (sub-
sumed by C04) · C06 FB TPx2.0 -29.28 (fallback winners must
stay capped) · C07 counter-trend-only -12.53 · C08 ADX veto
all -6.18 (FIT up, HO 8.40 — same flip) · C09 refined stall
(MFE<0.5R) +1.37 but HO -12.99, caught; numerically the
BRIEF21 C03 trade set · C10 = C04 (see above).
Phase B: dual-picks uniformly small-positive — C11 +0.52,
C12 +0.78, C13 +0.78, C14 +0.91, C17 +1.29 (best), C18
+0.78, C19 +0.39 — real but sub-material alone; they stack
additively (+1.15 of C20's +9.78 came from C17 on the C04
base). Fresh-signal partners fail in January in every form
tried across both rounds: C15 extra-check (15:00 UTC,
tightened, strong symbols) -11.99; C16 FB-check companion
-17.52. That family is closed for January.

## Reuse notes (Feb/Mar/May Plan B)
1. The stall cut is a real discovery engine where a month's
   losses are slow bleeders on a fallback layer — but ALWAYS
   check its audit sign before celebrating: it is an exit
   rule, so it rewrites the audit ledger too, and audit
   regimes that reward patience will pay for it.
2. LCT q05 is a WEAKEST-BLOCK statistic in disguise: audit
   any candidate's six block leftovers; one fixed block +
   one broken block still fails.
3. Segment-flip gates (ADX/BUY skips: FIT way up, holdout
   way down) are January's recurring mirage — the discovery
   screen's holdout-margin rule caught every one; keep it.
4. Dual-pick partners in 100%-coverage months add few legs
   (C17: 10) but they are consistently non-diluting on
   discovery and stack additively — worth keeping as the
   default Phase B stack component.

Nothing integrated, nothing pushed (verdict only, per orders).

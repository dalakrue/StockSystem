# BRIEF22 MAY (Plan B) — VALIDATION (2026-10-26)

Incumbent: C88-03 (N=66, A3 control). Frame A3: DISC 2016–2023
(FIT 2016–2020, HOLDOUT 2021–2023), AUDIT 2024+2025 (read once,
here). Cost @2.5. Exact raw-price replay only (C202 pools;
walk_multi_may probe-verified against the BRIEF21 control
ledger: 411 trades, keys + gross exact). Gates: BRIEF21.md
LOCKED + addendum 1 (middle overfit: PBO not-HIGH passes, DSR
report-only) + addendum 2 (partners within incumbent checks
10:30/16:30/18:30 UTC + at most ONE extra check; conflict-free
combination, verified per finalist). ALL designs
app-expressible per the BRIEF22 addendum: stateless per check,
price/score features only, NO re-entry, NO tick volume
(vol_z), NO closed-trade-ledger state.

Control (A3 battery basis): DISC n 317 net +3389.11 win 99.37
leftover 93.70 epd 1.781 | AUDIT n 94 net +851.12 win 95.74
leftover 76.58 epd 2.089. Exactly 2 losing discovery trades
(2016 GBPUSD h10 momS, 2017 CHFJPY h10 momS, both −102.50),
holdout leftover 100.00.

## THE STRUCTURAL FACT (probe22_may.py, measured before design)

The 2 losses sit in LCT blocks 0 and 1 of the check-sorted
discovery ledger; control blocks 2–5 have leftover exactly
100.00 (no losses). A candidate's leftover is bounded by 100,
so in the paired block bootstrap (6 blocks, draw 3 with
replacement) the candidate can strictly beat the control ONLY
on draws that include block 0 or 1: **paired P ≤ 1 − (4/6)³ =
70.37% < 80% for ANY May candidate in this frame.** LCT-middle
is unsatisfiable for May — not a quality judgment, an
arithmetic property of a near-perfect control. Empirical
confirmation below: three structurally different finalists all
measure P = 69.68% (BRIEF21's two finalists: 69.68% / 66.83% —
five May candidates across two rounds, none above 69.68%).

## FINALIST 1: C20a = C01 + C16 (composition finalist)
C01: direction-relative RSI-extension veto — a pool row is
vetoed when d×(rsi14−50) < −18.68 (FIT-picks q10 of the same
quantity; d = +1 BUY / −1 SELL); vetoed rows fall through to
the next eligible row, a check whose rows are all vetoed is
skipped. C16 stacked: volr-banded score-gated dual-pick
(second pick at the same check, score ≥ pool median 1000.29,
price-volr = M15 ATR14 / trailing-96-bar median ATR ≤ FIT
q90 1.439, live cap 3; 33 partner legs on the vetoed base).
App-expressible: both rules are per-check functions of the
check's own price/score fields (volr needs ≤ ~111 M15 price
bars); occupancy = current open positions (October selector
pattern). Conflict-free verified, max concurrency 4.

- DISC: n 335 net +3800.07 win 100.00 leftover **100.00**
  (+6.30) epd 1.882, account DD 0.12% — a PERFECT discovery
  ledger: zero losses in 8 years (control: 2)
- AUDIT: n 95 net +860.60 win 96.84 leftover **78.73**
  (control 76.58) epd 2.111 — audit net AND leftover both
  ABOVE control: the first May combination ever to pass the
  materiality audit clause
- LCT-middle: paired P **69.68%**, own q05 **100.00** — FAIL
  on P only, at the structural ceiling (≤70.37%)
- EC22-middle: 15 vs 15 — PASS (candidate fails only 13_lct
  in the count; flips 14_leftover: audit 78.73 > 76.58)
- Monte Carlo (paired, 2,500 paths): median final ratio
  23.10x control (uncapped-chain compounding artifact;
  identical-method comparison only); P(call) 0.0000 vs
  0.0000 — PASS both clauses; sizing guard PASS (peak margin
  6.06% on the 1:1000 basis, max DD 11.18%)
- Materiality: DISC +6.30 ≥ +5 PASS; audit leftover 78.73 ≥
  76.58 PASS — BOTH clauses pass, a May first
- Red lines: audit net +860.60 > 0; discovery not collapsed
  — PASS
- Frequency: epd_disc 1.882 < 2 — FAIL (short by 21 trades:
  the veto nets −15 disc trades, the volr dual adds back 33
  of the 44 it adds on the plain base); epd_audit PASS
- Overfit: PBO 17.50% (MEDIUM, not HIGH) — PASS; DSR 0.9997
  (report-only)
- Loss clusters: DISC max_consec 0 (control 1), worst5
  **+37.50** (control −68.34 — no losing 5-trade window
  exists), floating DD 5.03% (control 5.89%); AUDIT
  max_consec 1 (control 2), worst5 −50.32 (control −102.58),
  floating DD 14.76% (control 22.00%) — clusters improved on
  BOTH frames
- Leg anatomy (decisive): ADDED disc 47 legs (veto
  replacements + dual legs) — ALL winners, net +503.59,
  worst leg +7.50. REMOVED disc 29 rows, net +92.63,
  including BOTH −102.50 losers. ADDED audit 11 legs net
  −10.77 (1 loss −102.50) — the dual legs alone are still
  audit-negative; REMOVED audit 10 rows net −20.25 (incl. 2
  of the audit frame's 4 losers) — the veto's audit removals
  outweigh the legs, which is why the combined audit rises.

VERDICT C20a: **NOT VALIDATED** (fails LCT-middle P —
structurally capped — and epd_disc). Every other gate,
including both materiality clauses, passes.

## FINALIST 2: C01 (pure RSI-extension veto)
- DISC: n 302 net +3438.17 win 100.00 leftover 100.00
  (+6.30) epd 1.697 | AUDIT: n 87 net +783.87 win 96.55
  leftover 77.08 (≥ 76.58) epd 1.933
- LCT P 69.68% / q05 100.00 — FAIL (same ceiling)
- EC22 15 vs 15 PASS; MC median ratio 1.0259x, P(call)
  0.0000 vs 0.0000 PASS; materiality BOTH clauses PASS;
  red lines PASS; PBO 17.50%, DSR 0.9996; sizing PASS
- FAILS: LCT-middle, epd_disc, epd_audit (the veto alone
  removes volume on both frames: removed audit 10 rows net
  −20.25 incl. 2 losers; added 3 fall-through replacements
  net −87.50 incl. 1 loser)
- Clusters: DISC max_consec 0, worst5 +37.50; AUDIT
  max_consec 1, worst5 −40.55 (control −102.58)

VERDICT C01: **NOT VALIDATED** (LCT + both frequency gates).

## FINALIST 3: C20b = C19 (pick-strength dual alone)
Second pick only at checks where the base pick scores ≥
pool q75 (1000.41); second pick ≥ median, cap 3.
- DISC: n 349 net +3734.18 win 99.43 leftover 94.25 (+0.55)
  epd 1.961 | AUDIT: n 103 net +831.41 win 95.15 leftover
  68.98 (control 76.58) epd 2.289
- LCT P 69.68% / q05 87.43 — FAIL; EC22 14 vs 15 — FAIL
  (13_lct + 14_leftover); MC ratio 8.8061x, P(call) 0 vs 0
  PASS; PBO 2.50%, DSR 0.9998; sizing PASS
- Materiality FAIL both clauses (disc +0.55 < +5; audit
  68.98 < 76.58); epd_disc FAIL (1.961, short by 7 trades)
- Anatomy: disc legs 33, ALL winners, net +352.57; audit
  legs 9, net **−19.71** (1 loss) — BRIEF21's audit-negative
  dual-leg pattern, milder but unchanged in sign

VERDICT C20b: **NOT VALIDATED**.

## MAY PLAN-B VERDICT: NO IMPROVEMENT

No finalist validates, and SMALL is equally impossible —
LCT-middle is a core gate and it fails for every finalist at
the structural ceiling. C88-03 stands. But Plan B changes
May's factual picture in three durable ways:

1. **The losers ARE identifiable.** BRIEF21's "no FIT-fitted
   rule identifies the losers" was a property of the features
   it tried (vol_z, ADX, confirmation). The direction-relative
   extension family (RSI/CMO/ret4h/DI, all FIT-q10 fitted)
   finds them: SIX different veto variants (C01–C04, C06,
   C07) each produce a perfect discovery ledger (leftover
   100.00, zero losses, FIT and HOLDOUT both 100.00). The
   signature is robust, not knife-edge: both losers are
   momentum SELLs taken against extreme upward extension
   (rsi14 pctile 0.95–1.00, cmo14 0.94, ret4h 0.95–1.00,
   di_diff 0.98 — direction-relative). Score-floor (C05)
   fails (−0.30): score alone does not separate them.
2. **Dual-pick volume is discovery-perfect but audit-negative,
   again.** Every gated dual family's discovery legs are
   lossless (C11 18 legs +169.69; C14 22 +211.87; C15 28
   +279.50; C16 44 +482.43, epd 2.022 alone; C19 33 +352.57;
   C17 silent-check fresh 8 +87.90 — all 0 losses). On audit
   the same families' legs lose money (C19 −19.71; stack
   −10.77). What finally carries a May combination's audit
   is not the legs but the veto's audit-side removals.
   Geometry scale-ups are catastrophic (TP×1.25 −33.17;
   TP+SL×1.25 −30.89 — May's small-target geometry is
   load-bearing), and the fresh signal is toxic at ANY
   off-grid time (14:30 sleeve C18: −37.08, 163 legs, 22
   losses — closing the family BRIEF21 opened at 19:30,
   −72.36). The q90 score gate (C12) is vacuous: zero legs.
3. **The binding constraint is the gate, not the system.**
   C20a passes red lines, EC22 count, Monte Carlo,
   conflict-freedom, sizing, and BOTH materiality clauses,
   with a perfect discovery ledger and improved loss
   clusters on both frames. It fails (a) LCT P — capped at
   70.37% for any candidate by the control's own perfection
   (blocks 2–5 at exactly 100.00), and (b) epd_disc 1.882 —
   short 21 trades. On (b): the union of ALL partner-family
   discovery legs is 64 (plain-base measurement); a
   union-of-families stack on the vetoed base was not a
   frozen finalist and its vetoed-base yield is unmeasured
   (it would need ≥54 of 64 legs to survive changed
   occupancy) — and it would still fail (a). The verdict
   does not depend on it.

C20a is recorded as May's Plan-B best: the strongest May
system ever measured under this programme, blocked by one
arithmetically unsatisfiable gate and one volume clause —
not by quality. If the user ever scopes a waiver for May
(Kind-1, his prerogative — cf. the 2026-10-25 precedent),
C20a is the candidate on file, fully app-expressible.

Nothing integrated, nothing pushed (verdict only, per
orders). Records: brief22/may/results/ (C01–C20 screens +
validation22_may.json), brief22/may/logs/, STATUS22_MAY.md,
probe22_may.py (diagnostic + ceiling proof).

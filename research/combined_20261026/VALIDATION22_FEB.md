# BRIEF22 FEBRUARY (Plan B) — VALIDATION (2026-10-26)

Incumbent: C85-23 + C96-N082 (N=104). Frame A3: DISC 2016–2023
(FIT 2016–2020, HOLDOUT 2021–2023), AUDIT 2024+2025 (read once,
here). Cost @2.5. Exact raw-price replay only. Gates: BRIEF21.md
LOCKED + addendum 1 (middle overfit: PBO not-HIGH passes, DSR
report-only) + addendum 2 (partners within incumbent checks + at
most one extra; conflict-free) + BRIEF22 addendum (designs must
be APP-EXPRESSIBLE: stateless per check, price/score features
within the app's data reach, NO closed-trade-ledger state, NO
tick-volume statistics — BRIEF21's vol_z veto and re-entry
partner are both out of scope here).

Machinery: probe-verified before any cycle ran — the BRIEF21
February walk reproduces the published control exactly (DISC
n 379 LO 66.21), and the new multi-pick walk reproduces
BRIEF21's verified C12 log exactly (n 405/405, identical nets).

Control (A3 battery basis): DISC n 379 net +3256.95 win 94.72
leftover 66.21 epd 2.354 | AUDIT n 103 net +342.81 win 85.44
leftover 28.22 epd 2.512. Clusters: DISC max_consec 1 worst5
-131.32 floatDD 15.23; AUDIT max_consec 2 worst5 -118.72
floatDD 14.13.

## FIT decomposition (2016–2020 picks, the design input)
EURUSD is 87/230 FIT picks, ALL of them FB rows (h11 LO 76.91,
h16 LO 60.41) carrying sentinel scores (~-1e8) — the eq score
cannot grade EURUSD. EURUSD's FIT bleed is 6 TIME exits
(-328.20) + 1 SL. Toxic FIT bands: atr15 mid-band (EURUSD
(9.74, 11.52] LO -6.99) — but both ATR-band vetoes screened
negative (walk fall-through dynamics dominate ledger bands).
The tick vol_z toxic zone is a mid-band, not the tail. The
PRICE vol ratio (M15 ATR14 / trailing 96-bar median) separates
cleanly: FIT picks above its q90 (1.643) run LO 53.99 vs 84.32
below — the price-based replacement for the veto works.

## Screens (discovery only; frequency screened from day one)
Phase A: C01 price-vol veto (volr > 1.643, fall-through)
+8.08 @ epd 2.124 — BEATS BRIEF21's tick-volume veto screen
(+4.09). C05 EURUSD-only volr veto +9.02 @ 2.186 (best single
gate). C06 stack of C01+C02 +4.88. C07 volr q75 veto +6.08 but
epd 1.845 — frequency-killed. C04 EURUSD-16:30 veto +13.48 but
epd 1.876 — frequency-killed (the suppression trap in milder
form: removing the h16 block still removes too much volume).
Dead: C02/C03 ATR-band vetoes (-2.00/-4.33), C08 EURUSD
TPx0.80 (-2.34), C09 ADX band (-4.54). C10 composition = C01
(the two best gates are nested volr vetoes).
Phase B (raw control): every gated dual variant positive but
small: C11 q40 dual +2.15, C12 relative dual +1.93, C13 cap-5
dual +2.03, C14 non-EURUSD dual +1.77 (= BRIEF21 C12 exactly;
the median gate already excludes sentinel-scored EURUSD rows),
C15 triple-pick +2.09, C16 same-direction dual +0.67.
Stacks: C17 (C05 + median dual) +10.40 @ 2.348, C18 (C10 +
median dual) +9.48 @ 2.273, C19 (C05 + q40 dual) +10.71 @
2.391, C20 (C05 + cap-5 dual) +10.57 @ 2.360.

## Finalists — one anatomy
Four stacks were validated (see picker note below). ALL FOUR
pass EVERY core gate — red lines, LCT-middle (three of four
also pass STRICT), EC22-middle >= incumbent, win > 80 both
frames, entries/day >= 2 BOTH frames, Monte Carlo median
2.26x–7.14x with P(call) 0 vs 0, discovery materiality
+9.48..+10.71 — and ALL FOUR miss exactly one clause: the
materiality AUDIT clause (audit leftover >= incumbent).
Their audit nets are also all BELOW control (still positive):
the discovery-fitted volr base + gated duals add +14% net on
2016–2023 and subtract ~14–20% on 2024–2025.

## BEST CANDIDATE: C19 = C05 + C11-style loose dual (SMALL)
C05: EURUSD rows ineligible when volr > 1.643 (fall-through).
Partner: second pick at the same check, different symbol,
score >= 959 (q40 of positive pool scores), cap 3.
- DISC: n 385 net +3715.92 win 96.36 leftover 76.92 (+10.71)
  epd 2.391, FIT LO 85.20, HOLDOUT LO 63.78 (control 51.89)
- AUDIT: n 105 net +296.42 win 85.71 leftover 25.63
  (control 28.22, -2.59) epd 2.561, DD 8.34%
- LCT-middle: paired P 96.63%, own q05 60.13% — PASS (STRICT
  also passes)
- EC22-middle: 14 vs 13 (candidate fails 3_boot, 14_leftover,
  report-only 20_dsr; control also fails 8_weeks) — PASS
- Monte Carlo (paired, 2,500 paths): median final ratio
  7.1363x — PASS; P(call) 0.0000 vs 0.0000 — PASS
- Materiality: DISC +10.71 >= +5 PASS; audit leftover 25.63 <
  28.22 — FAIL (sole missed clause)
- Red lines PASS; PBO 2.50% (not HIGH); DSR 0.1819
  (report-only); sizing guard PASS (peak margin 47.71%,
  max DD 8.53%)
- Loss clusters: DISC max_consec 1 (= control), worst5
  -131.32 (= control — worst window is untouched incumbent
  trades), floatDD 11.62 (control 15.23); AUDIT max_consec 2
  (= control), worst5 -118.72 (= control), floatDD 16.41
  (control 14.13)
- Conflict-free verified, max concurrency 5

## Other validated finalists (all SMALL, same sole miss)
- C20 stack (C05 + cap-5 median dual): DISC n 380 net
  +3691.53 leftover 76.78 (+10.57); AUDIT identical to C19
  (n 105 net +296.42 leftover 25.63); LCT P 96.63% q05 59.70%
  (strict passes); EC22 14 vs 13; MC ratio 6.1511, P(call) 0.
- C17 (C05 + median dual cap 3): DISC n 378 net +3657.15
  leftover 76.61 (+10.40); AUDIT n 103 net +281.42 leftover
  24.62 (-3.60); LCT P 96.63% q05 59.70% (strict passes);
  EC22 14 vs 13; MC 5.1331, P(call) 0.
- C18 (C10 + median dual): DISC n 366 net +3472.46 leftover
  75.69 (+9.48); AUDIT n 102 net +273.92 leftover 24.11
  (-4.11); LCT P 92.64% q05 58.00% (middle passes); EC22
  13 vs 13; MC 2.2598, P(call) 0.

## Finalist-picker note (transparency)
The picker inherited from validate21_feb.py excludes the key
'C20' from the "others" pool — correct in BRIEF21 (C20 was a
composition pointer), wrong here (BRIEF22's C20 built a real
candidate). The main pass therefore validated C19, C17, C18;
the C20 stack (+10.57, second-best by discovery) was validated
in a supplementary pass with identical machinery and merged
into validation22_feb.json. All four verdicts are the same
kind (SMALL), so the deviation changes no outcome.

## App-expressibility of the best candidate (C19)
- EURUSD volr gate: volr = ATR(14) on M15 at the entry bar /
  median of ATR(14) over the trailing 96 M15 bars; threshold
  1.643 is a fixed constant (FIT q90 of incumbent picks).
  Data: M15 OHLC price bars only, <= ~111 bars back from the
  entry bar — inside the app's 200-bar M15 window. Stateless:
  a function of price bars at the check; never reads trade
  history. ( atr15_pips / adx14-style indicator family; the
  blocked BRIEF21 feature was tick-volume vol_z — not used.)
- Score-gated dual partner: the score is the incumbent
  family's own per-check selection score (the app computes it
  for its own ranking — October dual-pick precedent); gate
  959 is a fixed constant; the partner fires only at
  incumbent checks (11:30/13:30/16:30 UTC — NO extra check
  time used), on a different symbol than the primary, under
  concurrency cap 3 (live open-position count, which the
  app's selector already tracks; per-symbol occupancy, no
  same-symbol doubles, incumbent priority — addendum 2).
- No exit-triggered legs, no closed-trade-ledger reads, no
  tick-volume statistics anywhere in the design.

## FEBRUARY PLAN-B VERDICT: NO IMPROVEMENT at the HUGE bar —
## best result SMALL (C19)
BRIEF22 solved the problem BRIEF21 died on: inside the
app-expressible space, February now has a construction that
keeps EURUSD's volume, restores frequency on BOTH frames
(2.39/2.56 per day), passes LCT strict, EC22 ahead, and the
Monte Carlo median at 7.14x — with a +10.71 discovery
leftover gain. What it does not do is transfer: on the
unseen audit the same construction dilutes leftover by
2.59 pts and earns LESS net than the incumbent (+296.42 vs
+342.81). The materiality audit clause — January's killer
in BRIEF21, trivially passed by BRIEF21's February finalists
— is February's killer here. February's discovery-to-audit
transfer gap, not frequency, is now the binding constraint:
every volr/dual stack fitted on 2016–2023 lands its audit
leftover in a narrow 24.11–25.63 band under the incumbent's
28.22. Not a SMALL-is-nothing result: C19 is a fully validated
SMALL improvement under the locked gates and is February's
strongest app-expressible candidate in any round — but the
round's HUGE bar is not met, and the verdict at that bar is
NO IMPROVEMENT.

Nothing integrated, nothing pushed (verdict only, per orders).

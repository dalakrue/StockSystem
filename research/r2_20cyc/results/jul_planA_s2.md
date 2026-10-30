VERDICT: Jul planA s2 — NO IMPROVEMENT

# Jul Plan A Scenario 2 — 20 cycles CREATED natively for 07:30 MMT
Run 2026-10-30. Research level only; no push, no live app opened.
CREATION, not incumbent replay (brief §5): equations designed for
the 07:30 MMT slot (entry bar 01:00 UTC, stored check 01:30 UTC;
features from bars strictly before the entry bar, entry at the
entry-bar open, H1 exit SL-first, hold ≤ 48 bars, one pick per
check = strongest |direction-source momentum| among passing
symbols, 28 symbols). H1 primary; M15 = confirmation only.
DXY: BLOCKED-DATA (Wave 0, Twelve 429) — dollar legs are
DOLLARIDX-labelled only (Dukascopy H1, mom24, NO volume condition;
S08/S20). Runners: run_jul_planA_s2.py (pre-registered design;
pre-load version OOM-killed alongside parallel lanes after the
probes) and run_jul_planA_s2b.py (disk-cache/array version — it
reproduced both probe ledgers EXACTLY before the cycles ran).
Raw: jul_s2_run.json, jul_s2_*_slot_ledger.csv,
jul_s2_combined_ledger.csv.

## Base of record — D3 (attempt 4, EC-passing form)
D3 exists, so grading is against D3 (task order), ledger
results/jul_attempt4_D3_ledger.csv, asserted before mining:
- DISC: n 509, net +6325.13, win 97.25%, **leftover 89.11%**, epd 2.925
- AUDIT: n 132, net +1140.61, win 95.45%, **leftover 77.01%**, epd 2.870
- MC verbatim: P(profit) 1.0000 · DD obs 125.67 → **DD p95 172.54
  vs own cap 188.51 PASS** · cluster obs −125.67 → p95 125.67 vs
  cap 188.51 PASS · consec 2 → 2 PASS · flag TRUE
- Full-stop (−102.50 net) density: **0 DISC / 1 full-period**
  (the density D3 was built to remove).
References: C18+B04 combined 80.59 / 68.84, MC flag FALSE (DD p95
197.50 vs own cap 188.51); incumbent cycle78 66.10 / 64.97, MC
flag FALSE (DD p95 233.91). Jul convention throughout: DISC
174 d / AUDIT 46 d, leftover = net ÷ sum of positive NET @2.5.

## Slot + probe evidence (07:30 is forced — Jul already uses 00:30)
- Behaviour at the 01:00 UTC July bar (DISC years, 28 symbols):
  median H1 volume 5,279, median H1 range 13.97 pips — a thin,
  low-range hour (compare the incumbent's first check at 15:00
  UTC, July's highest-volume hour per the Plan C study).
- P-base (mom4 + M15 mom align + M15 vol_z > −1, TP20/SL100):
  DISC n 174, net +389.70, win 79.89%, leftover **16.09%** ·
  AUDIT n 46, net **−276.60**, win 73.91%, leftover **−46.49%**
- P-mom16 (mom16 + M15 mom align + H1 vol_z > −0.5, TP20/SL100):
  DISC net −423.10, leftover **−19.17%** · AUDIT net +278.60,
  leftover +41.53%
The two probes already disagree in sign across segments — the
Jan/Feb/Sep S2 regime-flip signature, present at probe stage.

## Created cycle selected (DISC-only) — S12, and its standalone form
Selection (pre-registered): among the 10 cycles with standalone
DISC net > 0 (S01, S06, S08, S09, S10, S12, S14, S16, S17, S20),
the one maximising D3+S2 combined DISC leftover = **S12**
(mom4 dir + M15 mom4 align, TP10/SL60 — the short-TP/tight-SL
form; notably the ONLY TP/SL geometry with zero −102.50 stops).
Standalone S12:
- DISC: n 174, net +157.20, win 89.66%, leftover 13.44%, epd 1.000
- AUDIT: n 46, net **−184.20**, win 80.43%, leftover **−66.38%**, epd 1.000
- Full-stops: 0 DISC / 0 full-period (SL60 geometry).
Merged second-priority against D3 (drop if D3 holds the symbol
open at slot entry): **210 accepted** (DISC +165, AUDIT +45).

## Combined D3+S12 vs base D3 — full numbers
| Metric | D3 base | D3+S12 combined |
|---|---|---|
| DISC n / net | 509 / +6325.13 | 674 / +6414.83 |
| DISC leftover | **89.11%** | **78.23%** (−10.88) |
| DISC win % / epd | 97.25 / 2.925 | 95.25 / 3.874 |
| AUDIT n / net | 132 / +1140.61 | 177 / **+948.91** (−191.70) |
| AUDIT leftover | **77.01%** | **54.19%** (−22.82) |
| AUDIT win % / epd | 95.45 / 2.870 | 91.53 / 3.848 |
| LCT Jul per-check vs D3 | — | P 100.00 / q05 83.14 — VACUOUS, see below |
| LCT canonical vs D3 | — | **P 2.13% / q05 66.77% — middle FAIL** |
| LCT canonical vs cycle78 | — | P 80.33% / q05 66.77% — middle PASS |
| MC P(profit) | 1.0000 | 1.0000 |
| MC DD obs → p95 vs OWN cap | 125.67 → 172.54 vs 188.51 PASS | 146.28 → **200.18 vs 219.42 PASS** |
| MC cluster obs → p95 vs cap | −125.67 → 125.67 vs 188.51 PASS | −125.67 → **142.30** vs 188.51 PASS |
| MC consec obs → p95 | 2 → 2 PASS | 2 → 2 PASS |
| MC verbatim flag (own-relative) | TRUE | TRUE |
| Full-stops DISC / full-period | 0 / 1 | 0 / 1 (slot adds none) |
| PBO canonical (family-23) | 55.00% (family reading) | **55.00% FAIL (> 50)** |
| DSR canonical (family-23) | 1.0000 | 1.0000 PASS |
| PBO / DSR (R2-engine CSCV 2nd reading) | — / 1.0000 | 27.78% PASS / 1.0000 |
| Decay | not FAIL | not FAIL (yearly leftover positive 2016–2025; AUDIT/DISC ratio 0.85 → 0.69) |

LCT disclosure: the Jul per-check LCT indexes on the BASE's DISC
checks, so slot picks at the new 01:30 checks are invisible to it
— its P 100.00 / q05 83.14 merely restates D3 at its own checks
and is reported as vacuous, not as a pass. The operative paired
reading is the canonical (validate_new8) LCT vs D3: **P 2.13%
FAIL**. Family-23 = {cycle78, D3, C18+B04, 20 D3+S2 combined
ledgers} daily DISC series; PBO 55.00% is the family reading for
the winner index (the D3 index reads the same family PBO).

## MC cluster/DD arms BEFORE → AFTER (the density question)
The added flow does NOT re-densify the −102.50 stacking tail —
because the DISC-selected form is the SL60 geometry: full-stops
stay 0 DISC / 1 full-period, worst-cluster OBS is unchanged at
−125.67, and the verbatim flag stays TRUE. But every resampled
arm moves the WRONG way: DD obs 125.67 → 146.28, DD p95 172.54 →
200.18 (+27.64; the own cap rises to 219.42 only because DD obs
rose), cluster p95 125.67 → 142.30 (+16.63). D3's hard-won DD
margin (15.97 under cap) becomes a pass carried by a higher cap,
not by a thinner tail. The other geometries were worse: the
TP20/SL100 creations carry **7–20 DISC full-stops standalone**
(S14 20, S11 17, S07 17, S03 16) — exactly the density D3 removed
— and the explicit cluster controls do not rescue them (S16
symbol-cooldown combined AUDIT 57.18%; S17 global skip-1 combined
AUDIT 70.93%, both below base 77.01%).

## All 20 creations — standalone → combined (vs D3 89.11 / 77.01)
| Cyc | Standalone DISC net/left | Standalone AUDIT net/left | FS DISC/full | Acc | Comb DISC left | Comb AUDIT left/net |
|---|---|---|---|---|---|---|
| S01 | +390 / 16.09 | −277 / −46.49 | 11/18 | 209 | 69.98 | 41.12 / +847 |
| S02 | −423 / −19.17 | +279 / 41.53 | 14/16 | 209 | 64.84 | 67.21 / +1446 |
| S03 | −143 / −6.07 | −277 / −46.49 | 16/23 | 205 | 67.27 | 46.10 / +949 |
| S04 | −178 / −7.56 | −347 / −60.09 | 15/22 | 213 | 64.58 | 38.02 / +776 |
| S05 | −565 / −25.12 | +150 / 23.51 | 15/17 | 213 | 62.78 | 61.91 / +1300 |
| S06 | +535 / 24.20 | −562 / −110.64 | 8/15 | 196 | 74.61 | 29.87 / +589 |
| S07 | −256 / −8.14 | +264 / 28.21 | 17/21 | 207 | 62.09 | 58.13 / +1404 |
| S08 | +272 / 11.40 | −252 / −42.34 | 12/18 | 209 | 68.98 | 42.32 / +871 |
| S09 | +212 / 8.89 | −277 / −46.49 | 12/19 | 209 | 68.34 | 41.12 / +847 |
| S10 | +17 / 0.70 | −83 / −13.88 | 14/19 | 215 | 68.93 | 51.68 / +1067 |
| S11 | −177 / −7.64 | −314 / −54.42 | 17/24 | 205 | 67.80 | 40.95 / +836 |
| **S12** | +157 / 13.44 | −184 / −66.38 | 0/0 | 210 | **78.23** | 54.19 / +949 |
| S13 | −501 / −45.97 | +175 / 54.29 | 0/0 | 215 | 71.06 | **72.72** / +1301 |
| S14 | +77 / 2.36 | −280 / −36.08 | 20/28 | 208 | 62.79 | 41.94 / +935 |
| S15 | −689 / −32.00 | +232 / 35.81 | 0/0 | 211 | 61.85 | 64.18 / +1355 |
| S16 | +500 / 24.13 | +4 / 0.77 | 7/11 | 177 | 74.08 | 57.18 / +1127 |
| S17 | +92 / 4.72 | +302 / 51.71 | 9/10 | 178 | 72.04 | 70.93 / +1452 |
| S18 | −15 / −0.67 | −470 / −80.78 | 11/19 | 198 | 67.96 | 32.49 / +670 |
| S19 | −301 / −12.73 | +157 / 24.63 | 14/17 | 214 | 65.94 | 61.93 / +1289 |
| S20 | +369 / 15.46 | −389 / −69.52 | 10/17 | 209 | 71.96 | 36.26 / +734 |

**No combined form reaches the base on either leftover**: best
combined DISC leftover = S12's 78.23% (< 89.11); best combined
AUDIT leftover = S13's 72.72% (< 77.01, and S13 was DISC-
ineligible: standalone DISC net −501). The slot's standalone
segment signs flip by construction family — momentum forms earn
on DISC and lose on AUDIT, the mom16/mom24 forms (S02/S05/S13/
S15/S17/S19) do the reverse — the same native-creation regime
flip measured for Jan, Feb and Sep S2.

## §2 check-time grade (vs D3) — DOWNGRADE
- IMPROVE requires AUDIT leftover up AND DISC leftover not down:
  54.19 < 77.01 and 78.23 < 89.11 — fails both arms.
- DOWNGRADE triggers, all three arms checked: AUDIT leftover
  down **22.82 pts > 0.5** ✓ TRIGGERS · win 91.53% ≥ 80 (not
  triggered) · AUDIT net down **191.70 > max(25, 10% × 1140.61 =
  114.06)** ✓ TRIGGERS.
- §2 best gates on the combined: LCT-middle canonical vs D3
  FAIL (2.13%) · PBO canonical 55.00% FAIL · MC flag TRUE and
  DSR PASS do not offset those. Only IMPROVE or ACCEPTABLE may
  be adopted — this is neither.

## Consequence
The 07:30 slot is NOT adopted for July. **D3 stands unchanged as
July's EC-passing form** (DISC 89.11 / AUDIT 77.01, DD p95 172.54
≤ own cap 188.51); cycle78 remains the live incumbent pending
the separate integration step. Fourth S2 measurement of the
round with the same shape: a natively created off-hours hour in
July is dilutive on DISC and regime-flipped on AUDIT, and its
TP20/SL100 forms would have re-imported the −102.50 full-stop
density (7–20 DISC stops standalone) that attempt 4 removed.
Sizing not a gate (brief §0). Loss-cluster mechanism used in
the slate: S16 post-loss symbol cooldown + S17 post-loss global
skip-1 (explicit), S12/S13/S15 SL60 geometry (implicit density
control — the only one that kept the combined MC flag TRUE).

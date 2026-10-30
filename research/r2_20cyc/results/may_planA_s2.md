VERDICT: May planA s2 — NO IMPROVEMENT

# May Plan A Scenario 2 — 20-Cycle Round R2 (2026-10-30)

CREATION of 20 equations natively for the added off-hours slot
**07:30 MMT** (entry bar 01:00 UTC, stored check 01:30 UTC; May
already uses 00:30). This is NOT the incumbent replay graded in
may_planB_s1 — every cycle below was mined fresh at this hour
(no-lookahead S2 standard: H1 features shifted 1 bar, M15 features
from the last M15 bar completed before entry, entry at entry-bar
open, SL-first exits, hold ≤ 48 bars, H1 primary, M15 confirmation
only, 28 symbols, one pick per check = strongest |direction-source
momentum| among passing symbols). Slate pre-registered in
`run_may_planA_s2.py` (the Jan/Nov S2 creation slate, unchanged),
biased state/confirmation-heavy per the Jan/Feb/Sep S2 lessons
(RSI/BB bands, MACD+EMA agreement, M15 confirmation on every
cycle, volume bands, post-loss cluster controls S16/S17).
DXY is BLOCKED-DATA (Wave 0, Twelve Data 429): dollar legs use
the DOLLARIDX-labelled control (Dukascopy H1, mom24 only, NO
volume condition, data from 2017-12-01 — materially shorter than
the 2015+ FX span; pre-2018 rows pass on NaN). Research level
only — no app push, no GitHub push, live crons untouched.

Incumbent read FRESH from the registry record and reproduced
EXACTLY from `work_new8/combined/May_ROUND4_combined.csv`
(464 rows, validate_new8.seg_stats): cycle88n checks 16:30
IN-OFFICE / 22:30 / 00:30 MMT (entries 10/16/18 UTC). Segment
days (distinct incumbent check dates): DISC 175 d / AUDIT 44 d.
DISC n 361, net +4711.99, win 99.45%, leftover 95.30%, epd
2.063 · AUDIT n 103, net +1021.86, win 96.12%, leftover 79.54%,
epd 2.341. Incumbent MC (mc9 verbatim, own-relative caps):
P(profit) 1.0000 · DD obs 136.78 / p95 153.70 vs own cap 205.17
PASS · cluster obs −136.78 / p95 136.78 vs cap 205.17 PASS ·
consec 2/2 PASS · decay PASS.

## The 07:30 slot flow itself — no edge on either segment

All 20 created cycles standalone at 07:30 (one pick per check;
epd denominator = the segment days above, so slot epd ≈ 1.0 by
construction — the slot can add at most one pick/day):

| cycle | DISC n / net / win / leftover | AUDIT n / net / win / leftover |
|---|---|---|
| S01 mom4+M15mom+M15vol | 178 / −677.80 / 76.40 / −21.88 | 45 / −685.60 / 62.22 / −87.06 |
| S02 mom16+M15mom+H1vol | 175 / **+324.20** / 78.86 / +10.71 | 45 / −847.40 / 57.78 / −107.61 |
| S03 mom4+RSI band+M15mom | 178 / −767.30 / 75.84 / −24.77 | 45 / −685.60 / 62.22 / −87.06 |
| S04 mom4+BB+M15vol band | 178 / −707.00 / 76.40 / −22.70 | 45 / −734.70 / 62.22 / −93.30 |
| S05 mom16+RSI+BB+M15mom | 178 / **+18.60** / 78.65 / +0.60 | 45 / −546.80 / 62.22 / −69.43 |
| S06 mom4+MACD+EMA+M15mom | 168 / −268.10 / 76.19 / −9.19 | 44 / −407.10 / 68.18 / −52.87 |
| S07 mom24+ATR+M15vol TP30 | 170 / −196.50 / 68.82 / −4.25 | 45 / −339.50 / 57.78 / −29.03 |
| S08 mom4+DOLLARIDX+M15mom | 178 / −872.90 / 74.72 / −28.02 | 45 / −687.20 / 62.22 / −87.26 |
| S09 mom4+EURUSD leg+M15mom | 178 / −1065.10 / 73.60 / −34.40 | 45 / −565.60 / 64.44 / −71.82 |
| S10 mom16+M15 RSI/BB/vol | 178 / **+4.90** / 80.90 / +0.16 | 45 / −649.70 / 60.00 / −82.50 |
| S11 strict all-confirm | 177 / −491.50 / 78.53 / −16.10 | 44 / −213.60 / 70.45 / −27.74 |
| S12 mom4+M15mom TP10/SL60 | 178 / −874.00 / 80.34 / −65.47 | 45 / −393.80 / 75.56 / −116.68 |
| S13 mom16+M15mom TP10/SL60 | 178 / −638.70 / 83.15 / −47.84 | 45 / −375.60 / 75.56 / −111.29 |
| S14 mom4+RSI TP30 | 178 / −1108.00 / 65.17 / −23.15 | 45 / −715.00 / 53.33 / −59.86 |
| S15 mom24+EMA+M15 RSI TP20/SL60 | 178 / −545.20 / 73.03 / −17.70 | 45 / −407.40 / 62.22 / −51.73 |
| S16 S01 + post-loss symbol cooldown | 150 / −614.20 / 76.67 / −23.56 | 33 / −593.50 / 57.58 / −102.77 |
| S17 mom16+M15mom + post-loss global skip-1 | 149 / **+204.00** / 80.54 / +7.93 | 30 / −818.30 / 50.00 / −155.87 |
| S18 mom4+H1 vol_z∈[0,3]+M15mom | 159 / −572.10 / 76.10 / −20.56 | 44 / −625.00 / 68.18 / −83.70 |
| S19 mom16+BB≤0.8+M15vol band | 178 / **+72.70** / 80.90 / +2.33 | 45 / −428.60 / 64.44 / −54.43 |
| S20 mom4&16 agree+DOLLARIDX loose | 176 / −533.30 / 75.57 / −17.44 | 45 / −589.70 / 64.44 / −74.88 |

**20 of 20 cycles are AUDIT-losing standalone** (net −213.60 …
−847.40) and 15 of 20 are DISC-losing. The confirmation-heavy
bias did NOT save the hour: this is worse than the Jan/Feb/Sep
pattern — at May's 07:30 the flow has no DISC edge to flip from
(best DISC leftover of any cycle: S02 +10.71%). The cluster
controls do not rescue it: S16 (symbol cooldown) and S17 (global
skip-1) both stay AUDIT-negative; S17's skip-1 merely concentrates
the AUDIT damage (win 50.00%, leftover −155.87%).

DISC-only selection (pre-registered: maximise INC+slot combined
DISC leftover among standalone DISC-net > 0 — eligible S02, S05,
S10, S17, S19) picks **S17**. Its combined readings are the
headline forms below. For the record, the best combined AUDIT
leftover among all 20 cycles is S11's 40.22% — still 39.32 pts
below the incumbent's 79.54%.

## (1a) Check-time grade — ADD 07:30 to cycle88n: DOWNGRADE

ADD = incumbent + S17 slot picks, second-priority merge
(177 of 179 slot picks accepted; 2 dropped on symbol occupancy):

- Combined: DISC n 508, net +5089.59, win 94.29%, leftover
  **68.66%** (Δ −26.64), epd 2.903 · AUDIT n 133, net **+203.56**
  (Δ −818.30), win 85.71%, leftover **11.65%** (Δ **−67.89**),
  epd 3.023 · AUDIT stress net @4.5 −62.44 (negative)
- §2 grade: **DOWNGRADE** on all three arms — AUDIT leftover
  down 67.89 pts (> 0.5), AUDIT net down −818.30 (line
  −max(25, 10% × 1021.86) = −102.19); win 85.71% stays > 80%
- LCT (combined vs incumbent, paired, DISC): P **0.00%** / q05
  64.55% — middle FAIL outright (not May's usual 69.68% ceiling;
  the slot actively destroys the paired comparison)
- MC combined (mc9, OWN-RELATIVE caps — governing ruling):
  P(profit) 1.0000 · DD obs 307.95 / p95 371.39 vs own cap
  461.93 PASS · cluster obs −197.98 / p95 205.00 vs own cap
  296.97 PASS · consec 3/3 PASS → mc flag TRUE. BUT the
  loss-cluster arm before → after: worst cluster obs
  **−136.78 → −197.98** and DD obs 136.78 → 307.95 — the slot
  IMPORTS a new loss cluster (the Jan S2 failure mode verbatim);
  MC passes only because the caps are own-relative to the
  already-damaged form
- PBO **50.00%** (canonical round_pbo_dsr, at the ≤50% line) /
  CSCV second reading **60.71%** (> 50%, disclosed) · DSR
  **0.9981** (≥ 0.90 ✓; family = incumbent + 20 combined forms,
  N = 21 trials, this run) · decay **WEAKENED** (not FAIL)

## (1b) Second-best grading — S17 as May's second-best: NOT CREATED

S17's equation was also run natively at the best's own checks
(16:30/22:30/00:30) + the one new 07:30 slot — the §2 second-best
firing pattern. Standalone (4 checks/day; epd denominator = the
same 175 DISC / 44 AUDIT segment days, stated honestly):

- Standalone: DISC n 534, net **−915.60**, win 78.28%, leftover
  −9.83%, epd 3.051 · AUDIT n 125, net **−494.70**, win 76.00%,
  leftover −23.25%, epd 2.841 · stress net @4.5 −1983.60 /
  −744.70 · MC standalone: P(profit) **0.1064**, DD p95 3691.94,
  cluster p95 462.00, consec 5/6 — mc flag FALSE · decay FAIL
- Combined (incumbent-priority merge; drops: check_busy 336,
  symbol_overlap 14; **delta +309 picks measured**): DISC n 623,
  net +4857.69, win 91.97%, leftover **51.69%** · AUDIT n 150,
  net +455.86 (Δ −566.00), win 87.33%, leftover **22.49%**
  (Δ **−57.05** vs the ≥ 77.54 combine-safety floor) · epd
  3.560 / 3.409 · LCT P 0.00% / q05 33.50% FAIL · MC combined:
  P(profit) 1.0000, DD p95 496.72 vs own cap 439.14 **FAIL**,
  cluster p95 219.90 vs cap 307.50 PASS, consec 2/3 — mc flag
  FALSE
- §2 second-best acceptance, item by item: standalone epd > 2.5
  ✓ (3.051 / 2.841, denominator stated above) · fires only at
  best's checks + ≤ 1 new slot ✓ · combined delta > 0 ✓ (+309)
  · combine-safety within −2.00 AUDIT-leftover tolerance ✗
  (−57.05, miss by 55.05 pts) · combined MC/EC not worse ✗
  (MC flag FALSE; LCT P 0.00%) · standalone quality ✗ (losing
  on BOTH segments — a red-line profile for a partner).
  **S17 is NOT created as May's second-best.** Native creation
  at 07:30 does not close the May second-best gap either — the
  gap from the 2026-10-29 audit stays open, and cycle88
  (contained, +0) stays as the registry second.

## (2) Office grade — mined 07:30 cycle REPLACING 16:30: DOWNGRADE

REP1630 = incumbent minus its 16:30 MMT picks (entry 10 UTC;
the drop-alone base reads DISC leftover 100.00% / AUDIT 84.94%,
net +3821.28 / +843.90 — the S1 drop form) + the same 177
accepted S17 slot picks. This is new mined evidence, not the S1
replay estimate:

- Combined: DISC n 412, net +4198.88, win 93.45%, leftover
  **66.57%** (Δ −28.73) · AUDIT n 106, net **+25.60**
  (Δ **−996.26**), win 83.02%, leftover **1.75%**
  (Δ **−77.79**), epd 2.409 · AUDIT stress net @4.5 −186.40
- §2 grade vs the incumbent: **DOWNGRADE** on the leftover arm
  (−77.79 > 0.5) AND the net arm (−996.26 vs the −102.19 line);
  win 83.02% stays > 80%
- LCT P **0.00%** / q05 61.52% FAIL · MC: P(profit) 1.0000, DD
  obs 298.56 / p95 365.27 vs own cap 447.84 PASS, cluster obs
  −125.67 / p95 205.00 vs cap 188.51 **FAIL**, consec 2/2 — mc
  flag FALSE · decay WEAKENED

The mined replacement is WORSE than the S1 bounded estimate
(AUDIT net ≈ +713.98 estimated there; the mined cycle delivers
+25.60) because the created 07:30 flow is itself AUDIT-negative,
where the S1 estimate only had to absorb the replay's −129.92.
**No office move is recommended for May. The 16:30 IN-OFFICE
check stays.**

## Numbers block (contract §9) — selected cycle S17

- Slot (07:30 MMT, entry 01:00 UTC), created cycle S17 =
  mom16 direction + M15 mom4 confirmation + post-loss global
  skip-1 (the explicit loss-cluster mechanism; before/after
  cluster arm on the ADD form: −136.78 → −197.98 obs — the
  mechanism did NOT contain the imported cluster)
- Standalone slot: DISC leftover +7.93%, AUDIT leftover
  −155.87%, AUDIT net −818.30, win 80.54 / 50.00%, epd 0.851 /
  0.682 (denominator: 175 / 44 segment days; the slot fired on
  149 / 30 of them)
- Combined ADD vs incumbent: DISC leftover 95.30 → 68.66% ·
  AUDIT leftover 79.54 → 11.65% · AUDIT net +1021.86 → +203.56 ·
  win 96.12 → 85.71% · entries/day 2.063 → 2.903 DISC
- LCT P/q05 (ADD): 0.00% / 64.55% · MC ADD: P(profit) 1.0000,
  DD p95 371.39 vs own cap 461.93, cluster p95 205.00 vs own
  cap 296.97, consec p95 3 — flag TRUE (own-relative), cluster
  obs worsened −136.78 → −197.98 · PBO 50.00% canonical /
  60.71% CSCV · DSR 0.9981 (family N = 21) · decay WEAKENED
- Check-time grade (ADD): **DOWNGRADE** · Second-best grade:
  **NOT CREATED** (combine-safety −57.05 vs −2.00 tolerance;
  standalone losing both segments) · Office-replacement grade
  (REP1630): **DOWNGRADE** (AUDIT leftover −77.79, net −996.26)
- Trial count: 20 cycles pre-registered; PBO/DSR family N = 21.
  DXY: BLOCKED-DATA, not used, not claimed; DOLLARIDX =
  Dukascopy-labelled leg in S08/S20 only (H1 from 2017-12-01,
  no volume conditions) — neither is the selected cycle.

## Method / files

- Runner: `~/workspace/fx/work_20cyc_r2/run_may_planA_s2.py`
  (slate + selection + grades pre-registered in its header).
  Machinery reused verbatim: `work_new8/validate_new8.py`
  (seg_stats, split_seg, lct, round_pbo_dsr, daily_pnl),
  `work_29load/mc9_verbatim.py` (mc_test),
  `work_20cyc_r2/support/planA_s1_engine.py` (full_decay,
  pbo_cscv). Data: Dukascopy M15 CSVs (the programme S2 source),
  H1 resampled from M15.
- Machine results: `results/may_s2_run.json`; per-cycle slot
  ledgers `results/may_s2_S01..S20_slot_ledger.csv`; forms
  `results/may_s2_ADD_ledger.csv`, `may_s2_REP1630_ledger.csv`,
  `may_s2_SB_COMB_ledger.csv`, `may_s2_S17_sb_ledger.csv`.
- Day-count note: segment days here are the incumbent ledger's
  distinct check dates (DISC 175 / AUDIT 44), giving incumbent
  epd 2.063 / 2.341; may_planB_s1's 178/45 grid gives 2.028 /
  2.289 for the same ledger. Nets, win % and leftovers are
  identical under both.
- Gaps named: (1) only the DISC-selected cycle (S17) was carried
  into the SB and REP forms — the other eligible cycles' SB/REP
  forms were not graded, but every cycle is AUDIT-losing
  standalone at the slot and the best combined AUDIT leftover
  of all 20 (S11, 40.22%) is 39.32 pts under the incumbent, so
  no ungraded form can plausibly clear a −2.00 tolerance;
  (2) sizing not measured (not a gate this round, brief §0).

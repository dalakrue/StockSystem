VERDICT: Jan s2 — NO IMPROVEMENT (CREATION at the added 00:30 MMT slot, chosen on DISC evidence: best probe DISC leftover 22.77% vs 07:30's 15.38%; 20 created cycles S01–S20, DISC-selected slot cycle = S14 mom4 + H1 RSI band + M15 mom alignment, TP30/SL100 — standalone DISC +1214.10 / leftover 25.66% but standalone AUDIT −233.20 / leftover −12.66%: the slot's DISC edge does NOT repeat unseen, the same Jan regime flip as Plan A D07/D08 and attempt-2's leg E. All three combined forms fail locked gates — (i) incumbent+S14: AUDIT leftover 70.06→23.68% = §2 class DOWNGRADE (also net arm −135.70 vs −74.99 line), LCT 49.05/13.97 FAIL, MC flag FALSE (DD p95 888.28 vs own cap 784.91); (ii) PC06+S14 ⚠fall-through-suspect base: AUDIT leftover 17.52%, LCT 56.95/17.07 FAIL, MC FALSE (848.39 vs 807.41); (iii) PC06+V04+S14 ⚠fall-through-suspect base — CLOSEST form and the epd rescue mechanically WORKS: AUDIT epd 1.761→3.196 with margin, DSR 0.9936 / PBO 10.00% (family-5), DISC leftover 33.85% — but AUDIT leftover 14.29%, LCT 58.16/19.15 FAIL, MC DD miss 32.94. Completeness: NO cycle's combined form clears the unseen gate — the best combined AUDIT leftover of all 20 is S19's 57.72% < 70.06%. Incumbent cycle60b+60 stands; Jan EC unchanged. Research level only)

# Jan Scenario 2 — CREATION for one added off-hours slot (R2, brief §5)
# Run 2026-10-30 (Wave 4d). CREATION of new equations designed FOR the
# slot — NOT an incumbent replay at the new hour (that replay was
# calculated 2026-10-29 and is not repeated). Machinery:
# validate_new8 verbatim (seg_stats, split_seg, lct, round_pbo_dsr,
# daily_pnl) + mc9_verbatim.mc_test (block 10, 10,000 paths, seed
# 20261101, net = gross − 2.5); MC-middle = the mc9 own-relative flag
# (settled ruling); PBO/DSR canonical, CSCV disclosed second.
# Data: Dukascopy M15 CSVs (~/workspace/fx/dukascopy_m15/, the Jan
# Plan C runs' source; H1 resampled from M15) — fx_data.db M15 reads
# stalled under cross-lane contention, indexed queries abandoned
# after timed probes (one 3,299-row M15 range read = 27.6 s).
# No Twelve Data calls; DXY BLOCKED-DATA — dollar legs are
# DOLLARIDX-labelled (Dukascopy, mom24 only, NO volume condition,
# data from 2017-12-01; pre-2018 picks pass the leg vacuously).
# Runner: ../run_jan_s2.py; independent grading pass:
# ../grade_jan_s2.py → jan_s2_grade_run.json (slot ledgers asserted
# against the run log; a same-named jan_s2_run.json from a parallel
# pass was NOT trusted until this pass reproduced its DISC/AUDIT/LCT
# numbers exactly — one bug found and corrected in both: form iii's
# first DSR call graded family index 3 via an 'ii_' substring match;
# corrected value 0.9936 at index 4 is used below).
# Form: H1 primary (direction + filters on completed H1 bars, entry
# at the slot bar's open); M15 = confirmation only. Per check the
# equation takes ONE pick — the strongest |direction momentum| among
# passing symbols across all 28 (the programme's per-check scale;
# a first full-breadth probe pass at epd ≈ 14 was discarded as
# off-scale and the study rerun — disclosed, not hidden).
# Slot stored-check convention (Dec/Sep S2 runs): 07:30 MMT → entry
# bar 01:00 UTC; 00:30 MMT → entry bar 18:00 UTC (Dec-31 entries map
# to the Jan-1 check). Incumbent stored checks 11:30/13:30/17:30 UTC
# — the slot can never collide with an incumbent check.
# Merge semantics (second priority, all three forms): slot picks
# exist ONLY at the new check, which the base never takes; a slot
# pick is additionally dropped if the base form holds the same
# symbol open at slot entry (drops: form i 4, form ii 3, form iii 2
# of 243 slot picks).

## Incumbent (reproduced EXACT before mining)
- Jan best cycle60b + second cycle60, combined 658 picks, checks
  17:30 / 19:30 / 23:30 MMT (all OFF-HOURS).
- DISC: n 523, net +1310.13, win 92.35%, leftover 29.82%, epd 2.972.
  AUDIT: n 135, net +749.88, win 95.56%, leftover 70.06%, epd 2.935.
- MC verbatim: P(profit) 0.9999 · DD obs 459.29, p95 527.91 vs own
  cap 688.94 PASS · cluster p95 205.00 vs cap 302.73 · consec 3/3 —
  MC middle PASS. PBO 40.00% / DSR 0.8630 (EC record, FAIL — Jan's
  original EC item). Decay PASS.
- Bases for forms (ii)/(iii), reproduced EXACT: PC06 DISC 39.02 /
  AUDIT 70.94, epd 2.369/2.109, MC DD miss 59.15 · PC06+V04 DISC
  43.68 / AUDIT 70.25, epd 2.000/1.761 (the frequency-bound form
  this wave was ordered to rescue).

## 1. SLOT STUDY (DISC-only — choice made on DISC evidence alone)
Bar behaviour at the entry hour (Jan DISC bars, 28 symbols):
- Median H1 volume: 07:30 → 5,626.0 · 00:30 → 5,642.3 (no material
  difference). Median H1 range: 14.25 pips (07:30) vs 12.35 pips
  (00:30) — 07:30 is the slightly wider hour.
Probe screen (pre-registered, per-check best-1, TP20/SL100):
| probe | 07:30 DISC n/net/win/leftover/epd | 00:30 DISC n/net/win/leftover/epd |
|---|---|---|
| P-base (mom4 + M15mom + M15vol>−1) | 170 / +457.6 / 82.35% / 15.38% / 0.966 | 176 / +222.4 / 84.09% / 7.32% / 1.000 |
| P-mom16 (mom16 + M15mom + H1vol>−0.5) | 167 / +26.3 / 81.44% / 0.90% / 0.949 | 173 / +685.5 / 84.97% / 22.77% / 0.983 |
CHOICE: **00:30 MMT** — on the pre-registered rule (best probe DISC
leftover per slot): 22.77% (00:30, P-mom16) vs 15.38% (07:30,
P-base). Winner/loser separation at 00:30 on DISC is real but thin
(probe win ≈ 85%, leftover ≈ 23% at best) — and, as the AUDIT
columns below show, it does not survive unseen. AUDIT figures were
never used in the choice.

## 2. CREATION — 20 cycles at 00:30 MMT (pre-registered slate)
3–4 indicators × 3–4 thresholds per equation; volume columns in
S01/S02/S04/S09/S10/S11/S13/S18/S19; M15 confirmation under
H1-primary in all; correlated legs: S08/S20 DOLLARIDX-labelled,
S09 EURUSD leg; loss-cluster controls: S16 post-loss symbol
cooldown, S17 post-loss global skip-1. Standalone slot results
(by-trade leftover; full table in jan_s2_grade_run.json):
| cycle | DISC n/net/left | AUDIT n/net/left | INC-combined DISC left | INC-combined AUDIT left |
|---|---|---|---|---|
| S01 mom4+M15mom+M15vol, 20/100 | 176/+222.4/7.32% | 67/−8.4/−0.72% | 20.36% | 34.50% |
| S02 mom16+M15mom+H1vol, 20/100 | 173/+685.5/22.77% | 66/−8.0/−0.71% | 27.30% | 35.00% |
| S03 mom4+RSI band+M15mom, 20/100 | 176/+486.5/16.01% | 67/−117.7/−10.04% | 24.12% | 29.63% |
| S04 mom4+BB+M15 vol band, 20/100 | 176/−212.6/−6.97% | 67/+111.6/9.75% | 14.60% | 40.39% |
| S05 mom16+RSI+BB+M15mom, 20/100 | 176/+313.7/10.24% | 67/+30.7/2.64% | 23.24% | 36.30% |
| S06 mom4+MACD+EMA+M15mom, 20/100 | 166/+622.9/21.62% | 66/−17.0/−1.47% | 26.38% | 39.40% |
| S07 mom24+ATR+M15vol, 30/100 | 172/−772.6/−16.33% | 66/+254.9/14.32% | 6.14% | 37.56% |
| S08 mom4+DOLLARIDX+M15mom, 20/100 | 176/+234.5/7.72% | 67/−292.7/−24.96% | 20.90% | 21.50% |
| S09 mom4+EURUSD leg+M15mom+H1vol | 175/−72.6/−2.40% | 67/−8.4/−0.72% | 16.36% | 34.50% |
| S10 mom16+M15 RSI/BB/vol, 20/100 | 176/−580.2/−18.90% | 67/+350.2/29.87% | 9.86% | 50.82% |
| S11 strict all-confirm, 20/100 | 174/+192.3/6.34% | 67/−205.7/−17.54% | 20.22% | 25.50% |
| S12 mom4+M15mom, 10/60 | 176/+294.6/22.32% | 67/+33.8/6.73% | 27.69% | 49.76% |
| S13 mom16+M15mom+H1vol, 10/60 | 175/+108.1/8.24% | 67/−54.7/−11.07% | 24.84% | 44.37% |
| **S14 mom4+RSI band+M15mom, 30/100** | **176/+1214.1/25.66%** | **67/−233.2/−12.66%** | **28.05%** | **23.68%** |
| S15 mom24+EMA+M15 RSI, 20/60 | 176/−444.2/−14.61% | 67/−197.8/−16.87% | 11.68% | 25.87% |
| S16 mom4+M15mom+sym-cooldown, 20/100 | 157/+257.8/9.53% | 59/+254.0/24.60% | 21.96% | 49.17% |
| S17 mom16+M15mom+global-cool, 20/100 | 153/+559.3/21.02% | 55/+63.3/6.73% | 26.83% | 41.88% |
| S18 mom4+H1 vol∈[0,3]+M15mom, 20/100 | 167/+177.1/6.11% | 64/+147.3/13.15% | 21.99% | 42.06% |
| S19 mom16+BB≤0.8+M15 vol band | 176/−866.6/−28.38% | 67/+513.4/44.58% | 6.68% | 57.72% |
| S20 mom4&16 agree+M15mom+DOLLARIDX | 175/+440.2/14.49% | 67/−428.7/−36.56% | 23.72% | 19.87% |
Selection (locked, DISC-only): among standalone DISC net > 0, the
cycle maximising INC+S2 combined DISC leftover → **S14** (28.05%).
Pattern, stated plainly: DISC and AUDIT slot performance are
near-negatively related across the slate (S14/S02/S06 DISC-strong,
AUDIT-negative; S19/S10/S07 DISC-negative, AUDIT-strong). Only
S05/S12/S16/S17/S18 are positive on both, all thin. S16 (the
cooldown) is the most balanced (+257.8/+254.0) — noted, not
selected: the selection rule was DISC-only and fixed in advance.

## 3. THREE COMBINED FORMS — full §2 battery vs incumbent
### (i) Incumbent + S14 (the pure S2 form)
- DISC leftover 29.82% → 28.05% · AUDIT leftover 70.06% → 23.68%
  (Δ −46.38) · AUDIT net +749.88 → +614.18 (Δ −135.70) · win
  DISC/AUDIT 89.22%/86.07% · epd 3.955/4.370 (slot adds ≈ +1/day ✓)
- LCT-middle vs incumbent: P 49.05% / q05 13.97% — FAIL both arms.
- MC: P(profit) 0.9991 · DD obs 523.27, p95 888.28 vs OWN cap
  784.91 FAIL (miss 103.37) · cluster obs −304.32, p95 304.32 vs
  cap 456.48 PASS · consec obs/p95 4/4 PASS — verbatim flag FALSE
  (DD arm alone). The slot's own losses create a NEW worst cluster
  (−304.32 vs incumbent −201.82).
- PBO 25.00% canonical (family-21: incumbent + 20 combined forms)
  PASS · CSCV second reading on the family-20 combined DISC
  ledgers = 66.67% FAIL (disclosed, same basis split as all round).
  DSR 0.9151 ≥ 0.90 PASS (family-21; incumbent in comparable
  families read 0.6279–0.7869). Decay PASS. Red lines intact
  (AUDIT net > 0, no discovery collapse).
- **Check-time class (§2 rule): DOWNGRADE** — AUDIT leftover down
  46.38 pts (> 0.5) AND AUDIT net down −135.70, worse than the
  −max(25, 10% × 749.88) = −74.99 line. Not adoptable.
- FORM VERDICT: NO IMPROVEMENT (fails unseen leftover, LCT, MC DD,
  and the class rule; passes only epd, win, PBO, DSR, decay).

### (ii) PC06 + S14 ⚠ FALL-THROUGH-SUSPECT (veto base, Feb precedent)
- DISC leftover 32.22% (vs incumbent 29.82) · AUDIT leftover
  70.06% → 17.52% · AUDIT net +406.15 · win 89.34%/83.44% ·
  epd 3.358/3.543 (PC06-alone was 2.369/2.109 — frequency fixed,
  quality destroyed).
- LCT vs incumbent: P 56.95% / q05 17.07% — FAIL.
- MC: P(profit) 0.9997 · DD p95 848.39 vs OWN cap 807.41 FAIL
  (miss 40.98) · cluster p95 304.32 vs cap 456.48 PASS · consec
  4/4 PASS — flag FALSE (DD arm).
- PBO 10.00% / DSR 0.9889 (family-5 {INC, PC06, V04, ii, iii})
  PASS · decay PASS · red lines intact.
- FORM VERDICT: NO IMPROVEMENT.

### (iii) PC06+V04-prune + S14 — the epd-rescue form ⚠ FALL-THROUGH-SUSPECT
- **The rescue target is MET mechanically**: AUDIT epd 1.761 →
  3.196 (≥ 2 with +1.196 margin), DISC epd 2.000 → 2.994. The
  frequency headroom S2 was ordered to create exists.
- DISC leftover 29.82% → 33.85% · AUDIT leftover 70.06% → 14.29%
  (V04-alone: 70.25%) · AUDIT net +316.34 (> 0 ✓) · win
  88.99%/82.31% (> 80 ✓).
- LCT vs incumbent: P 58.16% / q05 19.15% — FAIL (q05 short by
  0.85 pt, P short by 21.84).
- MC: P(profit) 0.9998 · DD obs 460.28, p95 723.36 vs OWN cap
  690.42 FAIL (miss 32.94 — the smallest DD miss of the three
  forms, but still a miss; PC06-alone missed by 59.15, V04-alone
  by 3.58 on a far smaller ledger) · cluster p95 304.32 vs cap
  456.48 PASS · consec 4/4 PASS — flag FALSE (DD arm).
- PBO 10.00% / DSR 0.9936 (family-5, corrected index) PASS ·
  decay WEAKENED (exp<50%) = not FAIL ✓ · red lines intact.
- FORM VERDICT: NO IMPROVEMENT — closest of the three (passes
  epd-rescue, DSR, PBO, DISC leftover, win, AUDIT-net, decay;
  fails AUDIT leftover, LCT, MC DD).

## Verdict reasoning (gates locked in brief §2 — none moved)
Scenario 2 creation was run exactly as ordered and it answers the
wave's question definitively: **the added slot DOES create the
frequency headroom** (every form gains ≈ +1.0–1.4 epd; form iii
lifts the frequency-bound V04 form from AUDIT epd 1.761 to 3.196),
**but January's 00:30 slot edge is a DISC-only artefact**. The
DISC-selected slot cycle S14 is the single worst AUDIT performer
among DISC-positive cycles (−233.20 unseen), and no created cycle
— selected or not — produces a combined AUDIT leftover above the
incumbent's 70.06% (best: S19-combined 57.72%, from a DISC-LOSING
cycle no DISC-only rule could select). The slot also imports a
new worst loss cluster (−304.32) that breaks the MC DD arm in all
three forms under the own-relative ruling. This is the third
independent measurement of the same January fact (Plan A D07/D08
regime flip · attempt-2 leg E · now the 00:30 slot): what DISC
certifies in January does not repeat on AUDIT. The remaining named
route for Jan is unchanged — a non-veto base or trade-level window
excision at the CURRENT check times — not more slot creation.
Incumbent cycle60b + cycle60 stands; PC06 and V04 stand as before;
Jan EC position unchanged (DSR the failing item on the incumbent;
the S2 forms that pass DSR fail the unseen/LCT/MC gates).
Research level only — nothing pushed, nothing integrated.

## Numbers block (contract §9) — incumbent vs closest form (iii)
- DISC leftover: 29.82% → 33.85% · AUDIT leftover: 70.06% →
  14.29% · AUDIT net: +749.88 → +316.34 · win (AUDIT): 95.56% →
  82.31% · entries/day DISC/AUDIT: 2.972/2.935 → 2.994/3.196
- LCT P/q05: — (reference) → 58.16% / 19.15% FAIL
- MC: P(profit) 0.9999 → 0.9998 · DD p95 527.91 vs cap 688.94 →
  723.36 vs OWN cap 690.42 FAIL (miss 32.94) · cluster p95 205.00
  vs cap 302.73 → 304.32 vs cap 456.48 · consec p95 3 → 4
- PBO: 40.00% (EC record) → 10.00% canonical family-5 (CSCV
  second reading on the S2 family-20 = 66.67%) · DSR: 0.8630
  (historical family) → 0.9936 (family-5) · decay: PASS →
  WEAKENED (not FAIL)
- Loss-cluster mechanism: S16/S17 sequential cluster controls in
  the creation slate (S16 standalone cluster-thinning is real:
  both segments positive); the SELECTED S14 carries no cluster
  control and imports the round's new worst cluster −304.32 —
  cluster arm before→after for form (iii): −201.82 → −304.32 obs
  (p95 205.00 → 304.32, cap-relative PASS but obs worse).
- Trial count: 2 probes × 2 slots (study) + 20 creation cycles,
  all pre-registered; PBO/DSR families stated per form (21 / 5).
  DXY: BLOCKED-DATA, not used, not claimed; DOLLARIDX-labelled
  legs only (S08/S09/S20), no volume conditions on them.
- Files: jan_s2_S01..S20_slot_ledger.csv · jan_s2_form_*_ledger.csv
  (+ _v2 from the grading pass, set-identical stats) ·
  jan_s2_grade_run.json (governing record) · jan_s2_study_*.

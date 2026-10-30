VERDICT: Jan planC s1 attempt2 — NO IMPROVEMENT (DD-tail attempt on PC06, mirroring Jul attempt 4: PC06 rebuilt and asserted EXACT — DISC 39.02 / AUDIT 70.94, MC DD obs 228.65 → p95 402.13 vs own cap 342.98, miss 59.15; DD window = 2017-01-09→2017-01-16, worst cluster = its tail pair FB_EURGBP_h17_0 −99.32 + FB_EURUSD_h11_0 −102.50 = −201.82; Jan has NO atomic stop size — 28 DISC losses, SL sizes 26.4–100 pips, only 5 at exactly −102.50; of 9 pre-registered 1–2-leg prunes, NONE passes the full §2 battery: the MC verbatim flag is FALSE on the DD arm in all 9 (own-cap cap-trap — DD p95 falls 402.13 → 182.72–397.72 but the cap falls with DD obs), 8/9 break AUDIT epd ≥ 2, and the canonical family-11 PBO reads 70.00% for every member (CSCV second reading 17.06%); closest = V04 prune FB_AUDUSD_h13_0 alone: DD p95 306.31 vs own cap 302.73, miss 3.58, AUDIT leftover 70.25 > 70.06 strictly, LCT 100.00/24.88, DSR 0.9397 — but AUDIT epd 1.761 < 2; the density/window route is EXHAUSTED within veto + leg-prune forms for Jan — no gate moved, incumbent cycle60b+60 and PC06 both stand, research level only)

# Jan Plan C S1 — ATTEMPT 2: DD-tail prune on PC06 (2026-10-30, Wave 4c)

Method = Jul attempt 4 verbatim, applied to Jan's base candidate
PC06 (M15 RSI+BB+volume confirmation veto on cycle60b+60
combined; Jan verdict jan_planC_s1.md). PC06 passed every gate
except MC DD p95 402.13 vs own cap 342.98 (miss 59.15).
Grading = full BRIEF.md §2 battery vs the incumbent combined
(DISC leftover 29.82 by-trade / AUDIT 70.06). MC = mc9_verbatim,
10,000 paths; mc_middle_pass is the OWN-RELATIVE flag (settled
ruling, applied without re-argument). PBO/DSR canonical =
validate_new8 round_pbo_dsr on the stated family; CSCV (R2
engine) disclosed as second reading. Research level only: no
pushes, no cron switch, no Streamlit, no Twelve Data calls.

⚠ FALL-THROUGH SUSPECT (applies to PC06 and EVERY variant
below): PC06 is a VETO graded at ledger level (the Jan
convention). Per the Feb C08 precedent, freed veto slots refill
with weaker picks at app replay, so no variant here — passing
or failing — could be promoted on this evidence alone; a
fall-through app replay would be required before any
integration decision. All variants fail on ledger-level gates
anyway, so the caveat does not change this verdict.

## Base rebuild — asserted before starting

- Incumbent combined (C20_STACK + C60-03 dedup merge, the
  run_jan_planA_s1.py path): DISC n 523, net +1310.13, win
  92.35%, leftover 29.82%, epd 2.972 · AUDIT n 135, net
  +749.88, win 95.56%, leftover 70.06%, epd 2.935 · MC DD obs
  459.29 → p95 527.91, cluster −201.82/205.00, consec 3/3 —
  EXACT vs Plan A / EC record.
- PC06 (saved ledger jan_planC_s1_PC06_rsi_bb_vol_ledger.csv):
  DISC n 417, net +1368.16, win 93.29%, leftover 39.02%,
  epd 2.369 · AUDIT n 97, net +541.85, win 94.85%, leftover
  70.94%, epd 2.109 · MC P(profit) 1.0000, DD obs 228.65 →
  p95 402.13 vs OWN cap 342.98 (miss 59.15, flag FALSE),
  cluster obs −201.82 → p95 201.82 vs cap 302.73 PASS,
  consec 2/2 PASS — EXACT vs jan_planC_s1.md on every figure.

## (a) DD window + full-stop census (DISC-only selection)

**DD window** (full-period equity peak → trough, DD obs
228.65): peak after the 2017-01-06 13:30 check → trough at
2017-01-16 11:30; 13 trades, net −228.65. Contents:

| check | leg | exit | net |
|---|---|---|---|
| 2017-01-09 11:30 | FB_EURUSD_h11_0 | SL (60) | −62.50 |
| 2017-01-09 13:30 | T3 AUDJPY | TP | +7.50 |
| 2017-01-09 17:30 | FB_EURGBP_h17_0 | TP | +7.50 |
| 2017-01-10 11:30 | FB_EURUSD_h11_0 | TP | +7.50 |
| 2017-01-10 13:30 | FB_AUDUSD_h13_0 | TP | +7.50 |
| 2017-01-10 17:30 | FB_EURGBP_h17_0 | TP | +7.50 |
| 2017-01-11 11:30 | FB_EURUSD_h11_0 | TP | +7.50 |
| 2017-01-11 17:30 | TSF USDCAD | TP | +7.50 |
| 2017-01-12 11:30 | FB_EURUSD_h11_0 | TP | +7.50 |
| 2017-01-12 13:30 | FB_AUDUSD_h13_0 | TIME | −38.70 |
| 2017-01-13 11:30 | mom USDCAD | TP | +14.38 |
| 2017-01-13 17:30 | FB_EURGBP_h17_0 | SL (96.8) | −99.32 |
| 2017-01-16 11:30 | FB_EURUSD_h11_0 | SL (100) | −102.50 |

The window is an accumulation bleed: three SL/TIME losses
(−62.50, −38.70, −99.32, −102.50) spaced by +7.50 TP wins —
no single trade explains the DD. **Worst cluster** (mc9
worstcl −201.82, consec 2) is the window's tail pair:
2017-01-13 FB_EURGBP_h17_0 −99.32 + 2017-01-16
FB_EURUSD_h11_0 −102.50. Next-worst runs: −137.18
(2019-01-03, AUDUSD −62.50 + EURGBP −74.68); all others are
single −102.50s.

**Full-stop census — Jan is NOT Jul.** DISC (417 trades):
28 losses = 24 SL exits + 4 TIME exits. SL sizes are NOT a
single atomic size: sl_pips_used ranges 26.4–100 (median 60),
so net SL losses run −28.90 … −102.50. Loss-size
distribution (net): 5 at exactly −102.50 (the sl-100 class) ·
10 ≤ −80 · 18 ≤ −60 · 25 ≤ −40 · median −62.50 · mean −67.96 ·
min −102.50, max −13.90. There is no dense atomic layer to
thin; the tail is a spread of sizes carried by three legs:

| leg | DISC n | DISC net | losses | ≤ −80 | loss-sum | in window? |
|---|---|---|---|---|---|---|
| FB_EURUSD_h11_0 (E) | 70 | −231.34 | 9 (8 SL) | **5** | −689.53 | yes ×2 + cluster |
| FB_EURGBP_h17_0 (G) | 56 | −67.40 | 8 (7 SL) | 1 | −446.13 | yes + cluster |
| FB_AUDUSD_h13_0 (A) | 65 | +53.20 | 5 (4 SL) | 3 | −403.70 | yes (TIME) |
| mom_NZDCAD_h17…0.3x5 (N) | 13 | −32.54 | 2 (2 SL) | 0 | −115.04 | no — control |

All other legs carry ≤ 1 DISC loss. Grading-only AUDIT note
(selection stayed DISC-only): E's AUDIT flow is 15 trades,
ALL TP wins, +112.50 — the regime-flip pattern of Plan A
D07/D08 sits inside PC06's top carrier; G AUDIT +19.70 (10),
A AUDIT +89.81 (16), N AUDIT +7.50 (1).

## (b) Pre-registered slate — 9 variants (≤ 12)

Written into run_jan_planC_attempt2.py BEFORE any variant was
measured. Leg prunes of the PC06 ledger, one or two legs at a
time, DISC-only selection (forms: ledger prune, no refill —
PC06 is a veto on a fixed combined ledger; there is no fill
layer to recompute, unlike Jul's T7 form):

  V01 prune E · V02 prune G · V03 prune E+G (the exact
  cluster pair) · V04 prune A · V05 prune E+A (the two ≤−80
  carriers) · V06 prune G+A · V07 prune N (control: carrier
  outside the window) · V08 prune E+N · V09 prune G+N

## (c) Full §2 battery — all 9 variants vs incumbent

Canonical PBO/DSR family (stated, attempt-2): 11 DISC daily
series {INC, PC06, V01..V09}. validate_new8's PBO is a
family-level statistic — it reads **70.00% for every member**
of this family (the family is 9 correlated prunes of one
ledger; PC06 read 30.00% in its own family-21). Disclosed
second reading (R2-engine CSCV basis, same family): PBO
**17.06%**. PC06's DSR in family-11 = 0.8961 (family-21
published 0.9256 — family sensitivity, disclosed). Decay:
PASS for PC06 and all 9 variants (every year 2016–2025
leftover > 0, AUDIT net > 0). All other MC arms pass in all
9 variants: P(profit) 1.0000, cluster p95 ≤ cap, consec
p95 ≤ cap throughout — the DD arm is the sole MC blocker,
as in Jul.

| Var | DISC lo | AUDIT lo | AUDIT net | win D/A % | epd D/A | LCT P/q05 | DD obs → p95 vs own cap (miss) | MC flag | DSR fam-11 |
|---|---|---|---|---|---|---|---|---|---|
| PC06 base | 39.02 | 70.94 | +541.85 | 93.29/94.85 | 2.369/2.109 | 95.96/23.27 | 228.65 → 402.13 vs 342.98 (+59.15) | FALSE | 0.8961 (0.9256 fam-21) |
| V01 E | 53.75 | 65.88 ✗ | +429.35 | 94.52/93.90 | 1.972/1.783 ✗ | 95.24/40.28 | 156.65 → 243.37 vs 234.98 (+8.39) | FALSE | 0.9712 |
| V02 G | 46.89 | 75.87 | +522.15 | 94.46/96.55 | 2.051/1.891 ✗ | 79.10 ✗/35.32 | 190.00 → 311.23 vs 285.00 (+26.23) | FALSE | 0.9460 |
| V03 E+G | 65.89 | 71.12 | +409.65 | 96.22/95.83 | 1.653/1.565 ✗ | 95.45/40.41 | 106.90 → 187.46 vs 160.35 (+27.11) | FALSE | 0.9913 |
| **V04 A** | **43.68** | **70.25** | **+452.04** | 93.47/95.06 | 2.000/**1.761 ✗** | **100.00/24.88** | 201.82 → **306.31 vs 302.73 (+3.58)** | FALSE | 0.9397 |
| V05 E+A | 62.38 | 63.90 ✗ | +339.54 | 95.04/93.94 | 1.602/1.435 ✗ | 99.59/49.12 | 118.12 → 182.72 vs 177.18 (+5.54) | FALSE | 0.9956 |
| V06 G+A | 53.89 | 76.16 | +432.34 | 94.93/97.18 | 1.682/1.543 ✗ | 98.27/38.80 | 125.50 → 214.40 vs 188.25 (+26.15) | FALSE | 0.9687 |
| V07 N (ctrl) | 41.10 | 70.65 | +534.35 | 93.56/94.79 | 2.295/2.087 ✓ | 99.45/29.66 | 228.65 → 397.72 vs 342.98 (+54.75) | FALSE | 0.9093 |
| V08 E+N | 56.73 | 65.48 ✗ | +421.85 | 94.91/93.83 | 1.898/1.761 ✗ | 98.17/45.50 | 137.18 → 236.79 vs 205.77 (+31.02) | FALSE | 0.9755 |
| V09 G+N | 49.55 | 75.60 | +514.65 | 94.83/96.51 | 1.977/1.870 ✗ | 83.02/33.85 | 190.00 → 301.69 vs 285.00 (+16.69) | FALSE | 0.9537 |

Gate tally: **no variant passes all gates.** Common failures:
MC flag FALSE in 9/9 (DD arm only) · canonical PBO 70.00% >
50 in 9/9 on the stated family (CSCV second reading 17.06%
passes; the verdict does not rest on PBO — MC + epd fail
regardless) · AUDIT epd < 2 in 8/9 (only the control V07
keeps ≥ 2 on both segments). Variant-specific: AUDIT
leftover below incumbent in V01/V05/V08 (every E-carrying
prune — the regime flip: E is DISC's worst leg and AUDIT's
cleanest winner leg) · LCT-P fails only in V02 (79.10 < 80
by 0.90). DSR ≥ 0.90, win > 80%, AUDIT net > 0, DISC
leftover > incumbent, decay not-FAIL and red lines pass in
all 9.

## Closest variant — V04 (prune FB_AUDUSD_h13_0 alone)

V04 is closest on the target arm and on the gate tally that
matters: DD p95 306.31 vs own cap 302.73 — **miss 3.58**
(PC06's miss was 59.15). It passes LCT-middle (100.00/24.88),
AUDIT leftover strictly > incumbent (70.25 vs 70.06, +0.19 —
thin), AUDIT net +452.04 > 0, win 93.47/95.06, DISC epd
exactly 2.000, DSR 0.9397 (family-11), decay PASS, cluster
−201.82 → p95 201.82 vs cap 302.73, consec 2/2. It fails
three gates: MC DD by 3.58 · AUDIT epd 1.761 < 2 (short by
≈ 11 AUDIT trades — A's 16 AUDIT trades were mostly wins,
+89.81) · canonical PBO on the stated family (70.00%,
family-level; CSCV 17.06% passes). Runner-up on the DD arm:
V05 (miss 5.54) — but it carries E, so its AUDIT leftover
collapses to 63.90. The control V07 fails only MC + PBO but
barely moves the DD arm (miss 54.75): it prunes nothing in
the window, confirming the window legs are where the DD
lives — and that pruning them is what breaks the other gates.

## Is the density/window route exhausted for Jan?

**Yes — within veto + leg-prune forms (≤ 2 legs), plainly:**

1. **The cap-trap binds, as in Jul's W7 form.** Every prune
   cuts DD obs AND DD p95, but the own-relative cap
   (1.5 × DD obs) chases obs down. The deepest cut (V03,
   the exact cluster pair: DD obs 228.65 → 106.90, worst
   cluster −201.82 → −102.50, DISC ≤−80 losses 10 → 4) has a
   WORSE miss (+27.11) than the shallowest carrier cut
   (V04, +3.58): once the window pair is gone, block-10
   resampling stacks the next loss layer (the remaining
   −80/−60 class) while the cap keeps shrinking. There is
   no monotone path from any variant to a pass.
2. **No frequency headroom.** PC06 starts at epd
   2.369/2.109 — the thinnest base graded this round. Any
   window-leg prune breaks AUDIT epd ≥ 2 (best 1.891); a
   3-leg prune (outside this slate's 1–2-leg rule) would
   land near epd 1.3 and is dead on that gate before the DD
   arm is even read.
3. **The top carrier is regime-flipped.** E (FB_EURUSD_
   h11_0) holds 5 of the 10 DISC ≤−80 losses, but its AUDIT
   flow is 15/15 TP wins (+112.50); every E prune drops
   AUDIT leftover below the incumbent — the same wall as
   Plan A D07/D08, now measured inside PC06.

What remains is outside this form, named not run: a
trade-level window excision (not a leg prune; DISC-window-
fitted, would need its own pre-registration), restoring epd
headroom via Scenario 2 before pruning, or a non-veto base.
No gate was moved. Incumbent cycle60b + cycle60 stands;
PC06 stands as the DSR-passing, MC-DD-failing candidate it
was. January's EC position is unchanged by this attempt.

## Numbers block (contract §9) — incumbent vs PC06 vs closest variant V04
- DISC leftover: 29.82% → 39.02% (PC06) → 43.68% (V04) ·
  AUDIT leftover: 70.06% → 70.94% → 70.25% · AUDIT net:
  +749.88 → +541.85 → +452.04 · win (AUDIT): 95.56% →
  94.85% → 95.06% · entries/day DISC/AUDIT: 2.972/2.935 →
  2.369/2.109 → 2.000/1.761
- LCT P/q05 (canonical, vs incumbent): — → 95.96% / 23.27%
  (PC06, family-21 run) → 100.00% / 24.88% (V04)
- MC: P(profit) 0.9999 → 1.0000 → 1.0000 · DD p95 527.91 vs
  cap 688.94 → 402.13 vs OWN cap 342.98 FAIL → 306.31 vs
  OWN cap 302.73 FAIL (miss 3.58) · cluster p95 205.00 →
  201.82 → 201.82 (caps 302.73) · consec p95 3 → 2 → 2
- PBO: 40.00% (EC record) → 30.00% canonical family-21
  (CSCV 67.06%) → 70.00% canonical on stated family-11
  (family-level; CSCV second reading 17.06%) · DSR: 0.8630
  (historical) → 0.9256 (family-21) / 0.8961 (family-11) →
  0.9397 (family-11) · decay: PASS → PASS → PASS
- Loss-cluster mechanism: leg prune of the DD-window /
  repeated-loss carrier legs on the PC06 veto form (Jul
  attempt-4 density route); cluster arm −201.82 → −102.50
  in the deepest cut (V03) — but the DD arm, not the
  cluster arm, is Jan's binding constraint, and it does
  not yield.
- Trial count: 9 variants pre-registered (≤ 12 allowed);
  PBO/DSR family N = 11 (incumbent + PC06 + 9). DXY:
  BLOCKED-DATA, not used, not claimed.

## Method / files
- Runner: `run_jan_planC_attempt2.py` (census summary +
  slate pre-registered in its header; Phase-1 census script
  and output retained in the run record). Machinery reused:
  `work_new8/validate_new8.py` (seg_stats, split_seg, lct,
  round_pbo_dsr, daily_pnl), `work_29load/mc9_verbatim.py`,
  `support/planA_s1_engine.py` (CSCV PBO second reading).
- Machine record: `results/jan_planC_attempt2_run.json`;
  ledgers `results/jan_planC_attempt2_V01..V09_ledger.csv`.
- Sizing: NOT a gate in this round (brief §0) — not measured.

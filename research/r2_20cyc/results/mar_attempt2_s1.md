VERDICT: Mar attempt2 s1 — IMPROVED-at-simulated-replay (winner M18 = PC14_bb_rpos M15 veto mask + veto of the EURAUD h12 b6v slot, graded on its SIMULATED ledger with mar_rp refill counted: DISC leftover 78.27→79.89%, AUDIT leftover 22.99→46.52% — clears the incumbent by +23.53 and the pre-stated +1.00 winner margin (≥23.99) by +22.53 — LCT 81.72%/70.70%, MC verbatim flag PASS, PBO 0.00% / DSR 1.0000 canonical, LOO sensitivity survives; M20 EURAUD-slot + PREPLACESB partner also passes all gates simulated as alternate; simulated-replay is the highest verification level available for Mar — no true app-code driver exists; incumbent cycle86c+86s stands until a separate integration decision)

# Mar ATTEMPT 2 Scenario 1 — vetoes screened WITH simulated fall-through (2026-10-30, Wave 4e)

Same lesson, same machinery as the Dec attempt-2 file:
`run_wave4e_attempt2.py` reuses `run_wave4a_verify.py`'s
simulation (veto applied, then refill from the mar_rp candidate
walk's 56 merge-dropped rows under `core.new8_walk.
build_combined` occupancy verbatim — check unused + no symbol
time-overlap; March's combined takes exactly 1 pick per check,
so a vetoed pick frees its whole check). Partner forms then
refill second-priority from the PREPLACESB cand1 walk's rows
not already in the incumbent. Every candidate is graded on its
SIMULATED ledger. Research level only — no app push, no GitHub
push, no cron switch, no Streamlit, no Twelve Data calls.

## Machinery note — level of this verdict (read first)

**Simulated-replay is the highest verification level available
for March, and this verdict is stated at that level only.**
No driver regenerates the 695-pick 86c+86s combined from app
code check-by-check (Wave 4a machinery note stands). What
remains UNMODELLED, named not hidden: (1) base-stream
(86b/86s) next-signal fall-through at freed checks — the era
signal pool on disk belongs to the old C86-24 stream, not the
86c combined; (2) the vetoes' feature status OF THE REFILLS —
`mar_planC_s1_features.csv` covers exactly the 695 combined
rows, so a refill is accepted WITHOUT a PC14-mask feature check
(the EURAUD *slot* veto, being a strategy-name rule, does apply
structurally to any refill row carrying that strategy — none
of the accepted refills do); (3) displaced-incumbent return —
rows the replacement layer displaced do not come back when a
candidate pick is vetoed (build_replaced semantics). The
simulated grade is the honest bound available, not an app
replay.

## Controls — validated before any candidate was trusted

- CONTROL on the incumbent 695 ledger: DISC 562 / +5766.70 /
  78.27%, AUDIT 133 / +338.25 / 22.99%, MC DD p95 288.84,
  cluster p95 138.22 — EXACT vs the EC step record,
  `mar_planC_s1.md` and Wave 4a. CONTROL_OK = True.
- REFERENCE rows (Wave 4a simulated grades, NOT counted toward
  this attempt's 20): PC14 simulated — AUDIT leftover 21.18%
  ✗ (one −102.50 AUDIT refill erased the ledger gain);
  PC08 simulated — AUDIT leftover 8.50% ✗ and MC flag FALSE.
  Both stand rejected; this attempt starts from that fact.
Machine record: `results/wave4e_attempt2_run.json`; simulated
ledgers of all battery finalists: `results/mar_attempt2_M*_sim_ledger.csv`.

## Numbers block — incumbent vs winner M18 vs co-passing M20 (simulated)

| Metric | Incumbent 86c+86s | M18 PC14 mask + EURAUD slot veto (SIM) | M20 EURAUD slot veto + SB partner (SIM) |
|---|---|---|---|
| Total picks | 695 | 557 (549 kept + 8 refills) | 837 (660 kept + 3 refills + 174 partner) |
| DISC n / net | 562 / +5766.70 | 452 / +4231.54 | 681 / +8611.42 |
| DISC leftover | 78.27% | **79.89%** (+1.62) | **83.87%** (+5.60) |
| DISC win % / epd | 95.02% / 3.122 | 95.35% / 2.511 | 95.89% / 3.783 |
| AUDIT n / net | 133 / +338.25 | 105 / **+492.55** | 156 / **+589.81** |
| AUDIT leftover | 22.99% | **46.52%** (**+23.53 ✓; margin line 23.99 cleared by +22.53**) | **34.21%** (+11.22 ✓, margin cleared) |
| AUDIT win % / epd | 87.97% / 3.167 | 92.38% / 2.500 | 89.74% / 3.714 |
| LCT P / q05 (canonical) | 100% / 67.63% (record) | **81.72% / 70.70%** PASS middle (P margin +1.72 — thin, named) | **96.74% / 76.48%** PASS (middle + strict) |
| MC P(profit) | 1.0000 | 1.0000 | 1.0000 |
| MC DD obs → p95 vs own cap | 218.55 → 288.84 vs 327.83 PASS | 150.56 → **190.02 vs 225.84 PASS** | 150.17 → 220.90 vs 225.26 PASS (margin 4.36 — thin, named) |
| MC cluster obs → p95 vs cap | −102.50 → 138.22 vs 153.75 PASS | −102.50 → **106.64 vs 153.75 PASS** | −132.90 → 143.20 vs 199.35 PASS |
| MC consec obs → p95 | 2 → 2 PASS | 2 → 2 PASS | 2 → 2 PASS |
| MC middle (verbatim flag) | PASS | **PASS** (all arms) | **PASS** (all arms) |
| PBO / DSR (canonical, attempt-2 family-21) | 0.00% / 1.0000 (record) | **0.00% / 1.0000** | **0.00% / 1.0000** |
| Decay | WEAKENED | WEAKENED (leftover fall >20) — not FAIL ✓ | WEAKENED — not FAIL ✓ |
| Red lines | — | PASS (AUDIT net +492.55 > 0, > incumbent; no discovery collapse) | PASS |

§2 gate check for simulated M18: LCT-middle ✓ (81.72 / 70.70)
· AUDIT leftover strictly > incumbent ✓ (+23.53, and ≥ the
pre-stated +1.00 winner margin) · DISC leftover ✓ · MC middle
PASS all arms ✓ · PBO ≤ 50 ✓ · DSR ≥ 0.90 ✓ · decay not FAIL
✓ · win > 80% both segments ✓ · epd ≥ 2 both segments ✓
(DISC 2.511 / AUDIT 2.500) · AUDIT net positive and above
incumbent ✓. **All §2 gates pass on the simulated battery →
IMPROVED-at-simulated-replay.**

Why M18 over M20: the attempt's target metric is simulated
AUDIT leftover, and M18 posts the highest AUDIT leftover of
any all-gates passer (46.52 vs 34.21) with the better MC arms
(DD p95 190.02 vs 220.90; cluster p95 106.64 vs 143.20) and no
structural addition. M20 is the stronger-LCT (96.74 strict),
higher-frequency (epd 3.783/3.714) alternate and also passes
everything — recorded in full, not selected. Disclosed second
reading: R2-engine CSCV PBO on the attempt-2 family reads
100.0% for every Mar finalist (the same basis split as the
lane file and Jul); canonical basis governs per settled
ruling. PlanA-engine family DSR: 1.0000 for both winners.

## Leave-one-out sensitivity (required report — winner M18)

March's AUDIT segment is thin (winner n 105) and PC14's
rejection turned on ONE −102.50 refill, so the winner is
stress-read trade-by-trade (reported, not gated beyond the
locked gates + the stated margin):

- M18 simulated AUDIT leftover 46.52%. Its 8 refills are net
  AUDIT **−191.56** — the verdict does not rest on refill luck;
  it survives DESPITE the refills. The single best AUDIT
  refill is +13.44 (EURAUD h16 rsi14 refill, check 2024-03-04
  16:30). Removing it: AUDIT leftover **45.85%** — verdict
  unchanged. Removing the single best AUDIT trade overall
  (+33.44 CHFJPY incumbent pick, check 2025-03-04 16:30):
  AUDIT leftover **44.86%** — verdict unchanged, still +21.87
  above the incumbent and +20.87 above the margin line.
  **The M18 verdict is NOT one-trade fragile** — the mirror
  image of PC14, whose simulated failure was exactly one trade.
- M20 LOO: 34.21% → 33.16% (without best refill, +28.20
  partner EURAUD pick) → 32.96% (without best trade) — verdict
  unchanged.
- M11 (below) LOO: 49.09% → 48.54% / 47.74% — its AUDIT figure
  is robust too; M11 fails on LCT, not on fragility.

## Why the EURAUD slot is the key — and why M11 alone still fails

The b6v EURAUD h12 slot (`N3_b6v_vol_z_x_nx_sq_2708508f_S_
EURAUD_h12_1.27x3.7_H48`, 35 picks) is two different slots by
segment: DISC net **+782.31** (a discovery winner) but AUDIT
net **−346.06** with 7 full-stop losses (−541.76 gross) — it
alone manufactures March's thin-AUDIT problem. Vetoing it
alone (M11) posts the slate's highest simulated AUDIT leftover
(49.09%) but its DISC leftover FALLS (78.27 → 76.05), so the
paired LCT collapses (P 19.87% ✗ — the only failing gate;
MC PASS, DD p95 239.39, PBO/DSR PASS, margin ✓). M18 fixes
exactly that: the PC14 mask (which at ledger level raised DISC
leftover to 80.89%) restores the DISC side (79.89% simulated)
while the slot veto keeps the AUDIT gain — the two mechanisms
cover each other's weak segment. That complementarity, not
either mechanism alone, is the attempt-2 finding. (PC14 alone
simulated: 21.18% ✗. Slot alone: LCT ✗. Together: all pass.)

## Full pre-registered screen — all 20 new candidates, simulated grade (PC14/PC08 reference rows excluded)

| ID | Form | Kept | DISC left / net / epd | AUDIT left / net / epd | Refills (n, AUDIT net) | Screen / failing gate |
|---|---|---|---|---|---|---|
| M01 | PC01_mom16_vol | 611 | 79.36 / +5010.35 / 2.744 | 17.42 / +240.99 / 2.881 | 4, −102.50 | AUDIT ✗ |
| M02 | PC05_climax_volr | 571 | 82.37 / +4834.02 / 2.561 | 16.95 / +218.40 / 2.762 | 6, 0.00 | AUDIT ✗ (= ledger; no AUDIT refill accepted) |
| M03 | PC06_rsi_bb_vol | 573 | 82.04 / +5065.78 / 2.650 | 8.27 / +99.79 / 2.500 | 9, −102.50 | AUDIT ✗ |
| M04 | PC10_agree_loose | 579 | 78.64 / +4643.85 / 2.600 | 20.79 / +260.79 / 2.786 | 6, −102.50 | AUDIT ✗ (ledger 29.21 → simulated 20.79: the PC14 pattern repeats) |
| M05 | PC15_mom16_macd_vol | 392 | 80.91 / +3834.61 / 1.878 | 4.50 / +41.11 / 1.905 | 26, −173.76 | AUDIT ✗, epd ✗ |
| M06 | PC18_climax_mom16 | 580 | 81.45 / +4856.16 / 2.617 | 13.72 / +181.02 / 2.810 | 9, −102.50 | AUDIT ✗ |
| M07 | PC19_corr_dxy_eur | 523 | 80.84 / +4587.97 / 2.350 | 16.44 / +211.26 / 2.548 | 7, −76.32 | AUDIT ✗ |
| M08 | PC20_volz_rpos_mom | 396 | 77.65 / +3494.64 / 1.894 | −3.74 / −33.46 / 1.905 | 25, −187.20 | AUDIT ✗ (AUDIT-losing, red line), epd ✗ |
| M09 | PC03_mom4_mom96_vol | 591 | 80.95 / +4909.95 / 2.667 | 4.18 / +51.52 / 2.786 | 6, −102.50 | AUDIT ✗ |
| M10 | PC13_atr_vol_band | 550 | 81.24 / +4439.27 / 2.483 | 8.43 / +109.63 / 2.762 | 13, −102.50 | AUDIT ✗ |
| M11 | slot veto EURAUD h12 b6v | 660 | 76.05 / +4998.31 / 3.011 | **49.09 / +595.25 / 2.881** | 3, −89.06 | battery: **LCT P 19.87 ✗ alone** (closest by AUDIT leftover) |
| M12 | slot veto FB_EURUSD_h11_0 | 625 | 82.92 / +5670.52 / 2.778 | 19.84 / +281.69 / 2.976 | 0 | AUDIT ✗ (the slot's DISC losses do not carry to AUDIT) |
| M13 | slot veto FB_USDCHF_h17_0 | 562 | 82.21 / +5390.69 / 2.517 | 12.89 / +170.25 / 2.595 | 0 | AUDIT ✗ (slot is AUDIT-clean: 24 picks, 0 losses, +168.00) |
| M14 | slot veto EURAUD+EURUSD | 590 | 81.09 / +4902.13 / 2.667 | 46.51 / +538.69 / 2.690 | 3, −89.06 | battery: LCT P 76.82 ✗ alone |
| M15 | slot veto EURAUD+USDCHF | 527 | 80.16 / +4622.31 / 2.406 | 40.58 / +427.25 / 2.310 | 3, −89.06 | battery: LCT P 70.28 ✗ alone |
| M16 | slot veto all three | 457 | 86.48 / +4526.13 / 2.061 | 37.07 / +370.69 / 2.119 | 3, −89.06 | battery: **MC flag FALSE alone** — DD p95 166.89 vs own cap 163.89 (1.5×109.26), miss 3.00 (cap-trap: veto cuts DD obs, cap falls with it); LCT strict PASS 96.82/76.09 |
| M17 | slot veto EURUSD+USDCHF | 492 | 87.94 / +5294.51 / 2.172 | 8.94 / +113.69 / 2.405 | 0 | AUDIT ✗ |
| M18 | PC14 mask + EURAUD slot | 549 | 79.89 / +4231.54 / 2.511 | **46.52 / +492.55 / 2.500** | 8, −191.56 | **WINNER — ALL GATES PASS + margin** |
| M19 | PC10 veto + SB partner | 579 | 86.82 / +8888.46 / 3.494 | 16.66 / +300.80 / 3.595 | 6 + 195 partner, −62.49 | AUDIT ✗ (partner is DISC-rich +4244.61, AUDIT-thin +40.01; cannot rescue PC10) |
| M20 | EURAUD slot + SB partner | 660 | 83.87 / +8611.42 / 3.783 | **34.21 / +589.81 / 3.714** | 3 + 174 partner, −94.50 | **ALL GATES PASS + margin (alternate)** |

Pattern across M01–M10: every not-yet-simulated M15 veto from
the Plan C slate fails simulated AUDIT — most take the same
single −102.50 AUDIT refill (the mar_rp pool's AUDIT rows are
net-negative, as Wave 4a established), and several were already
below the incumbent at ledger level. The M15-veto route for
March is exhausted at simulated level; the slot+mask
combination is what survives.

## Loss-cluster mechanism (before vs after, winner M18)

The EURAUD slot's 7 AUDIT full-stops (−541.76) are March's
unseen loss cluster; the PC14 range-position arm (aligned M15
rpos ≤ 0.85) is the DISC-side cluster control. MC
(mc9_verbatim, 10,000 paths, seed 20261101): DD obs 218.55 →
150.56, DD p95 288.84 → 190.02; worst cluster obs unchanged
−102.50 (the single dominating pair is in neither vetoed
state — named, not hidden), cluster p95 138.22 → 106.64;
consec 2 → 2; P(profit) 1.0000 → 1.0000.

## Files

- Runner: `run_wave4e_attempt2.py` (slates pre-registered in
  its docstring before any attempt-2 measurement; Mar winner
  margin +1.00 pt stated there in advance)
- Machine record: `results/wave4e_attempt2_run.json`
- Simulated ledgers: `results/mar_attempt2_M11/M14/M15/M16/M18/M20_sim_ledger.csv`
- Gaps named: no app-code replay for Mar (machinery note);
  refill rows' PC14 feature status unmeasurable from disk
  (features file covers the 695 only — standing gap);
  historical mega-family DSR not re-graded (canonical
  attempt-2 family-21 basis governs, as in the lane file).

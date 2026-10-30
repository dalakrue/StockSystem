VERDICT: Dec planC s1 — NO IMPROVEMENT (Wave-3b independent M15-veto slate only; the lane verdict in dec_planC_s1.md stands)

# Dec Plan C S1 — Wave-3b addendum (independent cross-check slate)
Run 2026-10-30. This addendum does NOT replace dec_planC_s1.md
(the Dec lane's file: IMPROVED at ledger level via C07 slot veto,
fall-through replay still required). It records a second,
independent Plan C slate run the same night by the Wave-3b
worker, on the SAME incumbent ledger, so the two slates are
never confused:
- This slate: 20 pre-trade M15-confirmation VETOES only
  (PC01–PC20: M15 momentum/RSI/MACD/Bollinger/range-position/
  volume combinations + H1–M15 agreement + a correlated-leg
  form PC19 with EURUSD M15 momentum and a labelled Dukascopy
  DOLLARIDX H1 leg, price only). No slot veto, no partner
  merge, no office-slot creation — those forms belong to the
  Dec lane's slate in the main file.
- Scripts: run_pc3_wave3b.py + run_pc3_grade_extra.py. Raw:
  dec_planC_s1_wave3b_run.json (screen + 5 finals),
  dec_planC_s1_extra.json (canonical LCT + PBO/DSR for all 20,
  verbatim MC for the other 15), dec_planC_s1_features.csv,
  finalist ledgers dec_planC_s1_PC*_ledger.csv.
- Data: Dukascopy M15 CSVs, H1 resampled (fx_data.db not
  touched). DXY BLOCKED-DATA — not used.

## Behaviour study (independent measurement, agrees with main file)
- Bar level, December: M15 return std 0.1395% vs H1 0.2768%
  (~2× per H1 bar — intraday partial mean-reversion); lag-1
  autocorr ≈ 0 both; up-share ≈ 49.7/50.1%.
- M15 volume by entry UTC hour: 14:00 = 2,921 · 13:00 = 2,642 ·
  10:00 (16:30 MMT, IN-OFFICE) = 1,738 · 11:00 = 1,642 vs
  all-hour mean 1,601. The office hour is mid-pack on volume —
  NOT the thinnest hour (agrees with the main file's study).
- Trade level (954 picks, 46 losers, max consec 2): losers vs
  winners differ only weakly on M15 state (vol_z 0.396 vs
  0.456; signed RSI −4.25 vs −2.64; signed range position
  −0.236 vs −0.095). Climax state (vol_z > 1 AND signed range
  position > 0.6): 0.0% of losers, 2.09% of winners — climax
  vetoes delete winners in December too.
- Incumbent reproduced independently, bit-for-bit on the MC
  arms: n 954, DISC net +8814.06, AUDIT net +1090.28, MC
  P(profit) 1.0000, DD obs 252.24, DD p95 309.61 (lane record
  309.60), cluster obs −120.09, cluster p95 158.1, consec 2,
  mc_middle_pass TRUE. Registry read fresh: Dec best
  cycle94c, second cycle94s ✓.

## Result of this slate: NO IMPROVEMENT
Canonical (validate_new8) grading, all 20 cycles graded
(LCT + PBO/DSR for every cycle; verbatim MC for every cycle):
- PC16_strict_all passes LCT strict (P 100.00% / q05 82.68%),
  MC verbatim (DD p95 126.30 vs own cap 153.75), PBO 0.00%,
  DSR 0.9926, AUDIT leftover above incumbent on both
  conventions — and fails ONLY entries/day: DISC 1.080 /
  AUDIT 0.978, both < 2. REJECTED on entries.
- PC03 (best full-frequency AUDIT riser): AUDIT leftover up
  (aggregate 49.18% vs inc 46.68%), MC PASS (DD p95 239.00 vs
  cap 269.61), DSR 1.0000, PBO 0.00% — canonical LCT P 74.17%
  < 80 FAIL. REJECTED on LCT alone.
- PC01: AUDIT aggregate 53.41% (highest full-frequency) but
  canonical LCT P 50.64% FAIL and MC verbatim FALSE (DD p95
  199.46 vs own cap 198.84, miss 0.62). PC05/PC14: MC PASS,
  canonical LCT 45.41% / 45.48% FAIL. PC18/PC19: LCT FAIL and
  MC FALSE (DD p95 misses own cap by ~4 and ~2). PC13: LCT
  76.40% FAIL, AUDIT below incumbent. PC02: LCT FAIL + entries
  FAIL. All remaining cycles fail AUDIT leftover and/or LCT.
- CSCV PBO second reading for this family: 100.0% FAIL
  (disclosed; canonical basis 0.00% — the same basis split
  seen all round).
Conclusion: December's M15-veto space contains no promotable
form. The lane's C07 slot veto (main file) is a different
mechanism class and is unaffected by this result; both
results agree the incumbent's M15 state carries no broad
veto edge — December's fixable defect is slot concentration,
not M15 state.

## Disclosure — file collision during the parallel run
This worker's run initially wrote its screen output to
results/dec_planC_s1_run.json, overwriting the Dec lane's
run.json of the same name (19:37). The file was renamed to
dec_planC_s1_wave3b_run.json as soon as the collision was
found. The Dec lane's verdict file, its per-cycle ledgers
(dec_planC_s1_C01..C20_ledger.csv) and its
dec_planC_s1_bytrade.json (full per-cycle grades) survive
intact; only its run.json copy was lost, and every number in
dec_planC_s1.md is carried in the surviving files.

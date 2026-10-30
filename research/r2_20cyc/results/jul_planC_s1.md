VERDICT: Jul planC s1 — NO IMPROVEMENT

# Jul Plan C Scenario 1 — 20 cycles (+100 refinement), cycle78 incumbent
Run 2026-10-30. Research level only; no push, no live app opened.
Plan C design: DIFFERENT indicator×threshold combinations from Plan A —
pre-trade M15-confirmation VETOES on the incumbent's H1 picks (H1 stays
primary; M15 = feature/confirmation source only, evaluated at the signal
candle, check −90m, programme convention). NO leg prune, NO partner
fill, NO cooldown/sequential designs (all Plan A mechanisms excluded).
Scripts: run_jul_pc_s1.py / run_jul_pc_s1_refine.py /
run_jul_pc_s1_refine2.py. Raw: jul_pc_s1_study.json,
jul_pc_s1_screen.json, jul_pc_s1_final.json, jul_pc_s1_refine*.json,
jul_pc_s1_refine2*.json, jul_pc_s1_features.csv.
Data note: M15 features computed from the per-symbol Dukascopy M15
CSVs in ~/workspace/fx/dukascopy_m15/ (same source as fx_data.db
ohlc_m15; the DB was IO-contended by parallel lanes this run), H1
resampled from M15. DXY: BLOCKED-DATA (Wave 0, Twelve 429) — no DXY
used; no DOLLARIDX leg was used either.
Segments/leftover identical to Plan A: DISC ≤2023 (174 d), AUDIT ≥2024
(46 d), leftover = net ÷ gross wins @2.5 cost.

## M15/H1 BEHAVIOUR STUDY — July (measured before the cycles ran)

Bar level (all incumbent symbols, July months 2015–2026, Dukascopy):
- Per-bar return std: M15 0.1529% vs H1 0.3052% — an H1 bar carries
  almost exactly 2× (not 4×) the M15 move: July intraday moves
  partially mean-revert inside the hour, so M15 momentum at 1–4h
  horizons is a genuinely different signal from H1 momentum, not a
  finer copy of it.
- Lag-1 return autocorrelation ≈ 0 on BOTH timeframes (M15 −0.0044,
  H1 −0.0050): no exploitable bar-to-bar drift persistence in July;
  any M15 edge must come from state (volatility/volume/position),
  not from return chasing. Up-bar share ≈ 50% both (49.71 / 50.04).
- M15 tick volume by UTC hour (July mean): 15:00 = 2,457 vs all-hour
  mean 1,721 (+43%); 17:00 = 1,460; 18:00 = 1,541. The first check
  (21:30 MMT = 15:00 UTC) sits in July's highest-volume M15 hour;
  the later checks trade on ~40% thinner M15 flow — M15 volume
  conditions are therefore mostly informative at the first check.

Trade level (595 incumbent picks, features at signal candle):
- Only 32 of 595 picks lose (net ≤0); max consec losses = 2, so every
  "loss cluster" is a pair — the DD path is built from near-adjacent
  losing pairs separated by small wins (as Plan A found).
- Losers vs winners at signal: M15 vol_z 0.716 vs 0.583 · M15 vol
  ratio (4-bar/96-bar) 1.449 vs 1.389 · M15 ATR ratio 1.359 vs 1.221
  · direction-signed M15 RSI +1.71 vs −0.62 · signed M15 16-bar range
  position +0.063 vs −0.037 · signed H1 mom24 +0.284 vs +0.046.
  July losers are entered in HOTTER, more stretched M15 states and
  MORE aligned with H1 momentum than winners — counter-trend H1
  alignment is not the July loss signature.
- M15 (4h) vs H1 (24h) signed-momentum agreement: 68.24% of all
  picks, but only 59.38% of losers vs 68.74% of winners — timeframe
  disagreement tilts losing, weakly.
- FALSIFIED hypothesis (tested, not assumed): the volume-climax +
  stretched-range state (vol_z > 1 AND signed range position > 0.6)
  occurs in 0.0% of losers but 8.53% of winners. A climax veto
  (PC04) therefore deletes winners: DISC leftover fell to 63.51%.
  July loss clusters are NOT M15-climax events.

## Incumbent (cycle78; checks 21:30/23:30/00:30 MMT) — from Plan A record
- DISC: n 467, net +3300.44, win 94.65%, leftover 66.10%, epd 2.684
- AUDIT: n 128, net +877.62, win 94.53%, leftover 64.97%, epd 2.783
- MC verbatim: P(profit) 1.0000 · DD obs 143.81, DD p95 233.91
  (step cap 215.72 FAIL; own cap 215.72 — same by construction) ·
  cluster p95 169.57 vs cap 188.51 · consec p95 2. PBO 17.46% ·
  DSR 0.9998 · decay not FAIL (AUDIT/DISC leftover 0.98).

## Plan A winner C18 (grading reference, NOT re-run as a candidate)
DISC leftover 76.30% · AUDIT leftover 66.58%, net +883.40 · LCT
86.32%/62.17% · MC DD obs 138.13, DD p95 210.67 (step cap PASS,
own cap 207.20 FAIL by 3.47) · cluster p95 141.20 · consec 2.

## Best Plan C candidate 1 — PC03 (3-indicator M15 veto)
Rule (keep pick only if): signed M15 mom4 > −0.15% AND signed M15
mom96 > −0.8% AND M15 vol_z > −1.0. (Multi-horizon M15 momentum
floor + M15 volume floor; 53 picks vetoed.)
- DISC: n 418, net +3089.63, win 94.98%, leftover 70.03% (inc 66.10 ✓, C18 76.30 ✗)
- AUDIT: n 124, net +840.59, win 94.35%, leftover 63.98% (inc 64.97 ✗ by 0.99; C18 66.58 ✗)
- Entries/day: DISC 2.402 · AUDIT 2.696 (≥2 ✓)
- LCT vs incumbent: P 85.99% ≥ 80 ✓ · q05 58.77% ≥ 20 ✓
- LCT vs C18: P 58.87% · q05 62.74% (DISC-leftover basis; C18's DISC
  leftover is higher, so this does not beat C18 on DISC)
- MC verbatim 10,000: P(profit) 1.0000 · DD obs 159.11,
  DD p95 216.46 — step cap 215.72 FAIL by 0.74; own cap 238.67 PASS ·
  cluster obs −125.67, cluster p95 148.30 vs cap 188.51 ✓
  (before→after: 169.57 → 148.30) · consec obs/p95 2/2 ✓
- PBO (20-cycle Plan C family, CSCV): 97.22% FAIL (≤50 required) ·
  DSR 0.9932 (20-trial family basis; incumbent record 0.9998) ·
  decay PASS

## Best Plan C candidate 2 — RP0.93 = PC03 + signed M15 range-position cap ≤ 0.93
Loss-cluster mechanism (explicit): veto entries whose M15 16-bar
range position is stretched in the trade direction (the study's
loser profile: signed range position +0.063 vs −0.037, ATR ratio
1.359 vs 1.221) ON TOP of the PC03 momentum/volume floors — a
pre-trade exhaustion veto, not a sequential cooldown.
- DISC: n 402, net +2897.97, win 94.78%, leftover 68.67% (inc ✓, C18 ✗)
- AUDIT: n 117, net +845.19, win 94.87%, leftover 69.51% — beats
  incumbent 64.97 ✓ AND C18 66.58 ✓ (best AUDIT leftover of any
  gate-eligible Plan C candidate)
- Entries/day: DISC 2.310 · AUDIT 2.543 (≥2 ✓)
- LCT vs incumbent: P 74.21% < 80 ✗ · q05 56.91% ≥ 20 ✓
- LCT vs C18: P 15.08% · q05 60.94% (C18 wins the DISC pairing)
- MC verbatim 10,000: P(profit) 1.0000 · DD obs 130.23,
  DD p95 205.67 — step cap 215.72 PASS ✓; own cap 195.34 FAIL
  by 10.33 ✗ · cluster obs −125.67, cluster p95 144.65 vs 188.51 ✓
  (before→after: 169.57 → 144.65; vs C18 141.20, slightly worse) ·
  consec obs/p95 2/2 ✓
- PBO (refine-2 finalist family): 42.86% PASS · DSR 1.0000
  (4-finalist refine-2 family basis — small family, stated) ·
  decay PASS

## MC cluster arms BEFORE → AFTER (verbatim where marked)
Incumbent BEFORE: DDobs 143.81 · DDp95 233.91 · CLp95 169.57 · CONSEC 2.
(Screen = mc9 at 2,000–3,000 paths; step cap 215.72 shown.)
| Cycle | Mechanism (all M15, pre-trade) | DDobs | DDp95 | CLp95 | vs step cap |
|---|---|---|---|---|---|
| PC03 | mom4/mom96 floors + vol_z floor | 159.11 | 216.46 verb | 148.30 | FAIL by 0.74 (own cap PASS) |
| RP0.93 | PC03 + range-position cap 0.93 | 130.23 | 205.67 verb | 144.65 | PASS (own cap FAIL by 10.33) |
| RP0.90 | PC03 + range-position cap 0.90 | 130.23 | 208.66 verb | 146.30 | PASS (own cap FAIL by 13.32) |
| PC09 | H1/M15 momentum agreement | 125.67 | 223.15 verb | 146.40 | FAIL |
| PC01 | mom16 + vol_z floors | 130.43 | 229.04 verb | 155.90 | FAIL |
| PC14 | bb ≤1.0 + rpos ≤0.85 + mom16 floor | 145.43 | 230.43 verb | 146.40 | FAIL |
| PC04 | climax veto (hypothesis falsified) | 162.89 | 250.01 scr | 171.00 | FAIL |
| PC16 | strict all-aligned (epd 0.667 — entries FAIL) | 102.50 | 167.45 scr | 102.50 | PASS but rejected on entries |
Worst observed cluster (−125.67) is UNCHANGED by every Plan C veto:
its trades pass all M15 state conditions — the July worst cluster
is not M15-distinguishable at the signal candle. Cluster p95 still
improves (169.57 → 144.65–148.30) because the vetoes thin the
near-adjacent losing pairs around it.

## Why NO IMPROVEMENT (locked gates, not moved)
No Plan C candidate satisfies ALL of: AUDIT leftover > incumbent,
LCT-middle P ≥ 80, DD p95 under BOTH caps. PC03 passes LCT and the
own-relative DD cap but misses the step cap by 0.74 and AUDIT
leftover by 0.99 pt. RP0.93 beats both incumbents on AUDIT leftover
and passes the step cap, but its lower DDobs (130.23) tightens its
own-relative cap to 195.34, which it misses by 10.33, and its LCT
vs incumbent is 74.21% < 80%. Neither beats C18 on DISC leftover
(C18 76.30% vs 70.03 / 68.67). Trial count: 20 pre-registered cycles
+ 100 refinement variants (48 PC03 threshold grid + 8 intersections
+ 44 RP/PC14 micro-grid) — the base family's PBO of 97.22% is
reported, not hidden. Red lines intact everywhere (all finalists
AUDIT-positive, no discovery collapse). Plan A C18 remains July's
best R2 result so far; incumbent cycle78 stands until a lane clears
both DD cap readings. Sizing not a gate (brief §2).

## Completion note (Wave-2 finish, 2026-10-30) — all five finals graded explicitly

The finals in `jul_pc_s1_final.json` are PC01/PC03/PC09/PC16/PC17.
PC03 and RP0.93 are graded in full above; for completeness the
remaining finals are graded here against the same §2 gates
(incumbent AUDIT leftover 64.97%; family PBO 97.22% — the CSCV
figure over all 20 Plan C candidates' DISC block nets, i.e. in
97.22% of splits the in-sample-best candidate ranks below the
out-of-sample median — applies as a FAIL to every final):

- PC01 mom16_vol: DISC 67.16 / AUDIT 64.08 (FAIL, −0.89; small-
  improvement rule also fails) · net +844.05 · win 94.35 · epd
  2.420/2.696 ✓ · LCT vs inc 59.19/54.06 FAIL · MC DD p95 229.04
  (step FAIL, own cap 195.65 FAIL, mc_middle FALSE), cluster
  p95 155.90, consec 2 · DSR 0.9846 ✓ · decay PASS → REJECTED
- PC09 h1m15_agree: DISC 68.50 / AUDIT 65.00 (✓ +0.03, the only
  final above incumbent) · net +707.15 · win 94.44 · epd
  2.201/2.348 ✓ · LCT vs inc 70.97/55.19 FAIL · MC DD p95 223.15
  (step FAIL, own cap 188.50 FAIL, mc_middle FALSE), cluster
  p95 146.40, consec 2 · DSR 0.9861 ✓ · decay PASS → REJECTED
  (LCT + MC + family PBO)
- PC16 strict_all: DISC 81.93 / AUDIT 45.31 (FAIL, −19.66) ·
  net +169.84 · win 94.12 · epd 0.667/0.739 FAIL · LCT vs inc
  92.37/63.02 ✓ · MC DD p95 167.45 (step PASS, own cap 153.75
  FAIL, mc_middle FALSE), cluster p95 102.50, consec 1 · DSR
  0.9695 ✓ · decay WEAKENED (leftover fall > 20 — not the
  literal FAIL class, reported verbatim) → REJECTED
- PC17 climax_agree: DISC 65.93 / AUDIT 62.37 (both below
  incumbent — FAIL) · net +631.01 · win 94.06 · epd 2.011/2.196
  ✓ · LCT vs inc 46.91/51.39 FAIL · MC DD p95 228.17 (step FAIL,
  own cap 188.50 FAIL, mc_middle FALSE), cluster p95 150.10,
  consec 2 · DSR 0.9732 ✓ · decay PASS → REJECTED

Verdict unchanged: NO IMPROVEMENT — every final fails at least
three locked gates and all carry the family PBO FAIL.

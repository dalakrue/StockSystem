VERDICT: Jan planC s1 — NO IMPROVEMENT

# Jan Plan C Scenario 1 — 20 cycles (R2, brief §2/§3/§6/§9)
# Run 2026-10-30. Plan C = DIFFERENT indicator×threshold combinations
# than Plan A, heavy M15 candles + M15 volume (confirmation/feature
# source only; H1 primary). Design: pre-trade M15-CONFIRMATION VETOES
# on the incumbent's H1 picks — a pick is kept only if its M15 state
# at the signal candle passes the cycle's multi-indicator rule.
# NO leg-ban, NO cooldown, NO partner fill (all Plan A mechanisms
# excluded by the task). Machinery: validate_new8 verbatim
# (seg_stats, split_seg, lct, round_pbo_dsr) + mc9_verbatim.mc_test
# (block 10, 10,000 paths, seed 20261101, net = gross − 2.5).
# Leftover = by-trade convention (validate_new8), identical to
# Plan A: DISC days 176, AUDIT days 46. Raw: jan_planC_s1_run.json,
# jan_planC_s1_features.csv, jan_planC_s1_PC*_ledger.csv (5 finals).
# Regrade note: the screen pass stored leftovers in a run-internal
# convention; every gate number below was RECOMPUTED canonically
# from the saved ledgers this run (incumbent reproduces Plan A
# exactly: DISC 29.82% / AUDIT 70.06%, MC bit-for-bit).
# DXY: BLOCKED-DATA (Wave 0, Twelve 429) — no DXY claimed. PC19's
# dollar leg is DOLLARIDX-labelled (Dukascopy H1, no volume
# condition, data from 2017-12-01).

## January M15/H1 BEHAVIOUR STUDY (measured BEFORE the cycles)

Bar level (incumbent symbols, January windows, Dukascopy M15/H1):
- Per-bar return std: M15 0.1485% vs H1 0.2931% — an H1 bar carries
  ~2× (not 4×) the M15 move: January intraday moves partially
  mean-revert inside the hour, so M15 state at the signal candle
  is a genuinely different signal from H1, not a finer copy.
- Lag-1 autocorrelation ≈ 0 on BOTH timeframes (M15 −0.0146,
  H1 −0.0073): no bar-to-bar drift persistence; any M15 edge must
  come from state (RSI/BB position/volume/volatility), not from
  return chasing. Up-bar share ≈ 49.5% / 49.8% both.
- M15 tick volume by entry hour (UTC): 11:00 (17:30 MMT check)
  1,708.6 · 13:00 (19:30 MMT) 2,775.3 · 17:00 (23:30 MMT) 1,702.8,
  all-hour mean 1,678.5. The 19:30 MMT check sits in January's
  M15 volume peak (+65% vs mean); the other two checks trade on
  average flow — M15 volume conditions bite mainly at 19:30.

Trade level (658 incumbent picks, features at signal candle;
only 46 losers, max consec losses 3):
- Winners vs losers: M15 vol_z 0.718 vs 0.660 · M15 vol ratio
  (4/96) 1.443 vs 1.306 · M15 ATR ratio 1.228 vs 1.224 (no
  separation) · direction-signed M15 RSI −1.00 vs −2.70 (losers
  are entered MORE RSI-stretched against the trade) · signed
  M15 BB position 0.098 vs 0.119 · signed H1 mom −0.136 vs −0.046.
  January's separable M15 signal is RSI/BB stretch + volume
  confirmation — exactly the PC06 family below.
- M15-vs-H1 signed-momentum agreement: 68.39% of all picks, but
  71.74% of LOSERS vs 68.14% of winners — agreement does NOT
  separate winners from losers in January (losers agree MORE).
  Agreement vetoes (PC09/PC10/PC17) were therefore expected to
  fail, and did.
- FALSIFIED hypothesis: the volume-climax state occurs in 4.35%
  of losers but 6.86% of winners — a climax veto deletes winners
  in January (PC04/PC11 confirm: near-incumbent leftovers, no
  DSR/LCT gain). January loss clusters are NOT climax events.
- Traded symbols (12): AUDJPY, AUDNZD, AUDUSD, EURGBP, EURUSD,
  GBPJPY, GBPUSD, NZDCAD, NZDUSD, USDCAD, USDCHF, USDJPY.

## Incumbent (read fresh; reproduced EXACT before mining)
- Jan best cycle60b + second cycle60, combined 658 picks,
  checks 17:30 / 19:30 / 23:30 MMT (all OFF-HOURS).
- DISC: n 523, net +1310.13, win 92.35%, leftover 29.82%,
  epd 2.972. AUDIT: n 135, net +749.88, win 95.56%,
  leftover 70.06%, epd 2.935.
- MC verbatim: P(profit) 0.9999 · DD obs 459.29, DD p95 527.91
  vs OWN cap 688.94 PASS · cluster obs −201.82, p95 205.00 vs
  cap 302.73 PASS · consec obs/p95 3/3 PASS — MC middle PASS.
- PBO 40.00% (EC record). DSR 0.8630 (EC record, historical
  family) — the ONE failing EC item. In THIS run's family
  (incumbent + 20 Plan C cycles, N = 21) the same incumbent
  scores DSR 0.7869. Decay PASS.

## All 20 cycles — screen (n / net / win are convention-free;
## finals regraded canonically in the next section)
| cycle | rule (keep-only-if, all M15 at signal) | DISC n/net | AUDIT n/net/win |
|---|---|---|---|
| PC01 mom16_vol | mom16 floor + vol floor | 476/+1331.70 | 123/+654.17/95.12% |
| PC02 mom16_rsi | mom16 + RSI band | 249/+373.41 | 66/+378.61/95.45% |
| PC03 mom4_mom96_vol | mom4+mom96 floors + vol | 438/+887.96 | 128/+697.37/95.31% |
| PC04 climax_veto | veto climax state | 485/+1089.09 | 129/+704.88/95.35% |
| PC05 climax_volr | climax + vol-ratio band | 458/+1440.89 | 119/+625.40/94.96% |
| PC06 rsi_bb_vol | RSI band + BB band + vol band | 417/+1368.16 | 97/+541.85/94.85% |
| PC07 macd_mom16_atr | MACD + mom16 + ATR band | 278/+853.50 | 68/+451.99/98.53% |
| PC08 ema_mom96 | EMA gap + mom96 | 436/+689.71 | 126/+681.15/95.24% |
| PC09 h1m15_agree | H1/M15 momentum agree | 445/+907.54 | 119/+705.69/95.80% |
| PC10 agree_loose | agreement, loose | 422/+715.40 | 124/+661.57/95.16% |
| PC11 climax2 | climax veto v2 | 513/+1332.97 | 134/+742.38/95.52% |
| PC12 mom4_rsi_volr | mom4 + RSI + vol-ratio | 363/+948.09 | 89/+524.56/95.51% |
| PC13 atr_vol_band | ATR + vol band | 465/+1030.45 | 119/+640.88/95.80% |
| PC14 bb_rpos | BB + range position | 423/+1155.08 | 109/+548.24/94.50% |
| PC15 mom16_macd_vol | mom16 + MACD + vol | 275/+918.06 | 66/+424.67/98.48% |
| PC16 strict_all | all-indicator strict | 145/+132.32 | 43/+288.06/95.35% |
| PC17 climax_agree | climax + agreement | 414/+757.45 | 113/+660.69/95.58% |
| PC18 climax_mom16 | climax + mom16 | 438/+1110.66 | 117/+609.17/94.87% |
| PC19 corr_dxy_eur | correlated-leg: EUR mom16 + DOLLARIDX mom24 (labelled) | 416/+1237.43 | 103/+546.66/96.12% |
| PC20 volz_rpos_mom | vol_z + range-pos + mom | 267/+967.14 | 65/+428.56/98.46% |
Loss-cluster mechanism (brief §3, explicit): every cycle is a
pre-trade M15 exhaustion/confirmation veto aimed at the study's
loser profile (RSI-stretched, unconfirmed entries); cluster and
consec arms before→after are in the finals table below. No
sequential cooldown was used (Plan A mechanism, excluded).

## Finals — full battery, canonical convention
### PC06 rsi_bb_vol — the closest candidate (PASSES 8 of 9 arms)
Rule: keep pick only if direction-signed M15 RSI, M15 BB
position and M15 volume all sit inside their confirmation
bands (3 indicators × multi-threshold, M15 volume included).
144 picks vetoed (106 DISC / 38 AUDIT).
- DISC leftover 29.82% → 39.02% · AUDIT leftover 70.06% →
  70.94% (Δ +0.88, strictly > ✓) · AUDIT net +749.88 → +541.85
  (>0 ✓) · win 94.85% AUDIT (>80 ✓) · epd 2.369 DISC / 2.109
  AUDIT (≥2 ✓, thinnest AUDIT margin of any final)
- LCT (paired, DISC, canonical): P 95.96% ≥ 80 ✓ · q05 23.27%
  ≥ 20 ✓ — middle PASS.
- PBO 30.00% ≤ 50 ✓ (canonical basis, family N = 21). Second
  reading disclosed: CSCV PBO on the 20-cycle family = 67.06%
  FAIL — the same basis split seen all round (Jul: canonical
  0% vs CSCV 95–100% on correlated-variant families).
- DSR 0.9256 ≥ 0.90 ✓ — family = incumbent + 20 Plan C cycles,
  N = 21 trials, daily Sharpe 0.2491 vs incumbent 0.1987-class.
  Incumbent in THIS family = 0.7869; historical record = 0.8630.
  The DSR target IS reachable by an M15 route that does NOT
  remove AUDIT-winning flow (contrast Plan A D08).
- Decay PASS.
- MC arms BEFORE → AFTER: P(profit) 0.9999 → 1.0000 ✓ ·
  DD obs 459.29 → 228.65, DD p95 527.91 → 402.13 vs OWN cap
  342.98 (= 1.5 × 228.65) — FAIL by 59.15 ✗ · cluster obs
  −201.82 → −201.82, cluster p95 205.00 → 201.82 vs cap 302.73
  ✓ · consec obs/p95 3/3 → 2/2 ✓. mc9_verbatim flag FALSE on
  the DD arm alone. Under ruling (1) the OWN-relative cap
  governs — the veto halves DD obs, but DD p95 falls less, so
  the tightened cap is missed. This is the SAME failure shape
  as Jul C18 / Jul combined (own-cap miss), not a new defect.
- ⚠ FALL-THROUGH SUSPECT (ruling 2): PC06 is a VETO. Feb C08's
  ledger-level gain was rejected at app replay because freed
  slots refill with weaker picks. PC06 is NOT promoted on this
  evidence even aside from the MC arm; it would need the
  fall-through app replay before any integration decision.

### Other finals (all fail ≥2 locked gates)
| final | DISC left | AUDIT left | AUDIT net | win | epd D/A | LCT P/q05 (canon) | DSR (fam21) | PBO | MC DD p95 vs OWN cap | decay |
|---|---|---|---|---|---|---|---|---|---|---|
| PC07 macd_mom16_atr | 36.94% | 83.60% | +451.99 | 98.53% | 1.580/1.478 ✗ | 61.08/9.13 ✗ | 0.8107 ✗ | 30% | 382.60 vs 317.73 ✗ | PASS |
| PC11 climax2 | 30.93% | 69.84% ✗ | +742.38 | 95.52% | 2.915/2.913 | 42.09/15.80 ✗ | 0.8514 ✗ | 30% | 505.28 vs 711.44 ✓ (MC pass) | PASS |
| PC15 mom16_macd_vol | 39.82% | 82.75% | +424.67 | 98.48% | 1.562/1.435 ✗ | 71.76/21.23 ✗ (P<80) | 0.8536 ✗ | 30% | 360.82 vs 302.73 ✗ | PASS |
| PC20 volz_rpos_mom | 43.10% | 82.85% | +428.56 | 98.46% | 1.517/1.413 ✗ | 77.67/26.09 ✗ (P<80) | 0.8866 ✗ | 30% | 308.96 vs 273.75 ✗ | PASS |
Pattern: the tight M15 vetoes (PC07/PC15/PC20) post the best
AUDIT leftovers of the round (82–84%) but starve entries/day
below 2 and fail LCT-P/DSR — January cannot be both this
selective and this frequent at its current check times. The
loose veto (PC11) keeps frequency and passes MC but moves
nothing else.

## Verdict reasoning (gates locked in brief §2 — none moved)
No cycle passes every promotion gate. PC06 is the round's
nearest January miss: it fixes the actual EC defect (DSR
0.9256 ≥ 0.90 in an honest 21-trial family, incumbent 0.7869
in the same family) WITHOUT Plan A's regime-flip cost —
AUDIT leftover RISES +0.88 instead of falling −7.76 — and it
passes LCT-middle, PBO (canonical), win, epd, AUDIT-net and
decay. It fails on ONE governing arm: MC DD p95 402.13 vs
its own-relative cap 342.98 (miss 59.15), with the CSCV PBO
second reading (67.06%) also against it, and it is a veto —
fall-through-suspect under the Feb C08 precedent. Under the
locked gates it cannot be promoted or called SMALL-IMPROVED
(SMALL-IMPROVED still requires the MC arm under the own-cap
ruling, as Jul C18's non-promotion established). January's
remaining problem is now precisely named: an M15-confirmed
form whose DD p95 falls as fast as its DD obs. Incumbent
cycle60b + cycle60 stands unchanged. Research level only —
nothing pushed, nothing integrated.

## Numbers block (contract §9) — incumbent vs best candidate PC06
- DISC leftover: 29.82% → 39.02% · AUDIT leftover: 70.06% →
  70.94% · AUDIT net: +749.88 → +541.85 · win: 95.56% → 94.85%
  (AUDIT) · entries/day: 2.972/2.935 → 2.369/2.109 (DISC/AUDIT)
- LCT P/q05: — (incumbent is the reference) → 95.96% / 23.27%
- MC: P(profit) 0.9999 → 1.0000 · DD p95 527.91 vs cap 688.94 →
  402.13 vs OWN cap 342.98 FAIL · cluster p95 205.00 vs cap
  302.73 → 201.82 vs cap 302.73 · consec p95 3 → 2
- PBO: 40.00% (EC record) → 30.00% canonical (CSCV second
  reading 67.06%) · DSR: 0.8630 (historical family) → 0.9256
  (this run's family N = 21; incumbent in same family 0.7869)
  · decay: PASS → PASS
- Loss-cluster mechanism: pre-trade M15 RSI/BB/volume
  confirmation veto (PC06); cluster arm 205.00 → 201.82,
  consec 3 → 2, DD obs 459.29 → 228.65 — but DD p95 does not
  fall proportionally, so the own-relative DD cap is missed.
- Trial count: 20 cycles pre-registered; PBO/DSR family
  N = 21 (incumbent + 20). DXY: BLOCKED-DATA, not used, not
  claimed; PC19's dollar leg is DOLLARIDX-labelled only.

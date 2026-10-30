VERDICT: Mar planC s1 — IMPROVED

**⚠ LEDGER-LEVEL ONLY — FALL-THROUGH-SUSPECT (Ruling 2).** Winner
PC14 is a confirmation VETO on the incumbent ledger. Per the Feb
C08 precedent this round, ledger-level veto gains can evaporate at
app replay with fall-through (freed slots refill with weaker
picks). **App replay with fall-through is REQUIRED before any
integration; nothing is promoted by this file.** Form of verdict
follows the Dec C07 precedent (IMPROVED, ledger-level, replay
required).

Winner: **PC14_bb_rpos** — M15 confirmation veto, keep a pick only
if ALL of: direction-aligned M15 Bollinger z ≤ 1.0 AND
direction-aligned M15 20-bar range position ≤ 0.85 AND aligned
M15 mom16 > −0.35 (features at the signal candle, check −90m;
H1 primary unchanged, entries at incumbent checks 17:30/18:30/
22:30/23:30 MMT only — Scenario 1, no timing shift). Kept 574 of
695 picks. DXY: BLOCKED-DATA (429) — no DXY used; the one
correlated-dollar cycle (PC19) used the DOLLARIDX-labelled H1 leg
only (no volume conditions, data from 2017-12-01) and did not win.

Base integrity: incumbent reproduced EXACTLY before mining —
695 picks; DISC leftover 78.27%, AUDIT net +338.25, MC DD p95
288.84 / cluster p95 138.22 = the 2026-10-29 EC step-test record
byte-for-byte. (An earlier aborted attempt graded the WRONG base —
the 724-pick parallel_regime ledger, DISC leftover 57.78% — and
was discarded in full; its features file is kept renamed
`*_WRONGBASE_aborted.csv` for the record.)

## March M15/H1 behaviour study (written BEFORE the cycles section, per brief §6)

Bar level (March months only, 16 incumbent symbols, Dukascopy
M15 resampled to H1): M15 return σ 0.1581% vs H1 σ 0.3155% (≈ √4
scaling, no extra M15 variance regime); lag-1 autocorrelation
M15 −0.0089 vs H1 −0.0070 (no exploitable M15 mean-reversion at
lag 1 on either timeframe); up-bar share M15 49.54% vs H1 50.07%.
M15 mean tick volume by check hour (UTC): 11:00 → 2,023; 12:00 →
2,574; 16:00 → 2,518; 17:00 → 1,974; all-hours mean 1,828 — the
12:00 UTC second-best slot and the 16:00 UTC slot sit in the
day's volume peak; the 17:00 close slot is the quietest check.

Trade level (695 incumbent picks, features at signal candle):
only 44 losers (net ≤ 0); max consecutive losses = 2 — March's
loss "clusters" are pairs, not runs, which is why every MC
cluster arm is dominated by a single −102.50 worst-cluster
observation that no veto in this slate removes (it survives in
all six finals: worstcl_obs −102.50 throughout; the cluster gain
comes through the p95 resample arm, 138.22 → 123.20).
Winners vs losers (direction-aligned means): M15 vol_z 0.772 vs
0.636 and vol_r4 1.821 vs 1.562 — losers are NOT volume-climax
trades; the climax state (vol_z > 1.0 & aligned rpos > 0.6)
covers 6.82% of losers vs 7.68% of winners — **the climax-veto
hypothesis is FALSIFIED for March** (unlike Jul, where it was
also falsified; the climax cycles PC04/PC11/PC17 indeed grade
flat: PC11 AUDIT identical to incumbent). What does separate:
aligned M15 RSI −0.76 (winners) vs −2.28 (losers) and H1 mom24
−0.069 vs −0.159 — losers enter against weaker aligned momentum,
but the effect is small. M15/H1 mom16 agreement is 68.35%
overall and HIGHER in losers (79.55%) than winners (67.59%) —
agreement is not a quality signal in March (PC09/PC10 confirm:
DISC leftover falls / LCT fails). Worst loss slots: the NEW8
b6v EURAUD h12 slot (7 trades, −541.76), FB_EURUSD_h11_0
(5, −381.10), FB_USDCHF_h17_0 (9, −342.94), FB_EURGBP_h16_2
(3, −175.10) — slot-targeted prunes were NOT used (veto form
only, per the fall-through ruling's preference against
ledger-level slot surgery claims).

## Numbers block — incumbent vs candidate (validate_new8 convention, @2.5)

| Item | Incumbent 86c+86s (695) | PC14_bb_rpos (574) |
|---|---|---|
| DISC leftover | 78.27% | **80.89%** |
| DISC net / win / epd | +5766.70 / 95.02% / 3.122 | +4556.92 / 95.43% / 2.556 |
| AUDIT leftover | 22.99% | **29.44%** (strictly > ✓) |
| AUDIT net | +338.25 | **+373.76** (> 0 ✓, > incumbent ✓) |
| AUDIT win / epd | 87.97% / 3.167 | 89.47% / 2.714 |
| Win > 80% / epd ≥ 2 | ✓ / ✓ | ✓ / ✓ (both segments) |
| LCT-middle (canonical V.lct) | record P 100% / q05 67.63% | **P 88.90% / q05 71.79%** (≥80 / ≥20 ✓) |
| LCT (R2 subset basis, disclosed) | — | P 68.25% / q05 64.68% |
| MC P(profit) | 1.0000 | 1.0000 |
| MC DD p95 vs own cap (1.5×obs) | 288.84 vs 327.83 | **239.46 vs 257.37 ✓** (also < step-test fixed cap 327.83) |
| MC cluster p95 vs cap | 138.22 vs 153.75 | **123.20 vs 153.75 ✓** |
| MC consec p95 vs cap (obs+2) | 2 vs 4 | 2 vs 4 ✓ |
| MC verbatim flag | PASS | **PASS (all arms)** |
| PBO | 0.00% (record) | **0.00% canonical** (≤50 ✓); R2-engine CSCV family reading 100.0% — disclosed basis split, same as Jul C18: CSCV reads 95–100% on every correlated-variant family this round, canonical basis governs |
| DSR | 1.0000 (record) | **1.0000 canonical / 1.0000 family-21** (≥0.90 ✓) |
| Decay | WEAKENED (exp<50%; leftover fall>20) | WEAKENED (same triggers) — not FAIL ✓ |

Loss-cluster mechanism + before/after: PC14's range-position
arm (aligned M15 rpos ≤ 0.85) is the cluster control — it blocks
entries chased at the extreme of the M15 20-bar range, the state
in which March's loss pairs form. Before → after: cluster p95
138.22 → 123.20 (−15.02), DD p95 288.84 → 239.46 (−49.38),
DD obs 218.55 → 171.58; worstcl_obs unchanged at −102.50 (the
single dominating pair is not in the vetoed state — named, not
hidden). Runner-up PC08_ema_mom96 also passes every gate
(AUDIT leftover 28.75%, LCT 85.50%/70.13%, DD p95 214.03 vs own
cap 225.12, cluster 114.23) but is second on both AUDIT leftover
and LCT, so PC14 is the selection under the strongest-first rule.

Full 20-cycle screen (DISC leftover / AUDIT leftover / AUDIT net):
PC01 79.15/25.04/+343.49 (LCT P 51.57 FAIL) · PC02 78.21/30.42/
+198.48 (epd 1.467/1.405 FAIL) · PC03 80.48/12.61/+154.02 ·
PC04 79.04/18.32/+253.68 · PC05 82.00/16.95/+218.40 (LCT PASS
89.77/73.90, AUDIT leftover FAIL) · PC06 81.71/16.92/+202.29 ·
PC07 80.06/11.22/+95.63 · PC08 81.25/28.75/+266.38 (all gates
PASS, runner-up) · PC09 74.76/17.08/+217.27 · PC10 78.17/29.21/
+363.29 (LCT P 44.01 FAIL) · PC11 77.68/22.99/+338.25 (= inc) ·
PC12 76.35/10.82/+102.25 · PC13 80.26/16.45/+212.13 ·
**PC14 80.89/29.44/+373.76 (WINNER)** · PC15 79.40/24.98/+214.87
(epd FAIL) · PC16 77.43/−1.40/−5.09 (AUDIT-losing, red line) ·
PC17 75.99/12.64/+152.17 · PC18 80.18/20.15/+258.91 (LCT canon
76.99 FAIL) · PC19 80.40/23.11/+287.58 (DOLLARIDX-labelled leg) ·
PC20 75.85/17.96/+153.75 (LCT FAIL). Pattern: nearly every veto
raises DISC leftover but only PC14/PC08 hold AUDIT leftover,
LCT and epd together — March's AUDIT segment (n133) is the
binding constraint, exactly as in the incumbent's own record
(22.99% vs DISC 78.27%).

Gaps: (1) fall-through app replay outstanding — the verdict is
ledger-level until it passes; (2) no partner/additive cycles in
this slate — all 20 are vetoes by the registered design, so if
replay rejects PC14 there is no additive fallback in this file;
(3) DSR/PBO on this run's 21-series family only (canonical basis),
historical mega-family not re-graded (standing gap, same as
Feb/Jul).

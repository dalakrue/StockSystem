VERDICT: Sep planA s1 — NO IMPROVEMENT

# Sep Plan A Scenario 1 — 20-Cycle Round R2 (2026-10-30)

Improvement job: **NO IMPROVEMENT** — no candidate clears all
locked §2 gates. The three LCT-passing forms (C02/C19/C20, all
built on the worst-slot veto) fail AUDIT leftover AND the MC DD
arm under the mc9 own-relative cap ruling; every form that
clears AUDIT leftover fails LCT or the entries/day floor.
Incumbent cycle91p+91s stands. All figures at LEDGER level
(no fall-through); every veto form is fall-through-suspect per
the standing flag — moot here, since none passes even at ledger
level.

Office job: **one ACCEPTABLE replacement found** — a created
cycle at **18:30 MMT** (entry 12:00 UTC, an off-hours :30 slot
outside the two standing added slots; the user is told here per
brief §4). Drop-16:30 and the created 00:30 cycle both grade
DOWNGRADE. Detail in the office table below. No adoption is
made by this worker — the grade is reported; the 18:30 form is
a baseline created cycle, not a mined Scenario-2 creation.

DXY: BLOCKED-DATA (Twelve Data 429, Wave 0) — no DXY feature
claimed. The one dollar leg used (C05/C07) is DOLLARIDX-labelled
(Dukascopy H1, no volume condition, data from 2017-12-01).

Incumbent read FRESH from the app registry this run
(`core/signal_mode.py`: Sep best = cycle91p, second = cycle91s;
best checks entry 01:00/10:00/11:00 UTC = 07:30 / **16:30
IN-OFFICE** / 17:30 MMT, second adds 02:00 UTC = 08:30 MMT).
Combined ledger rebuilt exactly: best ledger
Sep_PLANB9C_combined.csv (630) merged second-priority with the
R14 ledger MONTH_Sep_PLANB9SB_cand1_ledger.csv (310 → 47
accepted, 263 check_busy) = **677 picks**, reproducing the EC
record byte-for-byte: DISC n541 net +4075.39, AUDIT n136 net
+1152.25, MC DD obs 191.81 → p95 254.95, worst cluster −153.10
→ p95 155.17. Leftover convention = the lane by-trade
convention (validate_new8 seg_stats verbatim; DISC 171 d /
AUDIT 43 d), which reproduces the EC record's leftovers
(68.60 / 69.49). EC record for the incumbent: PASS (PBO 0.00%,
DSR 0.9982, MC middle PASS).

Fast re-scope (named gap): under heavy shared-DB contention
the M15 frame load stalled; this Plan A run is H1-primary
throughout (engine H1 features: RSI, mom24, MACD, ATR ratio,
H1 vol_z, Bollinger, H1 CLV proxy; EURUSD + DOLLARIDX
correlated legs). M15 veto variants were NOT run — M15-heavy
work is Plan C's brief, not Plan A's. Slot baselines are
H1-confirmed created cycles (Dec baseline form with H1
confirmation substituted for M15), labelled as such.

## Numbers block — incumbent 91p+91s vs best candidates

| Metric | Incumbent 91p+91s | C02 (veto worst-2 slots) | C19 (C01 + PLANB9C c1) | C10 (stack limit 2) |
|---|---|---|---|---|
| DISC n / net | 541 / +4075.39 | 434 / +3899.95 | 497 / +4285.53 | 518 / +3868.69 |
| DISC leftover | 68.60% | **76.23%** (+7.63) | **75.29%** (+6.69) | 67.44% (−1.16) |
| DISC win % / epd | 95.19 / 3.164 | 96.08 / 2.538 | 95.98 / 2.906 | 94.98 / 3.029 |
| AUDIT n / net | 136 / +1152.25 | 110 / +973.56 | 124 / +1053.77 | 131 / +1145.70 |
| AUDIT leftover | 69.49% | 67.07% (**−2.42 ✗**) | 67.44% (**−2.05 ✗**) | **71.16%** (+1.67 ✓) |
| AUDIT win % / epd | 94.85 / 3.163 | 94.55 / 2.558 | 94.35 / 2.884 | 95.42 / 3.047 |
| LCT P / q05 (DISC) | — | **89.56% / 67.25%** PASS | **85.58% / 67.87%** PASS | 0.00% / 59.48% **FAIL** |
| MC P(profit) | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| MC DD obs → p95 vs own cap | 191.81 → 254.95 vs 287.72 PASS | 109.80 → 180.34 vs **164.70 FAIL** | 109.80 → 182.25 vs **164.70 FAIL** | 199.31 → 268.99 vs 298.97 PASS |
| MC cluster obs → p95 vs cap | −153.10 → 155.17 PASS | −103.20 → 124.56 PASS | −103.20 → 130.64 PASS | −153.10 → 155.17 PASS |
| MC consec obs → p95 | 2 → 2 PASS | 2 → 2 PASS | 2 → 2 PASS | 2 → 2 PASS |
| MC middle (verbatim flag) | PASS | **FALSE (DD arm)** | **FALSE (DD arm)** | PASS |
| PBO / DSR (family-21, this run) | 0.00% / 0.9982 (EC record) | 40.00% / 1.0000 | 40.00% / 1.0000 | 40.00% / 0.9995 |
| Decay | PASS | PASS | PASS | PASS |
| Red lines | — | PASS | PASS | PASS |

§2 gate check: **no candidate passes all gates.** C02/C19/C20
pass LCT-middle, win, epd, PBO, DSR, decay and red lines, but
fail (a) AUDIT leftover strictly-> / small-improvement (67.07 /
67.44 / 67.18 vs 69.49 — below, not a tie) and (b) MC-middle
under the own-relative ruling: the veto cuts DD obs to 109.80,
so the own cap falls to 164.70 while p95 only reaches ~180.
(Under the incumbent's fixed step-test cap 287.72 the DD arm
would pass easily — the ruling in force is the own-relative
cap, as applied to Jul C18; both readings are stated, the
verdict follows the ruling.) C10 passes AUDIT leftover, MC,
epd, PBO/DSR and decay but its paired LCT is 0.00% — its DISC
leftover is below the incumbent's in essentially every paired
resample. C08 (cooldown) likewise: AUDIT 72.03 ✓, MC PASS,
LCT P 41.20% FAIL.

## Loss-cluster mechanism — headline (before vs after)

Diagnosis (DISC, measured on the combined ledger): the loss
mass is slot-concentrated — FB_AUDJPY_h11_0 (DISC losses
−256.00) and FB_AUDUSD_h10_0 (−213.03) are the worst two slots;
the incumbent's worst cluster is −153.10 and its DD window is
built from these slots' full-size losses.

Mechanisms tested and their MC cluster/DD arms (mc9_verbatim,
10,000 paths, seed 20261101; incumbent DD p95 254.95, cluster
p95 155.17):
- **C02 slot veto (worst-2): cluster obs −153.10 → −103.20,
  cluster p95 155.17 → 124.56; DD obs 191.81 → 109.80, DD p95
  254.95 → 180.34** — the cluster mechanism WORKS in absolute
  terms; it is the own-relative cap (164.70) that the reduced
  obs drags below the p95, the same cap trap as Jul attempt 3.
- C08 post-loss cooldown 1: cluster obs −117.30, p95 146.15,
  but DD obs RISES to 220.59 (p95 284.08) — cooldowns delete
  small wins interrupting the DD path (the Jul finding,
  repeated in Sep) and LCT collapses (P 41.20%).
- C09 symbol block 48h: near-no-op (5 dropped; AUDIT leftover
  69.34, −0.15; LCT P 0.00% FAIL).
- C10 stack limit 2: cluster unchanged (−153.10 / 155.17);
  MC PASS on a higher obs (cap 298.97).

## Office-fix grade table (§2 check-time rule, locked)

Reference = full incumbent (DISC leftover 68.60, AUDIT
leftover 69.49, AUDIT net +1152.25, AUDIT win 94.85%).
IMPROVE = AUDIT leftover up AND DISC leftover not down.
DOWNGRADE = AUDIT leftover down > 0.5 pt OR win < 80% OR AUDIT
net down worse than −max(25, 10% of 1152.25) = −115.23.
Created cycles = pre-registered baseline form (H1 mom4
direction, H1 mom1 alignment + H1 vol_z > −1 confirmation,
TP 20 / SL 100, hold ≤ 48 H1 bars, SL-first, top-2 per check
by |H1 mom4|), graded as DROP-16:30 + slot picks (replace).

| Option tested | DISC leftover | AUDIT leftover | AUDIT net | AUDIT win | Grade |
|---|---|---|---|---|---|
| Drop 16:30 only (no replacement) | 71.45 (+2.85) | 74.16 (+4.67) | +956.68 (**−195.57**) | 95.70% | **DOWNGRADE** (net arm: −195.57 worse than −115.23 line) |
| Created cycle at 00:30 MMT (entry 18:00 UTC), replace | 46.84 (−21.76) | 44.53 (−24.96) | +1548.58 (+396.33) | 88.18% | **DOWNGRADE** (AUDIT leftover −24.96) |
| Created cycle at 00:30 MMT, add-only (16:30 kept — not a fix) | 48.44 (−20.16) | 45.57 (−23.92) | +1744.15 | 88.97% | **DOWNGRADE** (AUDIT leftover) |
| Created cycle at **18:30 MMT** (entry 12:00 UTC), replace | 67.76 (−0.84) | **73.64 (+4.15)** | **+2609.98 (+1457.73)** | 92.38% | **ACCEPTABLE** |

Slot baselines standalone: 00:30 — DISC leftover 30.02 / AUDIT
26.71, epd 2.327/2.953, n 525 (a weak slot; it dilutes the
combined form despite adding net). 18:30 — DISC leftover
65.00 / AUDIT 72.96, epd 2.257/3.023, n 516 — a genuinely
strong created slot at baseline level; combined with the
16:30 drop it lifts AUDIT leftover +4.15 and AUDIT net
+1457.73 at a DISC leftover cost of −0.84 (not down enough to
be IMPROVE, not a DOWNGRADE trigger) → **ACCEPTABLE, the only
non-DOWNGRADE office option tested for Sep.** Caveats: this
is a baseline created cycle measured at ledger level, NOT a
mined 20-cycle Scenario-2 creation and NOT an app replay; the
May/Dec lesson (bare replacements grade DOWNGRADE) holds for
Sep's drop and 00:30 forms, and 18:30's ACCEPTABLE grade
should be confirmed by a mined creation run before any
adoption. The 16:30 check itself is net-critical in Sep too
(214 of 677 picks; dropping it costs −195.57 AUDIT net).

## All 20 cycles (by-trade DISC / AUDIT leftover; epd DISC/AUDIT)

Direct — slot vetoes + loss-cluster controls:
- C01 veto FB_AUDJPY_h11_0 (worst DISC cluster slot): dropped 78 · 74.21 / 66.84 · epd 2.795/2.814 · LCT 73.71/65.53 FAIL · MC flag FALSE (DD p95 182.31 vs own cap 164.70)
- C02 veto worst-2 slots (+ FB_AUDUSD_h10_0): dropped 133 · 76.23 / 67.07 · epd 2.538/2.558 · LCT PASS · MC flag FALSE — closest LCT-passing form (table above)
- C08 cooldown 1 pick after a loss: dropped 31 · 69.18 / 72.03 · epd 3.018/3.023 · LCT 41.20 FAIL · MC PASS (DD obs rises — see cluster section)
- C09 symbol block 48h after a loss: dropped 5 · 68.33 / 69.34 · LCT 0.00 FAIL · MC PASS
- C10 same-direction stack limit 2: dropped 28 · 67.44 / 71.16 · epd 3.029/3.047 · LCT 0.00 FAIL · MC PASS

Direct — H1 multi-indicator vetoes (3–4 ind × thr, volume, correlated legs):
- C03 RSI+MACD+vol_z: dropped 288 · 70.10 / 50.41 · epd 1.825/1.791 — epd FAIL, AUDIT down
- C04 RSI+mom24+ATR band: dropped 321 · 64.94 / 62.82 · epd 1.637/1.767 — epd FAIL, both down
- C05 mom24 + DOLLARIDX-labelled leg + RSI: dropped 391 · 70.56 / 77.10 · epd 1.351/1.279 — AUDIT leftover best of the vetoes but epd FAIL and LCT 63.73 FAIL; MC PASS (DD p95 216.87 vs cap 229.65)
- C06 BB+RSI+vol_z+H1 CLV: dropped 281 · 65.70 / 88.05 · epd 1.865/1.791 — AUDIT leftover highest of all 20, epd FAIL (<2), LCT 40.65 FAIL; MC PASS
- C07 mom24 + EURUSD leg + DOLLARIDX leg + vol_z: dropped 274 · 66.30 / 62.77 · epd 1.883/1.884 — epd FAIL, AUDIT down

Partners (prior Sep mined designs, incumbent-priority merge):
- C11–C18 (PLANB c1/c2, PLANB9 c1/c2, PLANB9C c1/c2, ROUND2
  c1/c2): **accepted 0 of every design** — all partner picks
  sit at checks the combined already takes (check_busy) or
  overlap held symbols; combined = incumbent exactly
  (68.60 / 69.49). The Sep combined is saturated at its own
  check times, the Jan pattern: there is no silent-check room
  for any prior design to fill.

Combinations:
- C19 = C01 veto + PLANB9C cand1 partner (22 accepted at the
  veto-freed checks): 75.29 / 67.44 · LCT PASS · MC flag FALSE
  · AUDIT FAIL (table above)
- C20 = C01 veto + PLANB cand2 partner (14 accepted): 75.27 /
  67.18 · LCT 83.92/67.20 PASS · MC flag FALSE (DD p95 179.97
  vs 164.70) · AUDIT FAIL

Pattern, stated plainly: September splits into two families
that each fail the other's gate — the veto family buys DISC
leftover (+6.7…+7.6) and LCT but pays AUDIT leftover (−2.0…
−2.4) and trips the own-relative DD cap; the stateful/veto-
light family (C08/C10) keeps AUDIT leftover positive but its
DISC resamples never beat the incumbent (LCT 0–41%). The
partner channel is closed (0 accepted). Nothing meets the
locked bar; the incumbent — already EC-PASS — stands.

## Honest trial count / PBO-DSR note

Slate pre-registered in `run_sep_planA_s1.py` before measuring
(20 cycles + incumbent = 21 trials). PBO/DSR above are
validate_new8 round basis on that family (PBO 40.00% for every
shortlisted form — the family-level CSCV reading; DSR
0.97–1.0000). Named gaps: (1) M15 veto variants not run
(fast re-scope, above); (2) all results are ledger-level —
no fall-through app replay was run because no candidate
passed the ledger-level gates (the Feb C08 replay would only
be needed for a passing form); (3) the office 18:30 grade is
a baseline created cycle, not a mined creation.

Files: run data `results/sep_planA_s1_run.json` +
`results/sep_planA_s1_post.json` (by-trade recompute) +
`results/sep_planA_s1_post2.json` (C06/C09/C10 validation);
per-cycle ledgers `results/sep_planA_s1_C01..C20_ledger.csv`,
`sep_planA_s1_INC_ledger.csv`, `sep_planA_s1_DROP1630_ledger.csv`,
capped slot ledgers `sep_planA_s1_SLOT0030_*2_ledger.csv`,
`sep_planA_s1_SLOT1830_REPLACE2_ledger.csv`; scripts
`run_sep_planA_s1.py`, `run_sep_planA_s1_post.py`,
`run_sep_planA_s1_post2.py`.

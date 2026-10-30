VERDICT: Mar planA s2 — NO IMPROVEMENT

Scenario 2 CREATION for March, 20 cycles created natively for ONE
added off-hours slot — NOT incumbent replay (the 2026-10-29 replay
calculation was not repeated). DXY: BLOCKED-DATA (Wave 0, Twelve
Data 429) — the one dollar cycle (S08/S20 legs) used the
DOLLARIDX-labelled Dukascopy H1 leg only, no volume conditions,
data from 2017-12-01.

## Base used (per task order)

Strongest operative March form = **M18** (attempt-2 simulated
winner: PC14_bb_rpos M15 veto mask + EURAUD h12 b6v slot veto,
`mar_attempt2_M18_sim_ledger.csv`, 557 picks) — graded as the
primary base; the incumbent 86c+86s (695) is the secondary base.
Both reproduced EXACT before mining (asserted in the runner):
M18 DISC 79.89% / AUDIT 46.52% / AUDIT net +492.55, MC DD p95
190.02, cluster p95 106.64; incumbent DISC 78.27% / AUDIT 22.99% /
AUDIT net +338.25, MC DD p95 288.84 / cluster 138.22.

## Slot choice — DISC-only probes (pre-registered)

March uses NEITHER 07:30 nor 00:30 MMT (checks 17:30/18:30/22:30/
23:30), so both slots were screened with two DISC-only probes
(P-base = mom4 + M15 mom align + M15 vol_z > −1, TP20/SL100;
P-mom16 = mom16 + M15 mom align + H1 vol_z > −0.5, TP20/SL100):

| Slot | P-base DISC leftover / net | P-mom16 DISC leftover / net | Best probe |
|---|---|---|---|
| 07:30 MMT (entry 01:00 UTC) | −19.82% / −624.30 | −5.58% / −173.10 | −5.58% |
| 00:30 MMT (entry 18:00 UTC) | −21.12% / −683.40 | −5.42% / −174.40 | **−5.42%** |

**Chosen: 00:30 MMT** — stronger on DISC evidence only, by 0.16 pt.
Named plainly: BOTH slots are hostile on DISC probes (every probe
net-negative); 00:30 was the less-bad, not a good, hour. Behaviour
at the hour (March DISC bars, median across 28 symbols): M15
volume 6,316 at 00:30 vs 5,789 at 07:30; H1 range 15.45 vs 14.47
pips. The 20 creations were biased confirmation/state-heavy per
the Jan/Feb/Sep S2 lessons (RSI/BB/vol bands, MACD+EMA agreement,
M15 confirmation; raw-momentum forms kept only as contrast), with
two explicit cluster controls (S16 post-loss symbol cooldown,
S17 post-loss global skip-1). Features strictly before the entry
bar; entry at entry-bar open; SL-first, hold ≤ 48 bars; one pick
per check (strongest |direction momentum|); slot picks dropped
where the base holds the same symbol open (second priority).

## Created winner (DISC-only selection) — S06

S06 = mom4 direction + H1 MACD aligned + H1 EMA-gap aligned +
M15 mom4 confirm, TP20/SL100 — the slate's most confirmation-heavy
form and the ONLY one of 20 with standalone DISC net > 0.

Standalone S06: DISC n179 / net **+38.70** / leftover **1.25%** /
win 81.01% / epd 0.994; AUDIT n40 / net +26.20 / leftover 3.74% /
win 75.00% / epd 0.952. Even the winner is a near-zero-edge flow.

## Numbers block — M18 base vs M18+S06 combined (@2.5)

| Item | M18 base (557) | M18 + S06 (770) |
|---|---|---|
| DISC leftover | 79.89% | **52.68%** (down −27.21) |
| DISC net / win / epd | +4231.54 / 95.35% / 2.511 | +4337.74 / 91.40% / 3.489 |
| AUDIT leftover | 46.52% | **31.89%** (−14.63) |
| AUDIT net | +492.55 | +531.85 |
| AUDIT win / epd | 92.38% / 2.500 | 88.03% / 3.381 |
| Win > 80% / epd ≥ 2 | ✓ / ✓ | ✓ / ✓ (both segments) |
| LCT-middle vs base | — | **P 0.00% / q05 38.29% FAIL** (≥80 / ≥20) |
| MC P(profit) | 1.0000 | 1.0000 |
| MC DD obs → p95 vs own cap (1.5×obs) | 150.56 → 190.02 vs 225.84 ✓ | 220.12 → **359.02 vs 330.18 ✗** |
| MC cluster obs → p95 vs cap | −102.50 → 106.64 vs 153.75 ✓ | **−163.34** → 205.00 vs 245.01 ✓ |
| MC consec obs → p95 vs cap | 2 → 2 ✓ | 3 → 3 vs 5 ✓ |
| MC verbatim flag | PASS | **FALSE (DD arm alone)** |
| PBO | 0.00% (attempt-2 family) | **80.00% canonical family-21 FAIL** (≤50); CSCV second reading 26.59% disclosed |
| DSR | 1.0000 | 0.9790 family-21 (≥0.90 ✓) |
| Decay | WEAKENED | PASS (not FAIL ✓) |

Secondary base check — incumbent + S06: DISC leftover 78.27 →
56.78%, AUDIT leftover 22.99 → 17.36%, AUDIT net +338.25 →
+360.05, LCT P 0.00% / q05 38.88% FAIL, MC flag TRUE (DD p95
400.05 vs own cap 443.93) — also worse than the incumbent.

## §2 check-time grade: DOWNGRADE

Against M18: AUDIT leftover down 14.63 pts (> 0.5 pt line) →
DOWNGRADE on the leftover arm. (Net arm passes: +531.85 vs
+492.55; win 88.03% > 80%.) Not IMPROVE, not ACCEPTABLE — the
slot may not be adopted. §2 best gates also fail independently:
LCT-middle ✗, MC DD arm ✗, PBO ✗.

## Loss-cluster mechanism + before/after (named requirement)

The slot IMPORTS a cluster, exactly the Jan failure mode: worst
cluster obs −102.50 (base) → **−163.34** (combined), max consec
2 → 3, cluster p95 106.64 → 205.00. The two pre-registered
cluster controls do not rescue it: S16 (post-loss symbol
cooldown) standalone DISC −695.60 / combined AUDIT leftover
29.11%; S17 (post-loss global skip-1) standalone DISC −772.90 /
combined AUDIT 11.54% — both controls shrink an already-negative
flow rather than fixing it.

## Full 20-cycle screen (standalone DISC leftover / net; combined-vs-M18 DISC / AUDIT leftover)

S01 −21.12 / −683.40; comb 42.01 / 41.46 · S02 −5.42 / −174.40;
50.03 / −1.30 · S03 −25.49 / −825.10; 40.22 / 29.33 · S04 −13.99 /
−455.40; 44.76 / 0.22 · S05 −7.44 / −240.80; 49.36 / −7.12 ·
**S06 +1.25 / +38.70 (only DISC-eligible); 52.68 / 31.89** ·
S07 −7.06 / −349.00; 39.75 / 13.28 · S08 (DOLLARIDX leg) −20.90 /
−676.30; 42.21 / 35.34 · S09 −15.31 / −492.40; 44.12 / 34.65 ·
S10 −25.50 / −830.10; 42.38 / −16.32 · S11 −12.59 / −403.20;
46.59 / 26.62 · S12 −28.80 / −401.80; 56.65 / 43.51 · S13 −10.36 /
−143.80; 62.61 / 31.55 · S14 −24.95 / −1232.80; 31.63 / 34.26 ·
S15 −7.98 / −259.70; 47.87 / −7.25 · S16 cluster-ctrl −25.33 /
−695.60; 44.38 / 29.11 · S17 cluster-ctrl −29.68 / −772.90;
47.86 / 11.54 · S18 −14.85 / −457.60; 45.59 / **53.73** · S19
−34.51 / −1123.30; 37.86 / −5.42 · S20 −1.81 / −58.40; 49.39 /
32.41.

Pattern: 19/20 creations are DISC-losing standalone — March's
00:30 hour has no discovery edge to confirm, so confirmation
layers cannot manufacture one (the confirmation-heaviest form,
S06, is merely the least-bad). No combined form of any cycle
holds DISC leftover within 17 pts of the base (best S13 62.61%
vs 79.89%). The single combined AUDIT-leftover reading above the
base is S18's 53.73% (H1 vol_z ∈ [0,3] + M15 mom), but it is
DISC-ineligible standalone (−457.60) and its combined DISC
leftover collapses to 45.59% — dilution, not improvement, and it
fails the check-time IMPROVE definition (DISC leftover down) and
the LCT/best gates by construction. March joins Jan/Feb/Sep:
native creation at 00:30 does not survive grading; here it fails
on DISC itself, before any AUDIT regime-flip question arises.

## Verdict basis

NO IMPROVEMENT — no slot adopted. M18 (simulated) remains March's
strongest operative form and the incumbent 86c+86s stands in the
app; nothing is promoted by this file. Research level only — no
push, no live app.

Files: runner `run_mar_planA_s2.py`; machine record
`results/mar_s2_run.json`; slot ledgers
`results/mar_s2_S01..S20_slot_ledger.csv`; combined ledgers
`results/mar_s2_form_i_m18_plus_s2_ledger.csv`,
`results/mar_s2_form_ii_inc_plus_s2_ledger.csv`; probe ledgers
`results/mar_s2_study_*_ledger.csv`. Gap named: combined grades
for the 19 non-selected cycles are screen-level (leftover/net)
only — the full battery was run on the DISC-selected winner per
the pre-registered selection rule, as in the Jan/Feb S2 lanes.

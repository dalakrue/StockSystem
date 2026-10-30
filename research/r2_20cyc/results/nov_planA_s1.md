VERDICT: Nov planA s1 — IMPROVED

# Nov Plan A Scenario 1 — 20-Cycle Round R2 (2026-10-30)

Winner (improvement job): **C02 — veto of the two worst DISC
loss-cluster slots** of the incumbent: `CYB_cyb_pos_S_EURNZD_h15_
1.1x6.0_H48` (47 DISC picks, 8 losses — the most of any Nov slot)
and `BP_bp_pos_S_AUDCHF_h13_2.0x8.0_H48` (46 DISC picks, 6
losses), applied to the incumbent cycle93r+93s combined ledger.
All §2 best-promotion gates pass AT LEDGER LEVEL (no
fall-through — freed checks stay empty). **This is NOT yet a
promotion: C02 is a slot veto, and the Feb C08 precedent in this
same round showed a ledger-level veto IMPROVED rejected at app
replay with fall-through (AUDIT leftover 37.28→36.80%, LCT P
78.14%). C02 must pass the same fall-through app replay before
any integration decision.** Research level only — no app push,
no GitHub push, live crons untouched. Sizing not a gate (§0).

Office job: **NO replacement slot may be recommended** — drop,
baseline-transfer and every created cycle at 07:30 / 00:30 all
grade DOWNGRADE under the locked §2 check-time rule (table
below). November keeps its 15:30 (best) and 16:30 (second)
IN-OFFICE checks until a properly mined Scenario-2 creation
beats the rule; the created cycles here were mined for the
slot and still fail, so this is a creation result, not a bare
replay result.

DXY: BLOCKED-DATA (Twelve Data 429, Wave 0) — no DXY feature
is claimed anywhere in this file. The one dollar leg used
(C06/C09/C10) is DOLLARIDX-labelled (Dukascopy H1, no volume
condition, data from 2017-12-01; pre-2018 rows pass on NaN).

Incumbent read FRESH from the app registry this run
(`core/signal_mode.py`: Nov best = cycle93r, second = cycle93s;
checks entry 09:00 / 13:00 / 15:00 UTC = 15:30 IN-OFFICE /
19:30 / 21:30 MMT, second adds 10:00 UTC = 16:30 IN-OFFICE).
Ledger = the exact 826-pick combined the 2026-10-29 EC step
test graded (`work_new8/parallel_replace/combined/
Nov_PREPLACE_combined.csv`). Leftover convention =
validate_new8 seg_stats verbatim (by-trade, net pips), which
reproduces the EC record EXACTLY (DISC 77.05%, AUDIT 43.44%,
AUDIT net +982.60, MC DD p95 251.99 vs cap 275.72); days DISC
174 / AUDIT 41. Feature frames this run were read from the
per-symbol Dukascopy M15 CSVs (the fx_data.db source data,
H1 resampled from M15) because the shared DB was I/O-starved
by parallel lanes; the winning C02 is a pure slot veto and
uses no frame features at all.

## Numbers block — incumbent 93r+93s vs candidate C02

| Metric | Incumbent 93r+93s | Candidate C02 |
|---|---|---|
| DISC n / net | 676 / +9010.79 | 583 / +7794.46 |
| DISC leftover (by-trade) | 77.05% | **83.43%** (+6.38) |
| DISC win % | 94.08% | 95.54% |
| DISC entries/day | 3.885 | 3.351 |
| AUDIT n / net | 150 / +982.60 | 122 / +755.82 |
| AUDIT leftover (by-trade) | 43.44% | **44.03%** (+0.59, strictly >) |
| AUDIT win % | 88.00% | 89.34% |
| AUDIT entries/day | 3.659 | 2.976 |
| LCT P / q05 (DISC, paired) | — (reference; EC record P 99.59% vs predecessor) | **97.87% / 72.80%** — middle PASS, strict PASS |
| MC P(profit) | 1.0000 | 1.0000 |
| MC DD obs → p95 vs own cap (1.5×obs) | 183.81 → 251.99 vs 275.72 PASS | 189.19 → **237.06 vs 283.79 PASS** |
| MC cluster obs → p95 vs own cap | −183.81 → 183.81 vs 275.72 PASS | −183.81 → **183.81 vs 275.72 PASS** |
| MC consec obs → p95 | 2 → 3 PASS | 2 → 2 PASS |
| MC middle (mc9 verbatim flag) | PASS (TRUE) | **PASS (TRUE) — all arms** |
| PBO | 10.00% (EC record) | 0.00% (this-run family, validate_new8 basis — see note) |
| DSR | 1.0000 (EC record) | 1.0000 (this-run family, 21 trials — see note) |
| Decay | WEAKENED (exp<50%; leftover fall >20) | WEAKENED (same triggers) — not FAIL |
| Red lines | — | PASS (AUDIT net > 0, no discovery collapse) |

§2 gate check for C02: LCT-middle ✓ (97.87 ≥ 80, q05 72.80 ≥ 20)
· AUDIT leftover strictly > incumbent ✓ (+0.59 — the strict
form, the small-improvement rule is not needed) · win > 80%
both segments ✓ · entries/day ≥ 2 both segments ✓ · AUDIT net
positive ✓ · MC middle PASS all arms under the mc9
own-relative ruling ✓ · PBO ≤ 50% ✓ · DSR ≥ 0.90 ✓ · decay
not FAIL ✓. Two honest debits: AUDIT net is +755.82, i.e.
226.78 BELOW the incumbent's +982.60 (the two vetoed slots
were gross-positive overall — the veto trades raw net for
leftover quality and DD-tail thinning); and the result is
ledger-level with NO fall-through (above). DD obs rises
slightly (183.81 → 189.19) while DD p95 falls (251.99 →
237.06): the veto thins the resampled stacking tail rather
than the single observed window — the same density mechanism
that carried Jul attempt 4.

## Runner-up — C01 also passes ALL gates

C01 = veto of the single worst slot (EURNZD_h15 only, 60 picks
dropped): DISC leftover 81.11%, AUDIT leftover **43.71%**
(+0.27 ✓), AUDIT net +841.26, win 94.91 / 88.32, epd 3.615 /
3.341, LCT 82.92 / 70.09 ✓, MC flag TRUE (DD p95 243.17 vs own
cap 280.68; cluster p95 183.81), PBO 0.00% / DSR 1.0000, decay
WEAKENED. C02 is selected over C01 on DISC leftover (+6.38 vs
+4.06), AUDIT leftover (+0.59 vs +0.27) and LCT strength
(97.87 vs 82.92), with the lower DD p95 (237.06 vs 243.17).

## Loss-cluster mechanism — headline (before vs after)

Diagnosis (measured on the incumbent ledger, DISC): November
has only ~40 DISC losses in 676 picks, but they concentrate:
EURNZD_h15 carries 8, AUDCHF_h13 and FB_EURUSD_h9_0 carry 6
each. The incumbent's worst cluster (−183.81) and DD window
are stacking artefacts of these repeat-loss slots.

Mechanism (C02): pre-registered slot veto of the top-2 DISC
loss-count slots (identity fixed from DISC only, before any
candidate was measured); at ledger level the freed checks stay
empty (the conservative bound; fall-through replay is the
integration-time step that killed Feb C08 and has NOT been run
for C02 — flagged).

Before → after (MC, mc9_verbatim, 10,000 paths, seed 20261101;
incumbent reproduced: DD p95 251.99, cluster p95 183.81):
- DD obs 183.81 → 189.19 · DD p95 251.99 → 237.06
- Worst cluster obs −183.81 → −183.81 · cluster p95 183.81 → 183.81
- Max consec losses obs 2 → 2 (p95 3 → 2) · P(profit) 1.0000 → 1.0000

Stateful cluster controls all failed (see C12/C15 below):
post-loss cooldown and the rolling cluster cap latch dead
exactly as in Dec/Jan — once latched, skipped picks never
refresh the exited-state, so AUDIT empties. The slot veto is
the only cluster mechanism that survives contact with this
ledger's sparse-loss structure.

## Office-fix grade table (§2 check-time rule, locked)

Reference = full incumbent (DISC leftover 77.05, AUDIT leftover
43.44, AUDIT net +982.60, AUDIT win 88.00%). IMPROVE = AUDIT
leftover up AND DISC leftover not down. DOWNGRADE = AUDIT
leftover down > 0.5 pt OR win < 80% OR AUDIT net down worse
than −max(25, 10% of 982.60) = −98.26. Replacement form =
incumbent MINUS the 15:30 picks (entry 09:00 UTC, 223 DISC +
48 AUDIT picks) PLUS the slot cycle's picks. Slot cycles are
top-1-per-check across 28 symbols, TP 20 / SL 100, hold ≤ 48
H1 bars, SL-first, spread 2.5. "Replay" row = the V1 baseline
transfer (mom4 direction + M15 mom4 alignment + M15 vol_z >
−1): the incumbent's slot equations are hour-specific
(h9/h13/h15 strategies), so a literal replay of 93r at a new
hour is undefined — V1 is the Dec-lane baseline-transfer form,
labelled as the replay proxy. "Created" row = the best of 4
pre-registered mined variants (V1 baseline, V2 mom24+mom4
agreement, V3 mean-reversion on |mom24| ≥ 0.30, V4 mom4 + RSI
+ volume), variant chosen on DISC combined leftover ONLY,
AUDIT grading-only: at 07:30 the created variant is V3, at
00:30 it is V1.

| Option | DISC leftover | AUDIT leftover | AUDIT net | AUDIT win | Grade |
|---|---|---|---|---|---|
| Drop 15:30 only (no replacement) | 77.16 (+0.11) | 40.77 (−2.67) | +735.87 (−246.73) | 86.27% | **DOWNGRADE** |
| Replay (V1 baseline) at 07:30 MMT (entry 01:00 UTC) | 66.64 (−10.41) | 32.21 (−11.23) | +767.37 (−215.23) | 85.29% | **DOWNGRADE** |
| Replay (V1 baseline) at 00:30 MMT (entry 18:00 UTC) | 65.39 (−11.66) | 26.22 (−17.22) | +630.97 (−351.63) | 83.94% | **DOWNGRADE** |
| Created cycle V3 at 07:30 MMT | 67.78 (−9.27) | 31.09 (−12.35) | +691.87 (−290.73) | 83.33% | **DOWNGRADE** |
| Created cycle V1 at 00:30 MMT | 65.39 (−11.66) | 26.22 (−17.22) | +630.97 (−351.63) | 83.94% | **DOWNGRADE** |
| Complete fix: drop BOTH office checks (15:30 + 16:30) + created V3 at 07:30 | 64.19 (−12.86) | 26.30 (−17.14) | +518.18 (−464.42) | 82.14% | **DOWNGRADE** |

Slot cycles standalone: 07:30 V3 — DISC leftover 36.14 / AUDIT
−10.48 (AUDIT net −44.00, win 70.83% < 80 — unseen-losing,
would itself breach a red line standalone); 07:30 V1 — 33.78 /
5.46; 00:30 V1 — 28.76 / −17.47 (AUDIT net −104.90). Every
variant at both slots is far below incumbent quality: the
15:30 check's flow cannot be recreated at 07:30 or 00:30 by
any of the 8 mined forms. **No slot is ACCEPTABLE or IMPROVE;
nothing is recommended.** November's office fix remains open
and belongs to a full Scenario-2 mining run (20 cycles created
for the slot), not to this Plan A wave's 4-variant creation.

## All 20 cycles (by-trade DISC / AUDIT leftover; epd = DISC/AUDIT)

Direct — slot vetoes (loss-cluster, DISC-identified):
- C01 veto EURNZD_h15 (worst slot, 8 DISC losses): dropped 60 · **81.11 / 43.71 — ALL GATES PASS, runner-up (above)**
- C02 veto EURNZD_h15 + AUDCHF_h13 (top-2, 14 DISC losses): dropped 121 · **83.43 / 44.03 — WINNER (above)**

Direct — multi-indicator vetoes (3–4 ind × thr, H1 primary):
- C03 H1 mom24 aligned > −0.25 & RSI aligned > −15: dropped 123 · 75.63 / 54.29 — AUDIT leftover best of the vetoes but DISC −1.42 below incumbent; fails DISC side of the improvement comparison
- C04 M15 mom4 aligned > −0.20 & M15 RSI aligned > −10: dropped 117 · 74.71 / 51.42 — DISC down
- C05 H1 vol_z > −1.5 & M15 vol_z > −1.5: dropped 3 · 76.97 / 43.44 — near no-op, DISC down 0.08
- C06 correlated: EURUSD mom24 leg + DOLLARIDX-labelled leg (H1, no volume): dropped 188 · 78.40 / 38.65 — AUDIT down 4.79
- C07 = C03 × C04: dropped 197 · 74.35 / 51.26 — DISC down
- C08 = C04 × C05: dropped 119 · 74.66 / 51.42 — DISC down (= C04 on AUDIT; the volume leg adds nothing here)
- C09 = C03 × C06: dropped 254 · 77.79 / 47.18 · LCT 52.58 FAIL · MC flag FALSE (DD p95 209.39 but mc_middle_pass False on the verbatim arms) — not shortlisted past LCT/MC
- C10 = C03 × C04 × C05 × C06: dropped 321 · 76.65 / 43.54 — DISC down, AUDIT +0.10 only

Loss-cluster controls (explicit MC mechanism):
- C11 symbol block 48h after a loss on that symbol: dropped 15 · 76.74 / 42.13 — both down; mild harm
- C12 post-loss cooldown (skip next pick after an exited loss): dropped 603 · DISC 85.40 / AUDIT n 0 — sequential-state DEADLOCK in AUDIT (Dec C05 flaw, reproduced); REJECTED as a mechanism
- C13 same-direction stack limit ≥3 open: dropped 7 · 76.71 / 43.44 — near no-op, DISC down
- C14 day-cap 2 exited losses: dropped 0 — never triggers in November (losses too sparse per day); no-op = incumbent
- C15 rolling cluster cap (last-5 exited sum < −50): dropped 599 · DISC 85.55 / AUDIT n 0 — same latch deadlock as C12; REJECTED as a mechanism

Partners (incumbent-priority merges; DOLLARIDX rows excluded + counted):
- C16 PREPLACE cand1 merge: accepted 0 of 213 (all check-busy — that design IS the incumbent's own C04 slice) · = incumbent exactly
- C17 PREPLACE cand2 merge: accepted 7 · 77.25 / 43.44 (exact AUDIT tie) · LCT 100.00/68.01 strict PASS · MC flag TRUE (DD p95 256.55 — worse than incumbent 251.99) — passes the small-improvement rule on paper (tie + strongest LCT) but is strictly weaker than C02 on every headline arm; recorded, not selected
- C18 PREPLACESB cand1 merge: accepted 41 · 78.56 / 41.70 · LCT 82.26/69.86 · MC flag TRUE (DD p95 251.12) — AUDIT leftover down 1.74, fails the unseen gate
- C19 PLANB12C cand1 merge: accepted 6 · 77.22 / 43.44 (tie) — same class as C17, weaker; not selected
- C20 = C01 veto + PREPLACE cand2 merge: accepted 48 · 82.10 / 43.04 · LCT 85.80/72.00 · MC flag TRUE (DD p95 245.80) — AUDIT leftover 0.40 BELOW incumbent: fails both the strict gate and the small-improvement rule (tie required); the partner dilutes C01's AUDIT gain, the Feb A18 pattern

Pattern, stated plainly: November's incumbent is already the
cleanest EC record in the system, and almost every lever makes
it worse — the multi-indicator vetoes buy AUDIT leftover only
by spending DISC leftover, the partners are saturated or
AUDIT-dilutive, and the stateful cluster rules latch dead.
The one lever that works is compositional: remove the two
repeat-loss slots (14 of the DISC losses) and let the leftover
arithmetic and the MC tail improve on the remaining flow.

## Honest trial count / PBO-DSR note

Slate pre-registered in `run_nov_planA_s1.py` before measuring
(20 cycles + incumbent = 21 trials). PBO/DSR for C02 above are
validate_new8 round basis on that family (PBO 0.00%, DSR
1.0000). Named gaps: (1) the R2-engine CSCV PBO basis — which
read 95%+ on other months' correlated-variant families this
round (Jul addendum) — was NOT run for Nov; (2) decay for
every November form incl. the incumbent reads WEAKENED on the
programme's triggers (DISC→AUDIT leftover fall 77.05 → 43.44
is > 20 pts and AUDIT expectancy < 50% of DISC) — "not FAIL"
is the §2 bar and it holds, but November's unseen decay is
structural, not a C02 artefact; (3) C02 is ledger-level —
fall-through app replay is REQUIRED before integration
(Feb C08 precedent), and C12/C15's deadlock is a real
mechanism finding, not a hidden slot.

Files: run data `results/nov_planA_s1_run.json`; per-cycle
ledgers `results/nov_planA_s1_C01..C20_ledger.csv`; office
ledgers `results/nov_planA_s1_DROP1530_ledger.csv`,
`results/nov_planA_s1_SLOT0730_ledger.csv`,
`results/nov_planA_s1_SLOT0030_ledger.csv`,
`results/nov_planA_s1_COMPLETEFIX_ledger.csv`; script
`run_nov_planA_s1.py`.

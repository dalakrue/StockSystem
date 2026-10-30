VERDICT: Mar verify — REJECTED-at-simulated-replay (PC14 NOT VERIFIED: ledger-level IMPROVED fails the locked AUDIT-leftover gate once mar_rp fall-through refills are counted — AUDIT leftover 22.99→21.18% on the strength of ONE −102.50 refill; runner-up PC08 rejected at the same level, worse — AUDIT leftover 8.50% and MC flag FALSE; no true app-code replay exists for Mar, machinery note below; Mar incumbent cycle86c+86s stands)

# Mar VERIFICATION — fall-through test of Plan C PC14 / PC08 (2026-10-30, Wave 4a)

Closes the named gap in `mar_planC_s1.md` ("app replay with
fall-through is REQUIRED before any integration"). Research
level only — no app push, no GitHub push, live crons untouched.
**The ledger-level IMPROVED verdict for PC14 does NOT survive
fall-through, and PC08 fails harder.** No gate was moved.

## Machinery note — read this first (level of this verdict)

There is **NO true app-code replay for the full March 86c+86s
combined on disk**. What exists: `harness4.py` layer `mar_rp`
replays ONLY the replacement candidate walk through app code
(`core.new8_walk.walk157`) and merges it onto the RESEARCH
incumbent ledger (gate app4_mar_rp: combined EXACT, 695 rows);
`harness_mar22.py` regenerates only the OLD C86-24/86b base
over BRIEF21-era frames against a different (pre-86s,
pre-replacement) target. No driver regenerates the 695-pick
combined from app code check-by-check — there is no Mar
analogue of `harness_feb22.py` for cycle86c. Per the task's
fallback rule, the grade below is at **SIMULATED-replay**
level:

- What the simulation DOES model: March's combined takes
  exactly 1 pick per check (695 checks / 695 picks), so a
  vetoed pick frees its whole check. The refill source is the
  mar_rp candidate walk's own rejected rows — the 56 of its
  204 stored rows that `build_replaced` dropped because their
  check was busy with a kept incumbent pick. Under the app's
  occupancy rules (check-busy + symbol-overlap, verbatim form)
  those rows are re-offered, in check order, against the
  vetoed stream: a row is accepted only if its check is now
  free and its symbol does not time-overlap the stream or an
  earlier refill. PC14 frees 121 checks → 5 refills accepted;
  PC08 frees 242 checks → 24 refills accepted.
- What it does NOT model (named, not hidden): (1) base-stream
  (86b/86s) next-signal fall-through at freed checks — the
  era signal pool on disk (lib21_mar) belongs to the old
  C86-24 stream, not to the 86c combined, so no honest base
  refill can be drawn from it; (2) the vetoes' feature status
  OF THE REFILLS — `mar_planC_s1_features.csv` covers exactly
  the 695 combined rows, and the 56 refill-pool rows are not
  in it, so a refill is accepted here WITHOUT a PC14/PC08
  feature check (in a true app form the veto would presumably
  also screen candidate-layer picks; the direction of that
  correction is unknowable from disk data and is NOT assumed);
  (3) displaced-incumbent return — the 176 incumbent rows the
  replacement displaced do not come back when a candidate pick
  is vetoed (build_replaced semantics: displacement is
  structural, judged before occupancy). All three gaps cut
  the same way as in Feb: the simulated grade is the honest
  bound available, not an app replay.

## Method — control validated before the candidates were trusted

`run_wave4a_verify.py` (Mar section), battery = the Mar Plan C
lane's own conventions verbatim (validate_new8 seg_stats
180/42 days; mc9_verbatim 10,000 paths seed 20261101;
validate_new8 lct canonical / daily_pnl / round_pbo_dsr;
planA-engine dsr_family / pbo_cscv / full_decay):
- CONTROL on the incumbent 695 ledger: DISC 562 / +5766.70 /
  78.27%, AUDIT 133 / +338.25 / 22.99%, MC DD p95 288.84,
  cluster p95 138.22 — EXACT vs the 2026-10-29 EC step record
  and `mar_planC_s1.md`. CONTROL_OK = True.
- CANDIDATE CONTROLS: the PC14 mask rebuilt from the features
  file reproduces the lane's kept ledger EXACTLY (574 picks;
  DISC 80.89%, AUDIT 29.44%, MC DD p95 239.46, cluster p95
  123.20); the PC08 mask likewise (453 picks; DISC 81.25%,
  AUDIT 28.75%, MC DD p95 214.03). The simulation starts from
  verified bases and verified candidates.
Machine record: `results/wave4a_verify_run.json`; simulated
ledgers: `results/mar_verify_PC14_bb_rpos_sim_ledger.csv`,
`results/mar_verify_PC08_ema_mom96_sim_ledger.csv`.

## PC14 — numbers block (incumbent vs ledger-level vs simulated fall-through)

| Metric | Incumbent 86c+86s | PC14 ledger-level | PC14 simulated fall-through |
|---|---|---|---|
| Total picks | 695 | 574 | 579 (574 + 5 refills) |
| DISC leftover | 78.27% | 80.89% | **81.17%** (+2.90 ✓) |
| DISC net / win / epd | +5766.70 / 95.02% / 3.122 | +4556.92 / 95.43% / 2.556 | +4648.78 / 95.47% / 2.578 |
| AUDIT leftover | 22.99% | 29.44% (+6.45 ✓) | **21.18%** (**−1.81 ✗**) |
| AUDIT net | +338.25 | +373.76 | **+271.26** (> 0 ✓, < incumbent) |
| AUDIT win / epd | 87.97% / 3.167 | 89.47% / 2.714 | 88.70% / 2.738 |
| LCT P / q05 (canonical) | 100% / 67.63% (record) | 88.90% / 71.79% | **93.05% / 72.09%** PASS |
| MC P(profit) | 1.0000 | 1.0000 | 1.0000 |
| MC DD obs → p95 vs cap | 218.55 → 288.84 vs 327.83 PASS | 171.58 → 239.46 vs 257.37 PASS | 233.65 → **300.19 vs own 350.48 PASS** (also < fixed 327.83 ✓) |
| MC cluster obs → p95 vs cap | −102.50 → 138.22 vs 153.75 PASS | −102.50 → 123.20 vs 153.75 PASS | −102.50 → **128.80 vs 153.75 PASS** |
| MC consec obs → p95 | 2 → 2 PASS | 2 → 2 PASS | 2 → 2 PASS |
| MC middle (verbatim flag) | PASS | PASS | **PASS** (all arms — but DD p95 now ABOVE the incumbent's 288.84) |
| PBO / DSR | 0.00% / 1.0000 (record) | 0.00% / 1.0000 canonical | **0.00% / 1.0000** (canonical family-21, sim series; R2 CSCV family reading 100.0% — disclosed basis split, as in the lane file) |
| Decay | WEAKENED | WEAKENED | WEAKENED — not FAIL ✓ |
| Red lines | — | PASS | PASS (AUDIT net +271.26 > 0, no discovery collapse) |

What fall-through did: only 5 refills were accepted, and 4 of
them are DISC picks worth +91.86 net. The fifth is a single
AUDIT refill worth **−102.50** — one full-stop loss. On
March's thin AUDIT segment (n 114→115) that one trade erases
the entire ledger-level AUDIT gain and more: leftover
29.44 → 21.18, net +373.76 → +271.26 (below the incumbent's
+338.25), and DD obs jumps 171.58 → 233.65 (the refill loss
extends the drawdown window). This is exactly the Feb C08
pattern — the veto's unseen edge was partly an empty-check
artefact — except here a single trade carries it, which cuts
both ways and is stated plainly: the simulated failure is
real under the locked gates, and it is also fragile (one
trade). The gates do not grade fragility; they grade the
ledger in front of them.

§2 gate check for simulated PC14: LCT-middle ✓ (93.05 /
72.09) · DISC leftover ✓ · MC middle PASS ✓ · PBO ✓ · DSR ✓
· decay not FAIL ✓ · win > 80% ✓ · epd ≥ 2 ✓ · red lines ✓ —
**AUDIT leftover strictly > incumbent ✗ (21.18 < 22.99) ·
small-improvement rule ✗ (below incumbent; a tie would have
counted)**. One locked gate fails at simulated-replay level.

**Consequence: PC14 is NOT verified and is NOT promoted.**
March incumbent cycle86c+86s stands.

## PC08 (runner-up) — same treatment, rejected harder

| Metric | Incumbent | PC08 ledger-level | PC08 simulated fall-through |
|---|---|---|---|
| Total picks | 695 | 453 | 477 (453 + 24 refills) |
| DISC leftover / epd | 78.27% / 3.122 | 81.25% / 2.044 | 82.40% / 2.156 |
| AUDIT leftover | 22.99% | 28.75% | **8.50%** (**−14.49 ✗**) |
| AUDIT net / win | +338.25 / 87.97% | +266.38 / 88.24% | **+82.32 / 86.52%** (net45 −95.68) |
| LCT P / q05 (canonical) | — | 85.50% / 70.13% | 93.87% / 72.51% PASS |
| MC DD obs → p95 vs own cap | 218.55 → 288.84 PASS | 150.08 → 214.03 vs 225.12 PASS | 164.56 → **250.50 vs 246.84 FAIL** |
| MC cluster p95 / consec | 138.22 / 2 PASS | 114.23 / 2 PASS | 125.50 / 2 PASS |
| MC middle (verbatim flag) | PASS | PASS | **FALSE** (DD arm) |
| PBO / DSR (canonical family-21, sim) | — | PASS (lane file) | 0.00% / 1.0000 |
| Decay | WEAKENED | WEAKENED | WEAKENED (adds PF<1.2 trigger) — not FAIL |

PC08's 24 refills are worth +345.73 DISC but **−184.06
AUDIT**: its wider veto frees more checks and the replacement
walk's rejected rows are heavily AUDIT-negative. It fails
TWO locked gates at simulated level (AUDIT leftover, MC
middle). **PC08 is rejected at simulated replay in full** —
it is not a fallback for PC14.

## Files

- Runner: `run_wave4a_verify.py` (work dir root)
- Machine record: `results/wave4a_verify_run.json`
- Simulated ledgers: `results/mar_verify_PC14_bb_rpos_sim_ledger.csv`,
  `results/mar_verify_PC08_ema_mom96_sim_ledger.csv`
- Gaps named: no app-code replay machinery for Mar (above);
  base-stream fall-through unmodelled (above); refill picks'
  own PC14/PC08 feature status unmeasurable from disk
  (features file covers the 695 only — the task's anticipated
  limit, confirmed); historical mega-family DSR not re-graded
  (standing gap, same as the lane file).

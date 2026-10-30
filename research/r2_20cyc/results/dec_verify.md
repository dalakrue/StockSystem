VERDICT: Dec verify — REJECTED-at-simulated-replay (C07 NOT VERIFIED: the ledger-level IMPROVED fails the locked AUDIT-leftover gate once candidate-layer fall-through refills are counted — AUDIT leftover 53.02→47.60%; no true app-code replay exists for Dec, machinery note below; Dec incumbent cycle94c+94s stands)

# Dec VERIFICATION — fall-through test of Plan C C07 (2026-10-30, Wave 4a)

Closes the named gap in `dec_planC_s1.md` ("C07 must pass the
fall-through app replay before any integration decision").
Research level only — no app push, no GitHub push, live crons
untouched. **The ledger-level IMPROVED verdict for C07 does NOT
survive fall-through.** No gate was moved.

## Machinery note — read this first (level of this verdict)

There is **NO true app-code replay for the full December
94c+94s combined on disk**, and this file does not pretend
otherwise. What exists: `harness4.py` replays ONLY the new8
candidate layers (dec_rg, dec_rgc) through app code
(`core.new8_walk.walk157`) and merges them onto the RESEARCH
incumbent ledger (gate app4_dec_rgc: combined EXACT, 954 rows).
The base FB stream (cycle94b chain + cycle94s) is never
regenerated check-by-check by any driver on disk — there is no
Dec analogue of `harness_feb22.py`, and `cycle94c_best.
panel_entries` depends on persisted merged-walk state and live
frames, with no historical driver script. Per the task's
fallback rule, the grade below is at **SIMULATED-replay** level:

- What the simulation DOES model: the veto removes the 71
  FB_EURJPY_h11_0 picks; the 47 checks where that slot was the
  stream's ONLY pick become empty; the two candidate layers
  then fall through exactly as the app's occupancy rule
  (`core.new8_walk.build_combined`, verbatim) allows — a stored
  candidate-walk row (dec_rg 312-row walk first, then dec_rgc
  210-row walk, the cycle94c research order) is accepted at a
  check only if the check carries no pick in the current
  stream and its symbol does not time-overlap the stream or an
  earlier refill. Result: 33 refills (26 dec_rg + 7 dec_rgc),
  ALL at freed checks.
- What it does NOT model (named gaps, not hidden): (1)
  base-stream next-signal fall-through at the 24 vetoed checks
  where other base picks remain (no signal pool for the 94b
  stream exists on disk); (2) base-stream open-position
  cascades (a vetoed EURJPY position no longer blocks later
  EURJPY signals inside the base walk); (3) the candidate
  walks' internal state if they were re-run against the vetoed
  stream instead of reusing their stored walks. The Feb C08
  precedent says unmodelled fall-through of exactly this kind
  is where ledger gains die, so the simulated grade is an
  UPPER-bound-flavoured test, not a substitute for an app
  replay if one is ever built.

## Method — control validated before the candidate was trusted

`run_wave4a_verify.py` (Dec section), battery = the Dec Plan C
lane's own conventions verbatim (validate_new8 seg_stats
by-trade, days DISC 175 / AUDIT 45; mc9_verbatim 10,000 paths
seed 20261101; validate_new8 lct / daily_pnl / round_pbo_dsr;
planA-engine full_decay):
- CONTROL on the incumbent 954 ledger: DISC 771 / +8814.06 /
  78.43%, AUDIT 183 / +1090.28 / 53.02% — EXACT vs the EC step
  record and `dec_planC_s1.md`; MC DD obs 252.24, cluster obs
  −120.09, cluster p95 158.1 — exact; DD p95 309.61 vs the
  recorded 309.60 (0.01 float residue, disclosed).
  CONTROL_OK = True.
- CANDIDATE CONTROL: removing FB_EURJPY_h11_0 at ledger level
  reproduces C07 exactly (883 picks; DISC 87.52%, AUDIT
  54.92%, LCT 99.59/82.48, MC DD p95 210.26). The simulation
  starts from a verified base and a verified candidate.
Machine record: `results/wave4a_verify_run.json`; simulated
ledger: `results/dec_verify_C07_sim_ledger.csv` (916 picks).

## Numbers block — incumbent vs C07 ledger-level vs C07 simulated fall-through

| Metric | Incumbent 94c+94s | C07 ledger-level | C07 simulated fall-through |
|---|---|---|---|
| Total picks | 954 | 883 | 916 (883 + 33 refills) |
| DISC n / net | 771 / +8814.06 | 720 / +9415.84 | 745 / +9648.23 |
| DISC leftover (by-trade) | 78.43% | 87.52% | **87.82%** (+9.39 ✓) |
| DISC win % / epd | 95.72% / 4.406 | 97.08% / 4.114 | 97.18% / 4.257 |
| AUDIT n / net | 183 / +1090.28 | 163 / +1044.89 | 171 / **+944.80** |
| AUDIT leftover | 53.02% | 54.92% (+1.90 ✓) | **47.60%** (**−5.42 ✗**) |
| AUDIT win % / epd | 92.90% / 4.067 | 92.64% / 3.622 | 91.81% / 3.800 |
| LCT P / q05 (DISC) | — (reference) | 99.59% / 82.48% | **99.59% / 84.48%** PASS (middle + strict) |
| MC P(profit) | 1.0000 | 1.0000 | 1.0000 |
| MC DD obs → p95 vs own cap | 252.24 → 309.60 vs 378.36 PASS | 164.43 → 210.26 vs 246.65 PASS | 198.77 → **235.70 vs 298.16 PASS** |
| MC cluster obs → p95 vs cap | −120.09 → 158.1 vs 180.14 PASS | −102.50 → 120.23 vs 153.75 PASS | −102.50 → **121.84 vs 153.75 PASS** |
| MC consec obs → p95 | 2 → 2 PASS | 1 → 2 PASS | 1 → 2 PASS |
| MC middle (verbatim flag) | PASS | PASS | **PASS** (all arms) |
| PBO / DSR (family-21, sim series in C07 slot) | 40.00% / 1.0000 (EC record) | 0.00% / 1.0000 | **0.00% / 1.0000** |
| Decay | WEAKENED | WEAKENED | WEAKENED — not FAIL ✓ |
| Red lines | — | PASS | PASS (AUDIT net +944.80 > 0, no discovery collapse) |

What fall-through did: the refills are net DISC +232.40 but
net AUDIT **−100.09** (8 AUDIT refills). The candidate layers'
rejected rows are, on the unseen segment, net-negative —
filling the vetoed checks with them costs 7.32 AUDIT leftover
points vs the ledger-level bound (54.92 → 47.60) and pushes
AUDIT leftover BELOW the incumbent. The DISC side and every
MC arm survive (DD p95 235.70 still far under the incumbent's
309.60; the loss-cluster fix is real), but §2 promotion needs
AUDIT leftover strictly greater than the incumbent, with the
small-improvement rule as the only fallback (leftover not
below incumbent — 47.60 < 53.02 fails that too).

§2 gate check for simulated C07: LCT-middle ✓ (99.59 / 84.48)
· DISC leftover ✓ · MC middle PASS all arms ✓ · PBO ✓ · DSR ✓
· decay not FAIL ✓ · win > 80% ✓ · epd ≥ 2 ✓ · red lines ✓ —
**AUDIT leftover strictly > incumbent ✗ (47.60 < 53.02) ·
small-improvement rule ✗**. One locked gate fails at
simulated-replay level.

**Consequence, stated plainly: C07 is NOT verified and is NOT
promoted.** December's Plan C result is downgraded by this
verification to: a real DISC + Monte Carlo improvement (the
13-loss slot's cluster damage is genuinely removed) whose
unseen edge does not hold once the checks it frees are
refilled by the system's own next layers. Incumbent
cycle94c+94s stands. The office-fix finding in
`dec_planC_s1.md` is unaffected (both replacement slots
already graded DOWNGRADE there).

## Files

- Runner: `run_wave4a_verify.py` (work dir root)
- Machine record: `results/wave4a_verify_run.json`
- Simulated ledger: `results/dec_verify_C07_sim_ledger.csv`
- Gaps named: no app-code replay machinery for Dec (above);
  base-stream fall-through unmodelled (above); R2-engine CSCV
  PBO basis not run for the simulated series (canonical
  family-21 basis governs, as in the lane file).

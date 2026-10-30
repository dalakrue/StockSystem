VERDICT: Feb planA s1 — IMPROVED

# Feb Plan A Scenario 1 — 20-Cycle Round R2 (2026-10-30)

Winner: **C08 — slot veto of FB_EURUSD_h16_1** (the single worst
loss-cluster slot), applied to incumbent cycle85b. All §2
best-promotion gates pass at ledger level (caveats below).
Research level only — no app push, no GitHub push, live crons
untouched.

## Numbers block — incumbent cycle85b vs candidate C08

Incumbent read FRESH from the app registry this run
(`core/signal_mode.py`: Feb best = cycle85b, NO second-best;
checks 11/13/16 UTC = 17:30/19:30/22:30 MMT, all off-hours).
Ledger = app-replay `work_29load/replay_out/feb22_c19_app.csv`
(n 490; keys exact vs research C19 logs). Segment days (distinct
check dates): DISC 160, AUDIT 41 (incumbent uniform DISC epd
2.391 on the 161-day grid convention; 2.406 on distinct dates —
denominator stated, gates judged on distinct dates).

| Metric | Incumbent 85b | Candidate C08 |
|---|---|---|
| DISC n / net | 385 / +4293.42 | 335 / +3936.71 |
| DISC leftover | 76.90% | **82.39%** (+5.49) |
| DISC win % | 96.36% | 97.31% |
| DISC entries/day | 2.406 | 2.094 |
| AUDIT n / net | 105 / +453.92 | 98 / **+481.79** |
| AUDIT leftover | 37.28% | **42.65%** (+5.37, strictly >) |
| AUDIT win % | 86.67% | 87.76% |
| AUDIT entries/day | 2.561 | 2.390 |
| LCT P / q05 (DISC, paired) | — (reference) | **95.24% / 66.97%** — middle PASS, strict PASS |
| MC P(profit) | 1.0000 | 1.0000 |
| MC DD obs → p95 vs cap | 146.32 → **228.72 vs 219.48 FAIL** | 126.37 → **183.71 vs 189.56 PASS** (also < incumbent's fixed 219.48 cap) |
| MC cluster obs → p95 vs cap | −104.50 → 143.30 vs 156.75 PASS | −104.50 → **107.12 vs 156.75 PASS** |
| MC consec obs → p95 (cap obs+2) | 2 → 2 PASS | 2 → 2 PASS |
| MC middle (all arms) | **FAIL (DD arm)** | **PASS** |
| PBO | 2.50% (step-test record) | 0.00% (this-run family) |
| DSR | 0.1819 FAIL (historical BRIEF22 mega-family) | 1.0000 (this-run family, 21 trials — see honesty note) |
| Decay | — | not FAIL (proxy: yearly leftover positive every year 2016–2025, range 35.8–94.6%) |
| Red lines | — | PASS (AUDIT net > 0, no discovery collapse) |

§2 gate check for C08: LCT-middle ✓ (95.24 ≥ 80, q05 66.97 ≥ 20)
· AUDIT leftover strictly > incumbent ✓ · win > 80% both
segments ✓ · entries/day ≥ 2 both segments ✓ · AUDIT net
positive ✓ · MC middle PASS all arms ✓ · PBO ≤ 50% ✓.

## Loss-cluster mechanism — headline (before vs after)

Diagnosis (measured on the incumbent ledger): only 28 losses in
490 picks, but the observed DD (146.32) is ONE window —
2022-02-24 FB_EURUSD_h16_1 −101.00 gross, then 2022-02-28
FB_EURUSD_h11_0 −72.32 gross. The two FB_EURUSD slots hold
16 of the 28 losses (h16_1: 7 losses; h11_0: 9), each a full
−100-class SL hit. The DD arm fails because two same-symbol FB
losses land 4 days apart.

Mechanism (C08): pre-registered slot veto — FB_EURUSD_h16_1
(the slot carrying the −101 leg of the DD window) never fires;
the walk falls through to the next eligible pick (the C19 veto
precedent form). Ledger-level measurement has NO fall-through
(freed slots stay empty), so the epd/leftover figures are the
conservative bound; an app-replay with fall-through is the
integration-time verification step, not run here.

Before → after (MC, mc9_verbatim, 10,000 paths, seed 20261101;
incumbent reproduced byte-exact vs the step test):
- DD obs 146.32 → 126.37 · DD p95 228.72 → 183.71 (cap 219.48 → PASS)
- Worst cluster obs −104.50 → −104.50 · cluster p95 143.30 → 107.12
- Max consec losses 2 → 2 (p95 2 → 2) · P(profit) 1.0000 → 1.0000

The broader veto C07 (both FB_EURUSD slots) is stronger still
(DISC leftover 87.33%, AUDIT 69.11%, DD p95 112.15, LCT strict
PASS) but its ledger-level DISC entries/day is 1.712 < 2 — it
fails the epd gate as measured and is NOT promoted; it is the
first candidate to re-test with fall-through replay.

## Honest trial count / DSR note

This run's slate was pre-registered (20 cycles, written into
`run_feb_planA_s1.py` before measuring). DSR/PBO above use
`validate_new8.round_pbo_dsr` verbatim on the DISC daily family
{incumbent + 20 candidates} = **21 trials** → C08 DSR 1.0000,
PBO 0.00%. The incumbent's 0.1819 was computed against the full
historical BRIEF22-era trial family — a much larger N. The
honest claim is: **on this run's small pre-registered slate the
DSR arm passes (≥ 0.90)**; a like-for-like EC re-grade of C08
inside the historical mega-family was NOT run and remains a
named gap for the integration step. No trial-count shopping was
done: the family is exactly the 20 cycles of this run + incumbent.

## All 20 cycles (DISC / AUDIT leftover, epd = DISC/AUDIT)

Direct (stateful, exited-outcomes only, no fall-through):
- C01 post-loss cooldown 48h: dropped 64 · 78.03 / 26.50 · epd 2.206/1.780 · MC DD p95 267.67 (own cap 312.44, pass) but AUDIT leftover + epd fail · LCT P 61.55 fail
- C02 cooldown after 2 consecutive losses (7d): dropped 3 · 76.90 / 35.54 · MC DD p95 230.84 vs cap 219.48 FAIL — mechanism too weak (the two DD losses are not consecutive picks)
- C03 cluster cap ≥2 losses in last 5 exited: dropped 238 · 81.45 / — (AUDIT n 0) · DEADLOCK at ledger level: once triggered, no new exits arrive to clear the state — REJECTED as designed without fall-through
- C04 correlated-currency block 72h: dropped 65 · 75.53 / 24.82 · MC DD p95 271.48 FAIL (own cap) · LCT fail
- C05 same-direction loss block 72h: dropped 34 · 76.21 / 34.46 · MC DD p95 248.42 vs fixed cap FAIL · LCT fail
- C06 same-direction open stack limit 2: dropped 5 · 76.74 / 36.40 · MC DD p95 230.73 FAIL — stack limit does not touch the DD window
- C07 veto ALL FB_EURUSD slots: dropped 133 · **87.33 / 69.11** · epd 1.712/2.024 — epd gate FAIL (ledger level) · MC DD p95 112.15 PASS · LCT 99.58/71.75 strict PASS
- **C08 veto FB_EURUSD_h16_1 only: dropped 57 · 82.39 / 42.65 · WINNER (above)**
- C09 = C04+C03: dropped 303 · 83.23 / — (AUDIT n 0) · same C03 deadlock — REJECTED
- C10 = C01+C04+C06+C03: dropped 259 · 82.76 / — (AUDIT n 0) · same deadlock — REJECTED

Partners (prior Feb designs merged incumbent-priority;
DOLLARIDX rows excluded + counted — Dukascopy-labelled held
layer, never counted in any figure):
- C11 PLANB cand1 (+51 picks, 41 DOLLARIDX excl.): 78.96 / 30.62 — AUDIT down
- C12 PLANB cand2 (+27, 8 excl.): 78.14 / 41.36 · LCT strict PASS · MC DD p95 220.15 vs cap 219.48 FAIL by 0.67
- C13 ROUND2 cand1 (+53, 21 excl.): 80.50 / 15.53 — AUDIT down
- C14 ROUND2 cand2 (+18, 0 excl.): 78.26 / 24.24 — AUDIT down
- C15 ROUND4 cand1 (+1, 51 excl.): 76.96 / 37.28 — near-no-op, MC FAIL
- C16 ROUND4 cand2 (+70, 0 excl.): 76.72 / 40.41 — DISC down
- C17 PLANB9 cand1 (+57, 0 excl.): 77.70 / 31.00 — AUDIT down
- C18 PLANB9 cand2 (+34, 0 excl.): 77.02 / 35.52 · MC DD p95 241.22 FAIL, consec obs 3
- C19 PLANB9 partner (+53, 0 excl.): 77.59 / 31.00 — AUDIT down
- C20 PLANB9C partner (+64, 0 excl.): 77.80 / 39.01 · MC PASS (DD p95 214.91) · LCT P 70.91 FAIL

No partner beat C08; no partner is promoted. DXY: BLOCKED-DATA
(Wave 0, Twelve 429) — no DXY feature used or claimed anywhere
in this run; all dollar exposure above is the incumbent's own
EURUSD/other FX legs, and excluded partner DOLLARIDX rows are
labelled Dukascopy per the brief.

## Method / files

- Runner: `~/workspace/fx/work_20cyc_r2/run_feb_planA_s1.py`
  (slate pre-registered in its header). Machinery reused, not
  rebuilt: `work_29load/mc9_verbatim.py` (MC), `work_new8/
  validate_new8.py` (LCT, PBO/DSR, merge semantics),
  `work_29load/harness_feb22.py` app-replay ledger.
- Full machine results: `results/feb_planA_s1_run.json`;
  per-cycle ledgers: `results/feb_planA_s1_C01..C20_ledger.csv`.
- Sizing: NOT a gate in this round (brief §0, chained ÷3 ruling)
  — not measured, per instructions.
- Gaps named: (1) C08 verified at ledger level only — app replay
  WITH fall-through is required before any integration;
  (2) DSR like-for-like re-grade on the historical family not
  run (see honesty note); (3) C03-family cooldowns need a
  fall-through walk to be judged fairly.

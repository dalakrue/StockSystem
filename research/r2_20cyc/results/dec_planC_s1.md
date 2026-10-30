VERDICT: Dec planC s1 — IMPROVED

# Dec Plan C Scenario 1 — 20-Cycle Round R2 (2026-10-30)

Winner (improvement job): **C07 — veto of the single slot
FB_EURJPY_h11_0** (December's worst loss-cluster slot), applied
to the incumbent cycle94c+94s combined ledger. All §2
best-promotion gates pass AT LEDGER LEVEL (no fall-through —
freed slots stay empty). **This is NOT a promotion: the Feb C08
precedent in this same round showed a ledger-level IMPROVED
rejected at app replay with fall-through (AUDIT leftover
37.28→36.80%, LCT P 78.14%). C07 must pass the same fall-through
app replay before any integration decision.** Research level
only — no app push, no GitHub push, live crons untouched.

Office job: **NO replacement slot may be recommended** — both
tested off-hours slots grade DOWNGRADE under the locked §2
check-time rule (table below). December keeps its 16:30
IN-OFFICE check until a properly mined Scenario-2 cycle exists.

DXY: BLOCKED-DATA (Twelve Data 429, Wave 0) — no DXY feature
is claimed anywhere in this file. The one dollar leg used
(C09/C15) is DOLLARIDX-labelled (Dukascopy H1, no volume
condition, data from 2017-12-01; 2016 rows pass on NaN).

Incumbent read FRESH from the app registry this run
(`core/signal_mode.py`: Dec best = cycle94c, second = cycle94s;
checks entry 10:00/11:00/13:00 UTC = 16:30 IN-OFFICE / 17:30 /
19:30 MMT + second's 14:00 UTC = 20:30 MMT). Ledger = the exact
954-pick combined the 2026-10-29 EC step test graded
(`work_new8/parallel_regime/combined/Dec_PREGIMEC_combined.csv`).
Leftover convention = the Dec lanes' by-trade convention
(validate_new8 seg_stats verbatim), which reproduces the EC
record exactly (DISC 78.43%, AUDIT 53.02%); days DISC 175 /
AUDIT 45 (lane denominators). Cross-check under the user's
net÷gross-wins definition: incumbent 69.94 / 46.68, C07 77.23 /
48.83 — both conventions agree on the direction of every gate
comparison used below.

## December M15/H1 behaviour study (BEFORE the cycles)

Measured this run from fx_data.db (indexed queries only),
December windows 2015–2025 (25 Nov–5 Jan pulls), all 28 symbols:

- **Range resolution:** mean December bar range H1 = 17.72 pips
  vs M15 = 8.72 pips — one M15 bar carries ~49% of the hourly
  range, so the 4 M15 bars inside an H1 candle resolve the
  hour's path well; M15 confirmation is informative in December,
  not noise. This is why the M15 vetoes below can cut losses
  without cutting the win stream.
- **Momentum does NOT persist:** P(next H1 bar has the same sign
  as the trailing 4-bar H1 momentum) = 0.4826 across the 28
  symbols — below a coin flip. December H1 momentum continuation
  is worthless raw; the incumbent's edge lives in its equation
  mix and gates. (This also predicts — correctly, see office
  table — that crude momentum baselines at new hours grade
  poorly in December.)
- **Hour structure (entry-hour UTC → MMT label), December means:**
  | Entry UTC | MMT | H1 range (pips) | M15 vol (mean) |
  |---|---|---|---|
  | 01:00 | 07:30 (candidate) | 16.50 | 1,382.6 |
  | 10:00 | 16:30 IN-OFFICE | 18.57 | 1,680.0 |
  | 11:00 | 17:30 | 17.79 | 1,581.9 |
  | 13:00 | 19:30 | 25.10 | 2,528.7 |
  | 14:00 | 20:30 (second) | 24.68 | 2,775.5 |
  | 18:00 | 00:30 (candidate) | 15.14 | 1,439.8 |
  December's volatility and volume concentrate in the two
  evening checks (19:30/20:30 MMT ≈ US session); the office
  16:30 hour is mid-pack; both candidate replacement slots are
  materially quieter and thinner (07:30 M15 volume = 55% of the
  19:30 hour's; 00:30 has the lowest H1 range of the six).
  EURUSD M15 volume by hour tells the same story: 4,410 at
  13:00 UTC vs 1,737 at 01:00 and 2,282 at 18:00.
- **The office hour is AUDIT-critical:** the 16:30 check
  (entry 10:00 UTC) carries 262 of 954 picks. Removing it
  RAISES DISC leftover (78.43 → 81.56) but collapses AUDIT
  leftover (53.02 → 38.88) and AUDIT net (+1090.28 → +588.84):
  in the unseen years the office hour carries the month.
- Loss structure: only 46 losses in 954 picks, but one slot —
  FB_EURJPY_h11_0 — holds 13 of them (−1,017.40 gross, ~−102.5
  per full SL hit). The incumbent's observed DD (252.24) and
  worst cluster (−120.09) are slot-concentration artefacts,
  not broad decay. That is the Plan C target C07 removes.
- Named gap: a first-pass M15 intra-hour reversal share
  returned an implausible 0.0 (grouping bug) and was DISCARDED,
  not published; the study stands on the items above.

## Numbers block — incumbent 94c+94s vs candidate C07

| Metric | Incumbent 94c+94s | Candidate C07 |
|---|---|---|
| DISC n / net | 771 / +8814.06 | 720 / +9415.84 |
| DISC leftover (by-trade) | 78.43% | **87.52%** (+9.09) |
| DISC win % | 95.72% | 97.08% |
| DISC entries/day | 4.406 | 4.114 |
| AUDIT n / net | 183 / +1090.28 | 163 / +1044.89 |
| AUDIT leftover (by-trade) | 53.02% | **54.92%** (+1.90, strictly >) |
| AUDIT win % | 92.90% | 92.64% |
| AUDIT entries/day | 4.067 | 3.622 |
| LCT P / q05 (DISC, paired) | — (reference) | **99.59% / 82.48%** — middle PASS, strict PASS |
| MC P(profit) | 1.0000 | 1.0000 |
| MC DD obs → p95 vs own cap | 252.24 → 309.60 vs 378.36 PASS | 164.43 → **210.26 vs 246.65 PASS** |
| MC cluster obs → p95 vs own cap | −120.09 → 158.1 vs 180.14 PASS | −102.50 → **119.1 vs 153.75 PASS** |
| MC consec obs → p95 (cap obs+2) | 2 → 2 PASS | 1 → 2 PASS |
| MC middle (all arms) | PASS | **PASS — every arm better than incumbent** |
| PBO | 40.00% (EC record) | 0.00% (this-run family, validate_new8 basis — see note) |
| DSR | 1.0000 (EC record) | 1.0000 (this-run family, 21 trials — see note) |
| Decay | WEAKENED (leftover fall >20) | WEAKENED (same triggers) — not FAIL |
| Red lines | — | PASS (AUDIT net > 0, no discovery collapse) |

§2 gate check for C07: LCT-middle ✓ (99.59 ≥ 80, q05 82.48 ≥ 20)
· AUDIT leftover strictly > incumbent ✓ (+1.90) · win > 80% both
segments ✓ · entries/day ≥ 2 both segments ✓ · AUDIT net
positive ✓ · MC middle PASS all arms ✓ · PBO ≤ 50% ✓ · DSR
≥ 0.90 ✓ · decay not FAIL ✓. Two honest debits: AUDIT net is
+1044.89, i.e. 45.39 BELOW the incumbent's +1090.28 (the veto
removes 20 AUDIT picks incl. some wins — leftover still rises);
and the result is ledger-level with NO fall-through (above).

## Loss-cluster mechanism — headline (before vs after)

Diagnosis (measured on the incumbent ledger): FB_EURJPY_h11_0
fires 71 picks with 13 full-size losses (−1,017.40 gross); the
next-worst slot (FB_EURUSD_h10_0) has 9 losses / −493.87. The
13-loss slot alone manufactures the incumbent's DD window and
its worst cluster.

Mechanism (C07): pre-registered slot veto — FB_EURJPY_h11_0
never fires; at ledger level the freed checks stay empty (the
conservative bound; fall-through replay is the integration-time
step that killed Feb C08 and has NOT been run for C07).

Before → after (MC, mc9_verbatim, 10,000 paths, seed 20261101;
incumbent reproduced: DD p95 309.60, cluster p95 158.1):
- DD obs 252.24 → 164.43 · DD p95 309.60 → 210.26
- Worst cluster obs −120.09 → −102.50 · cluster p95 158.1 → 119.1
- Max consec losses obs 2 → 1 (p95 2 → 2) · P(profit) 1.0000 → 1.0000

## Office-fix grade table (§2 check-time rule, locked)

Reference = full incumbent (DISC leftover 78.43, AUDIT leftover
53.02, AUDIT net +1090.28, AUDIT win 92.90%). Candidate form =
incumbent MINUS the 16:30 picks PLUS a created baseline cycle at
the slot (single pre-registered equation: H1 mom4 direction,
M15 mom4 alignment + M15 vol_z > −1 confirmation, TP 20 / SL 100,
hold ≤ 48 H1 bars, SL-first, top-1 per check by |H1 mom4| —
312 slot picks each). IMPROVE = AUDIT leftover up AND DISC
leftover not down. DOWNGRADE = AUDIT leftover down > 0.5 pt OR
win < 80% OR AUDIT net down worse than −max(25, 10% of 1090.28)
= −109.03.

| Slot tested | DISC leftover | AUDIT leftover | AUDIT net | AUDIT win | Grade |
|---|---|---|---|---|---|
| Drop 16:30 only (no replacement) | 81.56 (+3.13) | 38.88 (−14.14) | +588.84 (−501.44) | 90.98% | **DOWNGRADE** |
| 07:30 MMT (entry 01:00 UTC) | 63.67 (−14.76) | 41.32 (−11.70) | +1055.14 (−35.14) | 89.69% | **DOWNGRADE** |
| 00:30 MMT (entry 18:00 UTC) | 67.66 (−10.77) | 29.05 (−23.97) | +718.94 (−371.34) | 86.46% (standalone slot AUDIT win 76.27% < 80) | **DOWNGRADE** |

Slot baselines standalone: 07:30 — DISC leftover 26.44 / AUDIT
44.41, epd 1.434/1.356; 00:30 — DISC 38.93 / AUDIT 13.02, epd
1.446/1.311. Both are real created cycles, honestly measured —
and both are far below incumbent quality, exactly as the
behaviour study's momentum-persistence number (0.4826) predicts
for December. **No slot is ACCEPTABLE or IMPROVE; nothing is
recommended.** The office fix for December remains open and
belongs to a mined Scenario-2 creation run, not to a baseline.

## All 20 cycles (by-trade DISC / AUDIT leftover; epd = DISC/AUDIT)

Direct — M15 multi-indicator vetoes (novel Plan C combos):
- C01 M15 mom4 > −0.20 & M15 RSI aligned > −10: dropped 166 · 74.25 / 50.66 · epd 3.657/3.289 — both segments down
- C02 M15 mom4 > 0 & M15 vol_z > −1.0: dropped 704 · 97.57 / 33.00 · epd 1.183/0.956 — epd gate FAIL, AUDIT down
- C03 M15 CLV aligned > 0.30 & M15 RSI > −15: dropped 299 · 77.72 / 67.83 · epd 3.029/2.778 — AUDIT leftover highest of the vetoes but DISC −0.71 below incumbent; not shortlisted for LCT/MC (named near-miss)
- C04 M15 range-ratio 0.6–1.8 & mom4 > −0.25: dropped 947 · 42.67 / — (AUDIT n 0) — range feature as computed (H1-median-scaled) misfires; REJECTED
- C08 M15 volume-spike veto (volm_r > 2.5): dropped 121 · 77.08 / 57.15 · epd 3.846/3.556 — AUDIT up, DISC −1.35 down; fails DISC-not-below
- C09 H1 mom24 + DOLLARIDX-labelled leg + M15 mom4: dropped 323 · 69.90 / 43.50 — both down

Direct — loss-cluster controls (explicit MC mechanism):
- C05 post-loss cooldown 1 pick: dropped 176, ALL in AUDIT (DISC untouched, AUDIT n 7, net −15.51) — sequential-state DEADLOCK in the AUDIT segment (once the last exited taken trade is a loss, skipped picks never refresh the state); REJECTED as implemented, and C11/C13 inherit the flaw (their AUDIT figures are artefacts, not measurements)
- C06 symbol block 48h after a loss on that symbol: dropped 28 · 80.13 / 50.78 · LCT P 41.20 FAIL · MC PASS (DD p95 306.67) — mild, not an improvement
- C07 veto FB_EURJPY_h11_0: dropped 71 · **87.52 / 54.92 — WINNER (above)**
- C10 day-cap 2 losses: dropped 0 — never triggers in December (losses too sparse per day); no-op

Combinations / partners:
- C11 = C01 × C05: 74.25 / artefact (C05 flaw) — DISCARDED
- C12 = C02 × C06: 97.54 / 24.80 · epd 1.166/0.889 — epd FAIL
- C13 = C07 × C05: DISC = C07 exactly (87.52) / artefact — DISCARDED (C07 stands alone)
- C14 = C03 × C10 = C03 (C10 no-op): 77.72 / 67.83 — same near-miss as C03
- C15 = C09 × C06: 72.76 / 42.81 — both down
- C16 partner PREGIME cand2 merge: accepted 0 of 181 (all check-busy — the design's hours coincide with incumbent checks) · = incumbent
- C17 partner PREGIMEC cand2 merge: accepted 1 · 78.45 / 53.02 · LCT P 42.25 FAIL — no-op
- C18 partner PREGIMESB cand1 merge: accepted 53 · 79.81 / 46.49 — AUDIT down 6.53
- C19 partner PLANB12C cand1 merge: accepted 8 · 78.59 / 53.30 · LCT 100.00/72.61 strict PASS · MC PASS (DD p95 309.54) · AUDIT net +1102.82 — passes every gate but strictly weaker than C07 on DISC leftover, LCT q05 and every MC arm; recorded as the runner-up small improvement
- C20 = C07 + PREGIMEC cand2 merge: accepted 14 · 87.65 / 50.41 · LCT 99.59/82.67 strict PASS · MC PASS (DD p95 213.31, cluster p95 116.85) — AUDIT leftover below incumbent; the partner dilutes C07's AUDIT gain. C07 alone stands.

## Honest trial count / PBO-DSR note

Slate pre-registered in `run_dec_planC_s1.py` before measuring
(20 cycles + incumbent = 21 trials). PBO/DSR for C07 above are
validate_new8 round basis on that family (PBO 0.00%, DSR
1.0000). Named gaps: (1) the R2-engine CSCV PBO basis — which
read 95%+ on other months' correlated-variant families this
round (Jul addendum) — was NOT run for Dec; (2) decay for every
December form incl. the incumbent reads WEAKENED on the
programme's DISC→AUDIT leftover-fall trigger (78.43 → 53.02 is
a >20 pt fall) — "not FAIL" is the §2 bar and it holds, but
December's unseen decay is structural, not a C07 artefact;
(3) C05's sequential rule deadlocked in AUDIT (disclosed
above) — its family slot is spent, not hidden.

Files: run data `results/dec_planC_s1_run.json` +
`results/dec_planC_s1_bytrade.json`; per-cycle ledgers
`results/dec_planC_s1_C01..C20_ledger.csv`; office ledgers
`results/dec_planC_s1_DROP1630_ledger.csv`,
`results/dec_planC_s1_SLOT0730_capped_ledger.csv`,
`results/dec_planC_s1_SLOT0030_capped_ledger.csv`; scripts
`run_dec_planC_s1.py`, `run_dec_planC_s1_post.py`.

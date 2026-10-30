VERDICT: Jul planA s1 attempt3 — SMALL-IMPROVED (DD-window-targeted attempt: the window IS broken — DD obs 125.67 → 102.50 and worst cluster −125.67 → −102.50 in all 8 variants — but 0 of 8 reaches DD p95 ≤ its own cap 153.75, so the mc_middle_pass flag stays FALSE on the DD arm alone for every variant; closest is W8, DD p95 157.52 vs cap 153.75, miss 3.77, which also fails DISC epd 1.943 < 2; closest variant clean on every other gate is W7, miss 5.00 — NOT promoted)

# Jul Plan A S1 — ATTEMPT 3: prune the legs inside the actual DD window (2026-10-30, Wave 3c)

Target (single, pre-registered): close attempt 2's named gap. In
attempt 2 the DD obs stayed 125.67 in every variant because the
legs composing the observed DD window / worst cluster were in no
prune set (the prune sets came from the DISC-wide cluster-
contribution ranking). This attempt identifies the window first,
then builds ≤12 variants on the T7 form that prune ITS legs.
Slate of 8 written into `run_jul_attempt3.py` BEFORE measuring.
Mechanism honesty: the Jul machinery is ledger-level and supports
FULL PRUNE of a strategy leg only — there is no half-weight in
the unit-trade net convention (net = gross − 2.5) and no Jul
app-replay veto — so every variant below is a full prune; no
veto/half-weight variant is claimed. Grading = full BRIEF.md §2
battery vs cycle78 (Jul convention: DISC 174 d / AUDIT 46 d;
leftover = net ÷ sum of positive NET). MC = mc9_verbatim, 10,000
paths; mc_middle_pass is the OWN-RELATIVE flag (settled ruling,
applied without re-argument). Research level only.

## (a) Identification — the DD window and the worst cluster, by date

Worst cluster (mc9 sequence form; the incumbent's full-period
and DISC-only sequences agree exactly) = **−125.67, exactly 2
trades, both DISC (2017)**:

| check | symbol | strategy (leg) | gross | net |
|---|---|---|---|---|
| 2017-07-19 17:30 | EURJPY | FB_EURJPY_h17_1_G | −78.52 | −81.03 |
| 2017-07-19 18:30 | EURCHF | FB_EURCHF_h18_2_G | −42.14 | −44.64 |

DD windows:
- Incumbent full-period DD obs 143.81 is a DIFFERENT window:
  20 trades, 2023-07-25 → 2024-07-08 — losses FB_EURUSD_h15_0_G
  −102.50 (2023-07-25 15:30), FB_AUDJPY_h18_0_G −92.50
  (2023-07-28 18:30), FB_USDJPY_h15_2_G −102.50 (2024-07-08
  15:30), offset by 17 small wins (+7.50 … +22.19). In T7 the
  EURUSD leg is already pruned, so this window collapses.
- Incumbent DISC-only-sequence DD obs 130.43: 5 trades
  (2021-07-30 USDJPY −83.60, EURNZD +30.67, AUDJPY +7.50;
  2022-07-01 EURUSD +7.50, AUDUSD −92.50). Reported for
  completeness; the MC gate runs on the full-period sequence.
- **T7's own DD window IS the 2017 worst cluster, trade for
  trade** (rebuilt T7 asserted to its published DISC 84.96 /
  AUDIT 76.98 first; its DD window rows = its cluster rows,
  DD obs 125.67). So the legs that set T7's cap are:
  LEG_A = FB_EURJPY_h17_1_G, LEG_B = FB_EURCHF_h18_2_G.
  DISC-only choice: both window trades are 2017 (DISC), and the
  legs' DISC-wide cluster contributions (−160.82, 5th-worst;
  −85.64, 8th-worst) are DISC quantities — they ranked BELOW
  attempt 2's prune set (EURUSD −213.70, USDJPY −176.10,
  NZDUSD −175.00, AUDJPY −169.60) on DISC-wide totals, which is
  exactly why attempt 2 never touched them. AUDIT grading-only.

## (b)+(c) The 8 pre-registered variants on the T7 form, full §2 battery

T7 form = C18 prune {FB_EURUSD_h15_0_G, FB_USDJPY_h15_2_G} +
B04 fill recomputed (157 accepted). W1–W3 prune the T7 ledger
directly (no refill); W4–W6 prune the base then RECOMPUTE the
B04 fill (W4 188, W5 179, W6 210 accepted); W7–W8 prune the
base with NO fill (isolates the fill). Every variant: P(profit)
1.0000, cluster p95 102.50 ≤ cap 153.75 PASS, consec obs 1 /
p95 ≤ 2 PASS, PBO 0.00% canonical, decay not FAIL — the DD arm
is the sole MC blocker throughout, as in attempts 1–2.

| Var | Mechanism | DISC lo | AUDIT lo | AUDIT net | win D/A % | epd D/A | LCT Jul P/q05 | DD obs → p95 vs own cap | Miss |
|---|---|---|---|---|---|---|---|---|---|
| T7 (ref) | attempt-2 best | 84.96 | 76.98 | +1138.57 | 96.69/95.45 | 2.954/2.870 | 99.76/74.03 | 125.67 → 190.00 vs 188.51 | 1.49 |
| W1 | T7 prune LEG_A | 86.83 | 76.03 | +1080.20 | 96.93/95.20 | 2.805/2.717 | 99.88/76.84 | 102.50 → 176.11 vs 153.75 | 22.36 |
| W2 | T7 prune LEG_B | 85.90 | 76.74 | +1123.57 | 97.17/95.38 | 2.839/2.826 | 99.86/75.47 | 102.50 → 176.66 vs 153.75 | 22.91 |
| W3 | T7 prune LEG_A+B | 87.83 | 75.78 | +1065.20 | 97.44/95.12 | 2.690/2.674 | 99.94/78.17 | 102.50 → 176.45 vs 153.75 | 22.70 |
| W4 | base prune LEG_A + refill | 87.57 | 69.43 | +1021.54 | 97.08/93.89 | 2.948/2.848 | 99.97/78.33 | 102.50 → 176.11 vs 153.75 | 22.36 |
| W5 | base prune LEG_B + refill | 86.41 | **77.19** | **+1152.17** | 97.28/95.45 | 2.954/2.870 | 99.95/76.65 | 102.50 → 176.25 vs 153.75 | 22.50 |
| W6 | base prune LEG_A+B + refill | **88.93** | 69.71 | +1035.14 | 97.66/93.89 | 2.948/2.848 | 100.00/80.41 | 102.50 → 175.20 vs 153.75 | 21.45 |
| W7 | base prune LEG_A, no fill | 84.57 | **82.75** | +957.86 | 96.37/96.94 | 2.057/2.130 | 99.98/72.96 | 102.50 → 158.75 vs 153.75 | **5.00** |
| W8 | base prune LEG_A+B, no fill | 86.03 | 82.52 | +942.86 | 97.04/96.88 | **1.943**/2.087 | 100.00/74.90 | 102.50 → 157.52 vs 153.75 | **3.77** |

PBO/DSR stated family (canonical): 10 daily DISC series
{incumbent, T7, W1..W8}; every variant PBO 0.00%, DSR 1.0000
(W7/W8 0.9999). Disclosed second reading (R2-engine CSCV basis,
same split as all prior Jul files): PBO 100.00% for the family,
DSR identical to canonical. Canonical LCT (validate_new8) also
passes middle for every variant (P 90.97–96.88, q05 71.25–75.65).
Decay: AUDIT/DISC leftover ratios 0.78–0.98, yearly leftover
positive every year 2016–2025 for every variant — none FAIL.
§2 gate check per variant: LCT-middle ✓ all · AUDIT leftover
strictly > incumbent 64.97 ✓ all · win > 80% ✓ all · AUDIT net
> 0 ✓ all · PBO ≤ 50% ✓ canonical · DSR ≥ 0.90 ✓ · decay ✓ ·
red lines ✓ · epd ≥ 2 ✓ except W8 DISC 1.943 ✗ · **MC verbatim
flag ✗ ALL (DD arm only)**.

## Reading of the attempt — the window moved; the cap moved with it

- The identification was right and the prune works on the
  OBSERVED path: DD obs 125.67 → 102.50 and worst cluster
  −125.67 → −102.50 in all 8 variants; max consec losses 2 → 1.
  The new DD window is a single trade — a −102.50 full-stop loss
  (filled forms: the B04 GBPNZD fill leg, 2016-07-25 15:30;
  no-fill forms: mom_USDCAD_h15, 2020-07-20 15:30).
- But 102.50 is the ledger's ATOMIC loss size (−100 gross stop
  − 2.5 = −102.50 net), carried by many legs. The block
  bootstrap (block 10) regularly stacks two such stops into one
  resampled excursion, so p95 falls only to 175–177 (filled) or
  157–159 (no-fill) while the own-relative cap falls in
  proportion to obs (1.5 × 102.50 = 153.75). The p95/obs ratio
  does NOT improve (T7 1.512; W6 1.709; W7 1.549; W8 1.537).
  Pruning a window can never beat this cap while ≥2 full-stop
  losses remain anywhere in the sequence — the binding quantity
  is now the DENSITY of −102.50 stops, not any single window.
  The no-fill forms come closest precisely because they carry
  fewer such stops (the B04 fill re-adds them).
- Closest variant overall: **W8 — DD p95 157.52 vs own cap
  153.75, miss 3.77** — but W8 also fails DISC epd (1.943 < 2).
  Closest variant passing every other §2 gate: **W7 — DD p95
  158.75 vs cap 153.75, miss 5.00**, with the highest AUDIT
  leftover of any Jul form measured this round (82.75%) and
  DISC leftover 84.57% ≈ T7's 84.96.
- Named remaining gap (not chased — slate exhausted, time
  discipline): a mechanism that cuts the −102.50 stop density
  itself (e.g. pruning the remaining carriers of repeated
  full-stop losses, or a stop-size change — the latter is an
  engine/exit change outside this round's prune forms).

## Consequence for Jul

No Jul form passes the MC-middle gate under the own-relative
ruling in this wave: **0 of 8 attempt-3 variants is IMPROVED;
incumbent cycle78 stands.** Ranked research candidates now:
T7 (miss 1.49, strongest filled edge), W7 (miss 5.00, strongest
AUDIT leftover 82.75%, no-fill), W8 (miss 3.77, epd-blocked),
then the combined form (miss 8.99) and C18. The DD-window
question attempt 2 left open is ANSWERED: the window was the
2017-07-19 EURJPY/EURCHF pair, pruning it moves obs exactly as
predicted, and the gate still fails — on stop density, not on
the window.

## Method / files

- Runner: `run_jul_attempt3.py` (identification + slate
  pre-registered in its header; T7 rebuilt via the attempt-2
  code path and asserted 84.96/76.98 before use; clean-net LCT
  cross-check in `results/jul_attempt3_clean_lct.json`
  reproduces T7's published 99.76/74.03 exactly).
- Machine record: `results/jul_attempt3_run.json`; ledgers
  `results/jul_attempt3_W1..W8_ledger.csv`.
- Sizing: NOT a gate in this round (brief §0) — not measured.

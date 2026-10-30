VERDICT: Jul planA s1 attempt2 — SMALL-IMPROVED (targeted DD-cap attempt: 0 of 9 variants reaches DD p95 ≤ its own cap — the mc_middle_pass flag stays FALSE for every variant on the DD arm alone; closest is T7, DD p95 190.00 vs own cap 188.51, miss 1.49, with the strongest edge statistics of the round — NOT promoted)

# Jul Plan A S1 — ATTEMPT 2: push a C18-form ledger under its own MC DD cap (2026-10-30, Wave 3a)

Target (single, pre-registered): a C18-form ledger whose verbatim
MC flag is TRUE — i.e. DD p95 ≤ 1.5 × its own DD obs, the settled
own-relative ruling — via B04-style silent-check fill and/or
prune variants. Slate of 9 written into `run_jul_combined_s1.py`
BEFORE measuring; every leg choice is DISC-only (worst DISC
loss-cluster contribution, Jul legprune form). C18's worst DISC
cluster legs: FB_EURUSD_h15_0_G (−213.70), FB_USDJPY_h15_2_G
(−176.10), FB_NZDUSD_h18_1_G (−175.00), FB_AUDJPY_h18_0_G
(−169.60) — the combined ledger's worst legs are identical (the
B04 fill adds no new cluster leg). All other MC arms pass for
every variant below (P(profit) 1.0000, cluster p95 ≤ cap,
consec p95 2); the DD arm is the sole blocker throughout.
Leftover convention, segments and machinery as in
`jul_combined_s1.md`. Research level only.

## All 9 variants (DISC leftover · AUDIT leftover · LCT P/q05 vs incumbent · DD obs → p95 vs own cap · PBO/DSR attempt family)

Attempt PBO/DSR family (canonical): 11 daily DISC series
{incumbent, C18, T1..T9}; every variant PBO 0.00%, DSR ≥ 0.9999.

| Variant | Mechanism | DISC lo | AUDIT lo | AUDIT net | LCT | DD p95 vs cap | Miss |
|---|---|---|---|---|---|---|---|
| T1 | C18 + full B04 fill (= combined) | 80.59 | 68.84 | +996.85 | 100.00/67.03 | 197.50 vs 188.51 | 8.99 |
| T2 | C18 prune FB_EURUSD_h15_0_G, no fill | 79.13 | 75.71 | +942.10 | 99.28/65.56 | 191.77 vs 188.51 | 3.26 |
| T3 | T2 base + B04 fill recomputed (+fill vs pruned base) | 81.79 | 69.71 | +1019.31 | 98.93/69.14 | 201.04 vs 188.51 | 12.53 |
| T4 | combined prune FB_EURUSD_h15_0_G | 83.10 | 77.29 | +1055.55 | 99.97/70.07 | 190.88 vs 188.51 | 2.37 |
| T5 | combined + SYMBLK2x1 | 80.55 | 68.67 | +989.35 | 100.00/66.93 | 197.99 vs 188.51 | 8.48 |
| T6 | combined + CLUSPAUSE2 | 80.55 | 68.39 | +976.37 | 100.00/66.86 | 202.40 vs 188.51 | 13.89 |
| **T7** | **C18 prune 2 worst legs (EURUSD_h15_0_G + USDJPY_h15_2_G) + B04 fill recomputed** | **84.96** | **76.98** | **+1138.57** | 99.76/74.03 | **190.00 vs 188.51** | **1.49** |
| T8 | T3 + SYMBLK2x1 | 81.75 | 69.71 | +1019.31 | 98.92/69.00 | 201.28 vs 188.51 | 12.77 |
| T9 | combined + CAP2in5fix | 80.46 | 68.16 | +966.23 | 100.00/66.86 | 208.75 vs 197.43 (own DD obs 131.62) | 11.32 |

Full per-variant numbers (n, win, epd, all MC arms, decay
ratios 0.85–0.96 — none FAIL) are in
`results/jul_combined_s1_run.json` (`attempts`); ledgers in
`results/jul_combined_s1_T1..T9_ledger.csv`.

## Reading of the attempt

- Pruning moves DD p95 the right way (T2/T4/T7: 190–192) and
  RAISES AUDIT leftover sharply (75.71–77.29 for the no/low-fill
  prunes) — but no prune moves DD OBS: it stays 125.67 in every
  variant except T9. The observed DD window is a single
  −125.67 cluster that none of the pruned legs participates in,
  so the own-relative cap (1.5 × 125.67 = 188.51) never moves
  while p95 only shuffles between 190 and 202.
- Refilling silent checks (T3/T8) gives the DD p95 back —
  the fill's wins help leftover but its interleaved losses
  re-widen the resampled DD distribution.
- Sequential controls (T5/T6/T9) again do not help July —
  same finding as Plan A and Plan B.
- T7 is the strongest Jul ledger measured this round on edge
  (DISC leftover 84.96%, AUDIT 76.98%, AUDIT net +1138.57,
  LCT 99.76/74.03, PBO 0.00% / DSR 1.0000 on the attempt
  family, decay ratio 0.91) and misses promotion on exactly
  one number: DD p95 190.00 vs its own cap 188.51 (miss 1.49).
  Under the settled ruling it is NOT promoted; it is recorded
  as SMALL-IMPROVED and is the first candidate to re-test if
  a future mechanism can move the DD OBS window itself (the
  −125.67 cluster's legs were not in any variant's prune set
  because the cluster-contribution ranking is DISC-wide, while
  the DD window is one specific 2023–24 sequence — a named
  gap for a future round, not chased here per time discipline).

## Consequence for Jul

No Jul form passes the MC-middle gate under the own-relative
ruling in this wave: incumbent cycle78 stands; C18
(SMALL-IMPROVED), the combined form (SMALL-IMPROVED,
`jul_combined_s1.md`) and T7 (SMALL-IMPROVED, this file) are
the ranked research candidates, in that gate order all blocked
by the same DD arm.

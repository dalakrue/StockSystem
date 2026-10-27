# BRIEF22 Workstream B — APRIL second best: VALIDATION RECORD

**VERDICT: NO SECOND BEST for April.** Both finalists fail the locked
gates on core clauses (not just materiality), so neither reaches SMALL.
April C20a stands alone; there is no designated alternative second best.

Control = April C20a (BRIEF21 winner): DISC n710 net +6033.02 win 97.75%
leftover 84.47 · AUDIT n187 net +1971.36 win 95.72% leftover 79.06; checks
16:30/17:30/18:30 UTC; N=104; max concurrency 7; audit float DD 35.28%,
disc float DD 14.04%. Frame A3 (DISC 2016–2023 = FIT 2016–2020 +
HOLDOUT 2021–2023; AUDIT 2024+2025); cost @2.5; exact raw-price replay.
Gates = locked BRIEF21 set re-based to C20a (battery machinery verbatim:
LCT seed 20261101, 6 blocks draw 3, 10,000 paths; EC22 count basis
excludes waived 15_epd and report-only 20_dsr; paired chain 2,500 paths).

## Gap map (measured first, from the C20a ledger)

639 grid checks (DISC 507, AUDIT 132; 213 per check time).

- **Class (a) — C20a's checks, C20a silent: 5 DISC / 0 AUDIT** (all
  18:30: 2016-04-22, 2017-04-10, 2018-04-06, 2018-04-23, 2022-04-15).
  16 pool rows exist there (standalone leftover −21.50), but under
  full-interval same-symbol occupancy vs C20a, **0 legs are admissible**
  — those checks are empty precisely because every candidate symbol is
  already occupied by a live C20a trade. Class (a) is structurally void.
- **Class (b1) — pool symbols C20a never trades: EURGBP, GBPUSD.** Their
  only pool strategies are the banned FB rows. Supply 338 DISC / 88
  AUDIT rows; standalone DISC leftover EURGBP −59.51 (net −754.37),
  GBPUSD −57.41 (net −732.31). Toxic ungated.
- **Class (b2) — universe symbols with no pool rows: AUDCHF, AUDNZD,
  CHFJPY, USDJPY** — fresh-signal space only.
- **Class (c) — one new check time** (15:30 or 19:30 UTC tested).

C20a symbol concentration (897 rows): EURUSD 149, EURJPY 143, EURAUD
128, USDCAD 96, EURNZD 95, NZDUSD 74, GBPJPY 73, NZDCAD 43, EURCAD 30,
AUDUSD 22, AUDJPY 14, USDCHF 13, EURCHF 11, AUDCAD 6 (690 base + 207
re-entry).

## Screens S01–S18 (discovery): ZERO screen-positive families

- (a) S01/S02: 0 legs admitted (occupancy-blocked), dLO +0.00 trivially.
- (b1) S03 raw −34.22 · S04 H1-bias gate −28.26 · S05 FIT pat gate
  −32.69 · S06 pat+ADX gates −19.02. No price gate rescues the FB rows.
- (b2) S07 s≥0.25 top-1 −19.28 · S08 s≥0.50 −18.95 · S09 all-qualifying
  cap 4 −24.54 (legs leftover only +9.46) · S10 + M30 agreement −22.59.
- (c) S13/S14 15:30 fresh: legs DISC leftover **+20.46**, net +302.36 —
  the only positive-quality legs found — but combined dLO **−11.00**
  (legs' quality is far below C20a's 84.47, so they dilute). S11/S12
  19:30 fresh: legs leftover −41.40, dLO −11.46.
- Stacks: S15 gap-universe −24.27 · S16 reduces to S06 (−19.02) ·
  S17 reduces to S13 (−11.00) · S18: nothing screen-positive to stack.

Finalists (top-2 distinct combined candidates by discovery leftover):
fin1 = S13 (15:30), fin2 = S11 (19:30). Both fill class (c) ONLY.

## Finalist designs (both fully app-expressible)

Fresh momentum signal, stateless per check: direction = last completed
H1 bar bias; strength s = bias × (M15 close − EMA20) / ATR14 at the bar
before entry; enter if s ≥ 0.25, top-1 symbol per check, live cap 3;
TP = 1.152 × ATR, SL = 8.971 × ATR (incumbent discovery medians).
Features use only H1 closes and a ≤200-bar M15 window; no ledger state,
no re-entry, no tick volume. They failed on quality, not expressibility.

## Validation — fin1 (C20a + S13 legs, 15:30 UTC new check)

Legs: 189 total — DISC 152, AUDIT 37; 100% class (c).
Legs standalone: DISC n152 net +302.36 win 91.45% leftover +20.46 ·
AUDIT n37 net **−525.39** win 83.78% leftover **−118.19** (the discovery-
positive legs LOSE money in audit).
Combined: DISC n862 net +6335.38 win 96.64% leftover **73.47** (−11.00) ·
AUDIT n224 net +1445.97 win 93.75% leftover **49.13** (−29.93).
LCT P **0.41%** / q05 60.09 (middle FAIL) · EC22 **13 vs 15** (fails
8_weeks, 13_lct, 14_leftover; C20a fails only 14 by construction) ·
MC median ratio **0.2104×** (FAIL), P(call) 0.0000 vs 0.0000 (pass) ·
PBO 2.50% (pass), DSR 0.3614 report-only · conflict-free YES ·
concurrency **8** (vs 7) · audit float DD **47.89%** (vs 35.28%),
disc float DD 14.58% (vs 14.04%) · audit worst-5 window −197.49
(vs −65.40). Gates failed: red_disc (leftover), LCT, EC22 count,
leftover>, MC median, materiality both. **NOT VALIDATED.**

## Validation — fin2 (C20a + S11 legs, 19:30 UTC new check)

Legs: 103 total — DISC 82, AUDIT 21; 100% class (c).
Legs standalone: DISC n82 net −292.03 win 84.15% leftover −41.40 ·
AUDIT n21 net −135.27 win 80.95% leftover −53.06.
Combined: DISC n792 net +5741.00 win 96.34% leftover **73.01** (−11.46) ·
AUDIT n208 net +1836.09 win 94.23% leftover **66.72** (−12.34).
LCT P **0.35%** / q05 69.90 (FAIL) · EC22 **14 vs 15** (fails 13_lct,
14_leftover) · MC median ratio **0.1032×** (FAIL), P(call) 0 vs 0 ·
PBO 2.50%, DSR 0.8980 · conflict-free YES · concurrency 7 (unchanged) ·
audit float DD **43.07%** (vs 35.28%), disc float DD 12.70% ·
disc worst-5 −187.04 (vs −72.50), max_consec 2 (vs 1).
Same six gate failures. **NOT VALIDATED.**

## Why April has no second best

C20a fires at 502/507 discovery checks and its own occupancy blocks the
remaining 5. The only admissible gap space — undetected symbols and one
new check time — trades at leftover −118…+20 against C20a's 84.47: every
added leg dilutes discovery leftover by 11–34 points, the paired LCT is
~0% (the combined system is worse in essentially every resample), and
the compounding chain median collapses to 0.10–0.21× because the added
legs poison the resampled pool. The one mildly positive discovery family
(15:30 fresh, leftover +20.46) reverses in audit (−525.39 net). April's
gaps are structural — saturation plus occupancy — not missed
opportunity. Same conclusion shape as November's Workstream B.

Files: screens `brief22/apr2b/results/S01–S20.txt`, gap map
`results/GAPMAP.txt`, ledgers `brief22/apr2b/logs/`, validation JSON
`results/validation22_apr2b.json`, battery ledgers `val_logs/`.
No integration, no GitHub push (verdict only, per brief).

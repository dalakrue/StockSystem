VERDICT: May planB s1 — NO IMPROVEMENT

# May Plan B Scenario 1 — 20-Cycle Round R2 (2026-10-30)

Two deliverables: (1) create a REAL second-best for May best
cycle88n (incumbent second cycle88 is CONTAINED, delta +0);
(2) office fix for the 16:30 MMT IN-OFFICE first check.
**Neither deliverable passes its locked acceptance.** The
second-best fails on combine-safety (all 20 cycles); the office
fix fails on the locked §2 grade (07:30 = DOWNGRADE, drop-alone
= DOWNGRADE on the net arm). Office grade is stated in full in
its own section below, per the result contract. Research level
only — no app push, no GitHub push, live crons untouched.

Incumbent read FRESH from the app registry this run
(`core/signal_mode.py`: May best = cycle88n, second = cycle88
contained; checks 10/16/18 UTC entries = 16:30 IN-OFFICE /
22:30 / 00:30 MMT). Ledger = `work_new8/combined/
May_ROUND4_combined.csv` (464 rows), reproduced EXACTLY on the
programme convention (validate_new8.seg_stats, by-trade
leftover, DISC 178 d / AUDIT 45 d): DISC n 361, net +4711.99,
win 99.45%, leftover 95.30%, epd 2.028 (uniform-grid DISC epd
2.062 on the 223-day convention); AUDIT n 103, net +1021.86,
win 96.12%, leftover 79.54%, epd 2.289. MC reproduced
bit-for-bit vs the step-test record (below). May's EC pass
carries the user's LCT waiver (P 69.68% vs 80%) — unchanged by
this run.

## (1) SECOND-BEST — 20 cycles, none accepted

Method (pre-registered in `run_may_planB_s1.py` before measuring):
union walks over the pool of ALL 36 prior May candidate ledgers
(work_new8: NEW8 cand1 + PLANB/B2/B3/B4/B6/B7/B8/B9/B9C/B12/
B12C cand1+cand2+partner + ROUND3/ROUND4). PLANB7 ledgers are
the volume-in-every-combination + correlated-symbol +
DOLLARIDX-feature round (PLANB7_SPEC); PLANB6 = nested
multi-combinations; B12/B12C = threshold multi-combinations
(the brief §6 fallback space). Each cycle = priority cascade:
at each check inside the best's own times (10/16/18 UTC; NO new
slot used — at most one was allowed) take the first source's
row whose symbol interval conflicts with no taken row; max 1
pick/check. Variants: 9 priority orders × source-leftover
filters (≥40 / ≥60) × post-loss cooldowns (24h / 48h).
Selection on DISC only; AUDIT reported, never selected on.
DOLLARIDX: a FEATURE leg in the B7/B6 rounds (Dukascopy-
labelled, H1 only, from 2017-12-01, no volume conditions on
it); 0 pool rows trade DOLLARIDX as a symbol. Twelve DXY is
BLOCKED-DATA (Wave 0, HTTP 429) — no DXY feature is used or
claimed anywhere in this run.

### Standalone results (programme convention)

Every cycle clears the standalone rate floor — the epd problem
is SOLVED (incumbent second cycle88: 0.000 added epd; these
fire 2.955–2.966 DISC epd standalone):

| cycle | DISC n / net / win / leftover / epd | AUDIT n / net / win / leftover / epd |
|---|---|---|
| B01 leftover-cascade | 528 / +13021.24 / 100.0 / 100.00 / 2.966 | 134 / **−940.09** / 75.37 / −40.63 / 2.978 |
| B02 net-cascade | 528 / +12532.49 / 100.0 / 100.00 / 2.966 | 133 / **−1099.85** / 74.44 / −48.25 / 2.956 |
| **B03 chronological cascade** | 526 / +8902.31 / 100.0 / 100.00 / 2.955 | 132 / **+58.03** / 84.09 / +3.27 / 2.933 |
| B04 reverse-leftover | 527 / +6250.72 / 96.2 / 75.34 / 2.961 | 133 / −186.76 / 84.21 / −11.62 / 2.956 |
| B05 B7-first (volume+corr+dollar) | 528 / +8136.24 / 100.0 / 100.00 / 2.966 | 133 / −508.14 / 82.71 / −34.08 / 2.956 |
| B06 B6-first (nested multi-combo) | 528 / +12313.92 / 100.0 / 100.00 / 2.966 | 134 / −754.00 / 76.87 / −32.58 / 2.978 |
| B07 volume+corr-first | 528 / +10785.56 / 100.0 / 100.00 / 2.966 | 133 / −642.38 / 78.20 / −30.66 / 2.956 |
| B08 cand-only leftover | 526 / +13011.30 / 100.0 / 100.00 / 2.955 | 134 / −784.15 / 76.12 / −33.21 / 2.978 |
| B09 cand-only net | 526 / +12506.43 / 100.0 / 100.00 / 2.955 | 133 / −1099.85 / 74.44 / −48.25 / 2.956 |
| B10–B12 filtered (≥40/≥60) | = B01/B02 walks | = B01/B02 (AUDIT-losing) |
| B13–B18 cooldown 24h/48h | DISC = base walks (no DISC losses to trigger) | AUDIT n collapses to 36–74, net −424…−1106 (cooldown misfires on AUDIT loss clustering) |
| B19 B7-first ≥40 | = B05 walk | −508.14 |
| B20 vol+corr ≥60 | = B07 walk | −642.38 |

19 of 20 cycles are AUDIT-LOSING standalone (net −186.76 …
−1099.85) — the pool's DISC-perfect designs (DISC win 100%,
leftover 100% by-trade) do not repeat on unseen data; this is
the same DISC→AUDIT regime flip the Jan Plan A run measured.
Only **B03** (chronological cascade — earliest rounds first)
is AUDIT-positive standalone, and only barely: net +58.03,
leftover +3.27%, stress net @4.5 **−205.97** (negative).

### Combined results (incumbent-priority merge, delta measured)

Merge semantics = validate_new8/Feb-run form: a second-best
pick is accepted only at a check the best does not take and
with no symbol-interval overlap. Delta > 0 IS achieved by
every cycle (accepted +170…+194 picks; combined DISC epd
2.899–2.966 vs best-alone 2.028). Combine-safety is where
every cycle dies — locked tolerance: combined AUDIT leftover
≥ 79.54 − 2.00 = **77.54%**:

| form | DISC leftover | AUDIT leftover (Δ) | AUDIT net (Δ) | AUDIT win |
|---|---|---|---|---|
| Best-alone 88n | 95.30% | 79.54% | +1021.86 | 96.12% |
| B03 combined (best) | 96.86% | **61.97% (−17.57)** | +1009.48 (−12.38) | 93.89% |
| B15 combined | 96.71% | 59.39% (−20.15) | +884.15 | 94.35% |
| B05/B19 combined | 96.71% | 52.95% (−26.59) | +834.08 | 93.08% |
| B04 combined | 86.75% | 51.95% (−27.59) | +829.44 | 93.23% |
| B01/B10/B11 combined | 97.26% | 24.79% (−54.75) | +417.59 | 89.23% |
| all other combined | 96.71–97.29% | 24.79–44.58% | +417…+730 | 89–92% |

Best combined (B03) misses the −2.00 tolerance by **15.57
pts**. No cycle is within 15 pts of it.

### Full battery on B03 (the only DISC-qualifying cycle)

- Standalone: DISC leftover 100.00% · AUDIT leftover +3.27% ·
  net +8902.31 / +58.03 · win 100.00% / 84.09% · epd
  2.955 / 2.933 (BOTH > 2.5 ✓) · stress AUDIT net @4.5 −205.97 ✗
- Combined: DISC leftover 95.30 → 96.86% · AUDIT leftover
  79.54 → 61.97% · AUDIT net +1021.86 → +1009.48 · win
  96.12 → 93.89% · entries/day DISC 2.028 → 2.949 · **delta
  +192 picks measured** (drops: check_busy 457, symbol_overlap 9)
- LCT (combined vs incumbent, paired, DISC): P **69.68%** /
  q05 93.59% — middle FAIL (P < 80; identical P to the E07
  waiver record — May's LCT ceiling against this incumbent
  appears structural, not candidate-specific)
- MC combined (mc9_verbatim, 10,000 paths): P(profit) 1.0000 ·
  DD obs 226.05 → p95 239.77 vs cap 339.08 PASS · cluster obs
  −136.78 → p95 136.78 vs cap 205.17 PASS · consec obs 2 /
  p95 2 PASS — MC middle PASS, not worse than best-alone on
  cluster/consec (DD p95 153.70 → 239.77, still PASS)
- MC standalone B03: P(profit) 1.0000 · DD p95 296.73 vs cap
  346.94 PASS · cluster p95 144.90 vs cap 217.35 PASS ·
  consec 2/2 PASS
- PBO 0.00% · DSR 1.0000 (this-run family, N = 21 trials —
  incumbent + 20 cycles; honest for this run only)
- Decay: not FAIL (combined EV/trade DISC 13.69, AUDIT 7.71,
  both positive)
- Loss-cluster mechanism used: post-loss cooldown variants
  B13–B18 (they HURT on AUDIT — see table) + symbol-overlap
  exclusion in every walk; B03 itself carries no cooldown.
  Cluster arm before → after (combined): −136.78/136.78 →
  −136.78/136.78 (unchanged); standalone B03 cluster obs
  −144.90 is slightly worse than the incumbent's −136.78.

**§2 second-best acceptance for B03: standalone epd > 2.5 ✓ ·
fires only inside best's times ✓ (no new slot used) · combined
delta > 0 ✓ (+192) · combined MC not worse ✓ (all arms PASS) ·
combined AUDIT leftover within −2.00 ✗ (−17.57) · standalone
AUDIT quality: net +58.03 but leftover +3.27% and stress
−205.97 — below medium quality on unseen.** One locked item
fails decisively and the standalone unseen record is marginal;
B03 is NOT created as May's second-best. cycle88 stays as the
(contained, +0) registry second; the May second-best GAP
from the 2026-10-29 audit remains open. Closing it needs
equations mined for AUDIT-robustness at these hours, not a
recombination of DISC-perfect prior designs.

## (2) OFFICE FIX — 16:30 MMT first check: NO acceptable move

The 16:30 slot (ledger hour 10 UTC) carries 123 of 464 picks:
DISC n 96 / net +890.71 / leftover 79.60% · AUDIT n 27 /
net +177.96 / leftover 61.10% — it is a real, positive slot,
not dead weight. Grades under the LOCKED §2 rule (IMPROVE =
AUDIT leftover up AND DISC leftover not down; DOWNGRADE =
AUDIT leftover down > 0.5 pt OR win < 80% OR AUDIT net down
worse than −max(25, 10% of current AUDIT net = 102.19)):

| alternative | DISC leftover | AUDIT leftover | AUDIT net | AUDIT win | GRADE |
|---|---|---|---|---|---|
| Current (16:30/22:30/00:30) | 95.30% | 79.54% | +1021.86 | 96.12% | — |
| DROP 16:30 (22:30/00:30 only, exact from ledger) | 100.00% (up) | 84.94% (up +5.40) | +843.90 (**−177.96 < −102.19**) | 96.05% | **DOWNGRADE** (net arm) |
| ADD 07:30 (keep 16:30; full-cycle re-walk, ADDED_CHECK_CALC_20261029, control 462/464 keys) | −41.36 pts Δ | −32.79 pts Δ (→ 46.64%) | −129.92 Δ | 90.48% | **DOWNGRADE** (leftover arm) |
| REPLACE 16:30 → 07:30 (bounded estimate: drop-form + recorded 07:30 add-effect; occupancy interaction unmeasured) | down (add-effect dominates) | down (both components degrade it) | ≈ +713.98 (**Δ ≈ −307.88**) | ≥ 90% est. | **DOWNGRADE** (net + leftover arms) |
| Any other off-hours :30 slot (01:30/02:30/03:30/04:30/05:30/06:30/08:30/18:30/20:30/21:30/23:30 MMT) | — | — | — | — | NOT MEASURED — no full-cycle re-walk exists for May at these hours; no grade invented |

07:30 graded explicitly, as ordered: as an ADD it is a
recorded full-cycle DOWNGRADE; as the REPLACEMENT for 16:30
it is a DOWNGRADE on the bounded estimate (the drop alone
already breaches the net arm at −177.96, and the 07:30 picks
themselves subtract a further −129.92 of AUDIT net in the
add measurement). Only IMPROVE/ACCEPTABLE may be recommended
— **no office move is recommended for May in Scenario 1.**
The 16:30 check stays. A compliant fix requires a cycle
CREATED natively for a replacement hour (Scenario-2-style
creation, not incumbent replay) — outside this S1 task.

Drop-form MC (for the record): P(profit) 1.0000, DD obs/p95
61.27/61.27, consec 1/1, cluster −61.27/61.27 — MC middle
PASS; the drop fails on the §2 net arm, not on MC.

## Numbers block (contract §9) — best candidate B03

- Standalone B03: DISC leftover 100.00%, AUDIT leftover
  +3.27%, AUDIT net +58.03, win 100.00/84.09%, epd 2.955/2.933
- Combined vs incumbent: DISC leftover 95.30 → 96.86% ·
  AUDIT leftover 79.54 → 61.97% (tolerance ≥ 77.54 — FAIL) ·
  AUDIT net +1021.86 → +1009.48 · win 96.12 → 93.89% ·
  entries/day 2.028 → 2.949 DISC · delta +192 picks
- LCT P/q05: 69.68% / 93.59% (middle FAIL) · MC combined:
  P(profit) 1.0000, DD p95 239.77 vs cap 339.08, cluster p95
  136.78 vs cap 205.17, consec p95 2 — PASS · PBO 0.00% ·
  DSR 1.0000 (N=21 this-run family) · decay not FAIL
- Incumbent MC: P(profit) 1.0000, DD obs 136.78, DD p95
  153.70, cluster −136.78/136.78, consec 2/2 — PASS
- Office grades: 07:30 ADD = DOWNGRADE (recorded) ·
  07:30 REPLACE = DOWNGRADE (bounded) · DROP-only =
  DOWNGRADE (net arm, exact) · no move recommended
- Trial count: 20 cycles pre-registered; PBO/DSR family
  N = 21. DXY: BLOCKED-DATA, not used, not claimed;
  DOLLARIDX = Dukascopy-labelled feature leg only (B7/B6
  pool rounds), H1 from 2017-12-01, no volume conditions on it.

## Method / files

- Runners: `~/workspace/fx/work_20cyc_r2/run_may_planB_s1.py`
  (slate pre-registered in its header) +
  `recompute_may_planB.py` (programme-convention stats).
  Machinery reused verbatim: `work_29load/mc9_verbatim.py`,
  `work_new8/validate_new8.py` (seg_stats, lct, round_pbo_dsr,
  daily_pnl).
- Machine results: `results/may_planB_s1_run.json` (aggregate-
  convention first pass — superseded for leftover/win by
  `results/may_planB_s1_stats_vconv.json`, the programme-
  convention figures used above; net/epd identical),
  per-cycle standalone + combined ledgers
  `results/may_planB_s1_B01..B20_{ledger,combined}.csv`.
- Gaps named: (1) replacement-hour grade is a bounded
  estimate — an exact grade needs a full-cycle re-walk with
  16:30 removed and the new hour added (not run; the only
  exact 07:30 evidence is the recorded ADD measurement);
  (2) union walks are ledger-level recombinations of prior
  design walks, not fresh equation mining — fresh mining at
  May hours with AUDIT-robust selection is the untried route
  for the second-best gap; (3) sizing not measured (not a
  gate this round, brief §0).

## Wave-2 completion — leftover-convention restatement (2026-10-30)

Every leftover figure ABOVE is in the `validate_new8.seg_stats`
convention (the "vconv" of `may_planB_s1_stats_vconv.json`):
leftover = (W − R·L)/n × 100, R = avg-loss/avg-win — i.e. the
standard leftover multiplied by the win rate. The brief's
by-trade convention (the one the Jul files and the standing
leftover definition use) is leftover = net ÷ gross wins of
net-winning trades. Nets, win % and epd are identical under
both conventions; only leftover differs. Recomputed in the
brief's by-trade convention (machine record:
`results/may_planB_s1_stats_stdconv.json`):

- Incumbent 88n: DISC leftover **95.83%** (vconv 95.30) ·
  AUDIT leftover **82.75%** (vconv 79.54) · net +4711.99 /
  +1021.86 · win 99.45 / 96.12 · epd 2.028 / 2.289 (unchanged)
- Combine-safety tolerance in this convention: combined AUDIT
  leftover ≥ 82.75 − 2.00 = **80.75%**
- Best candidate B03: standalone DISC 100.00% / AUDIT **3.88%**
  (vconv 3.27) · combined DISC **97.23%** (vconv 96.86) ·
  combined AUDIT **66.00%** (vconv 61.97) → Δ vs incumbent
  **−16.75 pts — misses the tolerance by 14.75 pts** (vconv
  reading: −17.57, miss by 15.57)
- All 20 cycles in this convention: combined AUDIT leftover
  ranges 27.78–66.00% — **none reaches 80.75%**; the closest
  after B03 is B15 at 62.95%. Standalone AUDIT leftovers are
  negative for 19 of 20 cycles (B03 +3.88% the only positive),
  same as the vconv reading.

**The verdict is identical under both conventions: NO
IMPROVEMENT — no May second-best is created.** The convention
changes the size of the miss, never its sign or the ranking
(B03 closest on both). Read the body of this file as vconv
figures and this section as the brief-convention figures;
the two are never mixed inside a single comparison above.

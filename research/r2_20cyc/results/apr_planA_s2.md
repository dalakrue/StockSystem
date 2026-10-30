VERDICT: Apr planA s2 — NO IMPROVEMENT

# Apr Plan A Scenario 2 — 20 cycles CREATED for the added slot 07:30 MMT (2026-10-30)

CREATION, not replay: all 20 equations were designed natively for
07:30 MMT (April's free standing slot — April already uses 00:30;
entry bar 01:00 UTC, stored check 01:30 UTC). H1 direction/state +
M15 confirmation, features from bars strictly before the entry
bar, entry at the entry-bar open, H1 exit SL-first, hold ≤ 48
bars, one pick per check = strongest |direction momentum| among
passing symbols, 28 symbols. The 2026-10-29 incumbent-replay calc
was NOT repeated. Research level only — no push, no live app.

S2 lessons applied (Jan/Feb/Sep): the slate is biased to
STATE/CONFIRMATION-heavy equations (RSI/BB/vol/ATR bands + M15
confirmation in nearly every rule), includes two native
MEAN-REVERSION cycles (S19/S20) and two explicit loss-cluster
controls (S16 post-loss symbol cooldown, S17 post-loss global
skip-1). Data: indexed DB queries only (Feb 10–May 12 windows per
year — warmup + April + 48-bar exits; a full-history CSV load was
OOM-killed under parallel-lane memory pressure and replaced).
DXY: BLOCKED-DATA (Wave 0, Twelve 429) — dollar legs (S08/S20)
are DOLLARIDX-labelled only (Dukascopy H1, mom only, NO volume
condition, data from 2017-12-01).

## Base of record (stated, per task order)

**Incumbent 87c+87s** (946 picks, asserted exact before mining):
DISC leftover 85.26%, AUDIT leftover 71.26%, AUDIT net +1929.49,
win 97.72/94.47, epd 4.420/4.523; MC reproduced bit-for-bit this
run (DD obs 164.43 → p95 221.12 vs own cap 246.65, cluster obs
−102.50 → p95 103.30 vs cap 153.75, consec 1→2, P(profit) 1.0000,
flag PASS). Second variant base: Plan A S1 winner **C20**
(ledger-level, fall-through replay pending — NOT operative):
DISC 90.56%, AUDIT 78.92%, AUDIT net +2064.49, MC DD p95 174.91
PASS. Apr convention: validate_new8 seg_stats @2.5 (by-trade
leftover); segment days DISC 169 / AUDIT 44.

## Slot + probe evidence — 07:30 MMT is DISC-hostile

07:30 slot bars (01:00 UTC, April, DISC years): median H1 volume
5,091.3, median H1 range 14.65 pips. Three pre-registered probes,
one pick per check:
| probe | DISC leftover / net / win | AUDIT leftover / net |
|---|---|---|
| P-base (mom4+M15mom+M15vol) | −6.90% / −201.5 / 78.70% | 14.16% / +108.2 |
| P-mom16 (mom16+M15mom+H1vol) | −13.65% / −397.0 / 76.79% | 9.27% / +71.4 |
| P-state (mom4+RSI band+BB band+M15mom) | −29.89% / −870.5 / 75.15% | 23.54% / +179.9 |
Every probe is DISC-negative while AUDIT is mildly positive —
the same DISC→AUDIT sign-flip pattern as Jan/Feb/Sep S2, here
with the hostile side on DISC. The full 20-cycle slate was run
anyway, as ordered.

## Winner of the slate — S19 (native mean-reversion)

Pre-registered selection: maximise INC+slot combined DISC
leftover among cycles with standalone DISC net > 0. Only three
cycles are DISC-eligible standalone (S06 +26.4, S15 +269.1,
S19 +46.3); S19 wins on the combined measure.
S19 rule: direction = −sign(H1 mom4) (reversal); keep only if
trade-direction-signed H1 RSI ≤ −15 AND signed BB ≤ −0.8 (price
stretched against the trade) AND M15 mom4 aligns with the
reversal; TP20/SL100. It fires rarely by design.
Standalone: DISC n 26 / net +46.30 / leftover 10.18% / win
80.77% / epd 0.154; AUDIT n 6 / net +105.00 / leftover 100.00% /
win 100.00% / epd 0.136 (n=6 — small-sample, stated plainly).
Merged second-priority vs incumbent: **30 of 32 slot picks
accepted**.

## Numbers block — incumbent vs incumbent + S19

| Metric | Incumbent 87c+87s | INC + S19 |
|---|---|---|
| Total picks | 946 | 976 (946 + 30) |
| DISC n / net | 747 / +6620.36 | 771 / +6631.66 |
| DISC leftover | 85.26% | **81.34%** (−3.92) |
| DISC win % / epd | 97.72 / 4.420 | 97.15 / 4.562 |
| AUDIT n / net | 199 / +1929.49 | 205 / **+2034.49** (+105.00) |
| AUDIT leftover | 71.26% | **72.30%** (+1.04) |
| AUDIT win % / epd | 94.47 / 4.523 | 94.63 / 4.659 |
| LCT P / q05 (DISC, paired vs incumbent) | — | **13.21% / 74.32% — middle FAIL** |
| MC P(profit) | 1.0000 | 1.0000 |
| MC DD obs → p95 vs own cap (1.5×obs) | 164.43 → 221.12 vs 246.65 PASS | 164.43 → **217.98 vs 246.65 PASS** |
| MC cluster obs → p95 vs cap | −102.50 → 103.30 vs 153.75 PASS | −102.50 → **122.20 vs 153.75 PASS** |
| MC consec obs → p95 | 1 → 2 PASS | 1 → 2 PASS |
| MC middle (verbatim flag) | PASS | PASS (all arms, own-relative caps) |
| PBO / DSR (canonical, family-21 stated) | 0.00% / 1.0000 (EC record) | **20.00% / 1.0000** ✓ |
| Decay | PASS | PASS |

Stated family for PBO/DSR = 21 daily DISC series {INC + 20
INC+S2 combined variants}, validate_new8 verbatim. Disclosed
second reading (R2-engine CSCV, family-20 slot variants): PBO
49.60%, DSR(S19 combined) 0.9999 — not the gate.

## §2 check-time grade vs the incumbent — ACCEPTABLE, but §2 best gates FAIL

- IMPROVE needs AUDIT leftover up AND DISC leftover not down:
  AUDIT +1.04 ✓ but DISC −3.92 ✗ — not IMPROVE.
- DOWNGRADE arms: AUDIT leftover down >0.5pt ✗ (it rose);
  win <80% ✗ (94.63 AUDIT); AUDIT net down worse than
  −max(25, 192.95) ✗ (net rose +105.00). No arm fires →
  **ACCEPTABLE** on the check-time rule.
- §2 best gates on the combined: LCT-middle **FAIL** (P 13.21%
  < 80; q05 74.32 ≥ 20 ✓) · win >80 ✓ · epd ≥2 ✓ · AUDIT net >0
  ✓ · MC all arms PASS own-relative ✓ · PBO 20 ≤ 50 ✓ · DSR
  1.0000 ≥ 0.90 ✓ · decay PASS ✓ · red lines intact ✓.
  Adoption requires ACCEPTABLE **and** the best gates (task
  order); LCT-middle fails, so the slot is **NOT adopted**.

## Second variant — C20 + S19 (stated as such)

C20+S19 combined (913 picks, 30 accepted): DISC leftover
90.56% → **86.20%** (−4.36), AUDIT leftover 78.92% → **79.71%**
(+0.79), AUDIT net +2064.49 → **+2169.49**, win 97.79/95.74,
epd 4.290/4.273. Check-time grade vs C20: **ACCEPTABLE** (same
shape: AUDIT up, DISC down, no DOWNGRADE arm). §2 gates vs C20:
LCT P **13.21%** / q05 79.22% — middle FAIL; MC flag PASS
(DD p95 185.62 vs own cap 246.65, cluster p95 102.50, consec
2); decay PASS. Same conclusion: not adoptable.

## Loss-cluster mechanism — before vs after

Explicit controls in the slate: S16 (post-loss same-symbol
cooldown: standalone DISC −4.65%, combined AUDIT leftover
57.10% — DOWNGRADE) and S17 (post-loss global skip-1:
standalone DISC −12.98%, combined AUDIT 63.39% — DOWNGRADE).
Neither control fixes anything at this hour; both combined
forms dilute. For the selected S19 the cluster arms barely
move because the slot adds only 30 picks: worst cluster obs
−102.50 → −102.50 (unchanged — the slot imports NO new worst
cluster, unlike Jan S2's −304.32), cluster p95 103.30 →
122.20 (cap 153.75, PASS), DD obs unchanged 164.43, consec
1 → 1 obs. The mean-reversion slot is cluster-neutral; the
momentum slate's combined cluster arms were not batteried
(all 19 momentum/cluster combined forms already fail on the
check-time grade).

## All 20 created cycles at 07:30 (standalone DISC/AUDIT leftover · combined-with-incumbent DISC/AUDIT leftover · grade vs INC)

19 of 20 grade **DOWNGRADE**; only S19 grades ACCEPTABLE (and
fails LCT). Every momentum combined form drags DISC leftover
to 51–69% and AUDIT leftover below the incumbent despite
several AUDIT-positive standalone slots — the added hour's
~207 accepted picks per momentum cycle are priced at leftover
far below the incumbent's 85.26/71.26.

- S01 mom4+M15mom+M15vol: −6.90 / 14.16 · comb 61.08 / 58.60 DOWN
- S02 mom16+M15mom+H1vol: −13.65 / 9.27 · comb 60.51 / 57.59 DOWN
- S03 mom4+RSI+BB+M15mom (state): −29.89 / 23.54 · comb 54.97 / 60.64 DOWN
- S04 mom4+BB+M15 RSI/vol bands: −29.00 / 20.99 · comb 55.00 / 60.07 DOWN
- S05 mom16+RSI+BB+M15mom (state): −18.86 / 25.95 · comb 59.01 / 61.25 DOWN
- S06 mom4+MACD+EMA+M15mom: +0.95 / 6.09 · comb 64.81 / 57.73 DOWN
- S07 mom24+ATR+M15vol TP30: −20.30 / −37.92 · comb 51.11 / 39.15 DOWN
- S08 mom4+DOLLARIDX leg+M15mom: −19.41 / −17.26 · comb 57.72 / 51.93 DOWN
- S09 mom4+EURUSD leg+M15mom+H1vol: −13.40 / 14.16 · comb 59.61 / 58.81 DOWN
- S10 mom16+M15 RSI/BB/vol bands: −35.77 / −1.10 · comb 54.10 / 55.10 DOWN
- S11 strict all-confirm: −11.02 / 8.42 · comb 59.94 / 57.03 DOWN
- S12 mom4+M15mom TP10/SL60: −31.96 / 52.67 · comb 69.22 / 69.00 DOWN
- S13 mom16+M15mom+H1vol TP10/SL60: −51.50 / −6.06 · comb 66.20 / 62.48 DOWN
- S14 mom4+RSI+M15mom TP30: −10.81 / 3.11 · comb 53.24 / 51.43 DOWN
- S15 mom24+EMA+M15 RSI SL60: +9.15 / −29.01 · comb 66.03 / 49.34 DOWN
- S16 cluster ctrl symbol-cooldown: −4.65 / −2.23 · comb 64.33 / 57.10 DOWN
- S17 cluster ctrl global skip-1: −12.98 / 32.15 · comb 63.89 / 63.39 DOWN
- S18 state-max (RSI+BB+vol+M15mom): −25.09 / 23.54 · comb 56.07 / 60.64 DOWN
- **S19 MEAN-REV −mom4+RSI/BB stretch+M15mom: +10.18 / 100.00 (n 26/6) · comb 81.34 / 72.30 ACCEPTABLE (grade only; LCT FAIL)**
- S20 MEAN-REV −mom16+RSI stretch+DOLLARIDX loose: −15.45 / 48.25 · comb 69.31 / 68.77 DOWN

Pattern, stated plainly: at 07:30 MMT (01:00 UTC, thin
Asian-open hour) April H1 momentum continuation loses on DISC
in 17 of 20 forms (standalone leftover −51.50…+9.15%) while
several forms are AUDIT-positive standalone — a DISC/AUDIT sign
flip this programme does not promote on. State/confirmation
layers (S03/S05/S18) do NOT rescue the hour here (DISC −18.86…
−29.89 standalone) — the S2 lesson's preferred form was tried
first-class and still flips. The one non-dilutive creation is
the rare-firing mean-reversion S19: it adds only 30 picks in
10 Aprils, lifts AUDIT leftover +1.04 and AUDIT net +105.00
with no cluster damage, but its paired LCT P is 13.21% — the
DISC leftover cost (−3.92) is systematic, not noise — so it
cannot clear the locked middle gate.

## Verdict reasoning (gates locked in brief §2 — none moved)

20 native creations at the ordered slot, both bases graded.
Result: 19/20 DOWNGRADE under the §2 check-time rule; the sole
ACCEPTABLE form (S19, on both the incumbent and the C20
variant) fails LCT-middle, a mandatory §2 best gate, so no
form is adoptable and April's Scenario 2 closes with **NO
IMPROVEMENT**. Incumbent 87c+87s stands unchanged; C20 stands
as the S1 ledger-level candidate (its own fall-through replay
still pending, unaffected by this run). Research level only.

## Method / files

- Runner: `run_apr_planA_s2.py` (pre-registered slate in its
  header). Machinery reused: `work_new8/validate_new8.py`
  (seg_stats, LCT, PBO/DSR, daily_pnl), `work_29load/
  mc9_verbatim.py`, `support/planA_s1_engine.py` (decay, CSCV
  second reading).
- Machine record: `results/apr_s2_run.json`; slot ledgers
  `results/apr_s2_S01..S20_slot_ledger.csv`, probe ledgers
  `results/apr_s2_study_*_ledger.csv`, winner combined ledgers
  `results/apr_s2_S19_combined_inc_ledger.csv` and
  `results/apr_s2_S19_combined_c20_ledger.csv`.
- Batteries run on the DISC-selected winner only (S19, both
  bases) plus incumbent/C20 MC controls — the other 19 forms
  are decided by the check-time grade + full stats, all
  DOWNGRADE. Sizing: NOT a gate in this round — not measured.

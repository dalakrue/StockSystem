VERDICT: Jul planA s1 — SMALL-IMPROVED

# Jul Plan A Scenario 1 — 20 cycles (+9 refinement), cycle78 incumbent
Run 2026-10-30. Research level only; no push, no live app opened.
Scripts: run_jul_pa_s1.py / run_jul_pa_s1b.py; raw JSON:
jul_pa_s1_screen.json, jul_pa_s1_screen2.json, jul_pa_s1_final.json.
Incumbent ledger: work_c78/results/WINNER_disc_log.csv +
WINNER_unseen_log.csv (the ledger whose MC reproduces the step test
EXACTLY). Segments by year: DISC ≤2023 (174 d), AUDIT ≥2024 (46 d).
Leftover = net ÷ gross wins of winning trades (net basis, @2.5 cost),
computed identically for incumbent and candidates. Published
month_specs pool figures (different denominator): DISC 62.57 /
AUDIT 61.42. Registry uniform DISC epd for cycle78: 2.828 (audit
form); this ledger's raw DISC epd = 467/174 = 2.684.
DXY: BLOCKED-DATA (Wave 0, Twelve 429) — no DXY used anywhere;
no DOLLARIDX leg was needed by any winning mechanism.

## Incumbent (cycle78, no second-best; checks 21:30/23:30/00:30 MMT)
- DISC: n 467, net +3300.44, win 94.65%, leftover 66.10%, epd 2.684
- AUDIT: n 128, net +877.62, win 94.53%, leftover 64.97%, epd 2.783
- MC verbatim (mc9, 10,000 paths): P(profit) 1.0000 · DD obs 143.81,
  DD p95 **233.91 vs cap 215.72 FAIL** (cap = 1.5×DD obs, step test)
  · worst-cluster obs −125.67, cluster p95 169.57 vs cap 188.51 PASS
  · consec obs 2, consec p95 2 PASS. PBO 17.46% PASS · DSR 0.9998 PASS
  (step-test record). Decay: AUDIT/DISC leftover 0.98 — not FAIL.
- Loss-cluster anatomy: max consec losses = 2 only, but the worst
  cluster (−125.67) and the DD path are built from near-adjacent
  losses separated by small wins; the single worst cluster leg is
  FB_AUDUSD_h17_0_G (cluster contribution −457.21 across runs).

## WINNER — C18 = LEGPRUNE + partner fill (combinable-partner half)
Mechanism: (1) prune leg FB_AUDUSD_h17_0_G (worst loss-cluster leg);
(2) second-priority partner = work_new8 MONTH_Jul_PLANB_cand1 ledger,
fills ONLY checks where the (pruned) best is silent (+24 picks).
- DISC: n 453, net +4071.60, win 95.58%, **leftover 76.30%** (inc 66.10)
- AUDIT: n 122, net **+883.40** (inc +877.62), win 95.08%,
  **leftover 66.58%** (inc 64.97 — strictly greater ✓)
- Entries/day: DISC 2.603 · AUDIT 2.652 (≥2 ✓; combined delta +24 picks > 0 ✓)
- LCT (paired block-bootstrap, DISC, 10k): **P 86.32% ≥ 80 ✓ · q05 62.17% ≥ 20 ✓**
- MC verbatim 10,000 paths: P(profit) 1.0000 · DD obs 138.13,
  **DD p95 210.67 ≤ 215.72 step-test cap ✓ PASS** · cluster p95 141.20
  vs cap 188.51 ✓ · consec p95 2 ✓
- CAVEAT (gate not moved): under mc9's own-relative formula the DD cap
  recomputes to 1.5×138.13 = 207.20 and C18 misses it by 3.47 pips
  (mc_middle_pass=False on that arm alone). It passes the step test's
  fixed cap (215.72) that defined this round's target. Parent to rule
  which reading governs promotion; reported, not hidden.
- PBO / DSR: NOT recomputed for C18 (gap). Incumbent arms pass
  (17.46% / 0.9998); C18's DISC edge rose, but no claim is made.
- Decay: AUDIT/DISC leftover ratio 0.87 — not FAIL.
- Trial count: 29 variants evaluated this run (20 round-1 + 9
  refinement) + 5 verbatim finals. Red lines: AUDIT net positive,
  no discovery collapse ✓.

## Runner-up — C11 LEGPRUNE alone (direct half)
DISC leftover 73.41% · AUDIT leftover 65.85% (> inc ✓), net +854.92 ·
win 95.36/95.00 · epd 2.477/2.609 · LCT P 86.32 / q05 62.17 ✓ ·
MC verbatim: DD p95 225.92 — passes its own cap (249.92) but NOT the
fixed 215.72 step cap. Cluster p95 146.30 ✓, consec 2 ✓.

## MC arms BEFORE → AFTER, every cluster mechanism tried
Incumbent BEFORE (verbatim): DDobs 143.81 · DDp95 233.91 ·
CLp95 169.57 · CONSECp95 2 · P(profit) 1.0000.
(Screen = mc9 at 3,000 paths; cap shown = fixed step cap 215.72.)
| Cycle | Mechanism | DDobs | DDp95 | CLp95 | Consec | vs 215.72 |
|---|---|---|---|---|---|---|
| C01 CD1 | post-loss cooldown 1 pick | 177.07 | 271.78 | 161.40 | 2 | FAIL |
| C02 CD2 | cooldown 2 picks | 232.70 | 305.22 | 173.52 | 2 | FAIL |
| C03 CD3 | cooldown 3 picks | 292.64 | 383.63 | 176.81 | 2 | FAIL |
| C04/C05 | cluster-pause / cap2in5 (LATCH BUG — invalid, superseded by C12/C13) | — | — | — | — | invalid |
| C06 SYMBLK-all | block symbol until it wins again | 125.67 | 182.70 | 125.67 | 2 | PASS but epd 1.667/0.761 — entries gate FAIL, rejected |
| C07 FAMBLK | currency-family block after loss | 165.85 | 243.57 | 167.00 | 2 | FAIL |
| C08 DIRSTACK | same-direction stack limit | 183.92 | 253.86 | 173.52 | 2 | FAIL |
| C09 DAYCAP2 | day cap 2 losses (never binds: max 2/day pattern) | 143.81 | 236.83 | 171.00 | 2 | FAIL (= incumbent) |
| C10 DAYLOSS1 | stop day after 1st loss | 174.62 | 271.11 | 161.40 | 2 | FAIL |
| C11 LEGPRUNE | prune FB_AUDUSD_h17_0_G | 166.61 | 225.97 scr / 225.92 verb | 146.30 | 2 | FAIL fixed cap |
| C12 CLUSPAUSE2 | 2 consec losses → skip 2 (fixed) | 143.81 | 233.53 | 167.91 | 2 | FAIL |
| C13 CAP2in5fix | ≥2 losses in last 4 → skip (fixed) | 143.81 | 231.44 | 167.00 | 2 | FAIL |
| C14 SYMBLK1x1 | symbol lost → block its next 1 | 166.53 | 244.81 verb | 161.40 | 2 | FAIL |
| C15 SYMBLK2x1 | symbol 2 consec losses → block 1 | 143.81 | 231.20 verb | 162.55 | 2 | FAIL |
| C16 SYMBLK2x2 | symbol 2 consec losses → block 2 | 143.81 | 232.54 | 165.90 | 2 | FAIL |
| C17 LP+SYMBLK2x1 | prune + symbol block | 166.61 | 225.23 verb | 146.40 | 2 | FAIL fixed cap |
| C18 LP+P10 | prune + partner fill | 138.13 | **210.67 verb** | 141.20 | 2 | **PASS** |
| C19 INC+P10 | partner fill only | 130.43 | 216.70 | 162.55 | 2 | FAIL by 0.98 |
| C20 LP+CLUSPAUSE2 | prune + cluster pause | 166.61 | 226.23 | 144.73 | 2 | FAIL fixed cap |
Partners alone (screen): P01 cand1 292.13 · P02 cand2 379.81 ·
P04 PLANB9 partner 226.27 · P05 PLANB9C partner 226.05 ·
P06 PLANB9 cand1 222.93 · P07 PLANB9 cand2 223.52 ·
P08 ROUND3 cand1 222.93 · P09 ROUND4 cand1 222.93 ·
P10 PLANB cand1 216.70 — all FAIL fixed cap alone; P03 file missing
(MONTH_Jul_PLANB_partner_ledger.csv does not exist — named gap).
KEY FINDING: sequential cooldowns/stack limits make DD WORSE — they
delete the small wins that interrupt the observed DD path (DDobs
rises monotonically with cooldown length). What works is removing
the cluster-source LEG and backfilling its silent checks with an
uncorrelated partner (DDobs falls to 138.13, cluster p95 169.57→141.20).

## Gates vs §2 (C18)
LCT-middle ✓ (86.32/62.17) · AUDIT leftover strictly > inc ✓ ·
win >80 ✓ · epd ≥2 ✓ · AUDIT net >0 ✓ · red lines ✓ ·
MC DD: PASS on step-test fixed cap, FAIL by 3.47 on own-relative
cap (stated above) · PBO/DSR not recomputed (gap) → SMALL-IMPROVED,
not promoted by this worker.

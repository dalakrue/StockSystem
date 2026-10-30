VERDICT: Jan planA s1 — NO IMPROVEMENT

# Jan Plan A Scenario 1 — 20 cycles (R2, brief §2/§3/§9)
# Run 2026-10-30. Worker: ledger-level, recorded ledgers only (no DB
# mining — fx_data.db contended; no Twelve Data calls; DXY not used).
# Machinery: validate_new8.py verbatim (seg_stats, split_seg, lct,
# round_pbo_dsr, daily_pnl, metrics) + mc9_verbatim.mc_test
# (block 10, 10,000 paths, seed 20261101, net = gross − 2.5).
# Script + raw output: ../run_jan_planA_s1.py, jan_planA_s1_run.json.

## Incumbent (read fresh from registry; reproduced EXACT before mining)
- Jan best cycle60b (BRIEF23 C20_STACK) + second cycle60 (C60-03),
  combined = best-priority dedup merge (second fills only checks the
  best does not take), checks 17:30 / 19:30 / 23:30 MMT, all OFF-HOURS.
- Combined ledger rebuilt from C20_STACK_disc/audit + C60-03_disc/
  unseen: DISC (Jan 2016–2023) n 523, AUDIT (Jan 2024–2025) n 135,
  total 658 — matches the APP24/EC record (658) exactly.
- DISC: net +1310.13, win 92.35%, leftover 29.82% (by-trade formula,
  the validate_new8 convention used for every number below),
  entries/day 2.972. Cross-check, Net÷GrossWins convention: DISC
  leftover 64.23% is the BEST-ALONE (355-trade) figure in the app
  description; the combined's by-trade figure is the one the Jan
  PLANB verdict graded (29.82%) and is used consistently here.
- AUDIT: net +749.88, win 95.56%, leftover 70.06%, entries/day 2.935.
- MC (full walk, this run — reproduces the EC record bit-for-bit):
  P(profit) 0.9999, DD obs 459.29, DD p95 527.91 vs cap 688.94 PASS,
  consec obs 3 / p95 3 (cap obs+2), cluster (worst consec-loss sum)
  obs −201.82, p95 205.00 vs cap 302.73 — MC middle PASS.
- PBO 40.00% (EC record). DSR 0.8630 (EC record) — FAIL vs 0.90, the
  ONLY failing EC-middle item (target of this run).
- Decay (EC check-4 form): DISC EV 2.505, AUDIT EV 5.555 — PASS.
- Trial-count note (material): DSR is family-relative. The recorded
  0.8630 came from the PLANB family of 4 DISC-daily series
  (incumbent, cand1, combined, cand2). In THIS run's honest family
  (incumbent + the 20 cycles below, N = 21) the SAME incumbent
  ledger scores DSR 0.6279 (daily Sharpe 0.1987). Both numbers are
  reported; the candidate below is graded in this run's family,
  and its Sharpe gain is stated in absolute terms so the claim
  does not rest on family choice.

## Pre-registered slate (fixed BEFORE results; trial count = 20)
Direct improvement of the best (10): D01 post-loss cooldown ×1
check · D02 post-loss cooldown ×2 · D03 two-loss cooldown ×2 ·
D04 same-symbol loss block 48h · D05 same-symbol loss block 24h ·
D06 same-direction stack limit 3 · D07 slot replacement — ban the
worst DISC-net strategy (FB_EURUSD_h11_0, DISC net −367.34, 86
trades) · D08 slot replacement — ban the 2 worst DISC-net
strategies (+ FB_AUDUSD_h13_0, −208.52, 79 trades) · D09 ban worst
DISC-net symbol (EURUSD) · D10 FB trim — ban every FB strategy
with negative DISC net (identical set to D08: the two banned legs
are exactly the negative FB legs, so D08 ≡ D10 by construction).
Combinable partners (10): P01–P10 = the ten prior-lane Jan
candidate ledgers (PLANB2/3/4/5/6/7/8/9/12/12C cand1) merged under
incumbent priority (a partner pick is accepted only at a check the
combined does not already take). Slot bans were selected on DISC
only; AUDIT was never used for selection.
Loss-cluster mechanisms (brief §3, explicit): D01/D02/D03
(post-loss cooldowns), D04/D05 (repeat-loss symbol block), D06
(same-direction stack limit) — cluster/consec arms before vs after
in the table below.
DXY: not used (BLOCKED-DATA, Wave 0). No DOLLARIDX leg was added:
every prior Jan partner design is DOLLARIDX-saturated and added
zero picks (below); no new dollar leg was mined at ledger level.

## All 20 cycles — DISC / AUDIT (by-trade leftover; win = AUDIT win)
| cycle | DISC n | DISC net | DISC left | DISC epd | AUDIT n | AUDIT net | AUDIT left | AUDIT win | AUDIT epd |
|---|---|---|---|---|---|---|---|---|---|
| INCUMBENT | 523 | +1310.13 | 29.82% | 2.972 | 135 | +749.88 | 70.06% | 95.56% | 2.935 |
| D01 cool1 | 487 | +1357.59 | 33.11% | 2.767 | 130 | +721.07 | 70.00% | 96.15% | 2.826 |
| D02 cool2 | 455 | +1278.93 | 33.31% | 2.585 | 125 | +683.57 | 68.86% | 96.00% | 2.717 |
| D03 dblcool | 515 | +1305.40 | 30.24% | 2.926 | 133 | +734.58 | 69.62% | 95.49% | 2.891 |
| D04 symblock48 | 502 | +1150.62 | 27.16% | 2.852 | 132 | +725.25 | 69.35% | 95.45% | 2.870 |
| D05 symblock24 | 512 | +1225.62 | 28.44% | 2.909 | 134 | +742.08 | 69.84% | 95.52% | 2.913 |
| D06 dirstack3 | 477 | +1292.69 | 32.21% | 2.710 | 128 | +741.68 | 72.89% | 96.09% | 2.783 |
| D07 dropworst1 | 437 | +1677.47 | 44.83% | 2.483 | 114 | +592.38 | 64.85% | 94.74% | 2.478 |
| D08 dropworst2 | 358 | +1885.99 | 60.21% | 2.034 | 95 | +480.08 | 62.30% | 94.74% | 2.065 |
| D09 dropworstsym | 412 | +1448.66 | 41.42% | 2.341 | 108 | +542.56 | 62.83% | 94.44% | 2.348 |
| D10 fbtrim (= D08) | 358 | +1885.99 | 60.21% | 2.034 | 95 | +480.08 | 62.30% | 94.74% | 2.065 |
| P01–P10 partners | 523 | +1310.13 | 29.82% | 2.972 | 135 | +749.88 | 70.06% | 95.56% | 2.935 |
Partner result, stated plainly: all ten partners added ZERO picks.
The Jan combined already takes a pick at every one of its checks,
so no check-level partner can add anything — the same saturation
the NEW8 PLANB verdict measured (95 candidate picks, 0 accepted).
The combinable-partner half of Plan A is structurally exhausted
for January at its current check times.

## Full battery on the qualifying candidates (DISC leftover ≥ incumbent)
Family for PBO/DSR: [incumbent + all 20 cycles] DISC-daily,
round_pbo_dsr verbatim, N = 21 trials, T = 171 days.

### D08/D10 — the DSR fix that the unseen record rejects
- Mechanism: SLOT REPLACEMENT — permanent ban of the two DISC-
  losing FB legs FB_EURUSD_h11_0 and FB_AUDUSD_h13_0 (DISC
  combined net −575.86 over 165 trades). This is also the run's
  strongest loss-cluster action (see MC arms).
- DISC leftover 29.82% → 60.21% · AUDIT leftover 70.06% → 62.30%
  (Δ −7.76 pts) · AUDIT net +749.88 → +480.08 (Δ −269.80) ·
  win 94.74% (AUDIT) / 94.69% (DISC) · entries/day 2.034 DISC /
  2.065 AUDIT (both ≥ 2, thinnest margin in the slate).
- LCT (paired, DISC, 10,000 paths): P 99.59%, candidate q05
  48.19% — middle PASS and strict PASS.
- MC arms BEFORE → AFTER: P(profit) 0.9999 → 1.0000 · DD p95
  527.91 (cap 688.94) → 220.04 (cap 260.58 = 1.5 × obs 173.72)
  PASS · cluster p95 205.00 (cap 302.73) → 137.78 (cap 206.67)
  PASS · consec p95 3 → 2 (obs 2, cap 4) PASS. MC middle PASS,
  every arm improved.
- PBO 10.00% PASS · DSR 0.9947 PASS (daily Sharpe 0.1987 →
  0.4817 — the gain is a real Sharpe gain, not only a family
  artefact) · decay PASS (DISC EV 5.268, AUDIT EV 5.053).
- GATE FAILURE (locked, brief §2): AUDIT leftover must be
  strictly above incumbent, or not below it under the small-
  improvement rule. 62.30% is 7.76 pts BELOW 70.06% — outside
  even the −2.00 combine tolerance. The two banned legs lost
  −575.86 on DISC but WON +269.80 on AUDIT: a regime flip. A
  DISC-selected ban that costs unseen this much is exactly what
  the unseen rule exists to stop. NOT PROMOTED.

### D07 — ban FB_EURUSD_h11_0 only
DISC leftover 44.83% · AUDIT leftover 64.85% (Δ −5.21, also below
incumbent → fails the same unseen gate) · AUDIT net +592.38 ·
win 94.74% · epd 2.483/2.478 · LCT P 93.92% / q05 32.97% middle
PASS · MC PASS (P 1.0000, DD p95 449.57 vs cap 603.38, cluster
p95 200.28 vs cap 300.42, consec p95 3) · PBO 10.00% · DSR
0.9156 PASS · decay PASS. Rejected on the unseen-leftover gate
alone — same regime flip, smaller dose.

### D09 — ban EURUSD (worst DISC symbol)
DISC leftover 41.42% · AUDIT leftover 62.83% (Δ −7.23 → fails
unseen gate) · AUDIT net +542.56 · LCT P 87.91% / q05 22.56%
middle PASS · DSR 0.8488 FAIL · MC PASS. Rejected twice over.

### D01 — post-loss cooldown ×1 (the headline cluster mechanism)
DISC leftover 33.11% · AUDIT leftover 70.00% (Δ −0.06) · AUDIT
net +721.07 · win 96.15% · epd 2.767/2.826 · LCT P 71.14% /
q05 5.88% middle FAIL · DSR 0.7067 FAIL · MC PASS with cluster
arms improved BEFORE → AFTER: cluster p95 205.00 → 173.11,
consec p95 3 → 2, DD p95 527.91 → 450.06 (cap 619.97). The
cooldown genuinely thins loss clusters; it does not lift DSR
or LCT enough. Rejected.

### D06 — same-direction stack limit 3
The ONLY cycle with AUDIT leftover above incumbent: 72.89%
(Δ +2.83), AUDIT net +741.68 (Δ −8.20, inside tolerance), DISC
leftover 32.21%, win 96.09%, epd 2.710/2.783, decay PASS. But
LCT P 60.54% / q05 17.21% FAIL, DSR 0.6821 FAIL, and MC middle
FAIL on the DD arm (DD p95 463.30 vs cap 441.92 = 1.5 × obs
294.61; cluster p95 201.82 vs cap 302.73 PASS, consec p95 3
PASS, P(profit) 1.0000). Rejected on three locked gates.

## Verdict reasoning (gates locked in brief §2 — none moved)
No cycle passes every promotion gate. The DSR target IS
reachable — D08/D10 lifts DSR to 0.9947 with LCT strict pass,
MC all-arms pass and PBO 10% — but only by banning two legs
whose DISC losses reverse into AUDIT wins, costing −7.76 pts
of unseen leftover, which the brief's unseen rule (strictly
above, or not-below under small-improvement) forbids. Every
other DISC-improving ban (D07, D09) fails the same unseen gate;
every unseen-safe mechanism (D01–D06) fails DSR and/or LCT
and/or the MC DD arm. January's DSR failure and its unseen
record are the same fact seen from two sides: the edge that
DISC can certify is concentrated in legs that do not repeat
on AUDIT. Incumbent cycle60b + cycle60 stands unchanged.
Research level only — nothing pushed, nothing integrated.

## Numbers block (contract §9) — incumbent vs best-DSR candidate D08
- DISC leftover: 29.82% → 60.21% · AUDIT leftover: 70.06% →
  62.30% · AUDIT net: +749.88 → +480.08 · win: 95.56% → 94.74%
  (AUDIT) · entries/day: 2.972/2.935 → 2.034/2.065 (DISC/AUDIT)
- LCT P/q05: — (incumbent is the reference) → 99.59% / 48.19%
- MC: P(profit) 0.9999 → 1.0000 · DD p95 527.91 vs cap 688.94 →
  220.04 vs cap 260.58 · cluster p95 205.00 vs cap 302.73 →
  137.78 vs cap 206.67 · consec p95 3 → 2
- PBO: 40.00% (EC record) → 10.00% · DSR: 0.8630 (EC record,
  family N=4) → 0.9947 (this run's family N=21; incumbent in
  the same family = 0.6279) · decay: PASS → PASS
- Loss-cluster mechanism: slot replacement of the two DISC-
  losing FB legs (D08) + pre-registered cooldown/block/stack
  family (D01–D06); cluster arm 205.00 → 137.78 (D08),
  205.00 → 173.11 (D01 cooldown).
- Trial count: 20 cycles pre-registered; PBO/DSR family N = 21
  (incumbent + 20). DXY: BLOCKED-DATA, not used, not claimed.

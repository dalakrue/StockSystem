VERDICT: Oct planA s1 — IMPROVED

# Oct Plan A Scenario 1 — 20-Cycle Round R2 (2026-10-30)

Improvement job: **IMPROVED at ledger level** — two forms clear
ALL locked §2 gates. Winner by the locked selection rule
(strongest LCT first): **C01 = veto of slot FB_EURUSD_h15_0**,
the single DISC loss-cluster slot (12 of October's 13 DISC
losers, −540.00). Co-passing form: **C14 = PLANB9 cand2 partner**
(+43 accepted, incumbent-priority merge) — no veto, AUDIT net
ABOVE the incumbent. C01 is a ledger-level veto gain and is
therefore **fall-through-suspect per the standing ruling (Feb
C08 precedent): app replay REQUIRED before any integration**;
C14's partner-merge mechanism is the incumbent's own
construction mechanism and carries no such flag. No integration
is made by this worker.

C155 dual-pick preservation: the incumbent ledger REF657 already
embodies the C155 dual-pick (596 best-layer picks incl. second
entries + 61 cycle92e survivors). Both candidates preserve it:
C14 only ADDS second-priority partner picks into free checks —
the dual-pick primary/second selection is untouched. C01 removes
one equation slot (FB_EURUSD_h15_0) from the combined ledger;
all other dual-pick second entries remain in place (539 picks
kept of 657). In an app form, banning that equation would change
primary/second selection at its checks (fall-through) — that is
exactly the unmodelled part flagged above.

DXY: BLOCKED-DATA (Twelve Data 429, Wave 0) — no DXY feature
claimed. The dollar legs used (C05/C07) are DOLLARIDX-labelled
(Dukascopy H1, no volume condition, data from 2017-12-01).

Incumbent read FRESH from the app registry this run
(`core/signal_mode.py`: Oct best = cycle92, second = cycle92e;
checks 21:30 / 23:30 / 00:30 MMT, all OFF-HOURS — no office job
for Oct). Combined ledger = oct_reval REF657 (check23 concat
order kept), reproduced EXACTLY: DISC n510 net +4515.65 win
97.45% leftover 86.96% epd 2.914 (175 d); AUDIT n147 net
+1118.43 win 95.92% leftover 72.41% epd 3.196 (46 d); MC DD obs
142.30 → p95 176.96 (record 176.89; +0.07 tie-order artefact of
the stable re-sort, disclosed). EC record: PASS (PBO 0.0%,
DSR 1.0). Leftover convention = validate_new8 seg_stats
by-trade verbatim. LCT basis cross-validated: C13 (the reval
MERGED-A form) reproduces the revalidation's LCT P 69.96%
exactly in this run.

## Numbers block — incumbent 92+92e vs passing candidates

| Metric | Incumbent 92+92e | C01 (veto FB_EURUSD_h15_0) ★ | C14 (PLANB9 cand2 partner) |
|---|---|---|---|
| DISC n / net | 510 / +4515.65 | 414 / +4425.65 | 546 / +4805.34 |
| DISC leftover | 86.96% | **99.66%** (+12.70) | **87.68%** (+0.72) |
| DISC win % / epd | 97.45 / 2.914 | 99.76 / 2.366 | 97.62 / 3.120 |
| AUDIT n / net | 147 / +1118.43 | 125 / +1000.30 | 154 / +1171.05 |
| AUDIT leftover | 72.41% | **72.52%** (+0.11 ✓ strictly >) | **73.35%** (+0.94 ✓) |
| AUDIT win % / epd | 95.92 / 3.196 | 96.00 / 2.717 | 96.10 / 3.348 |
| LCT P / q05 (DISC) | — | **100.00% / 98.62%** PASS strict | **100.00% / 81.05%** PASS strict |
| MC P(profit) | 1.0000 | 1.0000 | 1.0000 |
| MC DD obs → p95 vs own cap (1.5×obs) | 142.30 → 176.96 vs 213.45 PASS | 142.30 → 164.71 vs 213.45 PASS | 142.30 → 175.00 vs 213.45 PASS |
| MC cluster obs → p95 vs cap | −142.30 → 142.30 PASS | −142.30 → 142.30 PASS | −142.30 → 142.30 PASS |
| MC consec obs → p95 | 2 → 2 PASS | 2 → 2 PASS | 2 → 2 PASS |
| MC middle (verbatim flag) | PASS | PASS | PASS |
| PBO / DSR (family-21, this run) | 0.00% / 1.0000 (record 0.9982) | 0.00% / 1.0000 | 0.00% / 1.0000 |
| Decay | PASS | PASS | PASS |
| Red lines | — | PASS (AUDIT net > 0) | PASS |

§2 gate check: **C01 and C14 pass every gate** — LCT-middle
(both strict), AUDIT leftover strictly greater, win > 80%,
epd ≥ 2 both segments, AUDIT net positive, MC all arms under
the mc9 own-relative caps, PBO ≤ 50%, DSR ≥ 0.90, decay not
FAIL. C01's AUDIT-leftover gain (+0.11) is a close call, so
LCT blocks-or-passes by the standing rule — it passes at
100.00 / 98.62. Debits stated plainly: C01's AUDIT net
(+1000.30) is BELOW the incumbent's (+1118.43) — not a §2
gate (net > 0 is), but real; C14 has no such debit and the
higher AUDIT net, at a weaker LCT q05 (81.05 vs 98.62).

## Loss-cluster mechanism — headline (before vs after)

Diagnosis (DISC, measured on REF657): October's DISC loss mass
is almost a single slot — of 13 DISC losers, **FB_EURUSD_h15_0
carries 12 (−540.00 net)**; the second-worst slot
(COMBO_wt_sem_CHFJPY_h17_SELL) carries 1 (−4.50). The MC worst
cluster (−142.30) and DD window sit in AUDIT, not in that slot,
so the veto does NOT move DD obs or the cluster obs.

Mechanisms tested and their MC arms (mc9_verbatim, 10,000
paths, seed 20261101; incumbent DD p95 176.96, cluster p95
142.30, consec p95 2):
- **C01 slot veto (the cluster slot): DD obs 142.30 → 142.30
  (unchanged — the DD window is AUDIT-side), DD p95 176.96 →
  164.71; cluster obs/p95 unchanged −142.30/142.30; consec
  2 → 2.** The mechanism works on the leftover/P&L dimension
  (DISC leftover +12.70, LCT q05 98.62) rather than on the MC
  tail, which was already PASS.
- C02 veto worst-2 slots: DISC leftover 100.00 but AUDIT
  leftover 70.47 < 72.41 FAIL; decay WEAKENED.
- C08 post-loss cooldown 1: cluster obs −142.30 → −102.50,
  DD obs 142.30 → 102.50, DD p95 144.87 PASS, AUDIT leftover
  74.99 ✓ — but DISC leftover 86.52 < 86.96 and LCT P 30.04%
  FAIL (the Sep/Jul cooldown pattern again).
- C09 symbol block 48h: near-no-op (6 dropped; AUDIT 72.25,
  −0.16 FAIL strictly->).
- C10 stack limit 2: AUDIT leftover 71.51 FAIL.

## All 20 cycles (by-trade DISC / AUDIT leftover; epd DISC/AUDIT)

Direct — slot vetoes + loss-cluster controls:
- C01 veto FB_EURUSD_h15_0 (worst DISC cluster slot): dropped 118 · 99.66 / 72.52 · epd 2.366/2.717 · **ALL GATES PASS** (table above) — fall-through-suspect
- C02 veto worst-2 slots: dropped 175 · 100.00 / 70.47 · epd 2.086/2.543 · LCT strict PASS · AUDIT leftover FAIL · decay WEAKENED
- C08 cooldown 1: dropped 18 · 86.52 / 74.99 · LCT 30.04 FAIL · MC PASS
- C09 symbol block 48h: dropped 6 · 86.86 / 72.25 · AUDIT strictly-> FAIL (−0.16)
- C10 stack limit 2: dropped 22 · 86.40 / 71.51 · AUDIT FAIL

Direct — H1 multi-indicator vetoes (3–4 ind × thr, volume, correlated legs):
- C03 RSI+MACD+vol_z: dropped 282 · 83.72 / 61.72 · epd 1.680/1.761 FAIL
- C04 RSI+mom24+ATR band: dropped 268 · 85.44 / 63.88 · epd FAIL
- C05 mom24 + DOLLARIDX-labelled leg + RSI: dropped 325 · 85.47 / 56.58 · epd FAIL, AUDIT down
- C06 BB+RSI+vol_z+H1 CLV: dropped 267 · 87.53 / 82.78 (AUDIT leftover highest of the vetoes) · epd 1.743/1.848 FAIL · LCT 58.03 FAIL
- C07 mom24 + EURUSD leg + DOLLARIDX leg + vol_z: dropped 226 · 83.91 / 67.46 · epd FAIL

Partners (prior Oct mined designs, incumbent-priority merge):
- C11 PLANB cand1 (+14): 87.74 / 67.19 · LCT 100.00/80.93 PASS · AUDIT leftover FAIL · MC DD obs rises to 200.14 (p95 237.54, own cap 300.21 PASS)
- C12 PLANB cand2 (+7): 87.44 / 66.49 · AUDIT FAIL
- C13 PLANB9 cand1 (+22) = reval MERGED-A form: 87.40 / 72.72 ✓ · LCT 69.96 FAIL (reproduces the revalidation exactly — NOT WORTH there, same here)
- C14 PLANB9 cand2 (+43): 87.68 / 73.35 · **ALL GATES PASS** (table above)
- C15 PLANB9C cand1 (+32): 87.58 / 73.02 ✓ · LCT 69.96 FAIL (the reval CAND-B pattern)
- C16 PLANB9C cand2 (+35): 87.63 / 73.36 ✓ · LCT 69.96 FAIL
- C17 ROUND2 cand1 (+30): 88.19 / 60.53 · AUDIT FAIL · MC DD obs 330.49
- C18 ROUND2 cand2 (+16): 87.86 / 59.42 · AUDIT FAIL

Combinations:
- C19 = C01 veto + PLANB9C cand1 partner (79 accepted at veto-freed checks): 99.71 / 69.29 · AUDIT leftover FAIL — the partner's AUDIT picks dilute what the veto bought
- C20 = C01 veto + PLANB cand2 partner (33 accepted): 99.69 / 68.49 · AUDIT FAIL

Pattern, stated plainly: October's edge is concentrated — one
FB slot carries nearly all DISC losses, so removing it lifts
DISC leftover to ~100% at a small AUDIT cost that still nets
strictly positive (+0.11); partner fills at the freed checks
(C19/C20) give that gain back on AUDIT. The clean additive
route is C14: +43 partner picks, every gate green, AUDIT net
above incumbent. The B-9/B-9C partner family (C13/C15/C16)
repeats its revalidation result — AUDIT-positive but LCT
69.96% — while the PLANB9 cand2 design (C14) is the one
partner whose paired LCT clears.

## Honest trial count / gaps

Slate pre-registered in `run_oct_planA_s1.py` before measuring
(20 cycles + incumbent = 21 trials; PBO/DSR above are
validate_new8 round basis on that family). Named gaps:
(1) C01 is ledger-level only — fall-through app replay NOT
run (required before integration, Feb C08 precedent); C14
needs no veto replay but has not been app-replayed either.
(2) H1-primary throughout; M15 veto variants are Plan C's
brief, not Plan A's (Sep precedent). (3) Incumbent MC DD p95
reads 176.96 here vs the 176.89 record — a +0.07 tie-order
artefact of the stable re-sort in prep; all candidate MC arms
are measured on the same basis as the incumbent in this run.

Files: run data `results/oct_planA_s1_run.json` +
`results/oct_planA_s1_post.json` (C08/C11/C13/C17 validation);
per-cycle ledgers `results/oct_planA_s1_C01..C20_ledger.csv`;
scripts `run_oct_planA_s1.py`, `run_oct_planA_s1_post.py`.

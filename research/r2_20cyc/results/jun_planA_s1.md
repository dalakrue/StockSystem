VERDICT: Jun planA s1 — NO IMPROVEMENT

# Jun Plan A Scenario 1 — 20 cycles (10 direct + 10 combinable partners)

Incumbent (read fresh from registry `core/signal_mode.py`): Jun best
**cycle89p** + second **cycle89 (CONTAINED — adds zero picks)**; checks
07:30 / 21:30 / 00:30 MMT, all off-hours. Ledger graded:
`work_new8/combined/Jun_PLANB9_combined.csv` (640 rows), reproduced
EXACTLY against its B-9 record: DISC n=519, AUDIT n=121.
**Scenario 2: IMPOSSIBLE for June** — June already uses BOTH allowed
added slots (07:30 and 00:30 MMT); no slot exists and none was invented
(brief §5). DXY: BLOCKED-DATA (Wave 0, Twelve Data 429) — the only
dollar leg used (D06) is the DOLLARIDX-labelled Dukascopy control,
H1 only, no volume condition on it; DOLLARIDX depth from 2017-12-01
is materially shorter than the 28 FX symbols (from 2015-01-01).
Sizing is NOT a gate in this round (brief §0/§2).

## Numbers block — incumbent vs best candidates

| Measure | Incumbent 89p (+89 contained) | D01 veto worst slot | D02 veto worst-2 slots | D07 V6 bb/rsi/vol veto |
|---|---|---|---|---|
| DISC leftover % | 70.81 | **81.42** | **87.08** | 75.99 |
| AUDIT leftover % | 46.65 | **51.27** | **49.23** | **59.36** |
| AUDIT net (pips @2.5) | +518.13 | +486.33 | +448.83 | +497.78 |
| Win % DISC / AUDIT | 95.76 / 90.91 | 96.74 / 93.00 | 97.88 / 92.63 | 96.75 / 93.18 |
| Entries/day DISC / AUDIT | 3.000 / 2.951 | 2.486 / 2.439 | 2.179 / 2.317 | **1.954** / 2.146 |
| LCT P / q05 (canonical) | — (identity) | **98.25 / 71.36** (strict PASS) | **100.00 / 75.46** (strict PASS) | 82.55 / 61.02 (middle PASS) |
| MC P(profit) | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| MC DD obs / p95 vs own cap | 143.60 / 208.83 vs 215.40 PASS | 102.50 / **166.37 vs 153.75 FAIL** (+12.62) | 102.50 / **170.32 vs 153.75 FAIL** (+16.57) | 102.50 / **176.63 vs 153.75 FAIL** |
| MC cluster obs / p95 vs cap | −143.60 / 144.10 vs 215.40 PASS | −102.50 / 102.50 vs 153.75 PASS | −102.50 / 102.50 vs 153.75 PASS | −102.50 / 102.50 vs 153.75 PASS |
| MC consec obs / p95 (cap obs+2) | 2 / 2 PASS | 1 / 2 PASS | 1 / 1 PASS | 1 / 2 PASS |
| MC verbatim middle flag | PASS | **FALSE (DD arm only)** | **FALSE (DD arm only)** | FALSE (DD arm) |
| PBO (family-21 canonical) | 0.00% | 0.00% | 0.00% | 0.00% |
| DSR (family-21 canonical) | 0.9944 (EC record 0.9999) | 0.9996 | 0.9997 | 0.9629 |
| Decay class | PASS | WEAKENED (not FAIL) | WEAKENED (not FAIL) | PASS |

D01/D02 are ledger-level vetoes — per the standing ruling, ledger-level
veto gains are **fall-through-suspect (flagged)**; they fail the MC gate
at ledger level already, so no app replay was run for them.

## Loss-cluster mechanism (explicit, before/after)

DISC census: only 22 DISC losses; the worst loss-cluster slot is
**FB_GBPUSD_h1_1** (89 DISC trades, 8 losses, DISC net +55.96), second
**FB_NZDUSD_h18_1** (53 trades, 6 losses, +105.41). The incumbent's
worst cluster −143.60 is a −102.50 full stop plus a −41.10 loss.
- D01 (veto FB_GBPUSD_h1_1) / D02 (veto both slots): worst cluster obs
  −143.60 → **−102.50**, max consec 2 → **1**, cluster p95 144.10 →
  **102.50** — the cluster and consec arms genuinely improve.
- BUT DD obs falls to 102.50, so under the governing mc9 own-relative
  ruling the DD cap falls to 153.75 while DD p95 only reaches
  166.37 / 170.32 — the remaining density of atomic −102.50 full-stop
  losses holds the p95 up (the same cap-trap seen in Jul attempt 3/4
  and Jan Plan C attempt 2). **MC-middle FAILS on the DD arm alone.**
- Stateful cluster controls did NOT fix it either: D08 cooldown-1
  (AUDIT leftover 40.99 < 46.65 FAIL), D09 symbol-block-48h (43.66
  FAIL), D10 consec-cool (AUDIT identical, DISC leftover 70.73 down,
  LCT 16.98 FAIL).

## All 20 cycles (DISC leftover / AUDIT leftover / AUDIT net / epd D/A)

Direct: D01 81.42/51.27/+486.33/2.486/2.439 · D02 87.08/49.23/+448.83/
2.179/2.317 · D03 veto worst symbol EURCHF 71.71/45.91/+503.13 — AUDIT
leftover FAIL, LCT 42.09 FAIL · D04 V3 rsi/macd/vol 67.69/60.00 — DISC
leftover down, epd 1.514 FAIL, LCT 34.75 FAIL · D05 V4 65.74/33.24 —
AUDIT + epd FAIL · D06 V5 mom+DOLLARIDX-leg+rsi 49.19/**−1.27,
AUDIT net −3.78** — unseen-losing, FAIL · D07 75.99/59.36 — epd +
MC DD FAIL (above) · D08 cool1 71.80/40.99 FAIL · D09 symblock48
70.23/43.66 FAIL · D10 consec-cool 70.73/46.65 tie, LCT FAIL.

Partners (incumbent-priority merge, `build_combined`): P01 PLANB c1,
P02 PLANB c2, P03 PLANB9 c1, P04 PLANB9 c2, P08 PLANB9C partner —
**accepted 0 picks** (all check_busy): combined is the incumbent,
saturated exactly like the contained cycle89. P05 PLANB9 partner
accepted 2 (AUDIT only): AUDIT leftover 47.38 > 46.65, net +533.13,
combined MC PASS (DD p95 209.23 vs cap 215.40) — but DISC is
trade-identical so paired LCT P = 0.00% FAIL; not promotable.
P07 PLANB9C c2 accepted 1 (AUDIT): leftover 47.59, net +539.11,
LCT 0.00% FAIL, same reason. P06 PLANB9C c1 accepted 1: AUDIT
leftover 41.55, Δ −5.10 — combine-safety FAIL.
**Partners that actually ADD picks:** P09 PLANB9SB c1 accepted 96 —
DISC leftover 80.17 but AUDIT leftover **36.24 (Δ −10.41)** vs the
−2.00 combine-safety tolerance (floor 44.65): FAIL. P10 PLANB2SB c1
accepted 80 — AUDIT leftover **14.55 (Δ −32.10)**, AUDIT net +187.28,
AUDIT stress @4.5 −78.72: FAIL. No partner both adds picks and
clears combine-safety.

## Gate-by-gate for the closest candidate (D01)

LCT-middle PASS (98.25/71.36, strict) · AUDIT leftover strictly >
incumbent PASS (51.27 > 46.65) · win >80% PASS · epd ≥2 PASS ·
AUDIT net >0 PASS (+486.33) · DSR ≥0.90 PASS (0.9996) · PBO ≤50%
PASS (0.00%) · decay not FAIL PASS (WEAKENED) · **MC all arms FAIL —
DD arm only (p95 166.37 vs own-relative cap 153.75)**. One locked
gate fails, so under §2 nothing is promoted. June already EC-passes
(EC record: MC PASS, PBO 40.00%, DSR 0.9999); cycle89p + contained
cycle89 stand unchanged. Research level only; no push, no live app.

Artifacts: `jun_planA_s1_run.json`, per-shortlist ledgers
`jun_planA_s1_<cycle>_ledger.csv` in this results dir; runner
`~/workspace/fx/work_20cyc_r2/run_jun_planA_s1.py`, log
`~/workspace/fx/work_20cyc_r2/jun_planA_s1.log`.

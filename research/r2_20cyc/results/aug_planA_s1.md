VERDICT: Aug planA s1 — NO IMPROVEMENT

# Aug Plan A Scenario 1 — 20-Cycle Round R2 (2026-10-30)

**NO IMPROVEMENT** — no candidate clears all locked §2 gates.
The best LCT reading of the whole slate is C02 at P 69.68%
(< 80% line); the only form that beats the incumbent's AUDIT
leftover (C06, 90.97% vs 86.94%) has LCT P 0.00%. August
already EC-PASSes on its carried record, and the incumbent
cycle67 + cycle67p stands unchanged. All figures at LEDGER
level (no fall-through); every veto form is
fall-through-suspect per the standing flag — moot here, since
none passes even at ledger level.

**12:30 IN-OFFICE flag (no fix spent, per task):** August's
five checks are 07:30 / **12:30 IN-OFFICE** / 22:30 / 23:30 /
00:30 MMT (entry hours 01:00 / 06:00 / 16:00 / 17:00 / 18:00
UTC). The 12:30 check is NOT in the brief's ordered
office-fix list (Nov/May/Dec/Sep only) — flagged here for the
parent; no cycles were spent on an office replacement.

**Scenario 2: NONE for August** — August already uses BOTH
added slots (07:30 and 00:30), so there is no free off-hours
slot; no slot was invented (brief §5, Wave-0 map).

DXY: BLOCKED-DATA (Twelve Data 429, Wave 0) — no DXY feature
claimed. The one dollar leg used (C05/C07) is
DOLLARIDX-labelled (Dukascopy H1, no volume condition, data
from 2017-12-01, materially shorter than the 2015-start FX
frame).

Incumbent read FRESH from the app registry this run
(`core/signal_mode.py`: Aug best = cycle67, second =
cycle67p). Combined ledger = work_new8/combined/
Aug_PLANB_combined.csv (766 = best 692 + P07 second-best 74
accepted), reproduced EXACTLY against the EC step record:
DISC n621 net +6307.06, AUDIT n145 net +1500.12, MC DD obs
102.50 → p95 **124.26** (the EC record's 124.26, bit-for-bit),
worst cluster −102.50 → p95 102.50, consec obs 1 → p95 1.
Leftover convention = validate_new8 seg_stats by-trade
verbatim (DISC 180 d / AUDIT 43 d).

## EC carried-vs-measured note (task requirement)

The incumbent's EC record is PASS on a CARRIED, PARTIAL
record (no full EC22 battery was ever run on this form).
This run RE-MEASURES, on the exact combined ledger:
leftover / net / win / epd (DISC+AUDIT), stress net@4.5,
paired LCT (new — not on the carried record), the full mc9
Monte Carlo battery (reproduces the carried DD p95 124.26
exactly), PBO/DSR on this run's stated family-21 (0.00% /
1.0000 for the incumbent's family position and every
shortlisted form — consistent with the carried PBO 0.00% /
DSR 1.0000), and decay class (PASS). NOT re-measured /
still CARRIED: the EC22 primary-12 items other than the
above (per-check batteries 1–12, 17–22 as a set), and the
÷3 sizing simulation (not a gate this round; Aug ÷3 was
never measured and remains unmeasured).

## Numbers block — incumbent 67+67p vs best candidates

| Metric | Incumbent 67+67p | C02 (veto worst-2 slots) | C06 (BB+RSI+vol+CLV veto) | C01 (veto worst slot) |
|---|---|---|---|---|
| DISC n / net | 621 / +6307.06 | 585 / +6222.78 | 411 / +4023.11 | 601 / +6261.52 |
| DISC leftover | 96.75% | **100.00%** (+3.25) | 95.01% (−1.74) | 98.45% (+1.70) |
| DISC win % / epd | 99.68 / 3.450 | 100.00 / 3.250 | 99.51 / 2.283 | 99.83 / 3.339 |
| AUDIT n / net | 145 / +1500.12 | 129 / +1349.86 | 103 / +1156.96 | 134 / +1396.53 |
| AUDIT leftover | 86.94% | 85.64% (**−1.30 ✗**) | **90.97%** (+4.03 ✓) | 86.07% (−0.87 ✗) |
| AUDIT win % / epd | 97.93 / 3.372 | 97.67 / 3.000 | 99.03 / 2.395 | 97.76 / 3.116 |
| AUDIT net@4.5 (stress) | +1210.12 | +1091.86 | +950.96 | +1128.53 |
| LCT P / q05 (DISC) | — | 69.68% / 100.00% **FAIL P<80** | 0.00% / 89.01% **FAIL** | 42.05% / 93.87% **FAIL** |
| MC P(profit) | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| MC DD obs → p95 vs own cap | 102.50 → 124.26 vs 153.75 PASS | 102.50 → 102.50 vs 153.75 PASS | 102.50 → 132.25 vs 153.75 PASS | 102.50 → 104.85 vs 153.75 PASS |
| MC cluster obs → p95 vs cap | −102.50 → 102.50 PASS | −102.50 → 102.50 PASS | −102.50 → 102.50 PASS | −102.50 → 102.50 PASS |
| MC consec obs → p95 | 1 → 1 PASS | 1 → 1 PASS | 1 → 1 PASS | 1 → 1 PASS |
| MC middle (verbatim flag) | PASS | PASS | PASS | PASS |
| PBO / DSR (family-21, this run) | 0.00% / 1.0000 (carried record) | 0.00% / 1.0000 | 0.00% / 0.9982 | 0.00% / 1.0000 |
| Decay | PASS | PASS | PASS | PASS |
| Red lines | — | PASS | PASS | PASS |

§2 gate check: **no candidate passes all gates.** Every
shortlisted form passes MC (all arms, own-relative caps),
PBO, DSR, decay, win >80%, epd ≥2 and AUDIT net >0 — the
binding failures are LCT-middle and AUDIT leftover:
- C02 removes BOTH DISC losses (DISC leftover 100.00%) but
  its AUDIT leftover 85.64% is below the incumbent's 86.94%
  (fails strictly-> AND the small-improvement rule — below,
  not a tie) and its paired LCT P is only 69.68%: in ~30% of
  paired resamples the incumbent also reaches ~100% DISC
  leftover, so the veto's edge is not resample-robust.
- C06 is the ONLY one of all 20 with AUDIT leftover above
  the incumbent (+4.03 pts) — but DISC leftover falls to
  95.01% and LCT P is 0.00% (its DISC resamples never beat
  the incumbent's). The AUDIT gain is a small-n AUDIT-side
  effect (103 trades), not a DISC-robust improvement.
- All partner merges (C11–C18) RAISE DISC leftover to
  96.95–97.40% but dilute AUDIT leftover to 64.56–83.95% —
  every one fails the AUDIT arm; the veto+partner combos
  C19/C20 are worse still on AUDIT (70.25 / 64.62).

## Loss-cluster mechanism — headline (before vs after)

Diagnosis (measured on the combined ledger): August has
essentially NO loss clustering to fix — the entire ledger
holds **2 DISC losses and 3 AUDIT losses in 766 trades**,
every one isolated (consec obs 1, worst cluster −102.50 =
one single full-stop trade). The two DISC losses sit in
slots D_EURAUD_h6_G031x (−102.50 net) and D_EURJPY_h6_G003x
(−88.18 net), one trade each.

Mechanisms tested and their MC cluster/DD arms (mc9_verbatim,
10,000 paths, seed 20261101; incumbent DD p95 124.26, cluster
p95 102.50, consec p95 1):
- **C02 slot veto (worst-2): DISC losses 2 → 0, DISC
  leftover 96.75 → 100.00%; DD p95 124.26 → 102.50** — but
  cluster obs is UNCHANGED at −102.50 (the remaining
  full-stop is an AUDIT trade in a different slot) and the
  AUDIT leftover cost (−1.30) + LCT P 69.68% kill it.
- C08 post-loss cooldown 1: drops only 5 trades in 766 —
  with consec already 1 there is nothing for a cooldown to
  interrupt; near-no-op (DISC 96.74, AUDIT 86.69, LCT 0.00).
- C09 symbol block 48h: drops 3; C10 stack limit 2: drops
  48, cluster/DD arms unchanged (−102.50 / DD p95 125.57).
  All stateful controls are structurally inert on a ledger
  whose losses never repeat back-to-back.

## All 20 cycles (DISC / AUDIT leftover; epd DISC/AUDIT)

Direct — slot vetoes + loss-cluster controls:
- C01 veto D_EURAUD_h6_G031x (worst DISC slot): dropped 31 · 98.45 / 86.07 · epd 3.339/3.116 · LCT 42.05/93.87 FAIL · MC PASS
- C02 veto worst-2 slots (+ D_EURJPY_h6_G003x): dropped 52 · 100.00 / 85.64 · epd 3.250/3.000 · LCT 69.68/100.00 FAIL · MC PASS — closest form (table above)
- C08 cooldown 1 pick after a loss: dropped 5 · 96.74 / 86.69 · LCT 0.00 FAIL · MC PASS
- C09 symbol block 48h after a loss: dropped 3 · 96.74 / 86.94 · LCT 0.00 FAIL · MC PASS
- C10 same-direction stack limit 2: dropped 48 · 96.51 / 86.56 · LCT 0.00 FAIL · MC PASS

Direct — H1 multi-indicator vetoes (3–4 ind × thr, volume, correlated legs):
- C03 RSI+MACD+vol_z: dropped 142 · 95.91 / 83.83 · epd 2.806/2.767 — both leftovers down
- C04 RSI+mom24+ATR band: dropped 186 · 95.57 / 77.91 · epd 2.661/2.349 — both down
- C05 mom24 + DOLLARIDX-labelled leg + RSI: dropped 217 · 95.37 / 79.90 · epd 2.506/2.279 — both down
- C06 BB+RSI+vol_z+H1 CLV: dropped 252 · 95.01 / **90.97** · epd 2.283/2.395 · LCT 0.00 FAIL · MC PASS — only AUDIT-beating form (table above)
- C07 mom24 + EURUSD leg + DOLLARIDX leg + vol_z: dropped 193 · 95.56 / 81.57 — both down

Partners (prior Aug mined designs, incumbent-priority merge;
accepted / DISC / AUDIT leftover):
- C11 PLANB9 cand1: acc 132 · 97.23 / 70.18 — AUDIT FAIL
- C12 PLANB9 cand2: acc 93 · 97.08 / 78.60 — AUDIT FAIL
- C13 PLANB9C cand1: acc 165 · 97.29 / 76.79 — AUDIT FAIL
- C14 PLANB9C cand2: acc 175 · 97.40 / 71.66 — AUDIT FAIL
- C15 ROUND3 cand1: acc 72 · 97.06 / 73.59 — AUDIT FAIL
- C16 ROUND3 cand2: acc 85 · 84.88 / 64.56 — both FAIL
- C17 ROUND4 cand1: acc 58 · 97.15 / 78.80 — AUDIT FAIL
- C18 ROUND4 cand2: acc 26 · 96.95 / 83.95 — AUDIT FAIL (closest partner)

Combinations:
- C19 = C01 veto + PLANB9C cand1 partner (178 accepted): 98.73 / 70.25 — AUDIT FAIL
- C20 = C02 veto + PLANB9 cand1 partner (145 accepted): 100.00 / 64.62 — AUDIT FAIL

(PLANB cand1 is the incumbent's own second layer, already
merged into the 766; PLANB cand2 was NOT ADDABLE in its own
verdict at epd 0.33 — neither was re-run as a partner.)

Pattern, stated plainly: August's incumbent is a near-lossless
ledger (5 losses in 766 trades) whose DISC leftover is already
96.75%. There is no loss cluster to repair and no headroom
the locked gates can certify: vetoes that perfect DISC
leftover cost AUDIT leftover and fail the paired LCT, the one
AUDIT-beating veto fails LCT outright, and every partner
dilutes AUDIT. Nothing meets the locked bar; the incumbent —
already EC-PASS on its carried record — stands.

## Honest trial count / PBO-DSR note

Slate pre-registered in `run_aug_planA_s1.py` before measuring
(20 cycles + incumbent = 21 trials). PBO/DSR above are
validate_new8 round basis on that family (PBO 0.00% for every
shortlisted form; DSR 0.9982–1.0000). Named gaps: (1) all
results are ledger-level — no fall-through app replay was run
because no candidate passed the ledger-level gates (the Feb
C08 replay would only be needed for a passing form), and all
veto forms are fall-through-suspect per the standing flag;
(2) this Plan A run is H1-primary throughout (engine H1
features); M15 veto variants were NOT run — M15-heavy work is
Plan C's brief, not Plan A's; (3) the full EC22 battery was
not re-run on the incumbent (see carried-vs-measured note).

Files: run data `results/aug_planA_s1_run.json`; per-cycle
ledgers `results/aug_planA_s1_C01..C20_ledger.csv`,
`results/aug_planA_s1_INC_ledger.csv`; script
`run_aug_planA_s1.py`, log `aug_planA_s1.log`.

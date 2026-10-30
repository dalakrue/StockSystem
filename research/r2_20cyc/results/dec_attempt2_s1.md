VERDICT: Dec attempt2 s1 — IMPROVED-at-simulated-replay (winner D19 = Wave-3b PC03 M15 veto + PLANB12C cand1 partner merged second-priority, graded on its SIMULATED ledger with candidate-layer refill counted: DISC leftover 78.43→80.93%, AUDIT leftover 53.02→57.65% strictly greater, LCT 95.21%/75.89%, MC verbatim flag PASS, PBO 0.00% / DSR 1.0000 canonical — ALL §2 gates pass on the simulated battery; D03, the same veto without the partner, also passes all gates simulated; simulated-replay is the highest verification level available for Dec — no true app-code driver exists; incumbent cycle94c+94s stands until a separate integration decision)

# Dec ATTEMPT 2 Scenario 1 — vetoes screened WITH simulated fall-through (2026-10-30, Wave 4e)

Lesson applied: every ledger-level veto winner of Round R2 so far
(Feb C08, Dec C07, Mar PC14, Mar PC08) failed once refills were
counted. This attempt therefore grades EVERY candidate on its
SIMULATED ledger from the start: veto applied, then refill under
`core.new8_walk.build_combined` occupancy verbatim (a stored
candidate-walk row is accepted only if its check carries no pick
in the current stream and its symbol does not time-overlap the
stream or an earlier refill), Dec order dec_rg walk first, then
dec_rgc walk — the exact machinery of `run_wave4a_verify.py`,
reused in `run_wave4e_attempt2.py`. Partner forms then refill
second-priority from the named partner walk's rows not already
in the incumbent. Research level only — no app push, no GitHub
push, no cron switch, no Streamlit, no Twelve Data calls.

## Machinery note — level of this verdict (read first)

**Simulated-replay is the highest verification level available
for December, and this verdict is stated at that level only.**
There is NO true app-code replay for the full 94c+94s combined
on disk (Wave 4a machinery note stands: `harness4.py` replays
only the dec_rg/dec_rgc candidate layers onto the research
ledger; the base FB stream is never regenerated check-by-check).
What remains UNMODELLED, named not hidden: (1) base-stream
next-signal fall-through at vetoed checks where other base picks
remain (no signal pool for the 94b stream exists on disk);
(2) base-stream open-position cascades (a vetoed position no
longer blocks later same-symbol base signals); (3) the
candidate walks' internal state if re-run against the vetoed
stream instead of reusing their stored walks; (4) the PC03
veto's feature status OF THE REFILL ROWS — the Dec features
file covers exactly the 954 incumbent rows, so refills are
accepted here without a PC03 feature check (in a true app form
the veto might also screen candidate-layer picks; the direction
of that correction is unknowable from disk data and is NOT
assumed). Point (4) matters concretely for the winner: D03's
ledger-level canonical LCT was P 74.17% (FAIL, Wave-3b), while
its simulated LCT is 89.64% — the refill picks move the paired
bootstrap. The simulated grade is the honest bound available,
not an app replay.

## Controls — validated before any candidate was trusted

- CONTROL on the incumbent 954 ledger: DISC 771 / +8814.06 /
  78.43%, AUDIT 183 / +1090.28 / 53.02%, MC DD p95 309.60 —
  EXACT vs the EC step record, `dec_planC_s1.md` and Wave 4a.
  CONTROL_OK = True.
- CANDIDATE CONTROL: D01 (the C07 slot veto re-graded simulated
  inside this screen) reproduces Wave 4a's simulated C07
  EXACTLY — 916 picks, AUDIT leftover 47.60%, DISC 87.82%.
  The screen's machinery is the verified Wave-4a machinery.
Machine record: `results/wave4e_attempt2_run.json`; simulated
ledgers of all battery finalists: `results/dec_attempt2_D*_sim_ledger.csv`.

## Numbers block — incumbent vs winner D19 vs co-passing D03 / D20 (simulated)

| Metric | Incumbent 94c+94s | D19 PC03 veto + PLANB12C partner (SIM) | D03 PC03 veto alone (SIM) | D20 partner alone (SIM) |
|---|---|---|---|---|
| Total picks | 954 | 908 (840 kept + 50 refills + 18 partner) | 890 (840 + 50 refills) | 962 (954 + 0 refills + 8 partner) |
| DISC n / net | 771 / +8814.06 | 730 / +8124.85 | 713 / +7926.88 | 778 / +8894.21 |
| DISC leftover | 78.43% | **80.93%** (+2.50) | **80.54%** (+2.11) | 78.59% (+0.16) |
| DISC win % / epd | 95.72% / 4.406 | 96.16% / 4.171 | 96.07% / 4.074 | 95.76% / 4.446 |
| AUDIT n / net | 183 / +1090.28 | 178 / **+1161.63** | 177 / **+1149.09** | 184 / +1102.82 |
| AUDIT leftover | 53.02% | **57.65%** (**+4.63 ✓ strictly >**) | **57.38%** (+4.36 ✓) | 53.30% (+0.28 ✓) |
| AUDIT win % / epd | 92.90% / 4.067 | 93.26% / 3.956 | 93.22% / 3.933 | 92.93% / 4.089 |
| LCT P / q05 (DISC) | — (reference) | **95.21% / 75.89%** PASS (middle + strict) | **89.64% / 75.30%** PASS middle | 100.00% / 72.61% PASS |
| MC P(profit) | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| MC DD obs → p95 vs own cap | 252.24 → 309.60 vs 378.36 PASS | 179.74 → **239.00 vs 269.61 PASS** | 179.74 → 240.57 vs 269.61 PASS | 252.24 → 309.43 vs 378.36 PASS |
| MC cluster obs → p95 vs cap | −120.09 → 158.1 vs 180.14 PASS | −120.09 → **139.91 vs 180.14 PASS** | −120.09 → 141.30 vs 180.14 PASS | −120.09 → 158.10 vs 180.14 PASS |
| MC consec obs → p95 | 2 → 2 PASS | 2 → 2 PASS | 2 → 2 PASS | 2 → 2 PASS |
| MC middle (verbatim flag) | PASS | **PASS** (all arms) | **PASS** | **PASS** |
| PBO / DSR (canonical, attempt-2 family-21) | 40.00% / 1.0000 (EC record) | **0.00% / 1.0000** | **0.00% / 1.0000** | **0.00% / 1.0000** |
| Decay | WEAKENED | WEAKENED (leftover fall >20) — not FAIL ✓ | WEAKENED — not FAIL ✓ | WEAKENED — not FAIL ✓ |
| Red lines | — | PASS (AUDIT net +1161.63 > 0, no discovery collapse) | PASS | PASS |

§2 gate check for simulated D19: LCT-middle ✓ (95.21 / 75.89)
· AUDIT leftover strictly > incumbent ✓ (+4.63 — the target of
this attempt; C07 simulated managed only 47.60) · DISC leftover
✓ · MC middle PASS all arms ✓ · PBO ≤ 50 ✓ · DSR ≥ 0.90 ✓ ·
decay not FAIL ✓ · win > 80% both segments ✓ · epd ≥ 2 both
segments ✓ · AUDIT net positive and ABOVE incumbent ✓
(+1161.63 vs +1090.28 — unlike C07, the winner does not pay for
its leftover gain with unseen net). **All §2 gates pass on the
simulated battery → IMPROVED-at-simulated-replay.**

Why D19 over D03: D19 dominates D03 on AUDIT leftover (57.65 vs
57.38), AUDIT net, DISC leftover and LCT (95.21/75.89 vs
89.64/75.30); the partner's 18 second-priority picks are worth
DISC +197.97 / AUDIT +12.54 after refill. D03 stands as the
simpler co-passing alternate (veto only). D20 (the lane's C19
partner-only form, simulated unchanged — a partner-only form
frees no checks, so refill is 0 by construction) also passes
every gate, but its AUDIT margin is +0.28 only; it is recorded,
not selected.

Disclosed second reading (same basis split seen all round):
the R2-engine CSCV PBO on the attempt-2 family reads 98.02%
for every Dec finalist; the canonical validate_new8 basis
(0.00%) governs per the settled ruling, CSCV is disclosed, not
hidden. Family-21 DSR on the planA-engine basis: D19 0.9996.

## What fall-through did this time — and why the PC03 family survives it

The C07 pattern inverted. PC03's vetoed picks are spread across
checks and slots (114 dropped), and the candidate layers' refill
rows at the freed checks are net POSITIVE on both segments for
this veto (rg 34 picks: DISC +303.01 / AUDIT +39.04; rgc 16:
DISC +177.38 / AUDIT +33.23) — the opposite sign from C07, whose
47 sole-pick freed checks refilled AUDIT −100.09. By contrast
every EURJPY-slot form refills AUDIT-negative through the rg
layer (D01 rg AUDIT −131.63) AND removes AUDIT-positive slot
picks: the slot veto family is doubly hurt simulated.

## Full pre-registered screen — all 20 candidates, simulated grade

| ID | Form | Kept | DISC left / net / epd | AUDIT left / net / epd | Refills (n, AUDIT net) | Screen |
|---|---|---|---|---|---|---|
| D01 | slot veto EURJPY_h11 (=C07) | 883 | 87.82 / +9648.23 / 4.257 | 47.60 / +944.80 / 3.800 | 33, −100.09 | AUDIT ✗ (Wave-4a result reproduced) |
| D02 | PC01_mom16_vol veto | 869 | 79.67 / +7977.65 / 4.171 | 62.58 / +1232.34 / 3.956 | 39, +65.94 | battery: LCT P 70.77 ✗ only |
| D03 | PC03_mom4_mom96_vol veto | 840 | 80.54 / +7926.88 / 4.074 | 57.38 / +1149.09 / 3.933 | 50, +72.27 | **ALL GATES PASS** |
| D04 | PC16_strict_all veto | 233 | 95.22 / +4775.04 / 2.349 | 27.61 / +301.56 / 2.422 | 287, −80.34 | AUDIT ✗ (veto frees 721 picks; refill flood) |
| D05 | lane C03 CLV/RSI veto | 658 | 80.66 / +6922.92 / 3.606 | 44.83 / +754.45 / 3.467 | 129, −197.27 | AUDIT ✗ |
| D06 | lane C08 vol-spike veto | 835 | 77.80 / +7712.70 / 4.023 | 58.15 / +1042.19 / 3.756 | 38, +56.26 | battery: LCT P 39.85 ✗ only |
| D07 | slot veto EURUSD_h10 | 858 | 82.81 / +8954.29 / 4.091 | 48.78 / +975.79 / 3.867 | 32, −10.59 | AUDIT ✗ |
| D08 | slot veto EURCHF_h13 | 873 | 80.72 / +8946.25 / 4.183 | 51.48 / +1025.90 / 3.844 | 32, +13.92 | AUDIT ✗ |
| D09 | slot veto EURJPY+EURUSD | 787 | 92.75 / +9788.47 / 3.943 | 42.38 / +809.15 / 3.556 | 63, −131.83 | AUDIT ✗ |
| D10 | slot veto EURJPY+EURCHF | 802 | 90.36 / +9780.42 / 4.034 | 45.80 / +880.42 / 3.578 | 65, −86.17 | AUDIT ✗ |
| D11 | slot veto all three FB slots | 706 | 95.55 / +9946.22 / 3.737 | 39.50 / +740.37 / 3.400 | 101, −122.31 | AUDIT ✗ |
| D12 | slot veto EURUSD+EURCHF | 777 | 85.35 / +9112.04 / 3.711 | 46.19 / +907.01 / 3.711 | 70, −1.07 | AUDIT ✗ |
| D13 | PC01 + EURJPY slot | 805 | 88.32 / +8649.46 / 4.034 | 52.11 / +1004.74 / 3.756 | 70, −34.16 | AUDIT ✗ (−0.91) |
| D14 | PC03 + EURJPY slot | 779 | 88.18 / +8497.32 / 3.943 | 52.29 / +1016.50 / 3.689 | 77, −42.82 | AUDIT ✗ (−0.73) |
| D15 | PC16 + EURJPY slot | 220 | 97.48 / +4840.24 / 2.320 | 26.06 / +279.06 / 2.356 | 292, −80.34 | AUDIT ✗ |
| D16 | D01 + PLANB12C partner | 883 | 87.94 / +9747.57 / 4.309 | 47.93 / +957.34 / 3.822 | 33 + 10 partner, −87.55 | AUDIT ✗ (partner cannot rescue C07) |
| D17 | D02 + PLANB12C partner (rule form: best simulated pure veto = D02) | 869 | 79.96 / +8124.63 / 4.229 | 62.82 / +1244.88 / 3.978 | 39 + 11 partner, +78.48 | battery: LCT P 73.75 ✗ only — highest AUDIT leftover of the slate, closest failing candidate |
| D18 | D01 + PREGIMESB partner | 883 | 88.65 / +10506.56 / 4.491 | 41.76 / +950.24 / 4.178 | 33 + 58 partner, −94.71 | AUDIT ✗ (SB partner is DISC-rich, AUDIT-poor) |
| D19 | PC03 + PLANB12C partner | 840 | 80.93 / +8124.85 / 4.171 | **57.65 / +1161.63 / 3.956** | 50 + 18 partner, +84.81 | **WINNER — ALL GATES PASS** |
| D20 | PLANB12C partner alone (lane C19 form) | 954 | 78.59 / +8894.21 / 4.446 | 53.30 / +1102.82 / 4.089 | 0 + 8 partner, +12.54 | ALL GATES PASS (margin +0.28 only; not selected) |

Battery detail for the other finalists: D02 — MC PASS (DD p95
197.50 vs own cap 198.84… own cap = 1.5×132.56 = 198.84, PASS),
PBO 0.00 / DSR 1.0000, decay PASS, fails LCT-middle alone
(P 70.77 < 80; q05 72.02 ✓). D17 — same shape: MC PASS (DD p95
197.50), PBO/DSR PASS, decay PASS, LCT P 73.75 ✗ alone. D06 —
MC PASS (DD p95 304.23 vs cap 377.90), PBO/DSR PASS, decay
PASS, LCT P 39.85 ✗ alone. So the slate's near-misses all fail
exactly one gate (LCT P), and the three passers clear it
comfortably (89.64 / 95.21 / 100.00).

## Loss-cluster mechanism (before vs after, winner D19)

PC03's arms (aligned M15 mom4 > −0.15 & aligned M15 mom96 >
−0.8 & M15 vol_z > −1.0, features at the signal candle) cut
the weak-momentum entries in which December's loss pairs form,
and — unlike the slot veto — do not concentrate the freed
checks on one slot's refill pool. MC (mc9_verbatim, 10,000
paths, seed 20261101): DD obs 252.24 → 179.74, DD p95 309.60 →
239.00; worst cluster obs unchanged −120.09 (the dominating
pair survives the veto — named, not hidden), cluster p95
158.1 → 139.91; consec 2 → 2; P(profit) 1.0000 → 1.0000.

## Files

- Runner: `run_wave4e_attempt2.py` (slates pre-registered in
  its docstring before any attempt-2 measurement)
- Machine record: `results/wave4e_attempt2_run.json`
- Simulated ledgers: `results/dec_attempt2_D02/D03/D06/D17/D19/D20_sim_ledger.csv`
- Gaps named: no app-code replay for Dec (machinery note);
  refill rows' PC03 feature status unmodelled (note point 4);
  historical mega-family DSR not re-graded (standing gap —
  canonical attempt-2 family-21 basis governs, as in the lanes).

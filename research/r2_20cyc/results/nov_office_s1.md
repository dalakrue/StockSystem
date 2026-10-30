VERDICT: Nov office s1 — NO IMPROVEMENT (office replacement NONE — all 40 created replacement forms grade DOWNGRADE under the locked §2 check-time rule; November keeps its 15:30 MMT IN-OFFICE check)

# Nov Office-Hour Replacement — 20-Cycle Round R2, Wave 4g (2026-10-30)

User order: replace November's 15:30 MMT check (IN-OFFICE) with a
non-office check that grades ACCEPTABLE or IMPROVE, and improve Nov
overall as much as possible. The Plan A improvement half of the
order is in `nov_planA_s1.md` (IMPROVED at ledger level, C02 slot
veto — verified against its run JSON this wave). This file is the
office half, at full creation depth: **20 created cycles at EACH
of 07:30 and 00:30 MMT** (the order asked for 10 per slot; the
pre-registered S01–S20 slate was run at both), each graded as a
REPLACEMENT form on the full §2 class rule, with the full battery
on each slot's DISC-selected cycle. Result: **NONE — every one of
the 40 replacement forms grades DOWNGRADE.** This confirms and
deepens the Plan A file's 4-variant office result; it is a
creation result under the no-lookahead standard, not a replay.

Incumbent read FRESH from the registry (Wave 0 map, re-confirmed):
Nov best = cycle93r, second = cycle93s; best checks 15:30
IN-OFFICE / 19:30 / 21:30 MMT, second adds 16:30 IN-OFFICE.
Ledger = the exact 826-pick combined (Nov_PREPLACE_combined.csv),
reproduced EXACTLY this run: DISC n676 net +9010.79, leftover
77.05%, win 94.08%, epd 3.885 (174 d); AUDIT n150 net +982.60,
leftover 43.44%, win 88.00%, epd 3.659 (41 d); MC DD obs 183.81 →
p95 251.99 (own cap 275.72), cluster −183.81 → p95 183.81, flag
TRUE; decay WEAKENED (the incumbent's own class).

Method (locked before mining): replacement form = incumbent
MINUS the 15:30 picks (entry 09:00 UTC; 223 DISC + 48 AUDIT picks)
PLUS the created slot cycle, second-priority merge (slot pick
dropped if the base holds the same symbol open at slot entry).
Created cycles are hour-native equations (S01–S20: mom4/mom16/
mom24 direction × H1 RSI/BB/MACD/EMA/ATR/volume bands × M15 mom/
RSI/BB/volume confirmation, DOLLARIDX-labelled leg in S08/S20 —
Dukascopy H1 mom only, NO volume condition; EURUSD correlated leg
in S09; loss-cluster controls S16 post-loss symbol cooldown and
S17 post-loss global skip-1; exits TP10–30 / SL60–100, hold ≤48
H1 bars, SL-first, spread 2.5, ONE pick per check = strongest
|direction momentum| across all 28 symbols). NO-LOOKAHEAD
standard: H1 features from completed bars only (shift 1), M15
features from the last M15 bar completed before entry, entry at
the entry-bar open — the standard whose absence invalidated Sep's
S1 18:30 baseline. Selection per slot is DISC-only (among cycles
with standalone DISC net > 0, maximise replacement-form DISC
leftover); AUDIT is grading-only. Class rule (BRIEF §2, locked):
IMPROVE = AUDIT leftover up AND DISC leftover not down;
DOWNGRADE = AUDIT leftover down > 0.5 pt OR AUDIT win < 80% OR
AUDIT net down worse than −max(25, 10% of +982.60) = −98.26;
ACCEPTABLE = else. Precedence: any DOWNGRADE arm triggered ⇒
DOWNGRADE (the round's own reading; a follow-up re-grade of all
40 forms under this precedence changed NO Nov grade). DXY:
BLOCKED-DATA (Wave 0, Twelve Data 429) — no DXY feature claimed.
LEDGER LEVEL (no fall-through) — moot for adoption here, since
nothing is adoptable. Sizing not a gate (BRIEF §0).

## Numbers block — incumbent vs DISC-selected replacement forms

| Metric | Incumbent 93r+93s | REP15 + S12 @ 07:30 | REP15 + S05 @ 00:30 |
|---|---|---|---|
| DISC n / net | 676 / +9010.79 | 646 / +6496.64 | 649 / +8111.24 |
| DISC leftover | 77.05% | 60.54% (−16.51) | 64.80% (−12.25) |
| DISC win % / epd | 94.08 / 3.885 | 91.02 / 3.713 | 90.76 / 3.730 |
| AUDIT n / net | 150 / +982.60 | 141 / +748.37 (−234.23) | 143 / +518.87 (−463.73) |
| AUDIT leftover | 43.44% | 35.88% (−7.56) | 20.57% (−22.87) |
| AUDIT win % / epd | 88.00 / 3.659 | 87.23 / 3.439 | 83.22 / 3.488 |
| Class grade | — | **DOWNGRADE** | **DOWNGRADE** |
| LCT P / q05 (paired vs incumbent DISC) | — | 0.55% / 49.35% — FAIL | 2.75% / 45.67% — FAIL |
| MC P(profit) | 1.0000 | 1.0000 | 1.0000 |
| MC DD obs → p95 vs own cap | 183.81 → 251.99 vs 275.72 | 230.00 → 318.29 vs 345.00 | 333.35 → 457.56 vs 500.03 |
| MC cluster obs → p95 vs own cap | −183.81 → 183.81 vs 275.72 | −165.00 → 199.70 vs 247.50 | −205.00 → 245.80 vs 307.50 |
| MC consec obs → p95 | 2 → 3 | 2 → 3 | 3 → 3 |
| MC middle flag (mc9 verbatim) | TRUE | TRUE | TRUE |
| PBO (round, family-21) / CSCV (family-20, disclosed 2nd) | 10.00% (EC record) | 0.00% / 40.87% | 5.00% / **73.81%** |
| DSR | 1.0000 (EC record) | 1.0000 | 1.0000 |
| Decay | WEAKENED | WEAKENED (not FAIL) | WEAKENED (not FAIL) |

The MC flags on the REP forms pass
only because the own-relative caps rise with the forms' own
larger observed DD (230.00 / 333.35 vs incumbent 183.81) — the
tails are WORSE in absolute terms, and the class rule + LCT
already fail both forms. Standalone slot cycles: S12 @ 07:30 —
DISC leftover −40.08%, total net −558.6, MC P(profit) 0.0471,
flag FALSE (the 07:30 hour has NO discovery edge in November:
all 20 standalone DISC leftovers are negative, −12.98…−50.71%).
S05 @ 00:30 — DISC leftover +32.29% but AUDIT leftover −24.19%
(AUDIT net −182.0): the DISC→AUDIT flip again; standalone MC flag
FALSE (DD p95 783.23 vs own cap 781.05).

## All 40 replacement forms (class grades)

07:30 MMT (entry 01:00 UTC) — REP AUDIT leftover / DISC leftover:
S01 30.18/49.80 · S02 38.07/54.23 (best AUDIT of the slot, still
−5.37) · S03 27.14/49.43 · S04 31.01/47.00 · S05 34.62/45.11 ·
S06 22.65/47.16 · S07 28.98/43.17 · S08 30.41/50.57 · S09
30.18/49.17 · S10 37.89/43.48 · S11 24.79/49.75 · S12 35.88/60.54
(DISC-selected) · S13 23.73/59.00 · S14 20.74/43.85 · S15
24.51/49.41 · S16 26.95/52.03 (cluster ctrl) · S17 33.56/52.81
(cluster ctrl) · S18 31.37/51.75 · S19 35.19/44.37 · S20
28.34/47.86 — **20/20 DOWNGRADE.**

00:30 MMT (entry 18:00 UTC) — REP AUDIT leftover / DISC leftover:
S01 19.70/56.12 · S02 20.80/58.05 · S03 21.48/56.69 · S04
15.42/57.17 · S05 20.57/64.80 (DISC-selected) · S06 27.63/55.36
(best AUDIT of the slot, −15.81) · S07 16.04/42.14 (AUDIT win
78.57% also < 80) · S08 20.25/56.12 · S09 19.70/58.32 · S10
3.86/52.90 · S11 22.68/59.65 · S12 31.04/63.90 · S13 30.94/63.99 ·
S14 14.76/50.39 · S15 −6.02/51.57 (AUDIT net −153.03, win
75.00% — unseen-losing form) · S16 21.18/59.95 · S17 24.94/59.33 ·
S18 15.84/52.82 · S19 6.96/50.41 · S20 19.70/53.58 —
**20/20 DOWNGRADE.**

Reference forms: DROP 15:30 only = DOWNGRADE (AUDIT leftover
40.77, −2.67; AUDIT net +735.87, −246.73; its own MC flag also
FALSE, DD p95 231.36 vs own cap 203.74 — dropping the check does
not even preserve MC). REPBOTH (drop BOTH office checks 15:30 +
16:30, add the selected cycle): @07:30 S12 — DISC 56.00, AUDIT
31.44, net +574.68, DOWNGRADE; @00:30 S05 — DISC 60.69, AUDIT
15.22, net +345.18, DOWNGRADE. REP15 on the Plan A winner C02
ledger (secondary base): @07:30 — AUDIT leftover 33.86 vs C02's
44.03, DOWNGRADE (MC flag also FALSE); @00:30 — AUDIT 15.59,
DOWNGRADE. The loss-cluster controls inside the slate (S16/S17)
do not rescue either slot (REP AUDIT 26.95/33.56 @07:30,
21.18/24.94 @00:30 — all DOWNGRADE).

## Verdict reasoning

The 15:30 check carries flow that no created equation at 07:30
or 00:30 reproduces: at 07:30 the hour itself is discovery-dead
(every standalone DISC leftover negative); at 00:30 several
equations look alive on DISC (up to +32.29%) and every one of
the 20 flips unseen (standalone AUDIT leftovers −18.33…−115.80%,
all negative). Diluting the incumbent with either hour costs 5.4–22.9
AUDIT leftover points. Per the task's rule (both slots DOWNGRADE
⇒ NONE, as for Dec/May), **the office verdict is NONE: November
keeps 15:30 (best) and 16:30 (second) IN-OFFICE.** Nothing in
this file is adopted or promoted; incumbent 93r+93s stands, and
the Plan A C02 improvement candidate is unaffected by this
result (it keeps the 15:30 check). Research level only — no
push, no cron change, no Streamlit, no Twelve Data calls.
Ledgers: results/wave4g_nov_h{1,18}_*_slot_ledger.csv,
wave4g_nov_h{1,18}_REP_ledger.csv; full run JSON:
results/wave4g_office_run.json (script run_wave4g_office.py).
One process note: the first launch of this run was OOM-killed
under tonight's multi-lane memory saturation; the surviving
instance completed all 60 Nov+Sep forms deterministically and
both incumbents reproduced exactly before any grading.

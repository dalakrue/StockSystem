VERDICT: Feb planA s1 — IMPROVED (attempt 2, REPLAY level: A16 = C08 slot veto replayed WITH fall-through + PLANB cand2 partner merged against the replayed base — ALL §2 gates pass at replay: DISC leftover 76.90→82.62%, AUDIT leftover 37.28→41.21% strictly greater, LCT 96.40%/71.83%, MC verbatim flag TRUE with DD p95 171.39, PBO 0.00% / DSR 1.0000 on the stated 21-series family; A17 also passes all gates and is the runner-up)

# Feb Plan A ATTEMPT 2 — screened THROUGH the app-replay driver (2026-10-30, Wave 3a)

Attempt 1's C08 was IMPROVED at ledger level and REJECTED at app
replay (`feb_verify.md`: AUDIT leftover 36.80 < 37.28, LCT P
78.14 < 80) because fall-through cascades the walk state. This
attempt therefore screens every candidate THROUGH the validated
replay driver itself (`run_feb_verify.py` harness:
`core.cycle85b_best` evaluate + select over the BRIEF22-era
frames/pool, veto applied BEFORE select so the app's own
selection falls through). **Control first: the NONE walk
reproduces the recorded app ledger `feb22_c19_app.csv` keys
EXACTLY (CONTROL_KEYS_EQUAL = True) and its battery reproduces
the step test byte-for-byte; missing_pool = 0 for every
variant.** Nothing in this file is a ledger-level figure.

Slate: 20 candidates pre-registered in `run_feb_planA2_s1.py`
BEFORE any A-candidate was measured; all leg choices are
DISC-only (DISC leftover by leg: FB_EURUSD_h16_1 34.99%,
mom_NZDCAD_h16 41.02%, mom_NZDCAD_h11 42.47%,
mom_NZDUSD_h13 49.53%, FB_EURUSD_h11_0 54.96%,
mom_GBPUSD_h11 67.68%; DISC cluster contributions −410.90 /
−313.03 / −76.39 / −56.20 / −48.50 / −32.20 in the same order).
AUDIT was grading-only. Battery (replay ledgers only): Feb
Plan A stats (DISC 160 d / AUDIT 41 d), mc9_verbatim (10,000
paths, flag = verbatim mc_middle_pass), validate_new8 LCT
(DISC vs NONE replay), PBO/DSR on the stated family = 21 daily
DISC series {NONE replay + A01..A20}, decay (FAIL only if
AUDIT net ≤ 0; WEAKENED triggers as in the programme battery —
the incumbent itself is WEAKENED on the same triggers: AUDIT
exp 4.32 vs DISC 11.15, leftover fall 39.62 pts, so WEAKENED
is the incumbent's own class, not a candidate downgrade).
Research level only — no app push, no GitHub push, crons
untouched. Sizing not a gate (brief §0).

## WINNER — A16 = A01 (C08 veto at replay) + PLANB cand2 partner

Composition: (1) slot veto of FB_EURUSD_h16_1 at replay WITH
fall-through (the A01 walk = feb_verify's C08 walk, reproduced
exactly: 435 picks, DISC 80.37%, AUDIT 36.80%); (2) partner
merge of the prior mined design `MONTH_Feb_PLANB_cand2_ledger.csv`
(the Plan A C12 partner) against the REPLAYED A01 base under
second-priority semantics (partner pick accepted only at a
check the base does not take, no symbol-interval overlap):
115 partner rows → **45 accepted**, drops {check_busy 62,
symbol_overlap 0}, 8 DOLLARIDX rows excluded and counted
(Dukascopy-labelled held layer, as in Plan A). The base is
app-replayed; the partner ledger is a prior mined design
ledger merged at replay level — it is not itself app-replayed
(stated, same disclosure class as Plan A's partners).

| Metric | Incumbent 85b (NONE replay) | A16 |
|---|---|---|
| Total picks | 490 | 480 (435 base + 45 partner) |
| DISC n / net | 385 / +4293.42 | 375 / **+4903.75** |
| DISC leftover | 76.90% | **82.62%** (+5.72 ✓) |
| DISC win % / epd | 96.36% / 2.406 | 97.07% / 2.344 |
| AUDIT n / net | 105 / +453.92 | 105 / **+510.96** |
| AUDIT leftover | 37.28% | **41.21%** (**+3.93, strictly > ✓**) |
| AUDIT win % / epd | 86.67% / 2.561 | 87.62% / 2.561 |
| LCT P / q05 (DISC) | — | **96.40% / 71.83%** — middle PASS, strict PASS |
| MC P(profit) | 1.0000 | 1.0000 |
| MC DD obs → p95 vs own cap | 146.32 → 228.72 vs 219.48 FAIL | 126.37 → **171.39 vs 189.56 PASS** |
| MC cluster obs → p95 vs cap | −104.50 → 143.30 vs 156.75 PASS | −102.50 → **108.59 vs 156.75 PASS** |
| MC consec obs → p95 | 2 → 2 PASS | 2 → 2 PASS |
| MC middle (verbatim flag) | FALSE (DD arm) | **TRUE — all arms** |
| PBO / DSR (stated family of 21) | — / 0.1819 (historical record) | **0.00% / 1.0000** |
| Decay | WEAKENED (incumbent's own triggers) | WEAKENED — not FAIL; yearly leftover positive every year 2016–2025 (94.5 … 88.1 DISC; 41.5 / 40.9 AUDIT) |
| Red lines | — | PASS (AUDIT net +510.96 > 0, DISC leftover up — no collapse) |

§2 gate check for A16 — ALL PASS at replay: LCT-middle ✓ ·
AUDIT leftover strictly > incumbent ✓ (the strict form, the
small-improvement rule is not needed) · win > 80% ✓ ·
epd ≥ 2 ✓ · AUDIT net > 0 ✓ · MC verbatim flag TRUE ✓ ·
PBO ≤ 50% ✓ · DSR ≥ 0.90 ✓ · decay not FAIL ✓ · red lines ✓.

**Why A16 fixes what C08-replay broke:** the veto alone loses
AUDIT edge to fall-through replacements (AUDIT net 415.69 <
453.92). The cand2 partner's 45 accepted picks land exactly at
base-silent checks and are AUDIT-positive in aggregate: they
restore AUDIT net to +510.96 (above the incumbent) and lift
AUDIT leftover by +4.41 pts over the A01 base, while DISC
leftover rises further (80.37 → 82.62) and the MC DD fix the
veto bought is kept and deepened (DD p95 187.00 → 171.39,
cluster p95 122.50 → 108.59). The same partner against the
UNVETOED incumbent (A19) also lifts AUDIT leftover to 41.36%
but cannot fix the DD arm (p95 220.01 vs cap 219.48, miss
0.53) — the veto and the partner are both load-bearing.

## Runner-up — A17 also passes ALL gates

A17 = A01 base + PLANB9C partner (66 accepted, drops
{check_busy 140, symbol_overlap 9}, 0 DOLLARIDX): DISC
leftover 80.87%, AUDIT leftover **38.36%** (+1.08 ✓), AUDIT
net +461.31, win 97.23/86.54, epd 2.481/2.537, LCT
85.75/69.33 ✓, MC flag TRUE (DD 126.37 → 181.43 vs 189.56,
cluster 117.25), PBO 0.00% / DSR 1.0000, decay WEAKENED.
A16 is selected over A17 on both standing orderings: higher
AUDIT leftover (+3.93 vs +1.08) and stronger LCT (96.40 vs
85.75), with the lower DD p95 (171.39 vs 181.43).

## All 20 candidates at replay (DISC lo · AUDIT lo · LCT P/q05 · MC DD p95 vs own cap · flag · failing gates)

- A01 veto h16_1 (= C08 replication): 80.37 · 36.80 · 78.14/66.24 · 187.00 vs 189.56 · TRUE · AUDIT leftover ✗, LCT P ✗ (feb_verify result reproduced exactly; DSR 0.9998 on this family vs 1.0000 on the verify family — both pass)
- A02 C08+veto NZDCAD_h16: 81.68 · 35.73 · 81.59/69.95 · 183.31 · TRUE · AUDIT leftover ✗ (LCT now passes — the extra veto helps DISC/LCT but costs AUDIT)
- A03 C08+veto NZDCAD_h11: 80.12 · 35.64 · 55.36/62.44 · 190.93 · FALSE · AUDIT ✗, LCT ✗, MC ✗
- A04 C08+veto NZDUSD_h13: 80.81 · 35.84 · 78.98/69.52 · 187.30 · TRUE · AUDIT ✗, LCT ✗ (by 1.02)
- A05 C08+veto h11_0 (= C07 form): 71.29 · 33.81 · 30.22/46.45 · 292.35 · FALSE · DISC ✗, AUDIT ✗, LCT ✗, MC ✗ (rejected again)
- A06 C08+veto GBPUSD_h11: 69.80 · 32.39 · 12.29/54.98 · 279.93 · FALSE · DISC ✗, AUDIT ✗, LCT ✗, MC ✗ (fall-through after this veto is destructive)
- A07 veto NZDCAD_h16 alone: 77.93 · 37.14 · 42.66/63.66 · 225.19 · FALSE · AUDIT ✗ (by 0.14), LCT ✗, MC ✗
- A08 veto NZDCAD_h11 alone: 76.68 · 36.20 · 59.77/62.66 · 230.72 · FALSE · DISC ✗, AUDIT ✗, LCT ✗, MC ✗
- A09 veto NZDUSD_h13 alone: 77.16 · 36.40 · 42.25/61.99 · 228.72 · FALSE · AUDIT ✗, LCT ✗, MC ✗
- A10 veto GBPUSD_h11 alone: 69.53 · 33.19 · 3.15/58.25 · 288.95 · FALSE · all ✗
- A11 veto NZDCAD_h16+h11 double: 77.69 · 35.68 · 57.14/66.74 · 227.44 · FALSE · AUDIT ✗, LCT ✗, MC ✗
- A12 veto NZDUSD_h13+NZDCAD_h16 double: 78.21 · 36.25 · 42.25/64.77 · 223.99 · FALSE · AUDIT ✗, LCT ✗, MC ✗
- A13 C08 + replay-state cooldown 48h: 81.92 · 22.72 · 79.82/72.24 · 229.71 vs own 312.44 · TRUE · AUDIT leftover ✗✗, DISC epd 1.944 ✗, LCT ✗ (by 0.18) — skipping whole checks at replay starves the walk and guts AUDIT
- A14 C08 + replay-state cluster cap (≥2 losses in last 5 exited → skip): 83.39 · AUDIT n 0 · 72.85/69.43 · 143.92 · TRUE · AUDIT ✗✗, epd ✗, decay FAIL — the ledger-level C03 deadlock is REAL at replay too: once latched, no new picks are taken, so no new exits ever clear the last-5 state; the walk dies (DISC epd 1.381, AUDIT empty). REJECTED as a mechanism.
- A15 C08 + replay-state same-symbol loss block 72h: 81.06 · 24.14 · 89.80/66.36 · 265.96 vs own 283.79 · TRUE · AUDIT leftover ✗✗ (the block vetoes the fall-through replacements AUDIT needed)
- **A16 C08 replay + PLANB cand2 partner: 82.62 · 41.21 · 96.40/71.83 · 171.39 · TRUE · ALL GATES PASS — WINNER**
- A17 C08 replay + PLANB9C partner: 80.87 · 38.36 · 85.75/69.33 · 181.43 · TRUE · ALL GATES PASS — runner-up
- A18 C08 replay + PLANB cand1 partner: 83.83 · 33.62 · 99.58/76.03 · 205.31 · TRUE · AUDIT leftover ✗ (best DISC/LCT of the slate; its 89 accepted picks are DISC-strong but AUDIT-dilutive)
- A19 NONE replay + PLANB cand2 partner: 78.14 · 41.36 · 99.58/63.86 · 220.01 vs 219.48 · FALSE · MC ✗ by 0.53 only (partner alone cannot fix the DD arm — cf. ledger C12's 220.15 near-miss)
- A20 triple veto {h16_1, h11_0, NZDCAD_h16}: 72.31 · 33.14 · 33.30/53.53 · 295.71 · FALSE · DISC ✗, AUDIT ✗, epd ✗, LCT ✗, MC ✗

Pattern, stated plainly: at replay, EVERY additional veto
(A02–A06, A20) trades AUDIT leftover away — fall-through
replacements are systematically weaker on AUDIT than the slots
they refill — and every stateful cluster rule (A13–A15) either
starves or latches the walk. The only mechanisms that repair
C08's replay failure are second-priority partner fills against
the replayed base (A16/A17 pass; A18 fails on AUDIT dilution
alone). Loss-cluster control for Feb is therefore: the h16_1
veto (DD arm) + compositional fill (edge repair) — the same
shape that worked in July, now verified at app-replay level
for the base walk.

## Honest trial count / DSR note

Family for PBO/DSR = this attempt's own pre-registered slate:
21 daily DISC series {NONE replay + A01..A20} (161 DISC days),
validate_new8 verbatim — A16 PBO 0.00%, DSR 1.0000; A17 the
same. The historical BRIEF22 mega-family re-grade (the family
behind the incumbent's 0.1819) remains NOT recoverable from
disk and was NOT run — the same named gap as feb_verify.md,
unchanged. No family shopping: the family is exactly the
slate above, fixed before measuring.

## Method / files

- Runner: `run_feb_planA2_s1.py` (slate + DISC-only leg table
  pre-registered in its header). Machinery reused, not
  rebuilt: app `core.cycle85b_best`, `lib22_feb`,
  `work_29load/mc9_verbatim.py`, `work_new8/validate_new8.py`.
- Machine record: `results/feb_planA2_s1_run.json`; per-
  candidate replay ledgers `results/feb_planA2_s1_A01..A20_
  ledger.csv` (walk variants are full app-replay walks;
  A16–A19 are the merged ledgers on their replayed bases).
- Integration note (not done here, research level only):
  A16's partner is a design ledger, so an app-code form of
  the cand2 partner inside cycle85b's selection — plus a
  fresh exact-replay verification of the integrated form —
  is required before any promotion is integrated, exactly as
  feb_verify.md required for C08. The §2 verdict above is
  the research-level promotion decision for the A16 form:
  veto h16_1 (fall-through) + PLANB cand2 as second-priority
  partner.

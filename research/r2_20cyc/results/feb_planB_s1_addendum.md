VERDICT: Feb planB s1 — SECOND-BEST CREATED (addendum: X12 re-merged against replayed bases — remains VALID IN FULL against the incumbent cycle85b replay base; against the C08 replay base it passes leftover/delta/LCT/cluster/consec but its combined DD p95 202.99 is worse than C08-alone 187.00, so the strict arm-by-arm MC-not-worse test fails against that base only)

# Feb Plan B S1 — ADDENDUM: X12 re-merge against replayed bases (2026-10-30, Wave 3a)

Closes the caveat in `feb_verify.md` / `feb_planB_s1.md`: X12 was
merged against the LEDGER-LEVEL C08 ledger, and C08 was then
REJECTED at app replay. Here the X12 second-best ledger
(`results/feb_planB_s1_SB_ledger.csv`, 576 picks, byte-identical
to `feb_planB_s1_X12_sb.csv`) is re-merged, with the original
Feb Plan B merge semantics verbatim (second priority: SB pick
accepted only at a check the base does not take, no
symbol-interval overlap with the base or an accepted SB pick),
against two REPLAYED bases:
  (a) incumbent cycle85b replay base = the recorded app ledger
      `feb22_c19_app.csv` — the NONE control of feb_verify,
      keys exact (the replayed incumbent; also the operative
      base, since C08 is not promoted);
  (b) C08 replay ledger = `results/feb_verify_C08_ledger.csv`
      (435 picks, fall-through walk).
Grading = BRIEF.md §2 second-best acceptance against EACH base.
Research level only — no app push, no GitHub push, crons
untouched. Segment days: DISC 160, AUDIT 41 (Feb convention).

## Standalone X12 — re-measured, UNCHANGED from feb_planB_s1.md

| Segment | n | net | win % | leftover | entries/day |
|---|---|---|---|---|---|
| DISC | 456 | +8193.49 | 100.00% | 87.79% | **2.850** (> 2.5 ✓) |
| AUDIT | 120 | +16.05 | 84.17% | 1.04% | 2.927 |

Standalone MC (mc9_verbatim, 10,000 paths) also identical:
P(profit) 1.0000 · DD obs 485.77 → p95 466.93 vs own cap 728.65
PASS · cluster obs −323.12 → p95 323.12 PASS · consec 4 → 4 ·
mc_middle_pass TRUE. Fires only at the best's own checks
(17:30/19:30/22:30 MMT), no new slot — unchanged.

## (a) Against the INCUMBENT cycle85b replay base — VALID IN FULL

Merge: SB picks 576, accepted **144**, drops {check_busy 424,
symbol_overlap 8}.

| Metric | Incumbent alone | Incumbent + X12 |
|---|---|---|
| DISC n / net | 385 / +4293.42 | 502 / **+6216.38** |
| DISC leftover | 76.90% | **79.71%** |
| DISC win % / epd | 96.36% / 2.406 | 97.21% / 3.138 |
| AUDIT n / net | 105 / +453.92 | 132 / **+646.06** |
| AUDIT leftover | 37.28% | **40.58%** (**+3.30**, tolerance −2.00 ✓) |
| AUDIT win % / epd | 86.67% / 2.561 | 87.88% / 3.220 |
| Combined delta picks | — | **+144** (> 0 ✓) |
| MC P(profit) | 1.0000 | 1.0000 (equal ✓) |
| MC DD obs → p95 | 146.32 → 228.72 | 146.32 → **214.24 (better than base-alone ✓)** |
| MC cluster obs → p95 | −104.50 → 143.30 | −102.50 → **136.40 (better ✓)** |
| MC consec obs → p95 | 2 → 2 | 2 → 2 (equal ✓) |
| MC verbatim flag (combined) | FALSE (base) | **TRUE** (214.24 ≤ own cap 219.48) |
| LCT combined vs base (DISC) | — | P **99.58%** / q05 **70.44%** — middle AND strict PASS |

Combine-safety arm by arm: NO MC arm is worse than base-alone
(DD p95 and cluster p95 both improve; consec and P(profit)
equal), and combined AUDIT leftover is +3.30, inside the −2.00
tolerance with room. Combined yearly leftover positive every
year (93.9 … 60.6 DISC years; 46.4 / 34.8 AUDIT years) — decay
not FAIL. §2 checklist against this base: standalone epd > 2.5
✓ · best-times only ✓ · second priority ✓ · delta > 0 ✓ ·
combine-safety ✓ · base epd 2.406 < 3 (creation allowed) ✓.

**X12 remains a valid second-best against the incumbent
cycle85b — and the merge IMPROVES the incumbent's own failing
MC DD arm at replay level (combined DD p95 214.24 passes even
the fixed step cap 219.48 that the incumbent alone fails at
228.72, and the combined verbatim flag is TRUE).**

## (b) Against the C08 REPLAY base — valid on every arm except strict DD-not-worse

Merge: SB picks 576, accepted **196**, drops {check_busy 373,
symbol_overlap 7}. (Ledger-level merge in feb_planB_s1.md
accepted 197 with drops 371/8 — the replayed base's different
walk state changes exactly one acceptance.)

| Metric | C08 replay alone | C08 replay + X12 |
|---|---|---|
| DISC n / net | 336 / +3822.90 | 501 / **+7004.02** |
| DISC leftover | 80.37% | **83.88%** |
| DISC win % / epd | 96.73% / 2.100 | 97.80% / 3.131 |
| AUDIT n / net | 99 / +415.69 | 130 / **+663.88** |
| AUDIT leftover | 36.80% | **42.28%** (**+5.48**, tolerance −2.00 ✓) |
| AUDIT win % / epd | 86.87% / 2.415 | 88.46% / 3.171 |
| Combined delta picks | — | **+196** (> 0 ✓) |
| MC P(profit) | 1.0000 | 1.0000 (equal ✓) |
| MC DD obs → p95 | 126.37 → 187.00 | 150.71 → **202.99 (WORSE than base-alone by +15.99 ✗)** |
| MC cluster obs → p95 | −104.50 → 122.50 | −102.50 → **105.50 (better ✓)** |
| MC consec obs → p95 | 2 → 2 | 2 → 2 (equal ✓) |
| MC verbatim flag (combined) | TRUE (base) | TRUE (202.99 ≤ own cap 226.07) |
| LCT combined vs base (DISC) | — | P **93.49%** / q05 **81.62%** — middle PASS |

Named exactly: against this base the ONLY failing §2
second-best item is the strict arm-by-arm form of
combine-safety on the DD arm — combined DD p95 (202.99) is
higher than C08-alone's replayed DD p95 (187.00), because the
fill raises DD obs (126.37 → 150.71). The combined ledger still
passes its own verbatim MC flag and every other arm improves
or equals. Combined yearly leftover positive every year
(94.3 … 87.8 DISC; 45.3 / 39.3 AUDIT) — decay not FAIL.

## Plain statement of which base X12 is valid against

- **Incumbent cycle85b (replay): VALID IN FULL** — every §2
  second-best item passes, and the combined form fixes the
  incumbent's MC DD failure at replay level.
- **C08 replay: PARTIALLY valid** — leftover (+5.48), delta
  (+196), LCT, cluster, consec, P(profit) and the combined
  verbatim flag all pass; the strict DD-not-worse-than-base
  arm fails (+15.99). This base is in any case not operative:
  C08 was REJECTED at replay (feb_verify.md) and is not the
  Feb best, so no integration would ever be built on it.
- The original feb_planB_s1.md combined figures (vs the
  ledger-level C08 ledger: AUDIT 46.69%, DD p95 171.39) are
  superseded for any replay-based use by the two blocks above;
  the standalone X12 figures are unchanged.

## Method / files

- Runner: `run_feb_planB_remerge.py`. Machinery reused:
  `work_29load/mc9_verbatim.py`, `work_new8/validate_new8.py`
  (LCT). Combined ledgers:
  `results/feb_planB_remerge_incumbent85b_replay_combined.csv`,
  `results/feb_planB_remerge_C08_replay_combined.csv`; machine
  record `results/feb_planB_remerge_run.json`.
- Sizing: NOT a gate in this round (brief §0) — not measured.
- Gaps named: (1) X12 itself is a ledger-level union of prior
  mined designs — an app-code replay of the union is required
  before any integration (unchanged from feb_planB_s1.md);
  (2) no PBO/DSR was re-run for the re-merges — §2 second-best
  acceptance does not gate on them, and the original this-run
  family figures (PBO 0.00% / DSR 1.0000, 35 trials) were
  measured against the superseded ledger-level base.

VERDICT: Feb planB s1 — SECOND-BEST CREATED (addendum 2: X12 re-merged against A16, Feb's new replay-verified best candidate — X12 does NOT remain valid in full against A16: combined AUDIT leftover 42.28% vs A16-alone 41.21% ✓, delta +151 ✓, LCT 86.60/81.62 ✓, cluster and consec arms ✓, combined verbatim flag TRUE — but combined DD p95 202.99 is WORSE than A16-alone 171.39 by +31.60, so the strict arm-by-arm MC-not-worse test FAILS against A16; overlap: A16 already takes exactly 45 of X12's 576 picks — ALL 45 are the cand2 partner picks inside A16, 0 from the replayed base — so cand2 absorbs X12's partner slice only, not its fill: 151 further X12 picks still add on top of A16)

# Feb Plan B S1 — ADDENDUM 2: X12 re-merged against A16 (2026-10-30, Wave 3c)

A16 (`feb_planA2_s1.md`) is Feb's new best candidate at REPLAY
level: C08 slot veto (FB_EURUSD_h16_1) replayed WITH fall-through
+ PLANB cand2 partner merged against the replayed base, ALL §2
gates passing at replay. Question: if A16 is promoted, does X12
stay Feb's second-best — or does the cand2 partner already inside
A16 absorb X12's fill? The X12 second-best ledger
(`results/feb_planB_s1_SB_ledger.csv`, 576 picks) is re-merged
against the A16 combined ledger with the original Feb Plan B
merge semantics verbatim (second priority: SB pick accepted only
at a check the base does not take, no symbol-interval overlap —
the `run_feb_planB_remerge.py` combine, unchanged).

Base ledger: the attempt-2 run DID save the A16 combined ledger
(`results/feb_planA2_s1_A16_ledger.csv`, 480 picks = 435 replayed
A01 base + 45 partner). Before merging, this runner ASSERTED its
published figures under the Feb convention (DISC 160 d / AUDIT
41 d): DISC leftover **82.62** ✓, AUDIT leftover **41.21** ✓ —
no rebuild was needed. Grading = BRIEF.md §2 second-best
acceptance against A16. Research level only — no app push, no
GitHub push, crons untouched. Sizing not a gate (brief §0).

## Standalone X12 — re-measured, UNCHANGED

DISC n 456 / net +8193.49 / win 100.00% / leftover 87.79% /
epd **2.850** (> 2.5 ✓); AUDIT n 120 / net +16.05 / win 84.17% /
leftover 1.04% / epd 2.927. Standalone MC flag TRUE (DD obs
485.77 → p95 466.93 vs own cap 728.65). Fires only at the best's
own checks (17:30/19:30/22:30 MMT), no new slot — unchanged.

## Overlap analysis — how much of X12 A16 already takes

Exact-key match = same (check, symbol, strategy):

| X12 picks (576) | count | note |
|---|---|---|
| Already in A16 — via the cand2 partner layer | **45** | 100% of A16's 45 partner picks are X12 picks |
| Already in A16 — via the A01 replayed base | **0** | no base pick coincides with any X12 pick |
| Same check+symbol, different strategy | 2 | near-misses, not takes |
| **Total already taken by A16** | **45 / 576 (7.8%)** | carrying DISC net +1080.86 / AUDIT net +95.28 of X12's standalone nets |

Merge accounting closes exactly: 576 = 45 already-taken
(check_busy at partner-occupied checks) + 373 dropped check_busy
at base-occupied checks + 7 dropped symbol_overlap + **151
accepted on top of A16** (net DISC +2100.26 / AUDIT +152.92).

**Plainly: the cand2 partner inside A16 absorbs exactly one
slice of X12 — the 45 picks the two designs share — and nothing
more.** X12's remaining fill is NOT absorbed: 151 of its picks
still land at A16-silent checks and add net on both segments.
(Structural reason the combined ledger below is what it is:
A16 + X12 combined is SET-IDENTICAL — all 631 picks — to the
C08-replay + X12 combined ledger of addendum 1, because every
pick A16 adds over C08-replay is an X12 pick that simply goes
check_busy in this merge instead.)

## Combined A16 + X12 vs A16 alone — §2 second-best grading

Merge: SB picks 576, accepted **151**, drops {check_busy 418
(373 base-occupied + 45 partner-occupied), symbol_overlap 7}.

| Metric | A16 alone | A16 + X12 |
|---|---|---|
| DISC n / net | 375 / +4903.75 | 501 / **+7004.02** |
| DISC leftover | 82.62% | **83.88%** (+1.26) |
| DISC win % / epd | 97.07% / 2.344 | 97.80% / 3.131 |
| AUDIT n / net | 105 / +510.96 | 130 / **+663.88** |
| AUDIT leftover | 41.21% | **42.28%** (**+1.07**, tolerance −2.00 ✓) |
| AUDIT win % / epd | 87.62% / 2.561 | 88.46% / 3.171 |
| Combined delta picks | — | **+151** (> 0 ✓) |
| MC P(profit) | 1.0000 | 1.0000 (equal ✓) |
| MC DD obs → p95 | 126.37 → 171.39 | 150.71 → **202.99 (WORSE than A16-alone by +31.60 ✗)** |
| MC cluster obs → p95 | −102.50 → 108.59 | −102.50 → **105.50 (better ✓)** |
| MC consec obs → p95 | 2 → 2 | 2 → 2 (equal ✓) |
| MC verbatim flag (combined) | TRUE | **TRUE** (202.99 ≤ own cap 226.07) |
| LCT combined vs A16 (DISC) | — | P **86.60%** / q05 **81.62%** — middle PASS |

Combine-safety arm by arm: P(profit) equal, cluster p95 better,
consec equal — and the DD arm worse by +31.60, because the fill
raises DD obs (126.37 → 150.71) and p95 with it. This is the
same DD-arm failure X12 showed against the C08 replay base in
addendum 1 (+15.99 there), widened because A16-alone's DD p95
(171.39) is lower than C08-alone's (187.00): the partner that
fixed A16's own DD arm makes X12's DD dilution larger by
comparison. Combined yearly leftover positive every year
(94.3 … 87.8 DISC years; 45.3 / 39.3 AUDIT years) — decay not
FAIL. §2 checklist against A16: standalone epd > 2.5 ✓ ·
best-times only ✓ · second priority ✓ · delta > 0 ✓ ·
AUDIT-leftover tolerance ✓ · base epd 2.344 < 3 (creation
allowed) ✓ · **MC arms not worse ✗ (DD arm only)**.

## Plain statement

- **If A16 is promoted, X12 does NOT stay Feb's second-best in
  full.** It passes every §2 second-best item against A16
  except the strict arm-by-arm MC-not-worse test, which fails
  on the DD arm alone (+31.60). Under the locked gates it
  therefore cannot be certified as A16's second-best as-is.
- **The cand2 partner inside A16 does NOT already absorb X12's
  fill** — it absorbs 45 of 576 picks (the shared partner
  slice, 7.8%); X12 still adds +151 picks, +2100.26 DISC net
  and +152.92 AUDIT net on top of A16, and lifts combined
  AUDIT leftover by +1.07 pts. The two statements are both
  true: X12 remains materially additive over A16, AND its
  additivity is exactly what re-widens the DD arm past
  A16-alone.
- For the record: the A16+X12 combined form still passes its
  OWN verbatim MC flag (TRUE) and beats A16-alone on leftover,
  net and epd on both segments — the failure is only against
  the strict not-worse-than-base arm-by-arm form of
  combine-safety, the same single-arm failure recorded against
  the (rejected, non-operative) C08 replay base in addendum 1.
  Against the incumbent cycle85b, addendum 1's VALID IN FULL
  finding is unchanged.
- What would close it (named, not run): an X12 variant whose
  fill avoids the DD-window checks, or grading the pair as a
  combined BEST candidate (where the governing test is the
  combined ledger's own flag, which passes) — either is a
  separate decision, not taken here.

## Method / files

- Runner: `run_feb_x12_vs_a16.py`. Machinery reused:
  `work_29load/mc9_verbatim.py`, `work_new8/validate_new8.py`
  (LCT). A16 ledger asserted (82.62 / 41.21) before merging —
  the `run_feb_planA2_s1.py` A16 path did not need rebuilding.
- Combined ledger:
  `results/feb_planB_addendum2_A16X12_combined.csv` (631 picks;
  set-identical to `results/feb_planB_remerge_C08_replay_
  combined.csv` — verified key-by-key in this run's analysis);
  machine record `results/feb_x12_vs_a16_run.json`.
- Gaps named: (1) X12 itself is a ledger-level union of prior
  mined designs — an app-code replay of the union is required
  before any integration (unchanged); (2) no PBO/DSR re-run —
  §2 second-best acceptance does not gate on them.

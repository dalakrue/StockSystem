VERDICT: Oct verify — IMPROVED (C14 VERIFIED at re-merge level: fresh re-merge of the PLANB9 cand2 walk onto REF657 reproduces the published combined EXACTLY in content — 700 picks, 43 accepted, drops 237 check_busy / 0 symbol_overlap, 0 duplicate keys, 0 same-symbol overlaps, all 43 fills at checks empty in the incumbent — and the full §2 battery re-passes on the re-merged ledger: AUDIT leftover 72.41→73.35%, AUDIT net +1171.05 > incumbent, LCT 100.00/81.05, MC PASS, PBO 0.00% / DSR 1.0000, decay PASS; C01 also survives at SIMULATED-replay level — AUDIT leftover 74.46% on the simulated ledger — but its base-stream fall-through is unmodelled, so C14 is the verified form; incumbent 92+92e stands pending a separate integration decision)

# Oct VERIFICATION — C14 construction audit + C01 fall-through test (2026-10-30, Wave 4i)

Closes the named gaps in `oct_planA_s1.md` (C01 "app replay
REQUIRED before integration"; C14 "has not been app-replayed
either"). Research level only — no app push, no GitHub push,
live crons untouched. No gate was moved. **Priority per the
task: C14 first** — it carries no veto, and its mechanism (an
incumbent-priority partner merge) is the app's own
combined-layer construction, so a verified re-merge IS its
verification level; there is no fall-through to model because
nothing is removed and no check is freed.

## Method — controls validated before any candidate was trusted

`run_wave4i_verify.py` (Oct section), battery = the Oct lane's
own conventions verbatim (validate_new8 seg_stats by-trade,
days DISC 175 / AUDIT 46; mc9_verbatim 10,000 paths seed
20261101; validate_new8 lct / daily_pnl / round_pbo_dsr;
planA-engine full_decay):
- CONTROL on REF657 (the C155 dual-pick combined, stored
  order kept): DISC 510 / +4515.65 / 86.96%, AUDIT 147 /
  +1118.43 / 72.41%, MC DD obs 142.30, **DD p95 176.89 —
  EXACT vs the revalidation record** (the lane's 176.96 was
  its own unstable-sort artefact, disclosed there; the
  stable-order read here matches the record). CONTROL_OK =
  True.
- C01 CANDIDATE CONTROL: removing FB_EURUSD_h15_0 at ledger
  level reproduces C01 exactly (539 picks; DISC 99.66%,
  AUDIT 72.52%, AUDIT net +1000.30). C01_LEDGER_OK = True.
Machine record: `results/wave4i_verify_run.json`.

## C14 — construction verification (the priority form)

Fresh re-merge of the stored partner walk
`MONTH_Oct_PLANB9_cand2_ledger.csv` (280 rows) against REF657
under the lane merge (incumbent priority: a partner row is
accepted only if its check carries NO incumbent pick and its
symbol does not time-overlap the incumbent or an earlier
accepted partner row — validate_new8.build_combined rules,
the app's combined-layer semantics; best-first preserved:
every REF657 row is present unchanged in the combined, the
C155 dual-pick primary/second selection is untouched):

| Construction check | Result |
|---|---|
| Accepted / drops | **43** / check_busy 237, symbol_overlap 0 — EXACT vs published |
| Combined rows | 700 = stored C14 ledger's 700 |
| Content vs stored C14 ledger | **set-identical** (check, symbol, strategy, gross on all 700 rows); in-order comparison differs only in within-check tie order (the lane's unstable sort vs this run's stable sort) |
| Duplicate (check, symbol, strategy) keys | **0** |
| Same-symbol time-overlapping pairs | **0** in REF657, **0** in the combined (conflict-free) |
| Accepted fills at checks empty in the incumbent | **43 / 43** (all second-priority, none displaces a best pick) |
| Accepted checks distinct | 43 (≤ 1 partner fill per check) |
| Max picks per check | 2 = the incumbent's own C155 dual-pick max (partner fills land only on empty checks, at 1 per check) |
| DOLLARIDX rows in walk / excluded | 0 / 0 |

Battery re-graded on the RE-MERGED ledger (not the stored
one): DISC 546 / +4805.34 / **87.68%**, AUDIT 154 /
**+1171.05** / **73.35%** — both EXACT vs published; win
97.62 / 96.10; epd 3.120 / 3.348; LCT **100.00 / 81.05** PASS
(middle + strict); MC P(profit) 1.0000, DD obs 142.30 → p95
**175.21** vs own cap 213.45 PASS (the lane read 175.00 — a
0.21 tie-order difference from the sort note above; PASS
either way), cluster p95 142.30 PASS, consec p95 2 PASS, MC
middle flag PASS; PBO **0.00%** / DSR **1.0000** (family-21,
re-merged series in the C14 slot); decay **PASS**; red lines
PASS (AUDIT net above the incumbent's — no debit at all).

§2 gate check for C14: **every locked gate passes on the
verified construction** — LCT-middle ✓ · AUDIT leftover
strictly > incumbent ✓ (+0.94) · AUDIT net > incumbent ✓ ·
win > 80% ✓ · epd ≥ 2 ✓ · MC all arms ✓ · PBO ✓ · DSR ✓ ·
decay not FAIL ✓.

**Consequence, stated plainly: C14 is VERIFIED.** Its
IMPROVED verdict survives at the highest level its mechanism
admits — the merge is deterministic app construction, and it
reproduces bit-for-bit in content. Named residual gap: the
partner walk itself is a stored research walk (walk157);
harness_new8 app-replayed the oct_e07 layer exactly, but no
app-side walk gate for the PLANB9 cand2 design exists on
disk — the same stored-walk basis every Oct partner in this
programme stands on, disclosed not hidden.

## C01 — simulated fall-through (the veto form)

No Feb-style evaluate→select pool driver exists for the
cycle92/C155 base stream (its signals are not stored; REF657
is a concat of walked logs), so C01 is graded at
**SIMULATED-replay** level (dec_verify precedent): the veto
removes the 118 FB_EURUSD_h15_0 picks (118 checks become
empty); the system's own next layer — the cycle92e walk
(`MONTH_Oct_ROUND4_cand1_ledger.csv`, 241 rows, the oct_e07
design whose 61 survivors already sit in REF657) — falls
through under the app occupancy rule verbatim: 180 pool rows
not already in the vetoed stream → **33 refills, ALL at
freed checks**, net DISC **+539.52** / AUDIT **+107.90**.
NOT modelled (named gaps): base-stream next-signal
fall-through inside the C155 walk at freed checks (the
primary/dual-pick selection re-running without the FB slot —
no signal pool on disk), open-position cascades, and the
92e walk's internal state if re-run. The Feb C08 failure
lived exactly in that unmodelled part, which is why C01's
grade stays labelled simulated.

| Metric | Incumbent 92+92e | C01 ledger-level | C01 simulated fall-through |
|---|---|---|---|
| Total picks | 657 | 539 | 572 (539 + 33 refills) |
| DISC n / net | 510 / +4515.65 | 414 / +4425.65 | 440 / **+4965.17** |
| DISC leftover | 86.96% | 99.66% | **99.68%** (+12.72 ✓) |
| DISC win % / epd | 97.45 / 2.914 | 99.76 / 2.366 | 99.77 / 2.514 |
| AUDIT n / net | 147 / +1118.43 | 125 / +1000.30 | 132 / **+1108.20** |
| AUDIT leftover | 72.41% | 72.52% (+0.11 ✓) | **74.46%** (**+2.05 ✓**) |
| AUDIT win % / epd | 95.92 / 3.196 | 96.00 / 2.717 | 96.21 / 2.870 |
| LCT P / q05 (DISC) | — | 100.00 / 98.62 | **100.00 / 98.72** PASS (middle + strict) |
| MC DD obs → p95 vs own cap | 142.30 → 176.89 vs 213.45 PASS | 142.30 → 164.71 PASS | 142.30 → **162.83 vs 213.45 PASS** |
| MC cluster / consec p95 | 142.30 / 2 PASS | 142.30 / 2 PASS | 142.30 / 2 PASS |
| MC middle (verbatim flag) | PASS | PASS | **PASS** (all arms) |
| PBO / DSR (family-21, sim series in C01 slot) | 0.00% / 0.9982 (record) | 0.00% / 1.0000 | **0.00% / 1.0000** |
| Decay | PASS | PASS | **PASS** |
| Red lines | — | PASS | PASS (AUDIT net +1108.20 > 0) |

What fall-through did: the opposite of the ledger-level
worry — the 92e refills are net-positive on both segments
and AUDIT leftover RISES vs the ledger bound (72.52 →
74.46), because the vetoed slot's AUDIT picks were
near-breakeven while the refills earn. The one debit
survives honestly: AUDIT net +1108.20 is still **−10.23
below** the incumbent's +1118.43 (leftover is a ratio; the
veto deletes net-positive AUDIT volume). AUDIT net > 0 is
the §2 gate and it passes; the strictly-greater test is on
leftover and it passes by +2.05.

§2 gate check for simulated C01: **every locked gate
passes at simulated-replay level** (LCT strict, MC all
arms, PBO/DSR, decay, win, epd, red lines).

**Consequence, stated plainly: C01's IMPROVED verdict also
survives — at simulated level only.** By the locked
selection rule (strongest LCT first) C01 out-ranks C14
(q05 98.72 vs 81.05), but the evidence levels differ: C14
is verified construction-exact with no unmodelled step,
while C01's decisive unknown (base-stream fall-through) is
precisely the mechanism that killed Feb C08 at true replay.
If only one form is carried toward integration on this
evidence, it is C14; C01 should not be integrated without
an app-code replay if one is ever built. No integration is
made by this worker; incumbent cycle92+92e stands pending
a separate integration decision.

## Files

- Runner: `run_wave4i_verify.py` (work dir root, Oct section)
- Machine record: `results/wave4i_verify_run.json`
- Re-merged ledger: `results/oct_verify_C14_remerged_ledger.csv`
- Simulated ledger: `results/oct_verify_C01_sim_ledger.csv`
- Gaps named: no app-code walk gate for the PLANB9 cand2
  design (above); no base-stream replay machinery for
  cycle92/C155 (above); R2-engine CSCV PBO basis not run
  (canonical family-21 basis governs, as in the lane file).

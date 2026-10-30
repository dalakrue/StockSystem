VERDICT: Jul planA s1 — SMALL-IMPROVED (addendum: PBO/DSR for C18 now computed — DSR PASS on both bases, PBO PASS on the programme-canonical basis / FAIL on the R2-engine basis, disclosed; MC dual-cap reading unchanged, promotion consequence stated)

# Jul Plan A S1 — ADDENDUM: PBO + DSR for C18 (2026-10-30, Wave-2 finish)

Closes the named gap in `jul_planA_s1.md` ("PBO / DSR: NOT
recomputed for C18"). Research level only — no app push, no
GitHub push, live crons untouched. This addendum does NOT change
the Plan A verdict (SMALL-IMPROVED) and does NOT move any gate.

## Family — pre-stated before computing (no family shopping)

The family is the set of variants the Jul Plan A S1 run actually
evaluated, rebuilt with the exact transform code of
`run_jul_pa_s1.py` / `run_jul_pa_s1b.py`:
C01–C11 (round-1 direct), P01/P02/P04–P10 (round-1 partner merges
that exist on disk), C12–C20 (refinement) = **29 variants**.
P03 (MONTH_Jul_PLANB_partner) is excluded by construction — its
ledger file does not exist (Plan A record, named gap there too).
C18 = LP_P10 (prune FB_AUDUSD_h17_0_G + PLANB cand1 fill) is one
member of this family, not a post-hoc addition. Machine record:
`results/jul_c18_pbo_dsr.json` + `results/jul_c18_pbo_dsr_xbasis.json`;
runner: `run_jul_c18_pbo_dsr.py`.

## Results — both bases reported, neither hidden

DSR (gate ≥ 0.90):
- R2-engine basis (`support/planA_s1_engine.dsr_family`, per-trade
  DISC nets, N = 29, sr0 = 0.1220): **C18 DSR = 1.0000 — PASS**
- Programme-canonical basis (`validate_new8.round_pbo_dsr`,
  c129-verbatim daily CSCV family, N = 30 incl. incumbent,
  174 DISC days): **C18 DSR = 0.9999 — PASS**

PBO (gate ≤ 50%):
- Programme-canonical basis (validate_new8/c129, daily series,
  6-block CSCV — the basis family that produced the incumbent's
  step-test PBO record of 17.46%): **PBO = 0.00% — PASS**
- R2-engine basis (`pbo_cscv`, 10 trade-order blocks over the 29
  candidate DISC frames): **PBO = 95.24% — FAIL**

The two PBO implementations disagree on this family (they also
disagree across this round: the same R2-engine CSCV reads 97.22%
on the Jul Plan C family and 100.00% on the Jul Plan B combined
family, while the canonical basis reads 0.00% on both Feb's and
Jul's families). The bases differ in construction (daily-mean
CSCV over calendar blocks vs block-sum CSCV over trade-order
blocks, incumbent included vs candidates-only) and are NOT
interchangeable. The figure comparable to the step-test record
is the canonical one: **0.00%**. The R2-engine figure is reported
verbatim as a disclosed caveat, not suppressed: on highly
correlated single-ledger variant families its in-sample-best
ranking is unstable by construction.

## Both MC DD cap readings for C18 (restated, neither gate moved)

From `jul_planA_s1.md`, verbatim MC (10,000 paths): DD obs
138.13, DD p95 **210.67**.
- vs the step test's FIXED cap 215.72 (the cap that defined this
  round's target, from the incumbent's DD obs 143.81):
  **210.67 ≤ 215.72 — PASS**
- vs mc9's OWN-RELATIVE cap for C18 (1.5 × 138.13 = 207.20):
  **210.67 > 207.20 — FAIL by 3.47** (mc_middle_pass reads False
  on this arm alone; every other MC arm passes: P(profit) 1.0000,
  cluster p95 141.20 vs cap 188.51, consec p95 2)

## Promotion consequence — stated plainly

With this addendum, C18's §2 scorecard is: LCT-middle PASS
(86.32 / 62.17) · AUDIT leftover strictly > incumbent PASS
(66.58 > 64.97) · win > 80 PASS · epd ≥ 2 PASS · AUDIT net > 0
PASS · decay not FAIL PASS · DSR PASS (both bases) · PBO PASS
on the programme-canonical basis (FAIL on the disclosed
R2-engine basis) · MC middle: PASS on the fixed step cap, FAIL
by 3.47 on the own-relative cap.

**C18 is therefore NOT promoted by this worker.** Its only
remaining blocker under the canonical readings is a single
formula reading — whether the MC DD cap for a candidate is the
step test's fixed 215.72 or the candidate's own-relative
207.20. That is a ruling for the parent/user, not a gate this
addendum may move: both readings are reported above, and until
the ruling is made the incumbent cycle78 stands and C18 remains
SMALL-IMPROVED at research level. If the fixed-cap reading
governs, C18 clears every §2 gate on the canonical basis and is
promotable; if the own-relative reading governs, it fails EC-
middle on the DD arm alone and is not.

VERDICT: Apr verify — IMPROVED-at-simulated-replay (C20 SURVIVES the fall-through test: every §2 gate still passes on the simulated ledger — DISC leftover 85.26→90.37%, AUDIT 71.26→76.11% strictly greater, AUDIT net +2135.68 > incumbent +1929.49, LCT 95.42/82.35, MC all arms PASS; NO true app-code replay exists for Apr — harness2/harness3 replay only the candidate layers — so simulated-replay is the highest level available, with the base-stream gaps named below; C19-sim is the strongest simulated form and C02-sim also passes; NO non-veto passer exists in Plan A — incumbent 87c+87s stands pending a separate integration decision)

# Apr VERIFICATION — fall-through test of Plan A C20 + alternates (2026-10-30, Wave 4i)

Closes the named gap in `apr_planA_s1.md` ("App replay REQUIRED
before any integration"). Research level only — no app push, no
GitHub push, live crons untouched. **Unlike Dec C07 / Mar PC14,
the Apr ledger-level IMPROVED verdict SURVIVES its fall-through
test** — the refills the veto frees are net-positive on BOTH
segments here. No gate was moved.

## Machinery note — read this first (level of this verdict)

There is **NO true app-code replay for the full April 87c+87s
combined on disk**, and this file does not pretend otherwise.
`harness2.py` / `harness3.py` replay ONLY the candidate layers
(apr_q09, apr_pvote, apr_pvsb) through app code
(`core.new8_walk.walk157`) and merge them onto RESEARCH
ledgers (gates app2/app3: combined EXACT). The base FB stream
(the cycle87b chain inside cycle87c) is never regenerated
check-by-check by any driver on disk — there is no Apr
analogue of `harness_feb22.py` (no signal pool for the 87b
stream exists). Per the task's fallback rule, the grade below
is at **SIMULATED-replay** level, exactly as in `dec_verify.md`:

- What the simulation DOES model: the veto removes the 65
  FB_NZDUSD_h17_0 picks (55 checks become empty); the system's
  own next layers then fall through exactly as the app's
  occupancy rule (`core.new8_walk.build_combined`, verbatim)
  allows — stored candidate-walk rows not already in the
  stream (apr_q09 walk 175 non-dollar rows first, then
  apr_pvote walk 204, then apr_pvsb walk 124 — the cycle87c /
  combined-layer app order) are accepted at a check only if
  the check carries no pick in the current stream and the
  symbol does not time-overlap the stream or an earlier
  refill. Result for C20/C01: 31 refills (25 q09 + 6 pvote +
  0 pvsb), ALL at freed checks, net DISC +349.77 / AUDIT
  +133.34. The C20 partner walk (PLANB cand2) is merged LAST,
  second-priority: after the fall-through refills it accepts
  **0** (86 check_busy) — its 2 ledger-level fills sat at
  checks the q09/pvote refills take first, so simulated C20
  is identical to simulated C01.
- What it does NOT model (named gaps, not hidden): (1)
  base-stream next-signal fall-through at the 10 vetoed
  checks where other base picks remain, and inside the 87b
  ranked-candidate selection generally (no signal pool on
  disk); (2) base-stream open-position cascades (a vetoed
  NZDUSD position no longer blocks later NZDUSD signals
  inside the base walk); (3) the candidate walks' internal
  state if re-run against the vetoed stream instead of
  reusing their stored walks. The Feb C08 precedent says
  unmodelled fall-through of kind (1)/(2) is where ledger
  gains can die, so the simulated grade is an
  UPPER-bound-flavoured test, not a substitute for an app
  replay if one is ever built.

## Method — controls validated before the candidate was trusted

`run_wave4i_verify.py` (Apr section), battery = the Apr lane's
own conventions verbatim (validate_new8 seg_stats by-trade,
days DISC 169 / AUDIT 44; mc9_verbatim 10,000 paths seed
20261101; validate_new8 lct / daily_pnl / round_pbo_dsr;
planA-engine full_decay):
- CONTROL on the incumbent 946 ledger: DISC 747 / +6620.36 /
  85.26%, AUDIT 199 / +1929.49 / 71.26%, MC DD p95 221.12,
  cluster p95 103.30 — EXACT vs `apr_planA_s1.md` and the EC
  step record. CONTROL_OK = True.
- CANDIDATE CONTROLS: removing the veto slots at ledger level
  reproduces C01 / C02 / C19 / C20 EXACTLY (canonical stats vs
  `apr_planA_s1_canon.json`: C20 DISC 90.56 / AUDIT 78.92 /
  AUDIT net +2064.49 ✓, all four ok). The simulation starts
  from a verified base and verified candidates.
Machine record: `results/wave4i_verify_run.json`; simulated
ledgers: `results/apr_verify_C20_sim_ledger.csv` (= C01 sim),
`apr_verify_C19_sim_ledger.csv`, `apr_verify_C02_sim_ledger.csv`.

## Numbers block — incumbent vs C20 ledger-level vs C20 simulated fall-through

| Metric | Incumbent 87c+87s | C20 ledger-level | C20 simulated fall-through |
|---|---|---|---|
| Total picks | 946 | 883 | 912 (881 vetoed + 31 refills + 0 partner) |
| DISC n / net | 747 / +6620.36 | 701 / +6732.29 | 720 / **+7045.17** |
| DISC leftover (by-trade) | 85.26% | 90.56% | **90.37%** (+5.11 ✓) |
| DISC win % / epd | 97.72 / 4.420 | 98.43 / 4.148 | 98.33 / 4.260 |
| AUDIT n / net | 199 / +1929.49 | 182 / +2064.49 | 192 / **+2135.68** |
| AUDIT leftover | 71.26% | 78.92% (+7.66 ✓) | **76.11%** (**+4.85 ✓**) |
| AUDIT win % / epd | 94.47 / 4.523 | 95.60 / 4.136 | 95.31 / 4.364 |
| LCT P / q05 (DISC) | — (reference) | 99.59 / 81.34 | **95.42 / 82.35** PASS (middle + strict) |
| MC P(profit) | 1.0000 | 1.0000 | 1.0000 |
| MC DD obs → p95 vs own cap | 164.43 → 221.12 vs 246.65 PASS | 164.43 → 174.91 PASS | 164.43 → **180.04 vs 246.65 PASS** |
| MC cluster obs → p95 vs cap | −102.50 → 103.30 vs 153.75 PASS | −102.50 → 102.50 PASS | −102.50 → **102.50 vs 153.75 PASS** |
| MC consec obs → p95 | 1 → 2 PASS | 1 → 1 PASS | 1 → **1 PASS** |
| MC middle (verbatim flag) | PASS | PASS | **PASS** (all arms) |
| PBO / DSR (family-21, sim series in C20 slot) | 0.00% / 1.0000 (EC record) | 0.00% / 1.0000 | **0.00% / 1.0000** |
| Decay | PASS | PASS | **PASS** |
| Red lines | — | PASS | PASS (AUDIT net +2135.68 > 0, no discovery collapse) |

What fall-through did: it COST 2.81 AUDIT leftover points vs
the ledger-level bound (78.92 → 76.11) — the refill stream is
weaker per-trade than the vetoed stream it partially replaces
— but the refills are net-positive on the unseen segment
(+133.34 over 11 AUDIT refills), so AUDIT leftover stays
strictly above the incumbent and AUDIT net rises ABOVE even
the ledger-level C20 figure. This is the mirror image of Dec
C07 (refill AUDIT net −100.09 → REJECTED) and Mar PC14 (one
−102.50 AUDIT refill → REJECTED).

§2 gate check for simulated C20: LCT-middle ✓ (95.42 / 82.35,
strict too) · AUDIT leftover strictly > incumbent ✓ (76.11 >
71.26; the +4.85 gain is a close call, so LCT blocks-or-passes
— it passes) · DISC leftover ✓ · MC middle PASS all arms ✓ ·
PBO ✓ · DSR ✓ · decay PASS ✓ · win > 80% ✓ · epd ≥ 2 ✓ ·
red lines ✓. **Every locked gate passes at simulated-replay
level.**

**Consequence, stated plainly: C20 is VERIFIED at the highest
level available for April (simulated replay) and its IMPROVED
verdict survives** — with two honest qualifications: (1) the
surviving simulated form is veto + fall-through refills; the
PLANB cand2 partner layer that named C20 contributes 0 picks
once fall-through is modelled, so the form to integrate is
the veto itself (with the system's own layers refilling), not
the partner; (2) base-stream fall-through (gaps 1–2 above)
remains unmodelled — if an Apr app-replay driver is ever
built, this grade should be re-run through it before the
form is treated as app-verified. No integration is made by
this worker; incumbent cycle87c+87s stands pending a
separate integration decision.

## Alternates at the same level (fallback candidates)

- **C19-sim (veto + fall-through + PLANB9C cand1 partner,
  9 accepted after refills): the STRONGEST simulated form.**
  921 picks; DISC 90.58%, AUDIT **76.25%** / net **+2153.64**
  (highest AUDIT net of any Apr form, ledger or simulated),
  LCT 96.82 / 82.72 PASS strict, MC DD p95 177.90 PASS,
  cluster 102.50, consec 1, PBO 0.00 / DSR 1.0000, decay
  PASS — all §2 gates pass. All 40 added rows sit at
  veto-freed checks (refill + partner net DISC +539.77 /
  AUDIT +151.30).
- **C02-sim (veto worst-2 slots + fall-through): also passes
  all gates.** 874 picks (98 freed checks, 56 refills, net
  DISC +799.58 / AUDIT +202.18); DISC 94.13% (highest),
  AUDIT 74.69% / +1981.84, LCT 94.48 / 90.70 (middle PASS;
  strict fails on P alone, 94.48 < 95), MC DD p95 164.43
  PASS, PBO 0.00 / DSR 1.0000, decay PASS.
- **Non-veto fallback: NONE EXISTS.** The task asked for the
  strongest non-veto passer (C01/C02/C19 named) — all three
  are veto forms; every genuinely non-veto Plan A form is a
  partner merge (C11–C18) and all eight accepted **0** picks
  (combined saturated — combined ledger identical to the
  incumbent, NO IMPROVEMENT by construction) or a stateful
  cluster control that failed at ledger level (C08/C09/C10).
  There is no non-veto Apr candidate to grade; C19-sim above
  is the fallback at this level.

## Files

- Runner: `run_wave4i_verify.py` (work dir root, Apr section)
- Machine record: `results/wave4i_verify_run.json`
- Simulated ledgers: `results/apr_verify_C20_sim_ledger.csv`,
  `results/apr_verify_C19_sim_ledger.csv`,
  `results/apr_verify_C02_sim_ledger.csv`
- Gaps named: no app-code replay machinery for the Apr base
  stream (above); base-stream fall-through + cascades
  unmodelled (above); R2-engine CSCV PBO basis not run for
  the simulated series (canonical family-21 basis governs,
  as in the lane file).

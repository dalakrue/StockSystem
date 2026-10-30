VERDICT: Feb verify — REJECTED (C08 NOT VERIFIED at app replay with fall-through: AUDIT leftover and LCT-middle fail at replay; C07 rejected outright at replay)

# Feb VERIFICATION — app-replay of Plan A C08 / C07 WITH fall-through (2026-10-30, Wave-2 finish)

Closes the named gap in `feb_planA_s1.md` ("C08 verified at ledger
level only — app replay WITH fall-through is required before any
integration"). Research level only — no app push, no GitHub push,
live crons untouched. **The ledger-level IMPROVED verdict for C08
does NOT survive this replay.** Details and the surviving gains
are stated in full below; no gate was moved.

## Method — driver validated before any veto was trusted

`run_feb_verify.py`: `harness_feb22.py` c19 mode driven verbatim
(app module `core.cycle85b_best` evaluate + select over the
BRIEF22-era frames/pool, Forex_App_Updated tree), ONE pass over
the 514-check grid, THREE independent walk states:
- NONE (control): **reproduces the recorded app ledger
  `replay_out/feb22_c19_app.csv` keys EXACTLY, in order**
  (CONTROL_KEYS_EQUAL = True), and its battery reproduces the
  step test byte-for-byte (DISC 385/+4293.42/76.90%, AUDIT
  105/+453.92/37.28%, MC DD p95 228.72). The driver is sound.
- C08: signal rows with equation == FB_EURUSD_h16_1 removed
  BEFORE select — the app's own selection then falls through to
  the next eligible primary/partner (the C05-veto precedent form
  already inside cycle85b's select).
- C07: signal rows with equation startswith FB_EURUSD removed
  likewise.
Pool outcomes: missing_pool = 0 for all variants. Battery =
Feb Plan A conventions verbatim (segment days from the control
ledger: DISC 160, AUDIT 41; mc9_verbatim 10,000 paths;
validate_new8 LCT / daily_pnl / round_pbo_dsr). Machine record:
`results/feb_verify_run.json`; replay ledgers:
`results/feb_verify_C08_ledger.csv`, `results/feb_verify_C07_ledger.csv`.

## C08 replayed — numbers block (incumbent vs ledger-level vs replay)

| Metric | Incumbent 85b | C08 ledger-level (Plan A) | C08 app replay (fall-through) |
|---|---|---|---|
| Total picks | 490 | 433 | 435 |
| DISC n / net | 385 / +4293.42 | 335 / +3936.71 | 336 / +3822.90 |
| DISC leftover | 76.90% | 82.39% | **80.37%** (+3.47 ✓) |
| DISC win % / epd | 96.36% / 2.406 | 97.31% / 2.094 | 96.73% / 2.100 |
| AUDIT n / net | 105 / +453.92 | 98 / +481.79 | 99 / **+415.69** |
| AUDIT leftover | 37.28% | 42.65% | **36.80%** (**−0.48 ✗**) |
| AUDIT win % / epd | 86.67% / 2.561 | 87.76% / 2.390 | 86.87% / 2.415 |
| LCT P / q05 (DISC) | — | 95.24% / 66.97% | **78.14% / 66.24%** (P ✗) |
| MC P(profit) | 1.0000 | 1.0000 | 1.0000 |
| MC DD obs → p95 vs cap | 146.32 → 228.72 vs 219.48 FAIL | 126.37 → 183.71 vs 189.56 PASS | 126.37 → **187.00 vs 189.56 PASS** (also < 219.48 fixed cap ✓) |
| MC cluster obs → p95 vs cap | −104.50 → 143.30 vs 156.75 | −104.50 → 107.12 | −104.50 → **122.50 vs 156.75 PASS** |
| MC consec obs → p95 | 2 → 2 | 2 → 2 | 2 → 2 PASS |
| MC middle (all arms, verbatim flag) | FAIL (DD) | PASS | **PASS** (mc_middle_pass TRUE) |
| PBO / DSR | 2.50% / 0.1819 (historical record) | 0.00% / 1.0000 (21-trial this-run) | **0.00% / 1.0000** (replay family, below) |
| Decay | — | not FAIL (proxy) | not FAIL: yearly leftover positive every year 2016–2025 (35.8–94.6%); AUDIT/DISC leftover ratio 0.46 |
| Red lines | — | PASS | PASS (AUDIT net +415.69 > 0, no discovery collapse) |

What fall-through did: the veto freed 57 incumbent picks; the
replayed walk takes 435 picks (only +2 net vs the ledger-level
433) but the walk STATE changes cascade — different symbols are
open at later checks, so later primaries/partners differ, not
just the vetoed slots. Net effect by segment: DISC keeps most
of the gain (leftover 76.90 → 80.37, net −470.52 vs incumbent —
the veto still deletes net-positive DISC volume, as at ledger
level), but on AUDIT the replacement picks are net-negative
relative to the ledger-level bound: AUDIT net +415.69 is BELOW
the incumbent's +453.92 and AUDIT leftover 36.80% is BELOW the
incumbent's 37.28%.

§2 gate check for replayed C08: DISC leftover ✓ · MC middle
PASS all arms ✓ (the DD fix is REAL and survives replay —
p95 187.00 passes both the own cap 189.56 and the fixed step
cap 219.48) · PBO ✓ · DSR ✓ (this-run basis) · win ✓ · epd ✓ ·
red lines ✓ — **AUDIT leftover strictly > incumbent ✗ (36.80 <
37.28) · small-improvement rule ✗ (leftover is below incumbent,
a tie would have counted) · LCT-middle ✗ (P 78.14% < 80%, miss
by 1.86 pts; q05 66.24% ✓)**. Two locked gates fail at replay.

**Consequence, stated plainly: C08 is NOT verified and is NOT
promoted.** Feb's Plan A result is downgraded by this
verification to: a real, replay-confirmed MC DD fix and DISC
improvement whose unseen (AUDIT) edge does not hold once the
app's fall-through picks are counted. Feb incumbent cycle85b
stands. The Feb Plan B second-best X12 (feb_planB_s1.md) was
merged against the LEDGER-LEVEL C08 ledger — its combined
figures inherit this caveat in full: if the Feb best ever
changes form, X12's merge must be re-measured against the
replayed base before any integration; X12 is not re-graded
here (out of this task's scope, flagged not hidden).

## C07 replayed — REJECTED (the ledger-level strength was an empty-slot artifact)

| Metric | Incumbent | C07 ledger-level | C07 app replay |
|---|---|---|---|
| Picks | 490 | 357 | 423 |
| DISC leftover / epd | 76.90% / 2.406 | 87.33% / 1.712 | **71.29% / 2.069** |
| AUDIT leftover / net | 37.28% / +453.92 | 69.11% / — | **33.81% / +355.05** |
| LCT P / q05 | — | 99.58% / 71.75% | **30.22% / 46.45% FAIL** |
| MC DD p95 vs cap | 228.72 vs 219.48 FAIL | 112.15 PASS | **292.35 FAIL** (obs 189.19) |
| MC cluster p95 vs cap | 143.30 vs 156.75 | PASS | **178.89 vs 156.75 FAIL** |
| PBO / DSR (replay family) | — | — | 0.00% / 0.9881 |

Fall-through fixes C07's epd gate (1.712 → 2.069 DISC) but the
replacement picks destroy its edge: DISC leftover falls BELOW
the incumbent, MC DD p95 rises above even the incumbent's
failing 228.72, and the cluster arm fails too. **C07 is
rejected at replay in full** — do not re-test it as a promotion
candidate in this form.

## DSR like-for-like on the historical family — NAMED GAP (not run, not invented)

The incumbent's DSR 0.1819 survives on disk only as a battery
record (`work_m15mine/brief22/feb/val_logs/C19_battery.json`,
VALIDATION22_FEB.md). The historical BRIEF22-era trial family's
daily series — the denominator of that DSR — is NOT recoverable
from disk: val_logs/ holds only the C17–C20 finalists. A
like-for-like re-grade of C08 inside that mega-family therefore
cannot be computed honestly and was NOT run. What IS reported:
PBO/DSR on the disclosed replay family = the Plan A this-run
family (INC + C01..C20, 21 daily series, 161 DISC days) with
the candidate's own series REPLACED by its replayed series —
C08: PBO 0.00%, DSR 1.0000; C07: PBO 0.00%, DSR 0.9881
(validate_new8.round_pbo_dsr verbatim). These are this-run-
family figures, exactly as labelled in feb_planA_s1.md.

## Method / files

- Runner: `run_feb_verify.py` (this wave). Machinery reused,
  not rebuilt: app `core.cycle85b_best`, `lib22_feb` era
  context/pool, `work_29load/mc9_verbatim.py`,
  `work_new8/validate_new8.py`, Plan A family ledgers.
- Sizing: NOT a gate in this round (brief §0) — not measured.
- Gaps named: (1) historical-family DSR (above); (2) X12
  second-best re-merge against a replayed base not done
  (flagged in the C08 consequence); (3) no new candidate was
  mined in this task — fixing Feb's AUDIT-leftover/LCT replay
  failure needs a candidate designed against the fall-through
  walk itself (e.g. veto + a fall-through-aware partner), which
  is a new mining task, not a verification task.

VERDICT: Feb combined-best s1 — IMPROVED (A16+X12 combined graded as a §2 BEST candidate vs the incumbent cycle85b REPLAY control: EVERY §2 best gate passes — DISC leftover 76.90→83.88%, AUDIT leftover 37.28→42.28% strictly greater, LCT-middle PAIRED VS THE INCUMBENT 96.54% / q05 81.62% (the measurement addendum 2 did not run — its LCT was vs A16), MC verbatim flag TRUE with DD p95 202.99 ≤ own cap 226.07, PBO 0.00% / DSR 1.0000 canonical on the stated family of 22 {incumbent + A01..A20 A-slate + combined}, decay WEAKENED = the incumbent's own class, not FAIL, red lines intact; the combined form is therefore STRONGER than A16-alone as Feb's best candidate on the governing gates, with one named trade-off: its DD p95 202.99 is worse than A16-alone's 171.39 by +31.60 — it passes its own flag, it does not beat A16's DD arm)

# Feb — A16+X12 COMBINED graded as BEST candidate (2026-10-30, Wave 4b)

Candidate: the saved combined ledger
`results/feb_planB_addendum2_A16X12_combined.csv` (631 picks =
A16's replayed best form, 480 picks, + X12 second-priority fill,
151 accepted). Nothing was re-merged in this task; the ledger
was graded as-is. Control: the incumbent cycle85b REPLAY ledger
—the NONE walk of `run_feb_planA2_s1.py` reproduced the recorded
app ledger `replay_out/feb22_c19_app.csv` keys EXACTLY, and this
runner asserted that ledger's published battery before grading
(DISC 76.90% / AUDIT 37.28%, MC DD p95 228.72, flag FALSE —
all reproduced byte-for-byte). A16-alone figures (82.62 / 41.21)
were also asserted. Grading = BRIEF.md §2 BEST gates, locked.
MC = mc9_verbatim 10,000 paths, own-relative flag (settled
ruling). Research level only — no app push, no GitHub push,
crons untouched. Sizing not a gate (brief §0).

## Numbers block — incumbent vs A16-alone vs A16+X12 combined

| Metric | Incumbent 85b (replay) | A16 alone | A16 + X12 combined |
|---|---|---|---|
| Total picks | 490 | 480 | 631 |
| DISC n / net | 385 / +4293.42 | 375 / +4903.75 | 501 / **+7004.02** |
| DISC leftover | 76.90% | 82.62% | **83.88%** (+6.98 vs inc) |
| DISC win % / epd | 96.36% / 2.406 | 97.07% / 2.344 | 97.80% / 3.131 |
| AUDIT n / net | 105 / +453.92 | 105 / +510.96 | 130 / **+663.88** |
| AUDIT leftover | 37.28% | 41.21% | **42.28%** (**+5.00, strictly > ✓**) |
| AUDIT win % / epd | 86.67% / 2.561 | 87.62% / 2.561 | 88.46% / 3.171 |
| LCT P / q05 (DISC, paired vs incumbent) | — | 96.40% / 71.83% | **96.54% / 81.62%** — middle PASS, strict PASS |
| MC P(profit) | 1.0000 | 1.0000 | 1.0000 |
| MC DD obs → p95 vs own cap | 146.32 → 228.72 vs 219.48 FAIL | 126.37 → 171.39 vs 189.56 PASS | 150.71 → **202.99 vs 226.07 PASS** (also < 219.48 fixed step cap ✓) |
| MC cluster obs → p95 vs cap | −104.50 → 143.30 vs 156.75 PASS | −102.50 → 108.59 vs 156.75 PASS | −102.50 → **105.50 vs 153.75 PASS** |
| MC consec obs → p95 | 2 → 2 PASS | 2 → 2 PASS | 2 → 2 PASS |
| MC middle (verbatim flag) | FALSE (DD arm) | TRUE | **TRUE — all arms** |
| PBO / DSR (canonical, stated family) | — / 0.1819 (historical record) | 0.00% / 1.0000 (family-21) | **0.00% / 1.0000** (family-22, below) |
| Decay | WEAKENED (exp<50%; leftover fall>20) | WEAKENED | WEAKENED — not FAIL; yearly leftover positive every year 2016–2025 (94.3 … 87.8 DISC years; 45.3 / 39.3 AUDIT years) |
| Red lines | — | PASS | PASS (AUDIT net +663.88 > 0, DISC leftover up — no collapse) |

## The missing measurement — LCT paired vs the incumbent

Addendum 2 measured the combined ledger's LCT against A16
(P 86.60% / q05 81.62%). Graded as a BEST candidate, the paired
comparison that governs is against the incumbent:
**P 96.54% / q05 81.62% — LCT-middle PASS (P ≥ 80, q05 ≥ 20),
and strict PASS as well (P ≥ 95, q05 ≥ 40).** (q05 is a
candidate-only quantity, so it is the same 81.62 in both
pairings; P rises from 86.60 against A16's stronger DISC
leftover to 96.54 against the incumbent's 76.90%.)

## PBO/DSR — stated family

Canonical (validate_new8 `round_pbo_dsr`, the governing basis):
family = **22 daily DISC series {INC (replay control) +
A01..A20 (the Plan A attempt-2 A-slate) + COMB}**, 161 DISC
days — the family includes the incumbent and the full A-slate,
fixed as stated here, no family shopping. Combined graded at
its own index: **PBO 0.00% (≤ 50 ✓), DSR 1.0000 (≥ 0.90 ✓)**,
sr_daily 1.3064 (highest of the family; A16 in the same family:
PBO 0.00% / DSR 1.0000, sr 1.0160; incumbent in-family DSR
0.9985 — the historical 0.1819 belongs to the unrecoverable
BRIEF22 mega-family, the same named gap as feb_verify.md /
feb_planA2_s1.md, unchanged). Disclosed second reading
(R2-engine CSCV basis, trade-block, gross−2.5 nets): family PBO
100.00%, combined DSR 1.0000 — reported, not the gate, exactly
as in the Jul files of this round.

## §2 gate check — ALL PASS

LCT-middle ✓ (96.54 / 81.62 vs incumbent) · AUDIT leftover
strictly > incumbent ✓ (42.28 > 37.28, the strict form — the
small-improvement rule is not needed) · win > 80% both
segments ✓ · epd ≥ 2 both segments ✓ (3.131 / 3.171) · AUDIT
net > 0 ✓ · MC verbatim flag TRUE, all arms ✓ · PBO ≤ 50%
canonical ✓ · DSR ≥ 0.90 ✓ · decay not FAIL ✓ (WEAKENED is
the incumbent's own class) · red lines ✓.

## Plain statement — is the combined form stronger than A16?

- **Yes, on the governing §2 best gates.** Against the
  incumbent, the combined form beats A16-alone on every edge
  number: DISC leftover 83.88 vs 82.62, AUDIT leftover 42.28
  vs 41.21, DISC net +7004.02 vs +4903.75, AUDIT net +663.88
  vs +510.96, epd 3.131/3.171 vs 2.344/2.561, LCT q05 81.62
  vs 71.83 at the same P ≈ 96.5, cluster p95 105.50 vs
  108.59 (better), and it keeps PBO 0.00% / DSR 1.0000.
- **The one trade-off, named exactly:** the DD arm. Combined
  DD p95 202.99 is +31.60 worse than A16-alone's 171.39 (the
  arm-by-arm failure recorded in addendum 2 under the
  second-best combine-safety test). As a BEST candidate the
  governing MC test is the candidate's OWN verbatim flag —
  202.99 ≤ its own cap 226.07, PASS, and also below the
  incumbent's fixed step cap 219.48 — so no §2 best gate
  fails. But the margin is thinner: DD headroom is 23.08
  under its own cap, vs A16-alone's 18.17 under a much lower
  cap; in absolute p95 terms the combined form carries the
  wider resampled drawdown.
- **Decision recorded:** A16+X12 combined is graded IMPROVED
  and is the stronger Feb best candidate; A16-alone remains
  the fallback with the tighter DD arm. This grading is
  research-level: the combined form is a ledger-level union
  (A16's base walk is app-replayed; the cand2 partner and the
  X12 fill are prior mined design ledgers merged at ledger
  level) — an app-code form plus a fresh exact-replay
  verification of the integrated combined form is required
  before any integration, the same caveat A16 itself carries.

## Method / files

- Runner: `run_feb_combined_best_s1.py` (asserts incumbent
  76.90/37.28 + DD p95 228.72, A16 82.62/41.21, combined
  83.88/42.28 before grading). Machinery reused, not rebuilt:
  `work_29load/mc9_verbatim.py`, `work_new8/validate_new8.py`,
  `support/planA_s1_engine.py` (CSCV second reading only).
- Machine record: `results/feb_combined_best_s1_run.json`.
- Candidate ledger (unchanged):
  `results/feb_planB_addendum2_A16X12_combined.csv` (631 picks).

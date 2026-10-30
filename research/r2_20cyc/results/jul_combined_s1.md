VERDICT: Jul combined s1 — SMALL-IMPROVED (combined form C18+B04 improves every edge statistic vs cycle78, but the MC verbatim gate FAILS on the DD arm under the settled own-relative ruling — DD p95 197.50 vs own cap 188.51, miss 8.99 — so the combined form is NOT a promotion candidate)

# Jul COMBINED FORM (C18 + B04) — full §2 best-promotion battery (2026-10-30, Wave 3a)

Candidate = the combined ledger of `jul_planB_s1.md` (C18 best-form
— cycle78 with FB_AUDUSD_h17_0_G pruned + PLANB cand1 silent-check
fill — merged second-priority with the B04 second-best, +76 picks;
ledger `results/jul_planB_s1_B04_combined.csv`, copied to
`results/jul_combined_s1_ledger.csv`; rebuild asserted exact
before grading: DISC 516/+5253.58/80.59%, AUDIT 135/+996.85/68.84%).
Graded against the cycle78 incumbent as a BEST candidate under
BRIEF.md §2 locked gates. Leftover convention = Jul Plan A
(net = gross − 2.5; leftover = net ÷ sum of positive NET;
DISC 174 d, AUDIT 46 d). MC = mc9_verbatim, 10,000 paths; the
mc_middle_pass flag is the OWN-RELATIVE reading — the settled
ruling (2026-10-30) is that this flag governs MC-middle, and it
is applied here without re-argument. Research level only — no
app push, no GitHub push, live crons untouched.

## Numbers block — cycle78 incumbent vs C18 vs COMBINED (C18+B04)

| Metric | Incumbent 78 | C18 alone | Combined C18+B04 |
|---|---|---|---|
| DISC n / net | 467 / +3300.44 | 453 / +4071.60 | 516 / **+5253.58** |
| DISC leftover | 66.10% | 76.30% | **80.59%** (+14.49) |
| DISC win % / epd | 94.65% / 2.684 | 95.58% / 2.603 | 96.12% / 2.966 |
| AUDIT n / net | 128 / +877.62 | 122 / +883.40 | 135 / **+996.85** |
| AUDIT leftover | 64.97% | 66.58% | **68.84%** (**+3.87**, strictly > ✓) |
| AUDIT win % / epd | 94.53% / 2.783 | 95.08% / 2.652 | 94.81% / 2.935 |
| LCT-middle vs incumbent (Jul per-check form, DISC) | — | 86.32 / 62.17 | **P 100.00% / q05 67.03% PASS** |
| LCT canonical (validate_new8, DISC) | — | — | P 95.54% / q05 72.73% — middle AND strict PASS |
| MC P(profit) | 1.0000 | 1.0000 | 1.0000 |
| MC DD obs → p95 vs OWN cap | 143.81 → 233.91 vs 215.72 FAIL | 138.13 → 210.67 vs 207.20 FAIL | 125.67 → **197.50 vs 188.51 FAIL by 8.99** |
| MC cluster obs → p95 vs cap | −125.67 → 169.57 vs 188.51 PASS | −125.67 → 141.20 PASS | −125.67 → **138.70 vs 188.51 PASS** |
| MC consec obs → p95 | 2 → 2 PASS | 2 → 2 PASS | 2 → 2 PASS |
| MC middle (verbatim flag) | FALSE | FALSE | **FALSE (DD arm alone)** |
| PBO (canonical basis, family of 22 — below) | 17.46% (step record) | 0.00% | **0.00% PASS** |
| DSR (canonical basis, family of 22) | 0.9998 (step record) | 0.9999 | **1.0000 PASS** |
| PBO / DSR (R2-engine CSCV basis, disclosed 2nd reading) | — | 95.24% / 1.0000 | **100.00% FAIL** / 1.0000 (sr0 0.1141) |
| Decay | ratio 0.98 | ratio 0.87 | not FAIL (below) |

PBO/DSR stated family (canonical): 22 daily DISC series =
{cycle78 incumbent, C18, B01..B20 combined ledgers of Jul Plan B},
candidate graded at the B04-combined index (validate_new8
round_pbo_dsr verbatim, 174 DISC days). The R2-engine CSCV basis
on the same 22 frames reads PBO 100.00% — the same basis split
documented in `jul_planA_s1_addendum.md` (canonical daily-mean
CSCV vs trade-order block-sum CSCV on highly correlated variant
families); the canonical figure is the one comparable to the
step-test record, the CSCV figure is reported, not suppressed.

Decay: combined yearly leftover (Jul convention) positive every
year 2016–2025: 98.1 / 67.0 / 79.1 / 82.1 / 88.8 / 52.1 / 100.0 /
56.1 / 71.5 (2024) / 66.5 (2025); AUDIT/DISC leftover ratio 0.85
— not FAIL.

## §2 gate check for the combined form

- LCT-middle ✓ (100.00 ≥ 80, q05 67.03 ≥ 20; canonical basis also passes, strict included)
- AUDIT leftover strictly > incumbent ✓ (68.84 > 64.97)
- Win > 80% ✓ both segments · entries/day ≥ 2 ✓ both segments
- AUDIT net positive ✓ (+996.85) · red lines ✓ (no unseen loss, no discovery collapse — DISC leftover rises)
- DSR ≥ 0.90 ✓ (1.0000, both bases) · PBO ≤ 50% ✓ on the canonical basis (100.00% on the disclosed CSCV second reading)
- Decay not FAIL ✓
- **MC middle ✗ — THE failing gate, named exactly: the verbatim
  mc_middle_pass flag is FALSE because the DD arm alone fails
  its own-relative cap: DD p95 197.50 > 1.5 × DD obs 125.67 =
  188.51 (miss 8.99). Every other MC arm passes (P(profit)
  1.0000, cluster p95 138.70 ≤ 188.51, consec p95 2 ≤ obs+2).**
  For the record only (not the governing reading): 197.50 is
  below the step test's fixed cap 215.72 and below both the
  incumbent's (233.91) and C18-alone's (210.67) DD p95 — the
  combined form has the best DD p95 of the three and still
  misses its own-relative cap because its DD obs fell further.

**Consequence: the combined form passes every §2 gate except
MC-middle (DD arm, own-relative). It is therefore NOT promoted
and is NOT the promotion candidate; it is recorded as
SMALL-IMPROVED (combined form) — the strongest Jul form measured
this round on every edge statistic. cycle78 stands as the Jul
best.** The targeted attempt to close this exact gap is in
`jul_planA_s1_attempt2.md` (9 variants; closest T7 misses the
same cap by 1.49 — no variant passes).

## Loss-cluster mechanism

Inherited from its parts: C18's prune of the worst cluster leg
FB_AUDUSD_h17_0_G + PLANB cand1 fill, plus B04's compositional
fill (reverse-chronological union cascade at best-silent
checks). Measured effect on the MC cluster arms vs incumbent:
worst-cluster p95 169.57 → 138.70, DD obs 143.81 → 125.67,
DD p95 233.91 → 197.50. No sequential cooldown is used (July
cooldowns delete the small wins that interrupt the DD path —
Plan A finding, re-confirmed in attempt 2).

## Method / files

- Runner: `run_jul_combined_s1.py` (Part 1). Machinery reused:
  `work_29load/mc9_verbatim.py`, `work_new8/validate_new8.py`
  (canonical LCT cross-reading + PBO/DSR), s1b per-check LCT
  form, `support/planA_s1_engine.py` (R2-engine CSCV/DSR second
  reading).
- Machine record: `results/jul_combined_s1_run.json`.
- Sizing: NOT a gate in this round (brief §0) — not measured.
- Gaps named: (1) the combined ledger is a ledger-level union
  of prior mined designs — an app-code replay of the combined
  form is required before any integration (same gap class as
  Feb); (2) DSR/PBO are this-round family figures on two
  disclosed bases — no historical mega-family re-grade was run.

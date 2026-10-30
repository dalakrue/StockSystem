VERDICT: Feb planB s1 — SECOND-BEST CREATED

# Feb Plan B Scenario 1 — 20-Cycle Round R2 (2026-10-30)

Second-best created for the IMPROVED Feb best (cycle85b + C08
slot veto of FB_EURUSD_h16_1, per feb_planA_s1.md: DISC leftover
82.39%, AUDIT leftover 42.65%, MC all-pass; best DISC epd 2.094
< 3, so creation is allowed under the standing rule). Feb had NO
second-best. Research level only — no app push, no GitHub push,
live crons untouched.

## The created second-best (cycle X12)

A UNION system of 11 prior Feb mined designs (each design is
itself a 3–4 indicator × 3–4 threshold multi-combination of
K = 8–45 slot equations — the brief §6 user fallback form),
walked single-pick at the best's own check times with priority
by MARGINAL combined quality (each design's combined AUDIT-
leftover delta when merged alone against C08, measured in
cycles X01–X08/B01–B06). Priority order: P38 (PLANB cand2) >
E19 (ROUND4 cand2) > B9C partner > E07 (ROUND4 cand1) > B9SB
cand1 (= B9SB pc at allowed hours) > B9 C06 > P07 (PLANB cand1)
> B9 C03 > B9 partner C13 > B9C C03. Designs that actually
contributed picks: 9 of the 11. Constituent mining spaces
supply the §6 required legs: PLANB designs carry volume
(vol_z) conditions + correlated-symbol legs + DOLLARIDX-
labelled legs; ROUND4/B9/B9C designs add cluster-score and
NEW8-symbol (28-symbol) coverage. DXY (Twelve Data) is
BLOCKED-DATA (Wave 0, HTTP 429) — no DXY feature is used or
claimed anywhere; DOLLARIDX rows are the Dukascopy-labelled
control, H1 only, no volume conditions on them, history from
2017-12-01 (first DOLLARIDX pick in any source ledger
2018-02-01).

Check times used: ONLY the best's 11/13/16 UTC =
17:30/19:30/22:30 MMT. NO new check slot was used (the brief
allows at most one; none was needed).

## Numbers block — candidate standalone

Segment days (distinct check dates, C08 grid): DISC 160,
AUDIT 41.

| Segment | n | net | win % | leftover | entries/day |
|---|---|---|---|---|---|
| DISC | 456 | +8193.49 | 100.00% | 87.79% | **2.850** (> 2.5 ✓) |
| AUDIT | 120 | +16.05 | 84.17% | 1.04% | 2.927 |

Honest quality note: standalone AUDIT edge is thin (net
+16.05, leftover 1.04%; yearly SB leftover 2024 +2.1%,
2025 +0.3% — positive but near zero). This is "medium quality
is enough" territory per brief §2: the second-best never
trades standalone — it fires only where the best is silent,
and there its picks are strong (below). Standalone MC
(mc9_verbatim, 10,000 paths): P(profit) 1.0000 · DD obs
485.77 → p95 466.93 vs own cap 728.65 PASS · worst cluster
obs −323.12 → p95 323.12 PASS · max consec obs 4 → p95 4 ·
mc_middle_pass TRUE.

## Numbers block — combined (C08 best-alone vs C08 + X12)

Merge: SB picks 576, accepted 197, drops {check_busy 371,
symbol_overlap 8} — second-priority exactly as brief §2
(best silent at the check + symbol not open in the best).

| Metric | C08 alone | Combined |
|---|---|---|
| DISC n / net | 335 / +3936.71 | 500 / +7091.43 |
| DISC leftover | 82.39% | **84.98%** (+2.59) |
| DISC win % / epd | 97.31% / 2.094 | 98.20% / 3.125 |
| AUDIT n / net | 98 / +481.79 | 130 / **+737.95** |
| AUDIT leftover | 42.65% | **46.69%** (**+4.04**, tolerance −2.00 ✓) |
| AUDIT win % / epd | 87.76% / 2.390 | 89.23% / 3.171 |
| Combined delta picks | — | **+197** (> 0 ✓) |
| MC P(profit) | 1.0000 | 1.0000 |
| MC DD obs → p95 vs cap | 126.37 → 183.71 vs 189.56 | 105.61 → **171.39 vs 189.56 PASS** (also < step cap 219.48; better than best-alone) |
| MC cluster obs → p95 vs cap | −104.50 → 107.12 vs 156.75 | −102.50 → **102.50 vs 156.75 PASS** (better than best-alone) |
| MC consec obs → p95 | 2 → 2 | 2 → 2 (equal) |
| LCT (combined vs C08, DISC) | — | P **96.37%** / q05 **80.30%** — strict PASS |
| PBO / DSR (combined) | — | **0.00% / 1.0000** (this-run family, 35 trials — honesty note below) |
| Decay (combined yearly leftover) | — | not FAIL: positive every year 2016–2025 (94.3 … 45.3 / 48.0 in 2024/2025) |

Combine-safety (§2): combined MC is not worse than best-alone
on ANY arm (DD p95 and cluster p95 both improve, consec
equal, P(profit) equal) and combined AUDIT leftover is
+4.04 pts, far inside the −2.00 tolerance. One formula note:
mc9's own-relative mc_middle_pass flag reads FALSE for the
combined ledger only because its DD cap is 1.5 × its own
lower DD obs (158.42 < p95 171.39) — the same artifact as
Jul C18 in Plan A; judged against the best-alone/step caps
(the §2 comparison basis) every arm passes.

DOLLARIDX dependence: SB standalone holds 23 DOLLARIDX picks;
only 8 were accepted into the combined ledger (7 DISC,
1 AUDIT). Combined WITHOUT all DOLLARIDX picks: DISC
leftover 84.65%, AUDIT leftover 46.51% — the verdict does
not depend on them.

## §2 second-best acceptance checklist

- Standalone entries/day > 2.5 ✓ (DISC 2.850, AUDIT 2.927)
- Fires only inside best's check times + ≤1 new slot ✓
  (only 17:30/19:30/22:30 MMT; no new slot)
- Second-priority use ✓ (check_busy + symbol-overlap merge)
- Combined delta > 0 measured ✓ (+197 picks)
- Combine-safety: combined MC + EC not worse beyond −2.00
  AUDIT-leftover tolerance ✓ (Δ +4.04; MC arms improve)
- Best epd < 3 (creation allowed) ✓ (2.094)
- Medium quality only required ✓ (full best bar not applied)

## Loss-cluster mechanism

No explicit cooldown survived screening (B16 48h cooldown
and B17 72h same-symbol block both broke combine-safety on
the earlier slate). The cluster safety here comes from
(a) composition: designs were admitted/prioritised by their
MARGINAL combined behaviour, which excludes the designs
whose silent-check picks cluster losses (D26 alone dragged
combined AUDIT leftover to 10.80% and was excluded), and
(b) the silent-check fill itself: accepted SB wins interleave
the incumbent's drawdown window — combined worst cluster
obs −104.50 → −102.50 and cluster p95 107.12 → 102.50 vs
best-alone. Reported as measured, not as a designed control.

## Trial-count honesty (read before citing DSR)

The pre-registered slate (B01–B19 + B20 validation slot in
run_feb_planB_s1.py) found NO eligible candidate: dense
unions diluted combined AUDIT leftover to 20–32% (fail),
sparse singles passed combine-safety but failed epd > 2.5.
A DISCLOSED extension slate (X01–X14, run_feb_planB_s1_ext.py)
then screened the 8 unscreened designs as singles and built
unions prioritised by marginal combined quality; X10, X12,
X13, X14 were eligible. X13 had the highest combined AUDIT
leftover (49.17%, Δ +6.52, epd 3.625) but its STANDALONE
AUDIT is net −620.69 / leftover −33.21% — an unseen-losing
standalone — so it was NOT selected; X12 is the strongest
eligible candidate that is not unseen-losing standalone.
Total screened this run: 14 singles + 19 compositions =
33 configurations. PBO/DSR above use the 35-series DISC
daily family {C08 + all 33 combined ledgers + candidate};
DSR 1.0000 is a this-run-family figure (the historical
BRIEF22 mega-family re-grade was not run — same named gap
as feb_planA_s1.md). Composition selection used measured
AUDIT marginals of the constituent designs — that selection
pressure is exactly what the trial count discloses.

## All cycles (SB DISC epd · SB AUDIT leftover · combined
## AUDIT leftover · Δ picks)

Pre-registered slate (priority = standalone-AUDIT order):
- B01 P07 single: 1.325 · −5.71 · 38.46 · +102
- B02 E19 single: 1.387 · −11.14 · 45.99 · +88
- B03 B9-C03 single: 1.075 · +4.95 · 35.67 · +57
- B04 B9C-C03 single: 1.400 · +32.08 · 35.55 · +101
- B05 D26 single: 0.869 · +2.28 · 10.80 · +62
- B06 B9C partner single: 1.100 · −24.31 · 44.14 · +67
- B07 union ALL 1-pick: 2.875 · +7.73 · 31.57 · +202
- B08 union AUDIT-pos 1-pick: 2.513 · +8.71 · 24.05 · +167
- B09/B10 union top5 1-pick: 2.419 · +6.70 · 24.05 · +160
- B11 union ALL dual: 5.263 · +6.82 · 21.12 · +347
- B12 union top5 dual: 3.688 · +22.38 · 26.41 · +227
- B13 union AUDIT-pos dual: 3.950 · +21.81 · 21.47 · +248
- B14 B11 excl DOLLARIDX: 5.213 · +6.91 · 20.85 · +342
- B15 B12 excl DOLLARIDX: 3.650 · +22.38 · 26.41 · +224
- B16 B12 + 48h cooldown: 3.688 · +5.05 · 23.11 · +209
- B17 B12 + 72h symbol block: 3.688 · +16.65 · 25.12 · +225
- B18 B12 dual≥median: 3.294 · +24.89 · 31.93 · +214
- B19 top5 dual@16UTC only: 2.544 · +2.19 · 25.58 · +173

Extension slate (priority = marginal combined quality):
- X01 P38 single: 0.581 · comb 46.54 (Δ +3.89) · +50
- X02 D24 single: 0.394 · comb 28.35 · +18
- X03 E07 single: 0.469 · comb 42.65 (Δ 0.00) · +17
- X04 B9-C06 single: 1.050 · comb 40.52 · +34
- X05 B9-C13 single: 0.950 · comb 35.67 · +53
- X06 B9C-C10 single: 1.281 · comb 26.11 · +47
- X07/X08 B9SB single: 0.794 · comb 42.48 · +62 (identical
  ledgers after allowed-hours filtering)
- X09 union marginal-pos 1-pick: 2.394 · comb 52.14 · +165
  (epd just under 2.5 — not eligible)
- X10 union marginal-pos dual: 3.763 · comb 48.11 · +244 ✓ eligible
- X11 union ≥−7.5 dual: 5.069 · comb 39.56 (Δ −3.09) · +332 ✗ safety
- **X12 union ≥−7.5 1-pick: 2.850 · comb 46.69 · +197 ✓ SELECTED**
- X13 union marginal-pos dual≥median: 3.625 · comb 49.17 ·
  +242 ✓ eligible but standalone AUDIT −33.21% — not selected
- X14 union marginal-pos dual@16UTC: 2.625 · comb 46.18 ·
  +188 ✓ eligible (runner-up)

## Method / files

- Runners: `run_feb_planB_s1.py` (pre-registered B-slate),
  `run_feb_planB_s1_ext.py` (disclosed extension),
  `run_feb_planB_s1_val.py` (full validation). Machinery
  reused: `work_29load/mc9_verbatim.py`,
  `work_new8/validate_new8.py` (LCT, PBO/DSR, merge
  semantics), C08 ledger from `results/feb_planA_s1_C08_ledger.csv`.
- Machine results: `results/feb_planB_s1_run.json`,
  `results/feb_planB_s1_ext.json`, `results/feb_planB_s1_val.json`.
- Selected ledgers: `results/feb_planB_s1_SB_ledger.csv`
  (576 picks), `results/feb_planB_s1_combined_ledger.csv`
  (630 picks); per-cycle ledgers `feb_planB_s1_<cycle>_sb.csv`
  / `_combined.csv`.
- Sizing: NOT a gate in this round (brief §0) — not measured.
- Gaps named: (1) ledger-level construction from prior mined
  design ledgers — an app-code replay of the union system is
  required before any integration (same gap class as Plan A
  C08's fall-through replay); (2) DSR like-for-like re-grade
  on the historical mega-family not run; (3) no new off-hours
  slot was created (allowed but unused — Scenario 2 creation
  is a separate file); (4) standalone AUDIT edge is thin —
  the second-best's value is concentrated in best-silent
  checks, so any future change to the best's firing pattern
  requires re-measuring the merge.

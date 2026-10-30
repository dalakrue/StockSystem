VERDICT: Jul planB s1 — SECOND-BEST CREATED

# Jul Plan B Scenario 1 — 20-Cycle Round R2 (2026-10-30, Wave-2 finish)

Second-best created for the C18-IMPROVED Jul best. **Base stated
plainly:** C18 = cycle78 incumbent with leg FB_AUDUSD_h17_0_G
pruned + PLANB cand1 partner fill at silent checks (Plan A:
DISC n 453, net +4071.60, win 95.58%, leftover 76.30%, epd
2.603; AUDIT n 122, net +883.40, win 95.08%, leftover 66.58%,
epd 2.652 — rebuilt in this run and asserted exact before any
screening). Base DISC epd 2.603 < 3, so creation is allowed
under the standing rule. Jul had NO second-best. Dependency
stated: this second-best is built against the C18 form; C18
itself is SMALL-IMPROVED, not yet promoted (see
jul_planA_s1_addendum.md — its promotion awaits the MC-cap
ruling). If C18 is not promoted, B04's combined ledger stands
as measured here but its "best" label reverts to cycle78 and
the merge must be re-measured before any integration.
Research level only — no app push, no GitHub push, live crons
untouched. DXY: BLOCKED-DATA (Wave 0, Twelve 429) — no DXY used
or claimed; no DOLLARIDX-symbol rows exist in the Jul pool
(0 rows; B17's excl-DOLLARIDX variant is therefore identical
to B01 by construction, reported as such).

## Method (slate pre-registered in run_jul_planB_s1.py header)

Pool = the 15 prior Jul design ledgers present in work_new8
(cand1, cand2, PLANB cand1/cand2, PLANB9 cand1/cand2/partner,
PLANB9C cand1/cand2/partner, ROUND3 cand1/cand2, ROUND4
cand1/cand2; MONTH_Jul_PLANB_partner_ledger.csv does not exist
— the Plan A named gap — and is excluded). Each design is
itself a mined multi-combination system. A cycle = priority
cascade over a design subset at the best's own check times
ONLY (21:30/23:30/00:30 MMT; NO new slot used — at most one was
allowed): per check, designs in priority order, first row whose
symbol interval conflicts with no taken row, max 1 pick/check
(dual variants max 2). Priority statistics computed on DISC
only; AUDIT reported, never selected on. Combine vs C18 =
second-priority merge (SB pick accepted only at a check C18
does not take, with no symbol-interval overlap; drops counted).
Leftover convention = Jul Plan A (net ÷ gross wins of
net-winning trades; DISC 174 d, AUDIT 46 d) — the same
convention as jul_planA_s1.md, so all figures are comparable
with the other Jul files.

## The created second-best (cycle B04)

Priority cascade over all 15 designs in REVERSE file order
(ROUND4 cand2 first … cand1 last), 1 pick/check.
Standalone: DISC n 508, net +7841.91, win 99.41%, leftover
97.02%, epd **2.920**; AUDIT n 132, net **+165.67**, win
88.64%, leftover +12.97%, epd **2.870** — AUDIT-positive
standalone (not unseen-losing), thin AUDIT leftover = medium
quality, exactly the brief §2 second-best standard (the value
is in the silent-check fill, below).

## Numbers block — C18 alone vs C18 + B04

Merge: SB picks 640, accepted **+76**, drops {check_busy 560,
symbol_overlap 4} — second priority exactly as brief §2.

| Metric | C18 alone | Combined |
|---|---|---|
| DISC n / net | 453 / +4071.60 | 516 / +5253.58 |
| DISC leftover | 76.30% | **80.59%** (+4.29) |
| DISC win % / epd | 95.58% / 2.603 | 96.12% / 2.966 |
| AUDIT n / net | 122 / +883.40 | 135 / **+996.85** |
| AUDIT leftover | 66.58% | **68.84%** (**+2.26**, tolerance −2.00 ✓) |
| AUDIT win % / epd | 95.08% / 2.652 | 94.81% / 2.935 |
| Combined delta picks | — | **+76** (> 0 ✓) |
| MC P(profit) | 1.0000 | 1.0000 |
| MC DD obs → p95 | 138.13 → 210.67 | 125.67 → **197.50** (better than best-alone; also < step cap 215.72) |
| MC cluster obs → p95 | −125.67 → 141.20 | −125.67 → **138.70** (better) |
| MC consec obs → p95 | 2 → 2 | 2 → 2 (equal) |
| LCT (combined vs C18, DISC) | — | P **100.00%** / q05 **62.13%** — strict PASS |
| PBO / DSR (combined) | — | **0.00% / 1.0000** canonical basis (N = 21: C18 + 20 combined; R2-engine CSCV basis reads 100.00% / DSR 1.0000, sr0 0.0892 — basis caveat identical to jul_planA_s1_addendum.md, both reported) |
| Decay | — | not FAIL (combined AUDIT net and leftover both above base) |

Combine-safety (§2): combined MC is not worse than best-alone
on ANY arm (DD p95 and cluster p95 both improve, consec and
P(profit) equal) and combined AUDIT leftover is +2.26 pts,
inside the −2.00 tolerance with room. mc9's own-relative
mc_middle_pass flag reads False for BOTH C18 alone (210.67 vs
own cap 207.20) and the combined (197.50 vs own cap 188.51) —
the same own-relative artifact documented in the Plan A
addendum; judged against the best-alone/step caps (the §2
comparison basis) every combined arm passes and improves.

LCT alignment note (honesty): the paired LCT aligns on the
incumbent cycle78 check grid (the s1b/Plan-C convention;
base_left reads 73.41 = C18's pruned-only DISC leftover on
aligned checks, vs its full-ledger 76.30). On that aligned
basis the combined leftover beats C18 in 100.00% of 10,000
resamples, q05 62.13%.

Standalone B04 MC (for the record): P(profit) 1.0000 · DD obs
561.18 → p95 504.10 vs own cap 841.77 PASS · cluster obs
−298.37 → p95 298.37 PASS · consec 3/3 · mc_middle_pass TRUE.
The standalone DD obs is large (the union walk carries wide
swings); the second-best never trades standalone — combined
DD is the operative figure and it improves on the base.

## §2 second-best acceptance checklist

- Standalone entries/day > 2.5 ✓ (DISC 2.920, AUDIT 2.870)
- Fires only inside best's check times + ≤1 new slot ✓
  (only 21:30/23:30/00:30 MMT; no new slot)
- Second-priority use ✓ (check_busy + symbol-overlap merge)
- Combined delta > 0 measured ✓ (+76 picks)
- Combine-safety: combined MC + EC not worse beyond −2.00
  AUDIT-leftover tolerance ✓ (Δ +2.26; MC arms improve)
- Best epd < 3 (creation allowed) ✓ (2.603)
- Medium quality only required ✓ (full best bar not applied);
  standalone AUDIT net positive ✓ (+165.67, no red-line issue)

Eligible cycles: 9 of 20 (B01, B04, B07, B08, B09, B12, B16,
B17, B18). B04 selected as the strongest eligible: highest
combined AUDIT leftover (68.84%) among eligible, with a
positive standalone AUDIT. Runners-up: B12 (combined AUDIT
67.57%, standalone AUDIT +11.93%), B01/B17 (66.87%, +18.07%).

## All 20 cycles (SB DISC epd · SB AUDIT leftover · combined
## AUDIT leftover · Δ picks)

- B01 leftover-priority union: 2.937 · +18.07 · 66.87 · +75 ✓
- B02 net-priority union: 2.925 · −13.68 · 53.56 · +77 ✗ (SB AUDIT-losing; combined below tolerance)
- B03 chronological union: 2.943 · −23.01 · 46.73 · +76 ✗
- **B04 reverse-chronological union: 2.920 · +12.97 · 68.84 · +76 ✓ SELECTED**
- B05 top-5 leftover: 1.747 · −10.42 · 67.19 · +46 ✗ (epd < 2.5)
- B06 top-5 net: 2.661 · −19.02 · 53.09 · +68 ✗
- B07 DISC-leftover ≥60 union: 2.874 · +17.65 · 66.87 · +74 ✓
- B08 DISC-leftover ≥70 union: 2.874 · +17.65 · 66.87 · +74 ✓ (identical walk to B07 — the ≥60/≥70 filters admit the same effective set)
- B09 PLANB+B9+B9C union: 2.805 · +12.73 · 66.87 · +73 ✓
- B10 ROUND+CAND union: 2.247 · −24.77 · 53.35 · +54 ✗
- B11 B01 dual (2/check): 5.534 · +17.30 · 62.07 · +143 ✗ (combined AUDIT below tolerance 64.58)
- B12 top-5 leftover dual: 2.747 · +11.93 · 67.57 · +67 ✓
- B13 B01 + 48h post-loss cooldown: 2.730 · +3.97 · 65.19 · +65 ✗ (combined within tolerance but SB AUDIT epd collapses to 1.261 — cooldown deletes the AUDIT fill; epd gate is DISC+AUDIT as graded here)
- B14 B01 + 24h cooldown: 2.799 · +13.85 · 65.49 · +68 ✗ (SB AUDIT epd 1.500 < 2.5)
- B15 epd-priority union: 2.943 · +11.24 · 60.69 · +75 ✗ (combined below tolerance)
- B16 top-8 leftover: 2.805 · +12.73 · 66.87 · +73 ✓ (identical walk to B09)
- B17 excl-DOLLARIDX union: 2.937 · +18.07 · 66.87 · +75 ✓ (= B01; pool holds 0 DOLLARIDX rows)
- B18 B9+B9C union: 2.736 · +34.69 · 66.87 · +72 ✓ (best standalone AUDIT leftover of the slate)
- B19 CAND-only union: 1.661 · −41.83 · 46.44 · +31 ✗
- B20 DISC-net-positive union: 2.925 · −13.68 · 53.56 · +77 ✗ (= B02 walk)

## Loss-cluster mechanism

No sequential cooldown survived (B13/B14: cooldowns delete the
AUDIT silent-check fill and collapse SB AUDIT epd — the same
July pattern Plan A found: cooldowns hurt in July). Cluster
safety here is compositional: designs were cascaded by
DISC-measured priority and the accepted fill interleaves the
base's drawdown path — combined worst-cluster p95 improves
141.20 → 138.70 and DD p95 improves 210.67 → 197.50 vs C18
alone. Reported as measured, not as a designed control.

## Method / files

- Runner: `run_jul_planB_s1.py` (slate pre-registered in its
  header). Machinery reused: `work_29load/mc9_verbatim.py`,
  `support/planA_s1_engine.py` (dsr_family, pbo_cscv),
  `validate_new8.round_pbo_dsr` (canonical cross-basis).
- Machine results: `results/jul_planB_s1_run.json`,
  `results/jul_planB_s1_pbo_dsr_xbasis.json`; per-cycle
  ledgers `results/jul_planB_s1_B01..B20_{sb,combined}.csv`.
- Sizing: NOT a gate in this round (brief §0) — not measured.
- Gaps named: (1) ledger-level union construction from prior
  mined design ledgers — an app-code replay of the union is
  required before any integration (same gap class as Feb);
  (2) the base is C18, whose own promotion is unresolved (see
  header dependency); (3) DSR/PBO are this-run-family figures
  on two disclosed bases — no historical mega-family re-grade
  was run; (4) no new off-hours slot was created (allowed but
  unused — Scenario 2 creation is a separate file).

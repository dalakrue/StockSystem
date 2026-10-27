# BRIEF22 MARCH (Plan B) — VALIDATION (2026-10-26)

Incumbent: C86-24 (N=86). Frame A3: DISC 2016–2023 (FIT
2016–2020, HOLDOUT 2021–2023), AUDIT 2024+2025 (read once,
here). Cost @2.5. Exact raw-price replay only (C198 pools +
mar_walk). Gates: BRIEF21.md LOCKED + addendum 1 (middle
overfit: PBO not-HIGH passes, DSR report-only) + addendum 2
(partners within incumbent checks + at most one extra;
conflict-free combination, verified below). Plan B
constraint: app-expressible designs only — no re-entry,
no confirmation vetoes, no vol_z, no ledger state.

Control (A3 battery basis): DISC n 540 net +2717.77 win
92.59 leftover 56.70 | AUDIT n 125 net +512.66 win 92.80
leftover 50.22 epd 2.98.

## Diagnosis that drove the designs (diag22_mar / diag22b_mar)
March's bleed is the FB fallback layer: 273 disc trades,
leftover 19.86, losses −1421.95 of −1720.59 total loss pips;
the scored layer is healthy (267 trades, leftover 84.91).
TIME exits are the loss pool (33 trades, net −933.20; FB
TIME bleeds in both segments: FIT −455.0, holdout −221.3).
FB_EURGBP_h16_2 is toxic in BOTH segments (FIT leftover
−87.38, holdout −186.43); FB_EURCHF_h16 FLIPS (FIT −41.86
via 11 TIME trades −355.7; holdout +50.82 with zero TIME
trades) — an identity veto on EURCHF would be a FIT trap.
The FB bench is toxic everywhere (−28 to −46); the scored
bench is positive in both segments (63.88 / 27.94) but below
the holdout incumbent (69.38).

## FINALIST 1: C20a = C10 (C01 EURGBP veto × C09 dead-breadth day skip)
C01: pick-position veto of FB_EURGBP_h16_2. C09: drop ALL
rows at checks with breadth_m15 < FIT q25 (0.40) — whole-day
regime removal fitted on FIT, applied by value.

- DISC: n 413 net +2317.41 win 93.22 leftover 61.77 (+5.07)
  epd 2.29, account DD 8.62%
- AUDIT: n 101 net +416.76 win 93.07 leftover 49.79
  (control 50.22) epd 2.41, account DD 19.93%
- LCT-middle: paired P 82.66%, own q05 42.38% — PASS
- EC22-middle: 14 vs 15 (candidate fails 8_weeks,
  14_leftover; control fails 14_leftover on this basis) — FAIL
- Monte Carlo (paired, 2,500 paths): median final ratio
  0.0709× control — FAIL; P(call) 0.0000 vs 0.0000 — PASS
- Materiality: DISC +5.07 ≥ +5 PASS; audit leftover 49.79
  < 50.22 — FAIL
- Red lines: audit net +416.76 > 0 PASS; discovery not
  collapsed PASS
- Overfit clause: PBO 2.50% (not HIGH) — PASS; DSR 0.9920
  (report-only)
- Sizing guard (battery): peak margin 5.81% (1:1000 basis),
  max DD 20.99% — PASS
- Loss clusters: DISC max consec 2 (control 2), worst5
  −98.95 (control −100.72), float DD 10.16% (control 13.16%);
  AUDIT max consec 2, worst5 −107.99 (= control), float DD
  27.94% (control 16.94% — worse)
- Conflict-free: TRUE, max concurrency 5

VERDICT C20a: **NOT VALIDATED** (fails EC22 count, Monte
Carlo median, materiality audit clause). The discovery gain
is real (+5.07 with FIT +2.04 AND holdout +12.44) but the
day skip removes 24% of trades and the paired chain — a
compounding race — collapses to 0.0709×; the same
win-by-removal trap that killed February in BRIEF21.

## FINALIST 2: C20b = C01 (FB_EURGBP_h16_2 veto alone)
Pick-position veto of the one both-segments-toxic FB
equation; walk falls through to the next eligible row.
Trade count unchanged (540 / 125).

- DISC: n 540 net +2875.50 win 92.96 leftover 59.09 (+2.39)
  epd 3.00, DD 9.85%
- AUDIT: n 125 net +512.66 win 92.80 leftover 50.22 —
  IDENTICAL to control (the equation never fires in the
  audit walk; the veto is discovery-only in effect)
- LCT-middle: paired P 95.99%, own q05 41.59% — PASS
  (STRICT also passes)
- EC22-middle: 15 vs 15 (both fail only 14_leftover) — PASS
- Monte Carlo (paired): median final ratio 2.4263× control
  — PASS; P(call) 0.0000 vs 0.0000 — PASS
- Materiality: DISC +2.39 < +5 — FAIL (sole miss); audit
  leftover 50.22 ≥ 50.22 — PASS
- Red lines: PASS both. Overfit: PBO 2.50% (not HIGH)
  PASS; DSR 0.9391 report-only
- Sizing guard: peak margin 5.84%, max DD 11.28% — PASS
- Loss clusters: DISC max consec 2, worst5 −100.72, float
  DD 12.87% (control 13.16%); AUDIT identical to control
- Conflict-free: TRUE, max concurrency 5
- App-expressible: YES — a static equation exclusion in
  the pick rule (stateless, no features, no state)

VERDICT C20b: **SMALL** (all core gates pass; materiality
discovery clause missed). The first March candidate in the
programme to pass every core gate — BRIEF21's finalists
failed nearly all of them.

## FINALIST 3: C20c = C10 × C16 (breadth skip + veto base, de-risked dual legs)
C16 legs (scored-regime second picks resimmed at TP ×0.80)
rebuilt on the C10 base: 83 legs.

- DISC: n 481 net +2591.16 win 93.35 leftover 60.46 (+3.76)
- AUDIT: n 116 net +387.10 win 92.24 leftover 41.93 — FAIL
- LCT-middle: P 80.23%, q05 43.97% — PASS (marginal P)
- EC22-middle: 14 vs 15 — FAIL
- Monte Carlo: median ratio 0.2589× — FAIL; P(call) 0 vs 0 PASS
- Materiality: FAIL both clauses
- Conflict-free: **FALSE** — combine-built legs on a base
  whose walk did not carry them create a same-symbol
  overlap (the leg's symbol is re-picked by the base walk
  inside the leg's resimmed flight); the C10 base's breadth
  skip poisons the chain in any case

VERDICT C20c: **NOT VALIDATED**.

## MARCH PLAN-B VERDICT: NO IMPROVEMENT (at the HUGE bar) — best result SMALL (C01)

Twenty genuinely different, app-expressible cycles. March
keeps C86-24. What each new family did on March's anatomy:

- **FB identity surgery — WORKS, small.** Vetoing the one
  both-segments-toxic FB equation (EURGBP_h16_2) gains
  +2.39 discovery with FIT and holdout BOTH up, passes
  every core gate incl. LCT-strict and a 2.43× Monte Carlo
  median. It is small because the equation is small
  (13 disc trades) — and the audit never sees it.
- **Whole-day regime removal (breadth skip) — real on
  discovery, dead at the gates.** +1.99 alone, +5.07
  composed with the veto (FIT +2.04, holdout +12.44 — the
  best discovery composition March has produced). It dies
  three ways: the chain compounds trade count (0.0709×),
  EC22 loses 8_weeks, and audit leftover slips 0.43 under
  the incumbent. Win-by-removal is now 0-for-3 against the
  Monte Carlo median across the programme (Feb BRIEF21,
  Mar BRIEF22 ×2).
- **Exit surgery — dead in every form, two rounds.**
  MFE-conditioned zombie cut −7.35 (FB-scoped −2.38): even
  "never went favourable by 24h" does not separate March's
  TIME losers from its slow recoverers. With BRIEF21's
  blunt cut (−15.00), 36h cap (−10.81) and trailing stop
  (0.00), the exit-rule family is exhausted for March.
- **FB stop tightening −12.06**: drifters convert from
  −30 TIME exits into −60 stops. **Target expansion
  −17.44 / −23.40**: March's edge IS the fast small target;
  geometry is a dead end in both directions (contraction
  was +0.15 in BRIEF21).
- **Fall-through feature vetoes (asia-calm −17.62,
  VWAP-extension −8.35)**: in March the M08 top pick is
  far better than the next eligible row — substituting is
  toxic even when the vetoed pick is genuinely worse than
  average. Removal only helps when it removes the whole
  check (breadth) or the whole equation (EURGBP).
- **Partners — all dilute holdout.** Scored-regime dual
  −0.26 (holdout −6.46), FB-regime completion −1.35,
  never-lost whitelist −4.61, complex diversifier −0.29,
  Asia-active −0.98, multi-pick +0.14 (holdout −5.03).
  The holdout bench (leftover ~24–28) cannot feed a
  69.38-leftover incumbent. The ONE exception: de-risked
  legs at TP ×0.80 (C16, +1.66 / holdout +0.50) — the
  contracted geometry is what makes partner legs survivable
  in March, but the size is negligible and stacking them
  onto the skipped-day base breaks conflict-freedom.
- **Fresh signals at a new check (18:30) −24.22**: fourth
  confirmation across rounds that fresh-signal legs are
  decisively negative in this frame.

March's structure, measured twice now: a healthy scored
core (84.91) carrying a mediocre fallback layer (19.86)
whose damage is diffuse TIME-drift rather than separable
bad trades; every intervention that touches trade
SELECTION at the same check substitutes worse rows, every
intervention that touches EXITS amputates recoverers, and
every removal that works on discovery is taxed by the
chain for the trades it removed. The remaining honest
gain is the small one: C01 stands as March's recorded
Plan B best (SMALL, fully app-expressible) if the user
ever wants it.

Nothing integrated, nothing pushed (verdict only, per
orders).

# FIX NOTES 2026-10-29 — Lane-reconciliation bests (Mar / Nov / Dec)

User order (2026-10-29 ~08:52 MMT): install the parallel-lane
reconciliation winners (LANE_RECONCILIATION_20261029.md) as the
March, November and December BEST systems, apply the new
second-best rule (a second is kept only when the new best's
standalone discovery entries/day is below 3; all three new bests
measure >= 3, so no second-best slot changes), push to Git only.

## New systems (core/signal_mode.py MONTH_SYSTEMS)

- March: cycle86b -> **cycle86c** (core/cycle86c_best.py).
  P-REPLACE Track A C06 (design 'mar_rp', 30 equations): a
  REPLACEMENT layer -- the candidate claims 11 (symbol, hour-16
  UTC) slots (AUDNZD, AUDUSD, CHFJPY, EURAUD, EURCHF, EURJPY,
  NZDCAD, NZDCHF, NZDUSD, USDCAD, USDJPY); incumbent rows at
  claimed slots are displaced (176 research rows), candidate
  picks merge against the kept rows only; research revert set
  is empty. New core.new8_candidate.ReplacedMergedWalkState
  carries the semantics. Validated: DISC leftover 66.10 ->
  78.27, AUDIT 8.84 -> 22.99, LCT 100%, MC PASS (HUGE).
- November: cycle93q -> **cycle93r** (core/cycle93r_best.py).
  P-REPLACE Track A C04 (design 'nov_rp', 30 equations) merged
  over the shipped cycle93q+93s combined stream. Validated:
  DISC leftover +0.20, AUDIT +0.38, LCT 99.59%, MC PASS.
- December: cycle94b -> **cycle94c** (core/cycle94c_best.py).
  P-REGIME stack in research order: Track A C07 (design
  'dec_rg', 30 equations) then Plan C C07 (design 'dec_rgc',
  30 equations), one merged walk over the shipped
  cycle94b+94s combined stream. December winner on the user's
  AUDIT tiebreak rule. Caveat (report, not a gate): peak
  margin 191.95% at Best N / 3 sizing in the lane.

Seconds unchanged: Mar cycle86s, Nov cycle93s, Dec cycle94s.
Pairing deltas on discovery (second provably adds entries to
the new best): Mar +41 picks / +0.228 epd, Nov +98 / +0.563,
Dec +117 / +0.669. New-best standalone discovery epd:
Mar 3.122, Nov 3.885, Dec 4.406 (all >= 3 -> rule: no
second-best change). Best N unchanged (86 / 83 / 105; /3
values in the router updated to the new names).

## Feature ports

- core/new8_features.py: add_pr_columns + add_rp_columns
  (P-REGIME / P-REPLACE transforms of the planb9c superset,
  verbatim from the lane builders); the b3 block gained the
  planb3 er10 column those transforms read. Bit-exact audit
  vs the lane frames (work_29load/check_pr_rp.py): every
  column the four designs read is exact; the only differing
  columns (pr_g_dxy, rp_rsi_dxy -- read by no installed
  equation of these designs) diverge solely on the first 12
  bars of the DOLLARIDX series (2017-12-01 02:00-13:00 UTC),
  an RSI seed-window difference in the base block.
- core/new8_candidate.py: CandidateContext group order gained
  'pr' / 'rp'; ReplacedMergedWalkState + load_replaced_state.
- core/new8_designs.py: designs mar_rp, nov_rp, dec_rg,
  dec_rgc (scores recomputed by standalone discovery
  evaluation in work_29load/gen_designs4.py, cross-checked
  against the stored candidate ledgers, zero mismatches).

## Gates (work_29load/harness4.py, run twice per layer)

- mar_rp: walk 204/204 exact; combined 695/695 exact,
  order-equal (148 accepted, 176 displaced, 0 reverted).
- nov_rp: walk 213/213 exact; combined 826/826 exact,
  order-equal (6 accepted).
- dec_rg: walk 312/312 exact; combined 952/952 exact,
  order-equal (3 accepted).
- dec_rgc: walk 210/210 exact; final combined 954/954 exact,
  order-equal (2 accepted) -- the gate target is the lane's
  FINAL stack ledger (Track A + Plan C), per the P-REGIME
  verdict's reference chain.
- Controls (pre-change combined forms) reproduced exactly:
  Mar 723/723, Nov 820/820, Dec 949/949.

## Wiring

- core/signal_mode.py: MONTH_SYSTEMS 3/11/12 -> cycle86c /
  cycle93r / cycle94c; Best N maps, set_active_system,
  describe_active, evaluate/select branches, ledger-aware
  combined tuple and check hours for the three systems.
- ui/field3_multisymbol_regime_summary_20260722.py: combined
  panel best_id/labels for Mar/Nov/Dec; the March standalone
  panel and the December dedicated window now call the new
  modules (session-state keys unchanged).
- Tests: work_29load/test_28load4.py ALL PASS; freshness
  suite ALL PASS on the push candidate; 12-panel regression
  clean; panel smokes for the three new modules exact on
  candidate rows (see UPDATE_20261029.md in work_29load for
  the full record).

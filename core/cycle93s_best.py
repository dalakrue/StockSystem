"""Cycle 93S (NEW8 P-BRANCH Track B design R12) --
November SECOND-BEST system, integrated 2026-10-28
(phase 2) on the user's order to install all four
second-bests found by the 2026-10-28 scan
(SECONDBEST_SCAN_20261028.md); the order is his
waiver for the candidate's NEARLY items named below.
It replaces cycle93n as November's second best (the
pre-P-BRANCH November best, kept as second best in
phase 1; cycle93n remains selectable standalone).

The standalone Track B candidate design R12 (12
OR-branch equations, S-CLU3D ranking, K=12, no veto;
symbols AUDNZD, EURJPY, GBPCAD, NZDCAD; each equation
fires when ANY of its branches fires, each branch
with its own exit pair and hold), run as November's
second-priority system in the combined layer behind
cycle93q: evaluated only when the best produces no
entry at a check (the combined-layer rule in
core.signal_mode). Its check grid is the best's
hours (9, 13, 15 UTC) plus its Track B extra hour
10 UTC -- the November panel windows include hour 10
for exactly this reason.

Research verdict (parallel_score/
MONTH_Nov_PBRANCHSB_VERDICT.md, @2.5): NOT CREATED in
its round on the standalone DISC entries/day floor
(1.063 vs > 2.5), the standalone AUDIT net (-305.09,
leftover -64.15%) and LCT-middle. The user's phase-2
order installs it anyway. NOT waived and passed:
Monte Carlo middle (own sequence AND combined2),
combined cluster-not-worse, combine-safety STRICT
PASS (delta AUDIT net +188.69, delta AUDIT leftover
+3.66 pts), PBO 0.0% LOW, DSR 1.0, combined AUDIT
net > 0. Standalone: DISC n185 net +2,016.32
leftover 100.00%. Merged over the cycle93q best
(combined2, 820 rows): accepted 124, DISC n671 net
+8,907.07, AUDIT n149 net +967.40. App replay of the
candidate walk + combined2 merge EXACT (twice) --
see work_29load/UPDATE_20261028_PHASE2.md.

Design data frozen in core.new8_designs ('nov_pbsb');
features by core.new8_features.
"""

from __future__ import annotations

import pandas as pd

CYCLE93S_CHECK_HOURS = (9, 10, 13, 15)
DESIGN = "nov_pbsb"
SYSTEM_NAME = "cycle93s"
_DESIGN_SYMBOLS = ("AUDNZD", "EURJPY", "GBPCAD",
                   "NZDCAD")


def _cand_m15(m15_frames):
    """The design's branch features need M15 (with
    Volume) for its symbols; top up via the shared
    path."""
    from core.new8_candidate import ensure_m15
    return ensure_m15(m15_frames, _DESIGN_SYMBOLS)


def evaluate_cycle93s_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """R12 candidate signal rows at one check (one row
    per firing equation)."""
    from core.new8_candidate import CandidateContext
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           (DESIGN,))
    return ctx.signal_frame(DESIGN, check_time_utc)


def select_cycle93s_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """The candidate walk's single pick under the
    panel's occupancy: top-1 by score, skipping open
    symbols."""
    from core.new8_candidate import select_walk_pick
    return select_walk_pick(signals, open_symbols=open_symbols)


def is_cycle93s_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE93S_CHECK_HOURS and t.minute == 30

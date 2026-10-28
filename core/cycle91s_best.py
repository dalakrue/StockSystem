"""Cycle 91S (NEW8 Plan B-9 Track B design R14) --
September SECOND-BEST system, integrated 2026-10-28 on
the user's order with an explicit scoped waiver
(September only, non-precedential).

The standalone Track B candidate design R14 (40
equations, S-LEFT ranking, K=40, no veto; symbols
EURAUD, EURCAD, EURNZD, GBPAUD, GBPCAD, GBPJPY, GBPUSD),
run as September's second-priority system in the
combined layer behind cycle91p: it is evaluated only
when the best produces no entry at a check (the
combined-layer rule in core.signal_mode). Its check
grid is the best's hours (1, 10, 11 UTC) plus its Track
B extra hour 2 UTC -- the September panel windows
include hour 2 for exactly this reason (see
core.cycle91p_best).

Research verdict (MONTH_Sep_PLANB9SB_VERDICT.md, @2.5):
the creation decision was NOT CREATED on two items,
both waived for September only by the user's order of
2026-10-28: (1) the standalone DISC entries/day > 2.5
creation floor (candidate 1.468), and (2) the strict
combine item delta AUDIT leftover >= 0 (candidate
-2.01, 0.01 beyond the -2.00 tolerance). Everything
else passed and was NOT waived: Monte Carlo middle
(own + combined, cluster-not-worse), LCT-middle, PBO
0% LOW, combined delta AUDIT net +195.63, combined
AUDIT net > 0. Standalone: DISC n251 net +6,970.68
leftover 100.00%, AUDIT n59 net +598.69 leftover
48.33%. Merged over the cycle91p best (combined2, 677
rows): DISC n541 leftover 68.60%, AUDIT n136 leftover
69.49%; the design's 310 walk picks added 47 (41 of
them at the extra hour 2). App replay of the candidate
walk + combined2 merge EXACT -- see
work_29load/UPDATE_20261028.md.

Design data frozen in core.new8_designs ('sep_b9sb');
features by core.new8_features.
"""

from __future__ import annotations

import pandas as pd

CYCLE91S_CHECK_HOURS = (1, 2, 10, 11)
DESIGN = "sep_b9sb"
SYSTEM_NAME = "cycle91s"
_DESIGN_SYMBOLS = ("EURAUD", "EURCAD", "EURNZD", "GBPAUD",
                   "GBPCAD", "GBPJPY", "GBPUSD")


def _cand_m15(m15_frames):
    """The design's volm_* columns need M15 (with Volume)
    for its symbols; top up via the shared path."""
    from core.new8_candidate import ensure_m15
    return ensure_m15(m15_frames, _DESIGN_SYMBOLS)


def evaluate_cycle91s_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """R14 candidate signal rows at one check (one row per
    firing equation)."""
    from core.new8_candidate import CandidateContext
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           (DESIGN,))
    return ctx.signal_frame(DESIGN, check_time_utc)


def select_cycle91s_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """The candidate walk's single pick under the panel's
    occupancy: top-1 by score, skipping open symbols."""
    from core.new8_candidate import select_walk_pick
    return select_walk_pick(signals, open_symbols=open_symbols)


def is_cycle91s_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE91S_CHECK_HOURS and t.minute == 30

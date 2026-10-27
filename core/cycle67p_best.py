"""Cycle 67P (NEW8 Plan-B P07) -- August SECOND-BEST
system, integrated 2026-10-27 on the user's order
(29-symbol build).

The standalone NEW8 Plan-B candidate design P07 for August
(22 equations, S-AVGL ranking), run as August's
second-priority system in the combined layer behind
C67-04 (cycle67): it is evaluated only when the best
produces no entry at a check (the combined-layer rule in
core.signal_mode).

Research pairing (@2.5): merged over the C67-04 ledger
under incumbent-priority occupancy the design added 74 of
its 143 walk picks (combined Aug_PLANB_combined.csv, 766
rows). App replay of the candidate walk + merge EXACT --
see work_29load/BUILD_RESULT.md.

Design data frozen in core.new8_designs ('aug_p07');
features by core.new8_features.
"""

from __future__ import annotations

import pandas as pd

CYCLE67P_CHECK_HOURS = (1, 6, 16, 17, 18)
DESIGN = "aug_p07"
SYSTEM_NAME = "cycle67p"


def evaluate_cycle67p_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """P07 candidate signal rows at one check (one row per
    firing equation)."""
    from core.new8_candidate import CandidateContext
    ctx = CandidateContext(frames, m15_frames, (DESIGN,))
    return ctx.signal_frame(DESIGN, check_time_utc)


def select_cycle67p_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """The candidate walk's single pick under the panel's
    occupancy: top-1 by score, skipping open symbols."""
    from core.new8_candidate import select_walk_pick
    return select_walk_pick(signals, open_symbols=open_symbols)


def is_cycle67p_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE67P_CHECK_HOURS and t.minute == 30

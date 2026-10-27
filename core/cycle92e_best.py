"""Cycle 92E (NEW8 Round-4 E07) -- October SECOND-BEST
system, integrated 2026-10-27 on the user's order
(29-symbol build).

The standalone NEW8 Round-4 candidate design E07 for
October (18 equations on GBPAUD/GBPNZD), run as October's
second-priority system in the combined layer behind
C92-24/C155 (cycle92): it is evaluated only when the best
produces no entry at a check (the combined-layer rule in
core.signal_mode).

Research pairing (validate pass, @2.5): merged over the
C155 ledger under incumbent-priority occupancy the design
added 61 of its 241 walk picks (combined
Oct_ROUND4_combined.csv, 553 rows) -- DISC leftover
80.50 -> 85.07 with AUDIT leftover -4.55, which is why it
was REJECTED as a best-system improvement and stands here
as the user-ordered second best only. App replay of the
candidate walk + merge EXACT -- see
work_29load/BUILD_RESULT.md.

Design data frozen in core.new8_designs ('oct_e07');
features by core.new8_features.
"""

from __future__ import annotations

import pandas as pd

CYCLE92E_CHECK_HOURS = (15, 17, 18)
DESIGN = "oct_e07"
SYSTEM_NAME = "cycle92e"


def evaluate_cycle92e_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """E07 candidate signal rows at one check (one row per
    firing equation)."""
    from core.new8_candidate import CandidateContext
    ctx = CandidateContext(frames, m15_frames, (DESIGN,))
    return ctx.signal_frame(DESIGN, check_time_utc)


def select_cycle92e_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """The candidate walk's single pick under the panel's
    occupancy: top-1 by score, skipping open symbols."""
    from core.new8_candidate import select_walk_pick
    return select_walk_pick(signals, open_symbols=open_symbols)


def is_cycle92e_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE92E_CHECK_HOURS and t.minute == 30

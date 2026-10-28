"""Cycle 86S (NEW8 Plan B-6 SB-REDO design R17) --
March SECOND-BEST system, integrated 2026-10-28
(phase 2) on the user's order to install all four
second-bests found by the 2026-10-28 scan
(SECONDBEST_SCAN_20261028.md); the order is his
waiver for the candidate's NEARLY items named below.
March's second slot was empty: with this install the
March panel becomes a combined best + second-best
panel like the other combined months.

The standalone Track B candidate design R17 (40
equations, S-LEFT ranking, K=40, no veto; symbols
CHFJPY, EURAUD, EURJPY, GBPJPY, GBPNZD), run as
March's second-priority system in the combined layer
behind cycle86b: it is evaluated only when the best
produces no entry at a check (the combined-layer rule
in core.signal_mode). Its check grid is the best's
hours (11, 16, 17 UTC) plus its Track B extra hour
12 UTC -- the March panel windows include hour 12 for
exactly this reason.

Research verdict (MONTH_Mar_PLANB6SB2_VERDICT.md,
@2.5): NOT CREATED in its round on the standalone
DISC entries/day floor (1.072 vs > 2.5), the
standalone AUDIT net (-457.49, leftover -37.63%) and
the strict combine-safety items (delta AUDIT net
-395.80, delta AUDIT leftover -41.38 pts; combined
AUDIT leftover falls 50.22% -> 8.84%). The user's
phase-2 order installs it anyway. NOT waived and
passed: Monte Carlo middle (own sequence recorded;
combined2 fresh PASS), PBO 0.00% LOW, DSR 1.0000,
LCT-middle 100.00% / 55.60%, combined AUDIT net
+116.86 > 0. Standalone: DISC n193 net +6,178.53
leftover 100.00%. Merged over the cycle86b best
(combined2, 723 rows): accepted 58, DISC n582 net
+4,208.72, AUDIT n141 net +116.86. App replay of the
candidate walk + combined2 merge EXACT (twice) --
see work_29load/UPDATE_20261028_PHASE2.md.

Design data frozen in core.new8_designs ('mar_b6sb2');
features by core.new8_features (the Plan B-6 nested
columns are the 'b6' feature group).
"""

from __future__ import annotations

import pandas as pd

CYCLE86S_CHECK_HOURS = (11, 12, 16, 17)
DESIGN = "mar_b6sb2"
SYSTEM_NAME = "cycle86s"
_DESIGN_SYMBOLS = ("CHFJPY", "EURAUD", "EURJPY",
                   "GBPJPY", "GBPNZD")


def _cand_m15(m15_frames):
    """The design's volume / confirmation columns need
    M15 (with Volume) for its symbols; top up via the
    shared path."""
    from core.new8_candidate import ensure_m15
    return ensure_m15(m15_frames, _DESIGN_SYMBOLS)


def evaluate_cycle86s_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """R17 candidate signal rows at one check (one row
    per firing equation)."""
    from core.new8_candidate import CandidateContext
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           (DESIGN,))
    return ctx.signal_frame(DESIGN, check_time_utc)


def select_cycle86s_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """The candidate walk's single pick under the
    panel's occupancy: top-1 by score, skipping open
    symbols."""
    from core.new8_candidate import select_walk_pick
    return select_walk_pick(signals, open_symbols=open_symbols)


def is_cycle86s_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE86S_CHECK_HOURS and t.minute == 30

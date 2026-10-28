"""Cycle 87S (NEW8 P-VOTE Track B fallback design
R13) -- April SECOND-BEST system, integrated
2026-10-28 (phase 2) on the user's order to install
all four second-bests found by the 2026-10-28 scan
(SECONDBEST_SCAN_20261028.md); the order is his
waiver for the candidate's NEARLY items named below.
It replaces cycle87 as April's second best (the
pre-P-VOTE April best; cycle87 remains selectable
standalone).

The standalone Track B fallback candidate design R13
(40 vote-threshold equations, S-CLU3D ranking, K=40,
no veto; symbols CADJPY, GBPJPY, NZDJPY, USDCHF,
USDJPY; every equation is a single condition on a
pv_ vote-pool BUY share -- pools V01, V07, V10, V13,
V14, V15), run as April's second-priority system in
the combined layer behind cycle87c: evaluated only
when the best produces no entry at a check (the
combined-layer rule in core.signal_mode). Its check
grid is the best's hours (16, 17, 18 UTC) plus its
Track B extra hour 19 UTC -- the April panel windows
include hour 19 for exactly this reason.

Research verdict (parallel_vote/
MONTH_Apr_PVOTESB_VERDICT.md, @2.5): NOT CREATED in
its round on the standalone DISC entries/day floor
(0.550 vs > 2.5), the standalone AUDIT net (-272.89,
leftover -44.20%), its own-sequence Monte Carlo
middle, LCT-middle (P 76.64% vs the 80% line) and
the strict combine-safety items (delta AUDIT net
-41.87, delta AUDIT leftover -7.80 pts). The user's
phase-2 order installs it anyway. NOT waived and
passed: combined2 Monte Carlo middle,
cluster-not-worse, PBO 0.0% LOW, DSR 1.0, combined
AUDIT net > 0. Standalone: DISC n93 net +1,551.31
leftover 89.64%. Merged over the cycle87c best
(combined2, 946 rows): accepted 44, DISC n747 net
+6,620.36, AUDIT n199 net +1,929.49. App replay of
the candidate walk + combined2 merge EXACT (twice)
-- see work_29load/UPDATE_20261028_PHASE2.md.

Design data frozen in core.new8_designs ('apr_pvsb');
features by core.new8_features.
"""

from __future__ import annotations

import pandas as pd

CYCLE87S_CHECK_HOURS = (16, 17, 18, 19)
DESIGN = "apr_pvsb"
SYSTEM_NAME = "cycle87s"
_DESIGN_SYMBOLS = ("CADJPY", "GBPJPY", "NZDJPY",
                   "USDCHF", "USDJPY")


def _cand_m15(m15_frames):
    """The design's vote legs need M15 (with Volume)
    for its symbols; top up via the shared path."""
    from core.new8_candidate import ensure_m15
    return ensure_m15(m15_frames, _DESIGN_SYMBOLS)


def evaluate_cycle87s_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """R13 candidate signal rows at one check (one row
    per firing equation)."""
    from core.new8_candidate import CandidateContext
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           (DESIGN,))
    return ctx.signal_frame(DESIGN, check_time_utc)


def select_cycle87s_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """The candidate walk's single pick under the
    panel's occupancy: top-1 by score, skipping open
    symbols."""
    from core.new8_candidate import select_walk_pick
    return select_walk_pick(signals, open_symbols=open_symbols)


def is_cycle87s_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE87S_CHECK_HOURS and t.minute == 30

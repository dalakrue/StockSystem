"""Cycle 94S (NEW8 Plan B-6 SB-REDO design R18) --
December SECOND-BEST system, integrated 2026-10-28
(phase 2) on the user's order to install all four
second-bests found by the 2026-10-28 scan
(SECONDBEST_SCAN_20261028.md); the order is his waiver
for the candidate's NEARLY items named below.

The standalone Track B candidate design R18 (60
equations, S-CLU3 ranking, K=60, no veto; symbols
EURAUD, EURNZD, GBPAUD, GBPCAD, GBPJPY, GBPNZD), run
as December's second-priority system in the combined
layer behind cycle94b: it is evaluated only when the
best produces no entry at a check (the combined-layer
rule in core.signal_mode). Its check grid is the
best's hours (10, 11, 13 UTC) plus its Track B extra
hour 14 UTC -- the December panel windows include
hour 14 for exactly this reason.

Research verdict (MONTH_Dec_PLANB6SB2_VERDICT.md,
@2.5): NOT CREATED in its round on the standalone
DISC entries/day floor (1.086 vs > 2.5) and the
strict combine-safety items (delta AUDIT net -52.79,
delta AUDIT leftover -22.34 pts vs the B-6 reference
best); standalone AUDIT leftover only 9.41%. The
user's phase-2 order installs it anyway. NOT waived
and passed: Monte Carlo middle (own sequence), PBO
0.00% LOW, DSR 1.0000, LCT-middle 100.00% / 71.25%,
combined AUDIT net > 0. Standalone: DISC n190 net
+5,749.66 leftover 100.00%, AUDIT n49 net +92.82.
Merged over the reference best (combined2, 960
rows): accepted 139. Merged over the app's cycle94b
best (BRIEF21 C20a, 807 rows -- the app gate basis):
949 rows, accepted 142, DISC n767 net +8,774.26,
AUDIT n182 net +1,082.78. App replay of the
candidate walk + combined2 merge EXACT (twice) --
see work_29load/UPDATE_20261028_PHASE2.md.

Design data frozen in core.new8_designs ('dec_b6sb2');
features by core.new8_features (the Plan B-6 nested
columns are the 'b6' feature group).
"""

from __future__ import annotations

import pandas as pd

CYCLE94S_CHECK_HOURS = (10, 11, 13, 14)
DESIGN = "dec_b6sb2"
SYSTEM_NAME = "cycle94s"
_DESIGN_SYMBOLS = ("EURAUD", "EURNZD", "GBPAUD",
                   "GBPCAD", "GBPJPY", "GBPNZD")


def _cand_m15(m15_frames):
    """The design's volume / confirmation columns need
    M15 (with Volume) for its symbols; top up via the
    shared path."""
    from core.new8_candidate import ensure_m15
    return ensure_m15(m15_frames, _DESIGN_SYMBOLS)


def evaluate_cycle94s_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """R18 candidate signal rows at one check (one row
    per firing equation)."""
    from core.new8_candidate import CandidateContext
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           (DESIGN,))
    return ctx.signal_frame(DESIGN, check_time_utc)


def select_cycle94s_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """The candidate walk's single pick under the
    panel's occupancy: top-1 by score, skipping open
    symbols."""
    from core.new8_candidate import select_walk_pick
    return select_walk_pick(signals, open_symbols=open_symbols)


def is_cycle94s_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE94S_CHECK_HOURS and t.minute == 30

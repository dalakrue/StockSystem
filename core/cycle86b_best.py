"""Cycle 86B (C86-24 + BRIEF22 C01 veto) -- March H1
system, integrated 2026-10-27 on the user's order
(two-phase update, Phase 1b).

Definition: the shipped March system cycle86 (C86-24:
frozen C62-10 engine minus FB_USDCAD_h16_1, M08 Reject15
rerank, FB TP x0.95 -- core.cycle86_best, frozen) plus the
BRIEF22 Plan B C01 pick-position veto: FB_EURGBP_h16_2 is
removed from what March trades. In the research walk the
veto drops the equation from eligibility BEFORE the M08
rule (lib21_mar.pick_with_veto), so removing it from the
delegated equation list is the identical construction;
the walk falls through to the next eligible candidate and
the trade count is unchanged.

Validated numbers (BRIEF22 March, @2.5): C01 = SMALL
improvement -- DISC n540 net +2,875.50, win 92.96%,
leftover 59.09% (control 56.70%, +2.39); AUDIT identical
to control (the equation never fires on the audit slice:
n125 net +512.66, leftover 50.22%); LCT P 95.99% / q05
41.59% (middle + strict). App replay EXACT against
brief22 val_logs/C20B_disc.csv + C20B_audit.csv -- see
work_29load/UPDATE_20261027.md. March stays best-only.
Best N unchanged (86, as C86-24).
"""

from __future__ import annotations

import pandas as pd

import core.cycle86_best as _c86
from core.cycle86_best import (CYCLE86_CHECK_HOURS,
                               is_cycle86_check_time)

CYCLE86B_CHECK_HOURS = CYCLE86_CHECK_HOURS
_DROP_IDS = ("FB_EURGBP_h16_2",)

C86B_EQUATIONS = [e for e in _c86.C86_EQUATIONS
                  if e["id"] not in _DROP_IDS]
assert len(C86B_EQUATIONS) == len(_c86.C86_EQUATIONS) - 1
assert all(e["id"] not in _DROP_IDS for e in C86B_EQUATIONS)


def evaluate_cycle86b_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """C86-24 signals with FB_EURGBP_h16_2 also removed:
    the frozen cycle62 engine is delegated to with the
    cycle86 equation list swapped to the C86B list for the
    duration of the call (the module-level swap pattern of
    cycle85/cycle86), then cycle86's own post-processing
    (FB TP x0.95 + M08 flags) is applied by re-running its
    evaluate body on the swapped list."""
    import core.cycle62_best as _c62
    orig62 = _c62.CYCLE62_EQUATIONS
    orig86 = _c86.C86_EQUATIONS
    _c86.C86_EQUATIONS = C86B_EQUATIONS
    try:
        return _c86.evaluate_cycle86_signals(
            frames, check_time_utc, m15_frames=m15_frames)
    finally:
        _c86.C86_EQUATIONS = orig86
        _c62.CYCLE62_EQUATIONS = orig62


def select_cycle86b_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: the frozen C86-24
    selection (M08 Reject15 rerank)."""
    return _c86.select_cycle86_entries(
        signals, open_symbols=open_symbols)


def is_cycle86b_check_time(ts) -> bool:
    return is_cycle86_check_time(ts)

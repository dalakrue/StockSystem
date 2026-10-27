"""Cycle 88 (C88-03) -- May H1 system, PROMOTED 2026-10-21
(Program 4 retry round; BRIEF6 priorities).

C64-09 IS FROZEN as the entry engine (core.cycle64_best,
checks at 10:00 / 16:00 / 18:00 UTC, exactly 1 entry/check).
Cycle 88 changes exactly one thing: the ENTIRE TREND-fallback
(FB_*) layer is removed -- all 9 FB legs. The 15 mined
primaries plus the 6 added legs of C64-09 survive
byte-identical (21 equations). Partial FB cuts backfired in
the research round via occupancy refills; the full cut was
the clean repair.

Verified numbers (C88-03): paired LCT-middle AND LCT-strict
PASS vs C64-09 (P 100.00%, own 5th-percentile 84.43%);
unseen leftover 58.69% vs 48.33%, unseen net +377.0 vs
+373.0, 2.23 entries/day, win 91.84%; discovery net
+3,863.2, discovery leftover 94.44% (362 trades, 2 losses).
Best N 66 (own sizing run: peak margin 46.69%, max DD
0.13%). C64-09 remains selectable as cycle64.

Implementation: the frozen cycle64 engine is delegated to
with its equation list swapped to the 21-equation winner
list for the duration of the call. No other transform.
"""

from __future__ import annotations

import pandas as pd

import core.cycle64_best as _c64
from core.cycle64_best import (CYCLE64_CHECK_HOURS,
                               is_cycle64_check_time,
                               select_cycle64_entries)

CYCLE88_CHECK_HOURS = CYCLE64_CHECK_HOURS

_DROP_IDS = ("FB_EURUSD_h10_0", "FB_GBPUSD_h10_1",
             "FB_USDJPY_h10_2", "FB_AUDUSD_h16_0",
             "FB_EURJPY_h16_1", "FB_GBPJPY_h16_2",
             "FB_AUDJPY_h18_0", "FB_NZDUSD_h18_1",
             "FB_EURCHF_h18_2")

C88_EQUATIONS = [e for e in _c64.CYCLE64_EQUATIONS
                 if e["id"] not in _DROP_IDS]
assert len(C88_EQUATIONS) == 21, len(C88_EQUATIONS)
assert not any(e["id"].startswith("FB_") for e in C88_EQUATIONS)


def evaluate_cycle88_signals(frames: dict, check_time_utc,
                             m15_frames: dict | None = None) -> pd.DataFrame:
    """C64-09 signals with the whole FB_* layer removed.
    `m15_frames` is accepted for router uniformity and
    ignored (the system is pure H1)."""
    orig = _c64.CYCLE64_EQUATIONS
    _c64.CYCLE64_EQUATIONS = C88_EQUATIONS
    try:
        sig = _c64.evaluate_cycle64_signals(frames, check_time_utc)
    finally:
        _c64.CYCLE64_EQUATIONS = orig
    return sig


def select_cycle88_entries(signals: pd.DataFrame,
                           open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: the frozen C64-09 selection."""
    return select_cycle64_entries(signals, open_symbols=open_symbols)


def is_cycle88_check_time(ts) -> bool:
    return is_cycle64_check_time(ts)

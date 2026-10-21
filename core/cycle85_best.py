"""Cycle 85 (C85-23) -- February H1 system, PROMOTED
2026-10-21 (Program 4 retry round; BRIEF6 priorities).

C56-15 IS FROZEN as the entry engine (core.cycle56_best,
checks at 11:00 / 13:00 / 16:00 UTC, exactly 1 entry/check).
Cycle 85 changes exactly two things:

  1. Four discovery-negative TREND-fallback legs are REMOVED:
     FB_GBPUSD_h16_2, FB_USDCAD_h13_1, FB_EURGBP_h13_2,
     FB_NZDUSD_h11_2 (the incumbent FB layer lost -258.1 pips
     on discovery at leftover -12.04%; these four were its
     worst legs). 18 of the 22 equations remain.
  2. At entry, surviving FB_* trades get TP x1.75 (SL
     unchanged), re-simulated on H1 in the research round
     (the factor multiplies the trade's clipped TP distance,
     c85_lib.modify_pool semantics).

Verified numbers (C85-23): paired LCT-middle PASS vs
C56-15 (P 90.42%, own 5th-percentile 40.14%); unseen
leftover 29.35% vs 21.63%, unseen net +184.2 vs +124.8,
2.45 entries/day, win 85.71%; discovery net +3,380.1 vs
+2,321.1. Best N 104 (own sizing run: peak margin 47.7%,
max DD 14.6%). C56-15 remains selectable as cycle56.

Implementation: the frozen cycle56 engine is delegated to
with its equation list swapped to the 18-equation winner
list for the duration of the call; the TP factor is applied
to the emitted signals frame (FB rows only), exactly as the
research pool modification did.
"""

from __future__ import annotations

import pandas as pd

import core.cycle56_best as _c56
from core.cycle56_best import (CYCLE56_CHECK_HOURS,
                               is_cycle56_check_time,
                               select_cycle56_entries)

CYCLE85_CHECK_HOURS = CYCLE56_CHECK_HOURS
FB_TP_FACTOR = 1.75

_DROP_IDS = ("FB_GBPUSD_h16_2", "FB_USDCAD_h13_1",
             "FB_EURGBP_h13_2", "FB_NZDUSD_h11_2")

C85_EQUATIONS = [e for e in _c56.C56_EQUATIONS
                 if e["id"] not in _DROP_IDS]
assert len(C85_EQUATIONS) == 18, len(C85_EQUATIONS)
assert all(e["id"] not in _DROP_IDS for e in C85_EQUATIONS)


def evaluate_cycle85_signals(frames: dict, check_time_utc,
                             m15_frames: dict | None = None) -> pd.DataFrame:
    """C56-15 signals minus the 4 cut FB legs, with TP x1.75
    on surviving FB_* rows. `m15_frames` is accepted for
    router uniformity and ignored (the layer is pure H1)."""
    orig = _c56.C56_EQUATIONS
    _c56.C56_EQUATIONS = C85_EQUATIONS
    try:
        sig = _c56.evaluate_cycle56_signals(frames, check_time_utc)
    finally:
        _c56.C56_EQUATIONS = orig
    if sig is None or len(sig) == 0:
        return sig
    sig = sig.copy()
    fb = sig["equation"].astype(str).str.startswith("FB_")
    if fb.any():
        sig.loc[fb, "tp_pips"] = sig.loc[fb, "tp_pips"] * FB_TP_FACTOR
    return sig


def select_cycle85_entries(signals: pd.DataFrame,
                           open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: the frozen C56-15 selection."""
    return select_cycle56_entries(signals, open_symbols=open_symbols)


def is_cycle85_check_time(ts) -> bool:
    return is_cycle56_check_time(ts)

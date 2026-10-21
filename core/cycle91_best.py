"""Cycle 91 (C91-15) -- September H1 system, PROMOTED
2026-10-21 (Program 4 retry round; BRIEF6 priorities).
September was the last LCT-unfixed month of the earlier
rounds (paired P 41.85% under Program 3); C91-15 fixes it.

C59-18 IS FROZEN as the entry engine (core.cycle59_best,
checks at 01:00 / 10:00 / 11:00 UTC, exactly 1 entry/check,
effective score = score + 400 on Alligator agreement).
Cycle 91 changes exactly two things:

  1. The three hour-1 TREND-fallback legs are REMOVED:
     FB_GBPUSD_h1_1, FB_EURUSD_h1_0, FB_USDJPY_h1_2
     (the FB layer held 1.33% discovery leftover and 69.5%
     of the loss mass, inverted on the unseen month; the
     hour-sleeve cut is what worked -- direct worst-leg
     cuts fail in September via occupancy refills).
     21 of the 24 equations remain.
  2. The X30B at-entry overlay on EVERY trade: when
     ER15(16) <= 0.25 AND H1 r1(1) >= 0 at entry, the
     stop-loss distance is set to 0.85 x S (TP unchanged).
     ER15(16) = |c[j]-c[j-16]| / sum|c[k]-c[k-1]| over the
     17 M15 closes ending with the bar that ends at the
     entry time; r1(1) = direction-signed 1-bar H1
     momentum at the signal bar (only its sign enters).
     In the research round the picked trades' exits were
     re-simulated on M15 with the adjusted stop (11 trades
     changed vs the plain M15 replay); the app emits
     entries only, as for every other cycle, so the layer
     appears here as the adjusted stop distance.

Verified numbers (C91-15): paired LCT-middle PASS vs
C59-18 (P 80.28%, own 5th-percentile 24.63%); unseen
leftover 65.26% vs 55.95%, unseen net +285.1 vs +278.1,
2.64 entries/day, win 94.83%; discovery leftover and net
both up. Best N 83 (own sizing run: peak margin 47.94%,
max DD 9.18%). C59-18 remains selectable as cycle59.

M15 DATA: evaluate_cycle91_signals takes an optional
m15_frames argument; fetch_cycle91_m15_frames() builds it
for live use through the cycle78 data path (local candle
repository first, provider chain only for cache misses,
memoised 10 minutes). When no M15 frame is available for
a symbol, that symbol's signals pass through unmodified
-- the layer is simply inactive. The research
availability gate (bar index >= 90 and a finite positive
M15 Wilder ATR14 at the bar) is preserved via the
cycle78 helpers; the July/September research data had
no fallbacks from it.
"""

from __future__ import annotations

import pandas as pd

import core.cycle59_best as _c59
from core.cycle59_best import (CYCLE59_CHECK_HOURS,
                               is_cycle59_check_time,
                               select_cycle59_entries)
from core.cycle78_best import (_er15_16, _m15_arrays, _r1_1_sign,
                               fetch_cycle78_m15_frames)

CYCLE91_CHECK_HOURS = CYCLE59_CHECK_HOURS
X30B_ER15_16_MAX = 0.25
X30B_SL_FACTOR = 0.85

_DROP_IDS = ("FB_GBPUSD_h1_1", "FB_EURUSD_h1_0",
             "FB_USDJPY_h1_2")

C91_EQUATIONS = [e for e in _c59.C59_EQUATIONS
                 if e["id"] not in _DROP_IDS]
assert len(C91_EQUATIONS) == 21, len(C91_EQUATIONS)
C91_SYMBOLS = sorted({e["symbol"] for e in C91_EQUATIONS})


def evaluate_cycle91_signals(frames: dict, check_time_utc,
                             m15_frames: dict | None = None) -> pd.DataFrame:
    """C59-18 signals minus the 3 hour-1 FB legs, with the
    X30B stop-tightening layer applied. Adds the columns
    'sl_pips_base' (pre-layer stop) and 'x30b_modified'."""
    orig = _c59.C59_EQUATIONS
    _c59.C59_EQUATIONS = C91_EQUATIONS
    try:
        sig = _c59.evaluate_cycle59_signals(frames, check_time_utc)
    finally:
        _c59.C59_EQUATIONS = orig
    if sig is None or len(sig) == 0:
        return sig
    sig = sig.copy()
    sig["sl_pips_base"] = sig["sl_pips"]
    sig["x30b_modified"] = False
    if not m15_frames:
        return sig
    m15_cache: dict = {}
    for i, row in sig.iterrows():
        sym = str(row["symbol"])
        m15df = m15_frames.get(sym)
        if m15df is None or not len(m15df):
            continue
        if sym not in m15_cache:
            m15_cache[sym] = _m15_arrays(m15df)
        er = _er15_16(m15_cache[sym], row["entry_candle"])
        if er is None or not (er <= X30B_ER15_16_MAX):
            continue
        r1 = _r1_1_sign(frames[sym], row["signal_candle"],
                        str(row["direction"]))
        if r1 is None or not (r1 >= 0):
            continue
        sig.at[i, "sl_pips"] = float(row["sl_pips"]) * X30B_SL_FACTOR
        sig.at[i, "x30b_modified"] = True
    return sig


def select_cycle91_entries(signals: pd.DataFrame,
                           open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: the frozen C59-18
    selection (effective score incl. the Alligator bonus)."""
    return select_cycle59_entries(signals, open_symbols=open_symbols)


def is_cycle91_check_time(ts) -> bool:
    return is_cycle59_check_time(ts)


_M15_FETCH_MEMO = {"ts": None, "frames": None}
_M15_FETCH_TTL_S = 600.0


def fetch_cycle91_m15_frames(state=None):
    """Live M15 frames for the X30B layer: the cycle78 data
    path (local repository first, provider chain for
    misses), memoised 10 minutes, over the C91 symbol set."""
    import time
    now = time.monotonic()
    if _M15_FETCH_MEMO["ts"] is not None \
            and now - _M15_FETCH_MEMO["ts"] < _M15_FETCH_TTL_S:
        return _M15_FETCH_MEMO["frames"]
    frames = fetch_cycle78_m15_frames(state=state,
                                       symbols=C91_SYMBOLS)
    _M15_FETCH_MEMO["ts"] = now
    _M15_FETCH_MEMO["frames"] = frames
    return frames

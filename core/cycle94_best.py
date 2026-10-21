"""Cycle 94 (C94-23) -- December H1 system, PROMOTED
2026-10-21 (Program 4 retry round; BRIEF6 priorities).

C71-04 IS FROZEN as the entry engine (core.cycle71_best,
checks at 10:00 / 11:00 / 13:00 UTC, exactly 1 entry/check;
all 34 equations verbatim). Cycle 94 adds exactly one
thing: an entry gate on TREND-fallback (FB_*) picks only.

  Veto an FB_* candidate when the H1 Wilder ATR14
  percentile rank (480-bar, signal bar, c83 convention:
  preceding values only, count-less + half ties, x100)
  is > 70 AND the directional CLV of the last completed
  M15 bar at entry is < 0.45. On a veto the walk
  continues to the next candidate at that check (the
  veto depends only on the candidate itself, so dropping
  the row from the signals frame is exactly the research
  walk's behaviour). Non-FB picks are never vetoed; when
  the features cannot be computed the candidate is KEPT,
  matching the research gate. The Dec-25 exclusion of
  the research grid is a calendar property, unchanged.

December's FIRST LCT-middle pass in any program
(C94-23): paired P 94.14%, own 5th-percentile 31.54%;
unseen leftover 80.8121% vs 80.7740% (genuine: 4 vetoed
+7.5 FB wins refilled by +7.5/+7.5/+9.0/+7.5 trades,
identical 63W/3L), unseen net +490.6 vs +489.1, 2.87
entries/day, win 95.45%; discovery net +3,246.0 vs
+2,902.5. Best N 105 (own sizing run: peak margin
47.03%, max DD 15.68%). C71-04 remains selectable as
cycle71.

M15 DATA: the gate reads M15 through the cycle78 data
path (local candle repository first, provider chain only
for cache misses, memoised 10 minutes). Symbols without
M15 data keep their FB candidates unvetoed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import core.cycle71_best as _c71
from core.cycle71_best import (CYCLE71_CHECK_HOURS,
                               is_cycle71_check_time,
                               select_cycle71_entries)
from core.cycle78_best import _m15_arrays, fetch_cycle78_m15_frames

CYCLE94_CHECK_HOURS = CYCLE71_CHECK_HOURS
GATE_ATRPCT_MIN = 70.0
GATE_CLV_MAX = 0.45

C94_EQUATIONS = list(_c71.C71_EQUATIONS)
assert len(C94_EQUATIONS) == 34, len(C94_EQUATIONS)
C94_SYMBOLS = sorted({e["symbol"] for e in C94_EQUATIONS})


def _atrpct_at(atr: np.ndarray, pos: int) -> float:
    """H1 ATR14 percentile among the preceding 480 values
    (count-less + half ties, x100); NaN before 480 priors."""
    if pos is None or pos < 480:
        return float("nan")
    win = atr[pos - 480:pos]
    cur = atr[pos]
    if not np.isfinite(cur):
        return float("nan")
    return float(((win < cur).sum() + 0.5 * (win == cur).sum())
                 / 480.0 * 100.0)


def _clv15(m15a, entry_stamp, direction) -> float:
    """Directional CLV of the last completed M15 bar at
    entry; NaN when unavailable."""
    j = m15a["pos"].get(pd.Timestamp(entry_stamp)
                         - pd.Timedelta(minutes=15))
    if j is None:
        return float("nan")
    rng = m15a["h"][j] - m15a["l"][j]
    if rng <= 0:
        return float("nan")
    if direction == "BUY":
        return float((m15a["c"][j] - m15a["l"][j]) / rng)
    return float((m15a["h"][j] - m15a["c"][j]) / rng)


def evaluate_cycle94_signals(frames: dict, check_time_utc,
                             m15_frames: dict | None = None) -> pd.DataFrame:
    """C71-04 signals (34 equations verbatim) with the
    FB-only vol/CLV gate applied (vetoed rows dropped)."""
    orig = _c71.C71_EQUATIONS
    _c71.C71_EQUATIONS = C94_EQUATIONS
    try:
        sig = _c71.evaluate_cycle71_signals(frames, check_time_utc)
    finally:
        _c71.C71_EQUATIONS = orig
    if sig is None or len(sig) == 0:
        return sig
    sig = sig.copy()
    fb = sig["equation"].astype(str).str.startswith("FB_")
    if fb.any():
        m15_cache: dict = {}
        feat_cache: dict = {}
        drop_idx = []
        for i, row in sig[fb].iterrows():
            sym = str(row["symbol"])
            atrpct = float("nan")
            try:
                if sym not in feat_cache:
                    f = (frames or {}).get(sym)
                    if f is None or len(f) == 0:
                        feat_cache[sym] = None
                    else:
                        ff = _c71._norm_frame(f)
                        feat_cache[sym] = (
                            _c71._symbol_feat(sym, ff), ff)
                got = feat_cache[sym]
                if got is not None:
                    feat, ff = got
                    pos = ff.index.get_loc(
                        pd.Timestamp(row["signal_candle"]))
                    if isinstance(pos, (int, np.integer)):
                        atrpct = _atrpct_at(
                            feat["atr14"].to_numpy(dtype=float),
                            int(pos))
            except Exception:
                atrpct = float("nan")
            clv = float("nan")
            if m15_frames:
                m15df = m15_frames.get(sym)
                if m15df is not None and len(m15df):
                    if sym not in m15_cache:
                        m15_cache[sym] = _m15_arrays(m15df)
                    clv = _clv15(m15_cache[sym], row["entry_candle"],
                                 str(row["direction"]))
            if (np.isfinite(atrpct) and atrpct > GATE_ATRPCT_MIN
                    and np.isfinite(clv) and clv < GATE_CLV_MAX):
                drop_idx.append(i)
        if drop_idx:
            sig = sig.drop(index=drop_idx)
    return sig


def select_cycle94_entries(signals: pd.DataFrame,
                           open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: the frozen C71-04 selection."""
    return select_cycle71_entries(signals, open_symbols=open_symbols)


def is_cycle94_check_time(ts) -> bool:
    return is_cycle71_check_time(ts)


_M15_FETCH_MEMO = {"ts": None, "frames": None}
_M15_FETCH_TTL_S = 600.0


def fetch_cycle94_m15_frames(state=None):
    """Live M15 frames for the FB gate: the cycle78 data
    path (local repository first, provider chain for
    misses), memoised 10 minutes, over the C94 symbol set."""
    import time
    now = time.monotonic()
    if _M15_FETCH_MEMO["ts"] is not None \
            and now - _M15_FETCH_MEMO["ts"] < _M15_FETCH_TTL_S:
        return _M15_FETCH_MEMO["frames"]
    frames = fetch_cycle78_m15_frames(state=state,
                                       symbols=C94_SYMBOLS)
    _M15_FETCH_MEMO["ts"] = now
    _M15_FETCH_MEMO["frames"] = frames
    return frames

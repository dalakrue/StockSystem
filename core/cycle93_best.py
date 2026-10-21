"""Cycle 93 (C93-24) -- November H1 system, PROMOTED
2026-10-21 (Program 4 retry round; BRIEF6 priorities).

C70-07 IS FROZEN as the entry engine (core.cycle70_best,
checks at 09:00 / 13:00 / 15:00 UTC, exactly 1 entry/check).
Cycle 93 changes exactly two things:

  1. Nine legs are REMOVED: 8 of the 9 TREND-fallback legs
     (only FB_EURUSD_h9_0 survives) and the
     CYB_cyb_x_S_EURNZD_h9_1.5x7.0_H48 primary (its single
     -102.5 unseen stop was 64% of the incumbent's unseen
     loss mass). 15 of the 24 equations remain.
  2. The January-shape FBGATE on the surviving FB leg: an
     FB_EURUSD_h9_0 candidate is vetoed when the H1 ATR14
     percentile (480-bar, signal bar, c82 convention:
     count-less + half ties, x100) is > 80 AND the
     directional CLV of the last completed M15 bar at
     entry is < 0.50. A vetoed candidate is skipped and
     the walk continues (the veto depends only on the
     candidate itself, so dropping the row from the
     signals frame is exactly the research walk's
     behaviour). The gate fired exactly twice, both on
     discovery; when the features cannot be computed the
     candidate is KEPT, matching the research gate.

Verified numbers (C93-24): paired LCT-middle PASS vs
C70-07 (P 83.42%, own 5th-percentile 46.18%); unseen
leftover 40.11% vs 31.49%, unseen net +318.2 vs +268.2,
2.60 entries/day, win 84.62%. Best N 83 (own sizing run:
peak margin 48.19%, max DD 23.31%). C70-07 remains
selectable as cycle70.

M15 DATA: the gate reads M15 through the cycle78 data
path (local candle repository first, provider chain only
for cache misses, memoised 10 minutes). Symbols without
M15 data keep their FB candidates unvetoed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import core.cycle70_best as _c70
from core.cycle70_best import (CYCLE70_CHECK_HOURS,
                               is_cycle70_check_time,
                               select_cycle70_entries)
from core.cycle78_best import _m15_arrays, fetch_cycle78_m15_frames

CYCLE93_CHECK_HOURS = CYCLE70_CHECK_HOURS
GATE_ATRPCT_MIN = 80.0
GATE_CLV_MAX = 0.50

_DROP_IDS = ("FB_GBPUSD_h9_1", "FB_USDJPY_h9_2",
             "FB_AUDUSD_h13_0", "FB_EURJPY_h13_1",
             "FB_GBPJPY_h13_2", "FB_AUDJPY_h15_0",
             "FB_NZDUSD_h15_1", "FB_EURCHF_h15_2",
             "CYB_cyb_x_S_EURNZD_h9_1.5x7.0_H48")

C93_EQUATIONS = [e for e in _c70.CYCLE70_EQUATIONS
                 if e["id"] not in _DROP_IDS]
assert len(C93_EQUATIONS) == 15, len(C93_EQUATIONS)
C93_SYMBOLS = sorted({e["symbol"] for e in C93_EQUATIONS})


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


def evaluate_cycle93_signals(frames: dict, check_time_utc,
                             m15_frames: dict | None = None) -> pd.DataFrame:
    """C70-07 signals minus the 9 removed legs, with the
    FBGATE applied to surviving FB_* rows (vetoed rows
    dropped)."""
    orig = _c70.CYCLE70_EQUATIONS
    _c70.CYCLE70_EQUATIONS = C93_EQUATIONS
    try:
        sig = _c70.evaluate_cycle70_signals(frames, check_time_utc)
    finally:
        _c70.CYCLE70_EQUATIONS = orig
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
                    df = (frames or {}).get(sym)
                    if df is None or not len(df):
                        feat_cache[sym] = None
                    else:
                        ff = df.copy()
                        ff.index = pd.to_datetime(ff.index)
                        if ff.index.tz is not None:
                            ff.index = ff.index.tz_convert(
                                "UTC").tz_localize(None)
                        feat = _c70._symbol_feat(
                            ff.reset_index(drop=True))
                        feat_cache[sym] = (
                            feat["atr14"].to_numpy(dtype=float),
                            ff.index.get_indexer(
                                [pd.Timestamp(row["signal_candle"])])[0])
                got = feat_cache[sym]
                if got is not None:
                    atrpct = _atrpct_at(got[0], int(got[1]))
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


def select_cycle93_entries(signals: pd.DataFrame,
                           open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: the frozen C70-07 selection."""
    return select_cycle70_entries(signals, open_symbols=open_symbols)


def is_cycle93_check_time(ts) -> bool:
    return is_cycle70_check_time(ts)


_M15_FETCH_MEMO = {"ts": None, "frames": None}
_M15_FETCH_TTL_S = 600.0


def fetch_cycle93_m15_frames(state=None):
    """Live M15 frames for the FB gate: the cycle78 data
    path (local repository first, provider chain for
    misses), memoised 10 minutes, over the C93 symbol set."""
    import time
    now = time.monotonic()
    if _M15_FETCH_MEMO["ts"] is not None \
            and now - _M15_FETCH_MEMO["ts"] < _M15_FETCH_TTL_S:
        return _M15_FETCH_MEMO["frames"]
    frames = fetch_cycle78_m15_frames(state=state,
                                       symbols=C93_SYMBOLS)
    _M15_FETCH_MEMO["ts"] = now
    _M15_FETCH_MEMO["frames"] = frames
    return frames

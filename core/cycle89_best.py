"""Cycle 89 (C89-21) -- June H1 system, PROMOTED 2026-10-21
(Program 4 retry round; BRIEF6 priorities).

C65-01 IS FROZEN as the entry engine (core.cycle65_best,
checks at 01:00 / 15:00 / 18:00 UTC, exactly 1 entry/check).
Cycle 89 changes exactly three things:

  1. FB_AUDJPY_h18_0 is REMOVED (73 discovery trades,
     -322.9 pips). 29 of the 30 equations remain.
  2. FBGATE veto on the two h18 fallback-bench picks
     (FB_NZDUSD_h18_1, FB_EURCHF_h18_2): a bench candidate
     is vetoed when the H1 ATR14 percentile (480-bar,
     signal bar, c77 convention: count-less + half ties,
     x100) is > 80 AND the directional CLV of the last
     completed M15 bar at entry is < 0.50. A vetoed
     candidate is skipped and the walk continues to the
     next candidate (the veto depends only on the
     candidate itself, so dropping the row from the
     signals frame is exactly the research walk's
     behaviour). When the features cannot be computed
     (no M15 frame, NaN), the candidate is KEPT, matching
     the research gate.
  3. At entry, trades of the two REV_lr2 preempt legs
     (REV_lr2_EURCAD_h15_SELL_0.5x8.0,
     REV_lr2_EURNZD_h18_SELL_0.5x8.0) get TP x1.25.

Verified numbers (C89-21): paired LCT-middle AND
LCT-strict PASS vs C65-01 (P 99.91%, own 5th-percentile
52.13%); unseen leftover 58.20% vs 57.07%, unseen net
+364.0 vs +346.3, 3.00 entries/day, win 95.24%; discovery
net +3,713.3 vs +3,163.8. Best N 84 (own sizing run: peak
margin 47.4%, max DD 9.9%). C65-01 remains selectable as
cycle65.

M15 DATA: the gate reads M15 through the cycle78 data
path (local candle repository first, provider chain only
for cache misses, memoised 10 minutes). Symbols without
M15 data keep their bench candidates unvetoed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import core.cycle65_best as _c65
from core.cycle65_best import (CYCLE65_CHECK_HOURS,
                               is_cycle65_check_time,
                               select_cycle65_entries)
from core.cycle78_best import _m15_arrays, fetch_cycle78_m15_frames

CYCLE89_CHECK_HOURS = CYCLE65_CHECK_HOURS
REV_TP_FACTOR = 1.25
GATE_ATRPCT_MIN = 80.0
GATE_CLV_MAX = 0.50

_DROP_IDS = ("FB_AUDJPY_h18_0",)
_BENCH_IDS = ("FB_NZDUSD_h18_1", "FB_EURCHF_h18_2")
_REV_IDS = ("REV_lr2_EURCAD_h15_SELL_0.5x8.0",
            "REV_lr2_EURNZD_h18_SELL_0.5x8.0")

C89_EQUATIONS = [e for e in _c65.C65_EQUATIONS
                 if e["id"] not in _DROP_IDS]
assert len(C89_EQUATIONS) == 29, len(C89_EQUATIONS)
C89_SYMBOLS = sorted({e["symbol"] for e in C89_EQUATIONS})


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


_A1_MEMO: dict = {}


def _wilder_atr14(o, h, l, c):
    """Research H1 ATR14: Wilder smoothing of the true-range
    series (seed = mean of first 14 TRs at index 13, then
    y = (x + 13*prior)/14). The frozen gate percentile ranks
    THIS series (c77_feat A1); the feature-frame 'atr14'
    column is a plain 14-bar mean and is NOT the same series."""
    o = np.asarray(o, dtype=float)
    h = np.asarray(h, dtype=float)
    l = np.asarray(l, dtype=float)
    c = np.asarray(c, dtype=float)
    pc = np.empty_like(c)
    pc[0] = c[0]
    pc[1:] = c[:-1]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc),
                                      np.abs(l - pc)))
    y = np.full(len(tr), np.nan)
    p = 14
    if len(tr) <= p:
        return y
    seed = float(np.mean(tr[:p]))
    y[p - 1] = seed
    a = 1.0 / p
    b = (p - 1.0) / p
    try:
        from scipy.signal import lfilter
        y[p:] = lfilter([a], [1.0, -b], tr[p:], zi=[b * seed])[0]
    except Exception:
        prev = seed
        for t in range(p, len(tr)):
            prev = a * tr[t] + b * prev
            y[t] = prev
    return y


def _frame_wilder(ff: pd.DataFrame):
    """Wilder ATR14 array for a normalised H1 frame,
    memoised across calls on a frame fingerprint."""
    key = (len(ff), float(ff["Close"].sum()), float(ff["High"].sum()),
           float(ff["Close"].iloc[0]), float(ff["Close"].iloc[-1]))
    got = _A1_MEMO.get(key)
    if got is None:
        got = _wilder_atr14(ff["Open"].to_numpy(dtype=float),
                            ff["High"].to_numpy(dtype=float),
                            ff["Low"].to_numpy(dtype=float),
                            ff["Close"].to_numpy(dtype=float))
        if len(_A1_MEMO) > 64:
            _A1_MEMO.clear()
        _A1_MEMO[key] = got
    return got


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


def evaluate_cycle89_signals(frames: dict, check_time_utc,
                             m15_frames: dict | None = None) -> pd.DataFrame:
    """C65-01 signals minus FB_AUDJPY_h18_0, with the h18
    bench FBGATE applied (vetoed rows dropped) and TP x1.25
    on the two REV_lr2 rows."""
    orig = _c65.C65_EQUATIONS
    _c65.C65_EQUATIONS = C89_EQUATIONS
    try:
        sig = _c65.evaluate_cycle65_signals(frames, check_time_utc)
    finally:
        _c65.C65_EQUATIONS = orig
    if sig is None or len(sig) == 0:
        return sig
    sig = sig.copy()
    sig["tp_pips_base"] = sig["tp_pips"]
    rev = sig["equation"].isin(_REV_IDS)
    if rev.any():
        sig.loc[rev, "tp_pips"] = sig.loc[rev, "tp_pips"] * REV_TP_FACTOR
    bench = sig["equation"].isin(_BENCH_IDS)
    if bench.any():
        m15_cache: dict = {}
        feat_cache: dict = {}
        drop_idx = []
        for i, row in sig[bench].iterrows():
            sym = str(row["symbol"])
            # H1 ATR percentile at the signal bar (frozen
            # cycle65 feature frame, cache-shared with the
            # engine's own evaluation).
            atrpct = float("nan")
            try:
                if sym not in feat_cache:
                    f = (frames or {}).get(sym)
                    if f is None or len(f) == 0:
                        feat_cache[sym] = None
                    else:
                        ff = _c65._norm_frame(f)
                        feat_cache[sym] = (
                            _c65._symbol_feat(sym, ff), ff)
                got = feat_cache[sym]
                if got is not None:
                    feat, ff = got
                    pos = ff.index.get_loc(
                        pd.Timestamp(row["signal_candle"]))
                    if isinstance(pos, (int, np.integer)):
                        atrpct = _atrpct_at(
                            _frame_wilder(ff), int(pos))
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


def select_cycle89_entries(signals: pd.DataFrame,
                           open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: the frozen C65-01 selection."""
    return select_cycle65_entries(signals, open_symbols=open_symbols)


def is_cycle89_check_time(ts) -> bool:
    return is_cycle65_check_time(ts)


_M15_FETCH_MEMO = {"ts": None, "frames": None}
_M15_FETCH_TTL_S = 600.0


def fetch_cycle89_m15_frames(state=None):
    """Use the shared current M15 data; do not retain a stale private memo."""
    return fetch_cycle78_m15_frames(state=state, symbols=C89_SYMBOLS)

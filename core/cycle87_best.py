"""Cycle 87 (C87-24) -- April H1 system, PROMOTED
2026-10-21 (Program 4 retry round; BRIEF6 priorities).

C63-04 IS FROZEN as the entry engine (core.cycle63_best,
checks at 16:00 / 17:00 / 18:00 UTC, exactly 1 entry/check).
Cycle 87 changes exactly two things (a pure H1 walk
process -- exits are the incumbent's H1 exits):

  1. Three TREND-fallback legs are BANNED from the walk:
     FB_EURGBP_h18_1, FB_GBPUSD_h16_1, FB_USDCHF_h18_2
     (banned picks fall through to the next-ranked
     candidate at the same check). 39 of the 42 equations
     remain.
  2. The M18 "common-range" rerank within the top-3
     (frozen Cycle-75 definition), applied to the
     candidate list BEFORE the occupancy skip (the
     research do_walk order): candidates passing M18
     are moved ahead of the others, preserving order;
     the walk then picks the first candidate whose
     symbol is free. M18 for a candidate of direction d
     (+1 BUY / -1 SELL), with t = the last completed M15
     bar at entry and bars t-4..t-1 the prior corridor:
       lo4 = max(l[t-4..t-1]); up4 = min(h[t-4..t-1])
       (no common corridor -> fail)
       commonw = (up4-lo4)/A15[t] <= 0.75
       brk = (c[t]-up4)/A15[t] if d>0 else (lo4-c[t])/A15[t]
             >= 0.15
       0.70 <= atrratio1 <= 1.20, where atrratio1 =
             ATR14_1[sig] / median of the preceding 720
             H1 ATR14 values (finite-filtered)
     A15 is the M15 Wilder ATR14 (pandas ewm alpha=1/14
     recursion, the c75 convention). NaN inputs fail.

Verified numbers (C87-24): paired LCT-middle PASS vs
C63-04 (P 92.44%, own 5th-percentile 65.55%); unseen
leftover 60.26% vs 53.70%, unseen net +633.2, 3.00
entries/day, win 92.42%; discovery net +4,357.9,
leftover 78.99%. Best N 104 (own sizing run: peak margin
47.7%, max DD 10.2%). C63-04 remains selectable as
cycle63.

M15 DATA: the rerank reads M15 through the cycle78 data
path (local candle repository first, provider chain only
for cache misses, memoised 10 minutes). The M15 ATR14 is
computed over the frame as passed; on short live windows
its seed differs from the research full-history series,
so borderline M18 calls can differ live (the same class
of approximation as July's availability gate). When no
M15 frame is available for a symbol, that symbol's
candidates fail M18 and the walk keeps the incumbent
order.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import core.cycle63_best as _c63
from core.cycle63_best import (CYCLE63_CHECK_HOURS,
                               is_cycle63_check_time)
from core.cycle78_best import fetch_cycle78_m15_frames

CYCLE87_CHECK_HOURS = CYCLE63_CHECK_HOURS
M18_WIDTH_MAX = 0.75
M18_BRK_MIN = 0.15
M18_ATRR_LO = 0.70
M18_ATRR_HI = 1.20

_DROP_IDS = ("FB_EURGBP_h18_1", "FB_GBPUSD_h16_1",
             "FB_USDCHF_h18_2")

C87_EQUATIONS = [e for e in _c63.CYCLE63_EQUATIONS
                 if e["id"] not in _DROP_IDS]
assert len(C87_EQUATIONS) == 39, len(C87_EQUATIONS)
C87_SYMBOLS = sorted({e["symbol"] for e in C87_EQUATIONS})


def _m15_arrays87(m15df):
    """M15 arrays + the c75-convention Wilder ATR14 series
    (pandas ewm alpha=1/14, min_periods=14, adjust=False,
    over true ranges with prev-close rolled)."""
    f = m15df.copy()
    f.index = pd.to_datetime(f.index)
    if f.index.tz is not None:
        f.index = f.index.tz_convert("UTC").tz_localize(None)
    f = f.sort_index()
    o = f["Open"].to_numpy(dtype=float)
    h = f["High"].to_numpy(dtype=float)
    l = f["Low"].to_numpy(dtype=float)
    c = f["Close"].to_numpy(dtype=float)
    pc = np.roll(c, 1)
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc),
                                      np.abs(l - pc)))
    a15 = pd.Series(tr).ewm(alpha=1.0 / 14, min_periods=14,
                            adjust=False).mean().to_numpy()
    return {"idx": f.index, "o": o, "h": h, "l": l, "c": c,
            "a15": a15,
            "pos": {t: i for i, t in enumerate(f.index)}}


def _m18_pass(m15a, entry_stamp, d: int, atrratio: float) -> bool:
    """The frozen M18 conjunction. Any missing/NaN input
    fails the test."""
    try:
        if not (M18_ATRR_LO <= atrratio <= M18_ATRR_HI):
            return False
        t = m15a["pos"].get(pd.Timestamp(entry_stamp)
                            - pd.Timedelta(minutes=15))
        if t is None or t < 4:
            return False
        a15 = m15a["a15"][t]
        if not np.isfinite(a15) or a15 <= 0:
            return False
        lo4 = float(m15a["l"][t - 4:t].max())
        up4 = float(m15a["h"][t - 4:t].min())
        if up4 < lo4:
            return False
        width = (up4 - lo4) / a15
        if not (width <= M18_WIDTH_MAX):
            return False
        brk = ((m15a["c"][t] - up4) / a15 if d > 0
               else (lo4 - m15a["c"][t]) / a15)
        return bool(brk >= M18_BRK_MIN)
    except Exception:
        return False


def evaluate_cycle87_signals(frames: dict, check_time_utc,
                             m15_frames: dict | None = None) -> pd.DataFrame:
    """C63-04 signals minus the 3 banned FB legs, with an
    'm18_pass' flag per row for the rerank selection.

    M18 ELIGIBILITY (research-exact): in the research
    pipeline the M18 features exist only for candidates in
    the PRE-BAN top-3 of their check (the c75 feat table
    targets), so a candidate ranked 4th or lower before the
    ban can never be a passer even when its raw features
    satisfy the conjunction. The evaluation therefore runs
    on the FULL C63-04 equation set, ranks candidates
    within each check by score, and only then drops the
    banned legs."""
    orig = _c63.CYCLE63_EQUATIONS
    _c63.CYCLE63_EQUATIONS = list(orig)
    try:
        sig = _c63.evaluate_cycle63_signals(frames, check_time_utc)
    finally:
        _c63.CYCLE63_EQUATIONS = orig
    if sig is None or len(sig) == 0:
        return sig
    sig = sig.copy()
    sig["_preban_rank"] = (sig.groupby("check")["score"]
                           .rank(ascending=False, method="first"))
    sig["m18_pass"] = False
    m15_cache: dict = {}
    feat_cache: dict = {}
    for i, row in sig.iterrows():
        sym = str(row["symbol"])
        d = 1 if str(row["direction"]) == "BUY" else -1
        atrratio = float("nan")
        try:
            if sym not in feat_cache:
                f = (frames or {}).get(sym)
                if f is None or len(f) == 0:
                    feat_cache[sym] = None
                else:
                    ff = _c63._norm_frame(f)
                    feat_cache[sym] = (
                        _c63._symbol_feat63(sym, ff), ff)
            got = feat_cache[sym]
            if got is not None:
                feat, ff = got
                pos = ff.index.get_loc(
                    pd.Timestamp(row["signal_candle"]))
                if isinstance(pos, (int, np.integer)) and pos >= 720:
                    atr = feat["atr14"].to_numpy(dtype=float)
                    prev = atr[pos - 720:pos]
                    prev = prev[np.isfinite(prev)]
                    if len(prev):
                        med = float(np.median(prev))
                        if med > 0:
                            atrratio = float(atr[pos]) / med
        except Exception:
            atrratio = float("nan")
        ok = False
        if m15_frames and float(row["_preban_rank"]) <= 3:
            m15df = m15_frames.get(sym)
            if m15df is not None and len(m15df):
                if sym not in m15_cache:
                    m15_cache[sym] = _m15_arrays87(m15df)
                ok = _m18_pass(m15_cache[sym], row["entry_candle"],
                               d, atrratio)
        sig.at[i, "m18_pass"] = bool(ok)
    sig = sig[~sig["equation"].isin(_DROP_IDS)]
    return sig.drop(columns=["_preban_rank"]).reset_index(drop=True)


def select_cycle87_entries(signals: pd.DataFrame,
                           open_symbols=()) -> pd.DataFrame:
    """M18 rerank walk (c75 do_walk + m_rerank semantics):
    order by score (stable); passers among the top-3 are
    moved to the front (order preserved), the rest follow
    in original order; pick the first candidate whose
    symbol is not open. Exactly 1 entry per check."""
    if signals is None or len(signals) == 0:
        return signals.iloc[0:0] if signals is not None else pd.DataFrame()
    held = {str(s).upper() for s in (open_symbols or ())}
    ordered = signals.sort_values("score", ascending=False,
                                  kind="mergesort").reset_index(drop=True)
    n = len(ordered)
    passers = [k for k in range(min(3, n))
               if bool(ordered.iloc[k].get("m18_pass", False))]
    if passers:
        pset = set(passers)
        order = passers + [k for k in range(n) if k not in pset]
    else:
        order = list(range(n))
    for k in order:
        r = ordered.iloc[k]
        if str(r["symbol"]).upper() in held:
            continue
        return pd.DataFrame([r]).reset_index(drop=True)
    return signals.iloc[0:0]


def is_cycle87_check_time(ts) -> bool:
    return is_cycle63_check_time(ts)


_M15_FETCH_MEMO = {"ts": None, "frames": None}
_M15_FETCH_TTL_S = 600.0


def fetch_cycle87_m15_frames(state=None):
    """Live M15 frames for the M18 rerank: the cycle78
    data path (local repository first, provider chain for
    misses), memoised 10 minutes, over the C87 symbol set."""
    import time
    now = time.monotonic()
    if _M15_FETCH_MEMO["ts"] is not None \
            and now - _M15_FETCH_MEMO["ts"] < _M15_FETCH_TTL_S:
        return _M15_FETCH_MEMO["frames"]
    frames = fetch_cycle78_m15_frames(state=state,
                                       symbols=C87_SYMBOLS)
    _M15_FETCH_MEMO["ts"] = now
    _M15_FETCH_MEMO["frames"] = frames
    return frames

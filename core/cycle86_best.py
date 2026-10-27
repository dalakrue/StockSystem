"""Cycle 86 (C86-24) -- March H1 system, PROMOTED
2026-10-21 (Program 4 retry round; BRIEF6 priorities).

C62-10 IS FROZEN as the entry engine (core.cycle62_best,
checks at 11:00 / 16:00 / 17:00 UTC, exactly 1 entry/check).
Cycle 86 changes exactly three things:

  1. FB_USDCAD_h16_1 is REMOVED (8 discovery trades,
     -257.3 pips). 28 of the 29 equations remain.
  2. The M08 "Reject15" rerank (frozen Cycle-74
     definition) is applied within the top-3 ELIGIBLE
     candidates at each check (score order, symbol not
     already open): the first candidate passing M08 is
     picked; if none of the three passes, the top
     eligible candidate is picked (the incumbent rule).
     M08 for a candidate of direction d (+1 BUY / -1
     SELL), with i = the last completed M15 bar at entry:
       rej(j) = (min(o,c)-l)/(h-l) if d>0 else
                (h-max(o,c))/(h-l)   (NaN if h==l)
       pass iff rej(i-1) >= 0.45 AND rej(i) >= 0.45
                AND d*(c[i]-o[i]) > 0
                AND d*(C1[sig]-C1[sig-6])/ATR14_1[sig] >= -0.50
     NaN inputs fail the test (research semantics).
  3. At entry, FB_* trades get TP x0.95 (SL unchanged).
     In the research round ALL exits were simulated on
     M15 bars; the app emits entries only, as for every
     other cycle, so the layer appears here as the
     adjusted TP distance plus the rerank.

Verified numbers (C86-24): paired LCT-middle PASS vs
C62-10 (P 87.34%, own 5th-percentile 35.38%); unseen
leftover 69.30%, unseen net +350.3, 62 trades, win
93.55%, 2.95 entries/day; discovery net +2,880.1,
leftover 54.25%. Best N 86 (own sizing run: peak margin
48.78%, max DD 14.94%). C62-10 remains selectable as
cycle62.

M15 DATA: the rerank reads M15 through the cycle78 data
path (local candle repository first, provider chain only
for cache misses, memoised 10 minutes). When no M15
frame is available for a symbol, that symbol's candidates
fail M08 (the research behaviour for uncomputable
features), so the walk falls back to the top eligible
candidate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import core.cycle62_best as _c62
from core.cycle62_best import (CYCLE62_CHECK_HOURS,
                               is_cycle62_check_time)
from core.cycle78_best import _m15_arrays, fetch_cycle78_m15_frames

CYCLE86_CHECK_HOURS = CYCLE62_CHECK_HOURS
FB_TP_FACTOR = 0.95
M08_REJ_MIN = 0.45
M08_R1_6_MIN = -0.50

_DROP_IDS = ("FB_USDCAD_h16_1",)

C86_EQUATIONS = [e for e in _c62.CYCLE62_EQUATIONS
                 if e["id"] not in _DROP_IDS]
assert len(C86_EQUATIONS) == 28, len(C86_EQUATIONS)
C86_SYMBOLS = sorted({e["symbol"] for e in C86_EQUATIONS})


def _rej(m15a, j: int, d: int) -> float:
    rng = m15a["h"][j] - m15a["l"][j]
    if rng <= 0:
        return float("nan")
    if d > 0:
        return float((min(m15a["o"][j], m15a["c"][j])
                      - m15a["l"][j]) / rng)
    return float((m15a["h"][j]
                  - max(m15a["o"][j], m15a["c"][j])) / rng)


def _m08_pass(m15a, entry_stamp, d: int, r1_6: float) -> bool:
    """The frozen M08 conjunction. Any missing/NaN input
    fails the test."""
    try:
        j = m15a["pos"].get(pd.Timestamp(entry_stamp)
                             - pd.Timedelta(minutes=15))
        if j is None or j < 1:
            return False
        if not (_rej(m15a, j - 1, d) >= M08_REJ_MIN):
            return False
        if not (_rej(m15a, j, d) >= M08_REJ_MIN):
            return False
        if not (d * (m15a["c"][j] - m15a["o"][j]) > 0):
            return False
        if not (r1_6 >= M08_R1_6_MIN):
            return False
        return True
    except Exception:
        return False


_A1_MEMO: dict = {}


def _wilder_atr14(o, h, l, c):
    """Research H1 ATR14 (c74_prep): Wilder smoothing of the
    true-range series -- seed = mean of the first 14 TRs at
    index 13, then y = (x + 13*prior)/14. This is the ATR the
    frozen M08 definition divides by (Ctx.A1); the cycle12
    'atr14' column is a plain 14-bar mean and is NOT the same
    series."""
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


def _h1_a1(ff: pd.DataFrame):
    """(closes, Wilder ATR14) for a normalised H1 frame,
    memoised across calls on a frame fingerprint."""
    key = (len(ff), float(ff["Close"].sum()), float(ff["High"].sum()),
           float(ff["Close"].iloc[0]), float(ff["Close"].iloc[-1]))
    got = _A1_MEMO.get(key)
    if got is None:
        got = (ff["Close"].to_numpy(dtype=float),
               _wilder_atr14(ff["Open"].to_numpy(dtype=float),
                             ff["High"].to_numpy(dtype=float),
                             ff["Low"].to_numpy(dtype=float),
                             ff["Close"].to_numpy(dtype=float)))
        if len(_A1_MEMO) > 64:
            _A1_MEMO.clear()
        _A1_MEMO[key] = got
    return got


def evaluate_cycle86_signals(frames: dict, check_time_utc,
                             m15_frames: dict | None = None) -> pd.DataFrame:
    """C62-10 signals minus FB_USDCAD_h16_1, with TP x0.95
    on FB_* rows and an 'm08_pass' flag per row for the
    rerank selection."""
    orig = _c62.CYCLE62_EQUATIONS
    _c62.CYCLE62_EQUATIONS = C86_EQUATIONS
    try:
        sig = _c62.evaluate_cycle62_signals(frames, check_time_utc)
    finally:
        _c62.CYCLE62_EQUATIONS = orig
    if sig is None or len(sig) == 0:
        return sig
    sig = sig.copy()
    fb = sig["equation"].astype(str).str.startswith("FB_")
    if fb.any():
        sig.loc[fb, "tp_pips"] = sig.loc[fb, "tp_pips"] * FB_TP_FACTOR
    sig["m08_pass"] = False
    m15_cache: dict = {}
    feat_cache: dict = {}
    for i, row in sig.iterrows():
        sym = str(row["symbol"])
        d = 1 if str(row["direction"]) == "BUY" else -1
        # H1 r1(6) at the signal bar: research definition
        # (c74 Ctx.r1) -- close difference over the Wilder
        # ATR14 series, NOT the cycle12 mean-TR 'atr14'.
        r1_6 = float("nan")
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
                    closes, a1s = _h1_a1(ff)
                    feat_cache[sym] = (
                        closes, a1s,
                        ff.index.get_indexer(
                            [pd.Timestamp(row["signal_candle"])])[0])
            got = feat_cache[sym]
            if got is not None:
                closes, a1s, pos = got
                if pos >= 6:
                    a1 = float(a1s[pos])
                    if np.isfinite(a1) and a1 > 0:
                        r1_6 = float(d * (float(closes[pos])
                                          - float(closes[pos - 6]))
                                     / a1)
        except Exception:
            r1_6 = float("nan")
        ok = False
        if m15_frames:
            m15df = m15_frames.get(sym)
            if m15df is not None and len(m15df):
                if sym not in m15_cache:
                    m15_cache[sym] = _m15_arrays(m15df)
                ok = _m08_pass(m15_cache[sym], row["entry_candle"],
                               d, r1_6)
        sig.at[i, "m08_pass"] = bool(ok)
    return sig


def select_cycle86_entries(signals: pd.DataFrame,
                           open_symbols=()) -> pd.DataFrame:
    """M08 rerank walk (c86_core.walk86 semantics): order
    by score (stable), drop candidates whose symbol is
    open, take the first M08 passer among the top-3
    eligible, else the top eligible candidate. Exactly 1
    entry per check."""
    if signals is None or len(signals) == 0:
        return signals.iloc[0:0] if signals is not None else pd.DataFrame()
    held = {str(s).upper() for s in (open_symbols or ())}
    ordered = signals.sort_values("score", ascending=False,
                                  kind="mergesort")
    elig = [r for _, r in ordered.iterrows()
            if str(r["symbol"]).upper() not in held]
    if not elig:
        return signals.iloc[0:0]
    pick = None
    for r in elig[:3]:
        if bool(r.get("m08_pass", False)):
            pick = r
            break
    if pick is None:
        pick = elig[0]
    return pd.DataFrame([pick]).reset_index(drop=True)


def is_cycle86_check_time(ts) -> bool:
    return is_cycle62_check_time(ts)


_M15_FETCH_MEMO = {"ts": None, "frames": None}
_M15_FETCH_TTL_S = 600.0


def fetch_cycle86_m15_frames(state=None):
    """Use the shared current M15 data; do not retain a stale private memo."""
    return fetch_cycle78_m15_frames(state=state, symbols=C86_SYMBOLS)

"""Cycle 60B (BRIEF23 C20_STACK) -- January IMPROVED system.

Definition (BRIEF23 January, validated HUGE 2026-10-26):
C60-03 (core.cycle60_best, frozen) + C10 + C17:

  C10 rewrites ONLY the FB fallback layer:
  1. Breadth veto: every FB pick whose entry breadth_m15
     exceeds 0.4 is vetoed. breadth_m15 = cross-symbol mean,
     over the 20 symbols, of (M15 close > M15 EMA20) at the
     last completed M15 bar before the entry. (The C09 rsi
     veto is subsumed: it also requires breadth > 0.4.)
  2. FB geometry: SL x0.60 for all surviving FB rows.
  3. Conditional 24h stall cut, ONLY on FB trades with
     pat_score > 0 (pat_score = the M15 candlestick-pattern
     score recorded at entry, below): if at the first M15 bar
     at/after entry+24h the trade is still open and marked
     net-negative (previous close, cost incl.), it is cut at
     that bar's open. This is an exit rule on the trade's own
     bars; the app surfaces pat_score on every pick so the
     rule can be applied to the live position, and the
     research replay applies it exactly (transformed tabs).
  C17 partner: score-gated dual-pick -- a second pick at the
  same check, different symbol, eq score >= MED_SCORE
  (971.8205553571429 = median positive eq score), only when
  fewer than 5 positions are live after the primary pick.

Validated numbers (C20_STACK, @2.5): DISC n355 net +1984.54
win 95.21% leftover 64.23 (control 24.25); AUDIT n101 net
+550.18 win 96.04% leftover 67.50 (control 67.13); LCT
P 100.00% / q05 55.20%; EC22 15 vs 14; MC P(call) 0.0000 vs
0.0008. Best N: no winner-specific value recorded -- the
incumbent's values stand (full 83, divided-by-3
27.666666666666668 in the router).

PROMOTED 2026-10-26: the app replay is EXACT against the
validated C20_STACK ledgers (456/456 pick keys; one documented
data-artifact exception on a single SL field -- see
FIX_NOTES_20261026_BRIEF21_APP_INTEGRATION.md); this system is
January's BEST (MONTH_SYSTEMS[1]) and the old C60-03 is
January's second priority in the combined layer.

M15 requirement: the breadth veto needs the 20-symbol M15
set at the check. When breadth cannot be computed from the
provided frames, this system returns NO FB picks for that
check (non-FB picks are unaffected) and marks the frame
status 'insufficient_m15_history_for_breadth' -- it never
lets an un-vetoed FB pick through.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import core.cycle60_best as _c60
from core.cycle60_best import (CYCLE60_CHECK_HOURS,
                               is_cycle60_check_time,
                               select_cycle60_entries)

CYCLE60B_CHECK_HOURS = CYCLE60_CHECK_HOURS
GRID_HOURS = (11, 13, 17)
BREADTH_VETO_MAX = 0.4
FB_SL_MULT = 0.60
MED_SCORE = 971.8205553571429
DUAL_CAP = 5
SYMBOLS20 = ['AUDCAD', 'AUDCHF', 'AUDJPY', 'AUDNZD', 'AUDUSD',
             'CHFJPY', 'EURAUD', 'EURCAD', 'EURCHF', 'EURGBP',
             'EURJPY', 'EURNZD', 'EURUSD', 'GBPJPY', 'GBPUSD',
             'NZDCAD', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDJPY']


def _causal_window(df, entry_time, bars=1600):
    """M15 closes strictly before the entry bar (the research
    feature slice A[:e]), last `bars` of them, or None."""
    if df is None or len(df) == 0:
        return None
    idx = pd.to_datetime(df.index)
    pos = int(np.searchsorted(idx.values,
                              pd.Timestamp(entry_time).value))
    if pos < 1:
        return None
    return df.iloc[max(0, pos - bars):pos]


def _above_ema20(df, entry_time):
    w = _causal_window(df, entry_time)
    if w is None or len(w) < 1:
        return None
    c = w["Close"].to_numpy(dtype=float)
    ema = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy()
    return int(c[-1] > ema[-1])


def breadth_m15(m15_frames, entry_time):
    """Cross-symbol mean of above-EMA20 over the 20 symbols,
    or None when any symbol's M15 set is unavailable."""
    if not m15_frames:
        return None
    vals = []
    for sym in SYMBOLS20:
        a = _above_ema20((m15_frames or {}).get(sym), entry_time)
        if a is None:
            return None
        vals.append(a)
    return float(np.mean(vals))


def _pattern_flags(o, h, l, c):
    """Candlestick pattern flags on the last 3 bars (verbatim
    from the research feature generator, work_c194 step1)."""
    o = np.asarray(o, dtype=float)
    h = np.asarray(h, dtype=float)
    l = np.asarray(l, dtype=float)
    c = np.asarray(c, dtype=float)
    body1 = c[-1] - o[-1]
    body2 = c[-2] - o[-2]
    rng1 = h[-1] - l[-1]
    up_w = h[-1] - max(c[-1], o[-1])
    lo_w = min(c[-1], o[-1]) - l[-1]
    eng = 0
    if body1 > 0 and body2 < 0 and c[-1] >= o[-2] and o[-1] <= c[-2]:
        eng = 1
    elif body1 < 0 and body2 > 0 and c[-1] <= o[-2] and o[-1] >= c[-2]:
        eng = -1
    out = {'engulf': eng}
    out['hammer'] = 1 if (rng1 > 0 and lo_w >= 2 * abs(body1)
                          and up_w <= 0.5 * abs(body1) + 1e-12) else 0
    out['shoot'] = 1 if (rng1 > 0 and up_w >= 2 * abs(body1)
                         and lo_w <= 0.5 * abs(body1) + 1e-12) else 0
    b = np.sign(np.array([c[-3] - o[-3], body2, body1]))
    mono = (c[-3] < c[-2] < c[-1]) or (c[-3] > c[-2] > c[-1])
    out['three'] = int(b[0]) if (b[0] != 0 and (b == b[0]).all()
                                 and mono) else 0
    pin = 0
    if rng1 > 0:
        if lo_w / rng1 >= 0.6:
            pin = 1
        elif up_w / rng1 >= 0.6:
            pin = -1
    out['pin'] = pin
    return out


def pat_score_m15(df, entry_time):
    """M15 pat_score at entry (engulf/hammer/three-up/pin-b
    minus the bearish counterparts), or None."""
    w = _causal_window(df, entry_time)
    if w is None or len(w) < 3:
        return None
    fl = _pattern_flags(w["Open"].to_numpy(dtype=float),
                        w["High"].to_numpy(dtype=float),
                        w["Low"].to_numpy(dtype=float),
                        w["Close"].to_numpy(dtype=float))
    return float((1 if fl['engulf'] == 1 else 0) + fl['hammer']
                 + (1 if fl['three'] == 1 else 0)
                 + (1 if fl['pin'] == 1 else 0)
                 - (1 if fl['engulf'] == -1 else 0) - fl['shoot']
                 - (1 if fl['three'] == -1 else 0)
                 - (1 if fl['pin'] == -1 else 0))


def evaluate_cycle60b_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """C60-03 signals with the C10 FB layer applied: breadth
    veto on FB rows, SL x0.60 on surviving FB rows, and
    breadth_m15 / pat_score columns attached."""
    sig = _c60.evaluate_cycle60_signals(frames, check_time_utc)
    if sig is None or len(sig) == 0:
        return sig
    ent = pd.Timestamp(check_time_utc) - pd.Timedelta(minutes=30)
    if m15_frames is None:
        m15_frames = fetch_cycle60b_m15_frames()
    sig = sig.copy()
    is_fb = sig["equation"].astype(str).str.startswith("FB_")
    b = breadth_m15(m15_frames, ent)
    sig["breadth_m15"] = b if b is not None else np.nan
    pats = {}
    for sym in sorted({str(s) for s in sig["symbol"]}):
        pats[sym] = pat_score_m15((m15_frames or {}).get(sym), ent)
    sig["pat_score"] = [pats[str(s)] for s in sig["symbol"]]
    if b is None:
        out = sig[~is_fb].reset_index(drop=True)
        out.attrs["status"] = (
            "insufficient_m15_history_for_breadth: FB picks "
            "withheld this check (breadth veto not computable)")
        return out
    keep = ~(is_fb & (sig["breadth_m15"] > BREADTH_VETO_MAX))
    sig = sig[keep].reset_index(drop=True)
    fb = sig["equation"].astype(str).str.startswith("FB_")
    sig.loc[fb, "sl_pips"] = sig.loc[fb, "sl_pips"] * FB_SL_MULT
    return sig


def select_cycle60b_entries(signals: pd.DataFrame,
                            open_symbols=(),
                            live_count=None) -> pd.DataFrame:
    """C20_STACK selection: the frozen C60-03 primary pick,
    plus the C17 dual pick (first remaining row, different
    symbol, score >= MED_SCORE) when fewer than DUAL_CAP
    positions are live after the primary."""
    if signals is None or len(signals) == 0:
        return signals.iloc[0:0] if signals is not None \
            else pd.DataFrame()
    primary = select_cycle60_entries(signals,
                                     open_symbols=open_symbols)
    if len(primary) == 0:
        return primary
    held = {str(s).upper() for s in (open_symbols or ())}
    if live_count is None:
        live_count = len(held)
    live_after = live_count + 1
    if live_after >= DUAL_CAP:
        return primary
    pick = primary.iloc[0]
    ordered = signals.sort_values("score", ascending=False,
                                  kind="mergesort")
    for _, r in ordered.iterrows():
        if str(r["equation"]) == str(pick["equation"]) \
                and str(r["symbol"]) == str(pick["symbol"]):
            continue
        if str(r["symbol"]).upper() == str(pick["symbol"]).upper():
            continue
        if str(r["symbol"]).upper() in held:
            continue
        if float(r["score"]) < MED_SCORE:
            continue
        dual = pd.DataFrame([r]).reset_index(drop=True)
        return pd.concat([primary, dual],
                         ignore_index=True)
    return primary


def is_cycle60b_check_time(ts) -> bool:
    return is_cycle60_check_time(ts)


def fetch_cycle60b_m15_frames(state=None):
    """The 20-symbol M15 set for the breadth statistic: the
    shared cycle78 data path (repository first, provider
    chain for misses, freshness-guarded memo)."""
    from core.cycle78_best import fetch_cycle78_m15_frames
    return fetch_cycle78_m15_frames(state=state,
                                    symbols=SYMBOLS20)

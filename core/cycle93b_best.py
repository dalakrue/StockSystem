"""Cycle 93B (BRIEF21 C20a) -- November IMPROVED system,
integrated 2026-10-26 on the user's order to build the stateful
walk layer (core/walk_ledger.py). PROMOTED 2026-10-26: the
app replay is EXACT against the validated C20a ledger (see
FIX_NOTES_20261026_BRIEF21_APP_INTEGRATION.md); this system is
November's BEST (MONTH_SYSTEMS[11]) and the old C93-24 is
November's second priority in the combined layer.

Definition (BRIEF21 November, validated HUGE 2026-10-26):
C93-24 (core.cycle93_best, frozen) + two layers:

  1. C06 volatility-shock veto: a candidate row is dropped
     when its vol_z (Dukascopy-style M15 tick-volume statistic:
     rolling 4-bar volume sums over the last 384 causal bars,
     (last - median) / IQR -- core.walk_ledger.vol_z_at) exceeds
     the FIT-90th percentile of incumbent picks,
     1.498145894075274. The veto depends only on the candidate
     row's symbol at the check, so dropping the row from the
     signals frame is exactly the research walk's behaviour
     (the same argument as the incumbent's FBGATE).
  2. C16 TP-continuation re-entry partner: after a base trade
     exits at TP, re-enter the same symbol/direction at the
     first grid check strictly after the exit, when a candidate
     row for that symbol exists there (the highest eq-score row
     for the symbol at that check, research build_reentry) and
     the leg's full flight interval conflicts with no base/kept
     trade. This layer NEEDS the walk ledger -- see
     reentry_entries_at() and walk_cycle93b().

Validated numbers (C20a, @2.5): DISC n436 net +5128.59 win
92.20% leftover 69.12 (control 63.11); AUDIT n100 net +678.37
leftover 46.39 (control 36.33); LCT P 100.00% / q05 51.25%
(strict passes); EC22-middle 16 vs 14; Monte Carlo median
3.2419x control, P(call) 0 vs 0. Best N 83 (divided-by-3 sizing
value 27.666666666666668 in the router).

M15 / VOLUME DATA: the veto needs an M15 feed with volume and
>= 387 causal bars before the entry (the statistic's window).
When the provided M15 history is insufficient for a candidate's
symbol, this system returns NO entries for that check and marks
the frame status 'insufficient_m15_history' -- it never
silently computes a different (truncated-window) veto.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import core.cycle70_best as _c70
import core.cycle93_best as _c93
from core.cycle93_best import (CYCLE93_CHECK_HOURS,
                               fetch_cycle93_m15_frames,
                               is_cycle93_check_time,
                               select_cycle93_entries)
from core.walk_ledger import (WalkLedger, m15_arrays_from_frame,
                              vol_z_at)

CYCLE93B_CHECK_HOURS = CYCLE93_CHECK_HOURS
VOLZ_VETO_THRESHOLD = 1.498145894075274
GRID_HOURS = (9, 13, 15)


def _volz_by_symbol(sig, check_time_utc, m15_frames):
    """vol_z per candidate symbol at this check, or the string
    'insufficient' when any candidate symbol lacks the history
    the statistic needs."""
    ent = pd.Timestamp(check_time_utc) - pd.Timedelta(minutes=30)
    out = {}
    cache = {}
    for sym in sorted({str(s) for s in sig["symbol"]}):
        df = (m15_frames or {}).get(sym)
        if df is None or len(df) == 0 or "Volume" not in df.columns:
            return "insufficient"
        if sym not in cache:
            cache[sym] = m15_arrays_from_frame(df)
        vz = vol_z_at(cache[sym], ent)
        if vz is None:
            return "insufficient"
        out[sym] = vz
    return out


def evaluate_cycle93b_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """C93-24 signals with the C06 vol_z veto applied (vetoed
    rows dropped). Adds a 'vol_z' column. When a candidate
    symbol's M15 history is insufficient for vol_z, returns an
    EMPTY frame with .attrs['status'] = 'insufficient_m15_
    history' (no silently different veto)."""
    sig = _c93.evaluate_cycle93_signals(frames, check_time_utc,
                                        m15_frames=m15_frames)
    if sig is None or len(sig) == 0:
        return sig
    vzs = _volz_by_symbol(sig, check_time_utc, m15_frames)
    if vzs == "insufficient":
        out = sig.iloc[0:0].copy()
        out["vol_z"] = pd.Series(dtype=float)
        out.attrs["status"] = (
            "insufficient_m15_history: vol_z needs >=387 causal "
            "M15 bars with volume per candidate symbol")
        return out
    sig = sig.copy()
    sig["vol_z"] = [vzs[str(s)] for s in sig["symbol"]]
    keep = ~(sig["vol_z"] > VOLZ_VETO_THRESHOLD)
    return sig[keep].reset_index(drop=True)


def select_cycle93b_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Base selection: the frozen C93-24 selection (exactly 1
    entry per check)."""
    return select_cycle93_entries(signals, open_symbols=open_symbols)


def candidate_rows_at(frames: dict, check_time_utc,
                      m15_frames: dict | None = None) -> pd.DataFrame:
    """Pre-veto candidate signal rows for the re-entry layer:
    the C70-07 engine restricted to the C93 equation set,
    BEFORE the FBGATE / vol_z vetoes -- the app counterpart of
    the research eff_tabs the build_reentry pass reads."""
    orig = _c70.CYCLE70_EQUATIONS
    _c70.CYCLE70_EQUATIONS = list(_c93.C93_EQUATIONS)
    try:
        sig = _c70.evaluate_cycle70_signals(frames, check_time_utc)
    finally:
        _c70.CYCLE70_EQUATIONS = orig
    return sig


def is_cycle93b_check_time(ts) -> bool:
    return is_cycle93_check_time(ts)


def fetch_cycle93b_m15_frames(state=None):
    """M15 frames for this system: the shared cycle78 data path
    (repository first, provider chain for misses, freshness-
    guarded memo) over the C93 symbol set. Deliberately NOT the
    incumbent's private 10-minute memo wrapper, so a stale memo
    can never serve bars that predate the current check."""
    from core.cycle78_best import fetch_cycle78_m15_frames
    from core.cycle93_best import C93_SYMBOLS
    return fetch_cycle78_m15_frames(state=state,
                                    symbols=C93_SYMBOLS)


SYSTEM_NAME = "cycle93b"
REENTRY_RULE = "max_score"


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full C20a entries for one check (live panel path): the
    base pick (vol veto applied) plus any C16 re-entry leg due
    at this check, settled through the persisted walk ledger
    (core.walk_ledger.settle_panel_check). When the M15
    history is insufficient for the veto, returns NO entries
    for the check (the evaluate frame's status says why)."""
    from core.walk_ledger import settle_panel_check
    if m15_frames is None:
        m15_frames = fetch_cycle93b_m15_frames()
    sig = evaluate_cycle93b_signals(frames, check_time_utc,
                                    m15_frames=m15_frames)
    if sig is None:
        return pd.DataFrame()
    if len(sig) == 0 and sig.attrs.get("status"):
        return sig
    entries = select_cycle93b_entries(sig,
                                      open_symbols=open_symbols)
    cands = candidate_rows_at(frames, check_time_utc,
                              m15_frames=m15_frames)
    legs = settle_panel_check(SYSTEM_NAME, check_time_utc,
                              entries, cands, GRID_HOURS,
                              REENTRY_RULE, m15_frames)
    if legs:
        leg_df = pd.DataFrame(legs)
        entries = (pd.concat([entries, leg_df],
                             ignore_index=True)
                   if len(entries) else leg_df)
    return entries

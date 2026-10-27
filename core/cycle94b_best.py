"""Cycle 94B (BRIEF21 C20a) -- December IMPROVED system,
integrated 2026-10-26 on the user's order to build the stateful
walk layer (core/walk_ledger.py). PROMOTED 2026-10-26: the
app replay is EXACT against the validated C20a ledger (see
FIX_NOTES_20261026_BRIEF21_APP_INTEGRATION.md); this system is
December's BEST (MONTH_SYSTEMS[12]) and the old C94-23 is
December's second priority in the combined layer (cycle274
remains selectable standalone).

Definition (BRIEF21 December, validated HUGE 2026-10-26):
C94-23 (core.cycle94_best, frozen) + two layers:

  1. C06 volatility-shock veto: a candidate row is dropped
     when its vol_z (M15 tick-volume statistic -- see
     core.walk_ledger.vol_z_at) exceeds the December FIT-90th
     percentile of incumbent picks, 1.123626798751949. The veto
     depends only on the candidate row's symbol at the check,
     so dropping the row from the signals frame is exactly the
     research walk's behaviour.
  2. C16 TP-continuation re-entry partner: after a base trade
     exits at TP, re-enter the same symbol/direction at the
     first grid check strictly after the exit, when a gate-ok
     candidate row for that symbol exists there (the FIRST such
     row in walk/group order, research build_reentry) with the
     same resolved side (December FB rows are direction-
     stamped 'TREND'; the resolved side is the incumbent's
     mom24 rule) and the leg's full flight interval conflicts
     with no base/kept trade. This layer NEEDS the walk
     ledger -- see core/walk_ledger.py.

Validated numbers (C20a, @2.5): DISC n650 net +4479.75 win
94.92% leftover 66.20 (control 52.31); AUDIT n157 net +1135.57
leftover 75.39 (control 70.68); LCT P 100.00% / q05 54.61%;
EC22-middle 16 vs 14; P(call) 0 vs 0. Best N 105
(divided-by-3 sizing value 35.0 in the router).

M15 / VOLUME DATA: the veto needs an M15 feed with volume and
>= 387 causal bars before the entry. When the provided M15
history is insufficient for a candidate's symbol, this system
returns NO entries for that check and marks the frame status
'insufficient_m15_history' -- never a silently different veto.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import core.cycle94_best as _c94
from core.cycle94_best import (CYCLE94_CHECK_HOURS,
                               fetch_cycle94_m15_frames,
                               is_cycle94_check_time,
                               select_cycle94_entries)
from core.walk_ledger import m15_arrays_from_frame, vol_z_at

CYCLE94B_CHECK_HOURS = CYCLE94_CHECK_HOURS
VOLZ_VETO_THRESHOLD = 1.123626798751949
GRID_HOURS = (10, 11, 13)


def _volz_by_symbol(sig, check_time_utc, m15_frames):
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


def evaluate_cycle94b_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """C94-23 signals with the C06 vol_z veto applied (vetoed
    rows dropped). Adds a 'vol_z' column. Insufficient M15
    history for a candidate symbol -> EMPTY frame with
    .attrs['status'] = 'insufficient_m15_history'."""
    sig = _c94.evaluate_cycle94_signals(frames, check_time_utc,
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


def select_cycle94b_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Base selection: the frozen C94-23 selection (exactly 1
    entry per check)."""
    return select_cycle94_entries(signals, open_symbols=open_symbols)


def candidate_rows_at(frames: dict, check_time_utc,
                      m15_frames: dict | None = None) -> pd.DataFrame:
    """Candidate rows for the re-entry layer: the C94-23
    signals (the FB gate is part of the candidate definition
    in December -- research build_reentry reads gate_ok rows
    only), in walk order (score descending, stable)."""
    sig = _c94.evaluate_cycle94_signals(frames, check_time_utc,
                                        m15_frames=m15_frames)
    if sig is None or len(sig) == 0:
        return sig
    return sig.sort_values("score", ascending=False,
                           kind="mergesort").reset_index(drop=True)


def is_cycle94b_check_time(ts) -> bool:
    return is_cycle94_check_time(ts)


def fetch_cycle94b_m15_frames(state=None):
    """M15 frames for this system: the shared cycle78 data path
    (repository first, provider chain for misses, freshness-
    guarded memo) over the C94 symbol set. Deliberately NOT the
    incumbent's private 10-minute memo wrapper, so a stale memo
    can never serve bars that predate the current check."""
    from core.cycle78_best import fetch_cycle78_m15_frames
    from core.cycle94_best import C94_SYMBOLS
    return fetch_cycle78_m15_frames(state=state,
                                    symbols=C94_SYMBOLS)


SYSTEM_NAME = "cycle94b"
REENTRY_RULE = "first"


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
        m15_frames = fetch_cycle94b_m15_frames()
    sig = evaluate_cycle94b_signals(frames, check_time_utc,
                                    m15_frames=m15_frames)
    if sig is None:
        return pd.DataFrame()
    if len(sig) == 0 and sig.attrs.get("status"):
        return sig
    entries = select_cycle94b_entries(sig,
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

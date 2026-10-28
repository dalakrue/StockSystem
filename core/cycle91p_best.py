"""Cycle 91P (NEW8 Plan B-9 Track A C02 + Plan C C06) --
September IMPROVED system, integrated 2026-10-28 on the
user's order (app update, 4 winners).

Definition: the shipped September NEW8 system (cycle91n
-- C91-15 + Round-2 D26 + Plan-B P07, core.cycle91n_best,
frozen) as the incumbent, plus TWO added candidate
designs under incumbent-priority occupancy, in the
research order: first the Plan B-9 Track A design C02
(30 equations, S-CLU3D), then the Plan B-9 Plan C design
C06 (45 equations, S-CLU3DC, M15-heavy feature block)
merged over the Track-A-combined reference -- exactly
the two validate passes that produced
Sep_PLANB9_combined.csv and Sep_PLANB9C_combined.csv.

Validated numbers (NEW8 Plan B-9, @2.5): IMPROVED
(SMALL) at both steps -- Track A: DISC leftover 59.11 ->
60.43 (+1.32), AUDIT 67.36 -> 67.93 (+0.57), LCT 100% /
48.73, MC PASS (walk 303 picks, 15 accepted); Plan C:
DISC -> 62.69 (+2.26), AUDIT -> 71.50 (+3.57), LCT 100% /
51.85, MC PASS (walk 336 picks, 26 accepted). App replay
EXACT at both steps (604 rows, then 630 rows) -- see
work_29load/UPDATE_20261028.md.

September's second priority in the combined layer is
the Plan B-9 Track B design R14 (cycle91s, user waiver
2026-10-28), replacing the C287 stack. The panel check
windows below are the best's own hours (1, 10, 11 UTC)
PLUS the second best's extra hour 2 UTC from its Track B
design: at hour 2 this best's equations never fire, the
best is silent and the second best is evaluated -- the
research combined2 grid (677 trades) exactly.

Design data frozen in core.new8_designs ('sep_b9',
'sep_b9c'); merged walk state by
core.new8_candidate.MergedWalkState under system name
'cycle91p' (separate from cycle91n's state).
"""

from __future__ import annotations

import pandas as pd

import core.cycle91n_best as _c91n
from core.cycle91n_best import CYCLE91N_CHECK_HOURS

CYCLE91P_CHECK_HOURS = (1, 2, 10, 11)
DESIGNS = ("sep_b9", "sep_b9c")
SYSTEM_NAME = "cycle91p"
_DESIGN_SYMBOLS = ("AUDCHF", "AUDJPY", "CADJPY", "CHFJPY",
                   "EURCAD", "EURGBP", "EURJPY", "USDCAD",
                   "USDCHF")


def _m15(m15_frames):
    if m15_frames is not None:
        return m15_frames
    from core.cycle91_best import fetch_cycle91_m15_frames
    return fetch_cycle91_m15_frames()


def evaluate_cycle91p_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the frozen cycle91n signals."""
    return _c91n.evaluate_cycle91n_signals(
        frames, check_time_utc, m15_frames=_m15(m15_frames))


def select_cycle91p_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Base selection: the frozen cycle91n selection."""
    return _c91n.select_cycle91n_entries(
        signals, open_symbols=open_symbols)


def _cand_m15(m15_frames):
    """The B-9 designs' volm_* / M15 columns need M15
    (with Volume) for their symbols; top up via the
    shared path."""
    from core.new8_candidate import ensure_m15
    return ensure_m15(_m15(m15_frames), _DESIGN_SYMBOLS)


def candidate_rows_at(frames: dict, check_time_utc,
                      m15_frames: dict | None = None
                      ) -> pd.DataFrame:
    """B-9 candidate signal rows at one check (pre-walk)."""
    from core.new8_candidate import CandidateContext
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           DESIGNS)
    parts = [ctx.signal_frame(n, check_time_utc)
             for n in DESIGNS]
    parts = [p for p in parts if len(p)]
    return pd.concat(parts, ignore_index=True) if parts \
        else pd.DataFrame()


def is_cycle91p_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE91P_CHECK_HOURS and t.minute == 30


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check: the cycle91n
    panel entries plus accepted B-9 picks (Track A merged
    first, then Plan C), settled through this system's
    persisted merged-walk state."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row,
                                     load_state)
    from core.new8_features import frame_to_research
    from core.new8_walk import ohlc_from_frame
    m15_frames = _m15(m15_frames)
    entries = _c91n.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    state = load_state(SYSTEM_NAME, DESIGNS)
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           DESIGNS)
    for sym, fr in ctx.frames.items():
        if sym not in ctx.ohlc and fr is not None and len(fr):
            try:
                rfr, _ = frame_to_research(fr)
                ctx.ohlc[sym] = ohlc_from_frame(rfr)
            except Exception:
                pass
    accepted = state.step(ctx, check_time_utc, entries)
    state.save()
    if accepted:
        extra = pd.DataFrame([candidate_signal_row(r)
                              for r in accepted])
        entries = (pd.concat([entries, extra],
                             ignore_index=True)
                   if entries is not None and len(entries)
                   else extra)
    return entries if entries is not None else pd.DataFrame()

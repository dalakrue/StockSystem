"""Cycle 89P (NEW8 Plan B-9 Track A candidate C10) -- June
IMPROVED system, integrated 2026-10-28 on the user's order
(app update, 4 winners).

Definition: the shipped June NEW8 Plan-B system (cycle89n
-- C89-21 + Plan-B P07 design, core.cycle89n_best, frozen)
as the incumbent, plus the Plan B-9 Track A candidate
design C10 (30 equations, S-CLU3D ranking, no veto; B-9
feature block by core.new8_features groups b8/b9 on top of
the B-7 cross-symbol context) merged under
incumbent-priority occupancy (validate_new8.build_combined
rules), exactly as validate_planb9 built the research
ledger over the Jun_PLANB_combined reference.

Validated numbers (NEW8 Plan B-9, @2.5): IMPROVED (SMALL)
-- combined DISC leftover 70.48 -> 70.81 (+0.33), AUDIT
leftover 46.23 -> 46.65 (+0.42), LCT P 96.02% / q05
59.96%, Monte Carlo PASS; candidate 205 walk picks, 3
accepted. App replay EXACT against
combined/Jun_PLANB9_combined.csv (640 rows) -- see
work_29load/UPDATE_20261028.md. June's second priority in
the combined layer stays cycle89 (the old C89-21).

Design data frozen in core.new8_designs ('jun_b9'); merged
walk state by core.new8_candidate.MergedWalkState under
system name 'cycle89p' (separate from cycle89n's state).
"""

from __future__ import annotations

import pandas as pd

import core.cycle89n_best as _c89n
from core.cycle89n_best import (CYCLE89N_CHECK_HOURS,
                                is_cycle89n_check_time)

CYCLE89P_CHECK_HOURS = CYCLE89N_CHECK_HOURS
DESIGN = "jun_b9"
SYSTEM_NAME = "cycle89p"
_DESIGN_SYMBOLS = ("CADCHF", "EURAUD", "GBPCAD", "NZDJPY",
                   "USDCAD", "USDCHF")


def evaluate_cycle89p_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the frozen cycle89n base signals."""
    return _c89n.evaluate_cycle89n_signals(
        frames, check_time_utc, m15_frames=m15_frames)


def select_cycle89p_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Base selection: the frozen cycle89n selection."""
    return _c89n.select_cycle89n_entries(
        signals, open_symbols=open_symbols)


def _cand_m15(m15_frames):
    """The B-9 design's volm_* columns need M15 (with
    Volume) for its symbols; top up via the shared path."""
    from core.new8_candidate import ensure_m15
    return ensure_m15(m15_frames, _DESIGN_SYMBOLS)


def candidate_rows_at(frames: dict, check_time_utc,
                      m15_frames: dict | None = None
                      ) -> pd.DataFrame:
    """C10 candidate signal rows at one check (pre-walk)."""
    from core.new8_candidate import CandidateContext
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           (DESIGN,))
    return ctx.signal_frame(DESIGN, check_time_utc)


def is_cycle89p_check_time(ts) -> bool:
    return is_cycle89n_check_time(ts)


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check: the cycle89n
    panel entries plus the B-9 C10 pick when the merged
    walk accepts one, settled through this system's
    persisted merged-walk state."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row,
                                     load_state)
    from core.new8_features import frame_to_research
    from core.new8_walk import ohlc_from_frame
    entries = _c89n.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    state = load_state(SYSTEM_NAME, (DESIGN,))
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           (DESIGN,))
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

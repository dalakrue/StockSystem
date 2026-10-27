"""Cycle 89N (NEW8 Plan-B P07) -- June IMPROVED system,
integrated 2026-10-27 on the user's order (29-symbol build).

Definition: C89-21 (core.cycle89_best, frozen) + the NEW8
Plan-B candidate design P07 (22 equations, S-AVGL ranking)
added under incumbent-priority occupancy
(validate_new8.build_combined).

Validated numbers (NEW8 Plan B, @2.5): DISC leftover
70.09 -> 70.48, AUDIT 45.57 -> 46.23, AUDIT net +13.90,
LCT-middle PASS (P 87.83% / q05 59.02%), Monte Carlo PASS.
App replay EXACT against combined/Jun_PLANB_combined.csv
(637 rows; candidate walk 211 picks, 3 accepted) -- see
work_29load/BUILD_RESULT.md.

Design data frozen in core.new8_designs ('jun_p07');
features by core.new8_features; merged walk state by
core.new8_candidate.MergedWalkState.
"""

from __future__ import annotations

import pandas as pd

import core.cycle89_best as _c89
from core.cycle89_best import (CYCLE89_CHECK_HOURS,
                               is_cycle89_check_time,
                               select_cycle89_entries)

CYCLE89N_CHECK_HOURS = CYCLE89_CHECK_HOURS
DESIGN = "jun_p07"
SYSTEM_NAME = "cycle89n"


def _m15(m15_frames):
    if m15_frames is not None:
        return m15_frames
    from core.cycle89_best import fetch_cycle89_m15_frames
    return fetch_cycle89_m15_frames()


def evaluate_cycle89n_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the frozen C89-21 signals."""
    return _c89.evaluate_cycle89_signals(
        frames, check_time_utc, m15_frames=_m15(m15_frames))


def select_cycle89n_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Base selection: the frozen C89-21 selection."""
    return select_cycle89_entries(signals,
                                  open_symbols=open_symbols)


def candidate_rows_at(frames: dict, check_time_utc,
                      m15_frames: dict | None = None
                      ) -> pd.DataFrame:
    """P07 candidate signal rows at one check (pre-walk)."""
    from core.new8_candidate import CandidateContext
    ctx = CandidateContext(frames, m15_frames, (DESIGN,))
    return ctx.signal_frame(DESIGN, check_time_utc)


def is_cycle89n_check_time(ts) -> bool:
    return is_cycle89_check_time(ts)


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check (C89-21 pick plus an
    accepted P07 pick), settled through the persisted
    merged-walk state."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row,
                                     load_state)
    m15_frames = _m15(m15_frames)
    state = load_state(SYSTEM_NAME, (DESIGN,))
    ctx = CandidateContext(frames, m15_frames, (DESIGN,))
    entries = select_cycle89n_entries(
        evaluate_cycle89n_signals(frames, check_time_utc,
                                  m15_frames=m15_frames),
        open_symbols=open_symbols)
    accepted = state.step(ctx, check_time_utc, entries)
    state.save()
    if accepted:
        extra = pd.DataFrame([candidate_signal_row(r)
                              for r in accepted])
        entries = (pd.concat([entries, extra],
                             ignore_index=True)
                   if len(entries) else extra)
    return entries

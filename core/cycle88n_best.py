"""Cycle 88N (NEW8 Round-4 E07) -- May IMPROVED system,
integrated 2026-10-27 on the user's order (29-symbol build).

Definition: C88-03 (core.cycle88_best, frozen) + the NEW8
Round-4 candidate design E07 (18 equations on GBPAUD/GBPCAD)
added under incumbent-priority occupancy
(validate_new8.build_combined): a candidate pick is kept only
when the incumbent has no pick at that check and the pick's
[entry, exit) interval conflicts with no incumbent or
already-kept candidate trade on its symbol.

Validated numbers (NEW8 Round 4, @2.5): the design was
promoted at research level under the user's 2026-10-27 waiver
(only the LCT-middle P line waived: 69.68% vs the 80% line,
structurally capped against the near-perfect incumbent; gains
positive in both frames -- DISC leftover 93.70 -> 95.30,
AUDIT 76.58 -> 79.54, AUDIT net +170.74; Monte Carlo PASS).
App replay EXACT against combined/May_ROUND4_combined.csv
(464 rows; candidate walk 175 picks, 53 accepted) -- see
work_29load/BUILD_RESULT.md.

The equation set, conditions and walk scores are frozen in
core.new8_designs ('may_e07'); features are computed by
core.new8_features (research-identical ports); the merged
walk state is core.new8_candidate.MergedWalkState.
"""

from __future__ import annotations

import pandas as pd

import core.cycle88_best as _c88
from core.cycle88_best import (CYCLE88_CHECK_HOURS,
                               is_cycle88_check_time,
                               select_cycle88_entries)

CYCLE88N_CHECK_HOURS = CYCLE88_CHECK_HOURS
DESIGN = "may_e07"
SYSTEM_NAME = "cycle88n"


def evaluate_cycle88n_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the frozen C88-03 signals (the candidate
    layer enters through panel_entries)."""
    return _c88.evaluate_cycle88_signals(frames, check_time_utc)


def select_cycle88n_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Base selection: the frozen C88-03 selection."""
    return select_cycle88_entries(signals,
                                  open_symbols=open_symbols)


def _cand_m15(m15_frames):
    """The E07 design reads m30_mom, so its symbol needs M15
    history (for the app's M30 resample) even though the
    C88-03 incumbent itself uses none."""
    from core.new8_candidate import ensure_m15
    return ensure_m15(m15_frames, ("GBPCAD",))


def candidate_rows_at(frames: dict, check_time_utc,
                      m15_frames: dict | None = None
                      ) -> pd.DataFrame:
    """E07 candidate signal rows at one check (pre-walk)."""
    from core.new8_candidate import CandidateContext
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           (DESIGN,))
    return ctx.signal_frame(DESIGN, check_time_utc)


def is_cycle88n_check_time(ts) -> bool:
    return is_cycle88_check_time(ts)


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check: the C88-03 pick when
    it fires, plus the E07 candidate pick when the merged walk
    accepts one at this check, settled through the persisted
    merged-walk state."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row,
                                     load_state)
    state = load_state(SYSTEM_NAME, (DESIGN,))
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           (DESIGN,))
    entries = select_cycle88n_entries(
        evaluate_cycle88n_signals(frames, check_time_utc),
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

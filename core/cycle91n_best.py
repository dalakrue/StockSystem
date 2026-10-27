"""Cycle 91N (NEW8 D26 + Plan-B P07) -- September IMPROVED
system, integrated 2026-10-27 on the user's order
(29-symbol build).

Definition: C91-15 (core.cycle91_best, frozen) + TWO added
candidate designs under incumbent-priority occupancy, in the
research order: first the Round-2 design D26 (16 equations,
GBPAUD/GBPNZD), then the Plan-B design P07 (22 equations)
merged over the D26-combined reference -- exactly the two
validate passes that produced Sep_ROUND2_combined.csv and
Sep_PLANB_combined.csv.

Validated numbers (NEW8, @2.5): D26 took DISC leftover
50.21 -> 55.81 and AUDIT to 60.62; P07 then took DISC to
59.11 and AUDIT to 67.36 (AUDIT net +212.38 vs the Round-2
combined), Monte Carlo PASS at both steps. App replay EXACT
at both steps (574 rows, then 589 rows; D26 walk 206 picks /
24 accepted, P07 walk 343 picks / 15 accepted) -- see
work_29load/BUILD_RESULT.md. September's second priority in
the combined layer stays the C287 stack (cycle287).

Design data frozen in core.new8_designs ('sep_d26',
'sep_p07'); features by core.new8_features; merged walk
state by core.new8_candidate.MergedWalkState.
"""

from __future__ import annotations

import pandas as pd

import core.cycle91_best as _c91
from core.cycle91_best import (CYCLE91_CHECK_HOURS,
                               is_cycle91_check_time,
                               select_cycle91_entries)

CYCLE91N_CHECK_HOURS = CYCLE91_CHECK_HOURS
DESIGNS = ("sep_d26", "sep_p07")
SYSTEM_NAME = "cycle91n"


def _m15(m15_frames):
    if m15_frames is not None:
        return m15_frames
    from core.cycle91_best import fetch_cycle91_m15_frames
    return fetch_cycle91_m15_frames()


def evaluate_cycle91n_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the frozen C91-15 signals."""
    return _c91.evaluate_cycle91_signals(
        frames, check_time_utc, m15_frames=_m15(m15_frames))


def select_cycle91n_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Base selection: the frozen C91-15 selection."""
    return select_cycle91_entries(signals,
                                  open_symbols=open_symbols)


def candidate_rows_at(frames: dict, check_time_utc,
                      m15_frames: dict | None = None
                      ) -> pd.DataFrame:
    """D26 + P07 candidate signal rows at one check
    (pre-walk)."""
    from core.new8_candidate import CandidateContext
    ctx = CandidateContext(frames, m15_frames, DESIGNS)
    parts = [ctx.signal_frame(n, check_time_utc) for n in DESIGNS]
    parts = [p for p in parts if len(p)]
    return pd.concat(parts, ignore_index=True) if parts \
        else pd.DataFrame()


def is_cycle91n_check_time(ts) -> bool:
    return is_cycle91_check_time(ts)


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check (C91-15 pick plus
    accepted D26 / P07 picks, D26 merged first), settled
    through the persisted merged-walk state."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row,
                                     load_state)
    m15_frames = _m15(m15_frames)
    state = load_state(SYSTEM_NAME, DESIGNS)
    ctx = CandidateContext(frames, m15_frames, DESIGNS)
    entries = select_cycle91n_entries(
        evaluate_cycle91n_signals(frames, check_time_utc,
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

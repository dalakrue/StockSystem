"""Cycle 93P (NEW8 Plan B-7 candidate C02) -- November
IMPROVED system, integrated 2026-10-27 on the user's order
(two-phase update, Phase 1a).

Definition: the shipped November B-4 combined system
(cycle93n -- cycle93b + Plan B-4 partner C16, core
.cycle93n_best, frozen) as the incumbent, plus the NEW8
Plan B-7 candidate design C02 (25 equations, S-CLU3D
ranking, no veto; volume-anchor / correlated-basket /
dollar-deviation features by core.new8_features groups
b5/b6v/b7 with the cross-symbol context in
core.new8_candidate.b7_context) merged under
incumbent-priority occupancy (validate_new8.build_combined
rules), exactly as validate_planb7 built the research
ledger over the Nov_PLANB4P_combined reference.

Validated numbers (NEW8 Plan B-7, @2.5): IMPROVED (SMALL)
-- combined DISC leftover 73.15 -> 73.69 (+0.54), AUDIT
leftover 37.51 -> 38.56 (+1.05), LCT P 100% / q05 59.40%
(middle + strict), candidate 298 walk picks, 23 accepted.
App replay EXACT against combined/Nov_PLANB7_combined.csv
(687 rows; walk 298 picks, drops check_busy 275 /
symbol_overlap 0) -- see work_29load/UPDATE_20261027.md.
November's second best in the combined layer becomes
cycle93n (this system's incumbent), replacing cycle93b.

Design data frozen in core.new8_designs ('nov_b7'); merged
walk state by core.new8_candidate.MergedWalkState under
system name 'cycle93p' (separate from cycle93n's state).
"""

from __future__ import annotations

import pandas as pd

import core.cycle93n_best as _c93n
from core.cycle93n_best import (CYCLE93N_CHECK_HOURS,
                                is_cycle93n_check_time)

CYCLE93P_CHECK_HOURS = CYCLE93N_CHECK_HOURS
DESIGN = "nov_b7"
SYSTEM_NAME = "cycle93p"
_DESIGN_SYMBOLS = ("EURAUD", "EURUSD", "GBPUSD", "NZDCHF")


def evaluate_cycle93p_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the frozen cycle93n base signals
    (cycle93b: C93-24 with the C06 vol_z veto)."""
    return _c93n.evaluate_cycle93n_signals(
        frames, check_time_utc, m15_frames=m15_frames)


def select_cycle93p_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Base selection: the frozen cycle93n selection."""
    return _c93n.select_cycle93n_entries(
        signals, open_symbols=open_symbols)


def _cand_m15(m15_frames):
    """The B-7 design's volm_* columns need M15 (with
    Volume) for its four symbols; top up via the shared
    path."""
    from core.new8_candidate import ensure_m15
    return ensure_m15(m15_frames, _DESIGN_SYMBOLS)


def candidate_rows_at(frames: dict, check_time_utc,
                      m15_frames: dict | None = None
                      ) -> pd.DataFrame:
    """C02 candidate signal rows at one check (pre-walk)."""
    from core.new8_candidate import CandidateContext
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           (DESIGN,))
    return ctx.signal_frame(DESIGN, check_time_utc)


def is_cycle93p_check_time(ts) -> bool:
    return is_cycle93n_check_time(ts)


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check: the cycle93n
    panel entries (the B-4 combined system's picks at this
    check, settled through cycle93n's own merged-walk
    state) plus the B-7 C02 pick when the merged walk
    accepts one, settled through this system's persisted
    merged-walk state (research order: B-4 combined first,
    B-7 merged over it)."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row,
                                     load_state)
    from core.new8_features import frame_to_research
    from core.new8_walk import ohlc_from_frame
    entries = _c93n.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    state = load_state(SYSTEM_NAME, (DESIGN,))
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           (DESIGN,))
    # The merged walk sims incumbent exits for the overlap
    # rules; the context only builds ohlc for the design's
    # symbols, so top it up for every framed symbol.
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

"""Cycle 93Q (P-BRANCH Plan C candidate C10) -- November
IMPROVED system, integrated 2026-10-28 on the user's order
(app update, 4 winners; November winner chosen by the
cross-lane reconciliation, NOV_RECONCILIATION.md).

Definition: the shipped November Plan B-7 system
(cycle93p -- cycle93n + Plan B-7 C02, core.cycle93p_best,
frozen) as the incumbent, plus the P-BRANCH Plan C
candidate design C10 (12 OR-branch equations, S-CLU3DC
ranking, no veto) merged under incumbent-priority
occupancy (validate_new8.build_combined rules), exactly
as validate_pbranch built the research ledger over the
Nov_PLANB7_combined reference. Each OR equation carries
2 branches; a branch fires on its own conditions with its
own exit pair and hold (36h or 48h), and the first firing
branch in design order supplies the trade -- the research
tab construction (branch tabs concatenated in order,
de-duplicated on check keeping the first).

Validated numbers (P-BRANCH Plan C, @2.5): IMPROVED
(SMALL) -- combined DISC n563 net +7,741.13 leftover
73.88, AUDIT n133 net +778.71 leftover 39.40 (the only
November lane winner whose additions entered the unseen
years: 3 NZDCHF SELLs, Nov 2024); LCT P 100% / q05
59.60%, Monte Carlo PASS, PBO 0%. Candidate 196 walk
picks, 9 accepted. App replay EXACT against
parallel_score/combined/Nov_PBRANCHC_combined.csv (696
rows) -- see work_29load/UPDATE_20261028.md. November's
second priority in the combined layer stays cycle93n.

Design data frozen in core.new8_designs ('nov_pbranchc');
merged walk state by core.new8_candidate.MergedWalkState
under system name 'cycle93q' (separate from cycle93p's
state).
"""

from __future__ import annotations

import pandas as pd

import core.cycle93p_best as _c93p
from core.cycle93p_best import (CYCLE93P_CHECK_HOURS,
                                is_cycle93p_check_time)

CYCLE93Q_CHECK_HOURS = CYCLE93P_CHECK_HOURS
DESIGN = "nov_pbranchc"
SYSTEM_NAME = "cycle93q"
_DESIGN_SYMBOLS = ("EURUSD", "NZDCHF", "NZDJPY")


def evaluate_cycle93q_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the frozen cycle93p base signals."""
    return _c93p.evaluate_cycle93p_signals(
        frames, check_time_utc, m15_frames=m15_frames)


def select_cycle93q_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Base selection: the frozen cycle93p selection."""
    return _c93p.select_cycle93p_entries(
        signals, open_symbols=open_symbols)


def _cand_m15(m15_frames):
    """The P-BRANCH design's pbc_* columns are built on
    M15 for its three symbols; top up via the shared
    path."""
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


def is_cycle93q_check_time(ts) -> bool:
    return is_cycle93p_check_time(ts)


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check: the cycle93p
    panel entries plus the P-BRANCH C10 pick when the
    merged walk accepts one, settled through this
    system's persisted merged-walk state."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row,
                                     load_state)
    from core.new8_features import frame_to_research
    from core.new8_walk import ohlc_from_frame
    entries = _c93p.panel_entries(frames, check_time_utc,
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

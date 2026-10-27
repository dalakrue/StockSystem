"""Cycle 93N (NEW8 Plan B-4 partner C16) -- November
IMPROVED system, integrated 2026-10-27 on the user's order
(29-symbol build).

Definition: the shipped November combined layer (cycle93b
-- BRIEF21 C20a: C93-24 + C06 vol_z veto + C16
TP-continuation re-entry, core.cycle93b_best, frozen -- as
best, with the old C93-24 (cycle93) evaluated when the best
is silent) + the NEW8 Plan B-4 PARTNER design C16 (25
equations, S-LEFT ranking, stateful coolv two-loss cooldown
veto) added under incumbent-priority occupancy
(validate_new8.build_combined). The research reference
ledger is the two-layer combined ledger (536 best + 68
second rows), so the panel incumbent reproduces both
layers (see _incumbent_entries). The partner is a DIFFERENT
C16 from BRIEF21's re-entry leg: a mined equation design,
not a re-entry rule.

Validated numbers (NEW8 Plan B-4, @2.5): IMPROVED (SMALL)
under the user's -2.00 small-downgrade tolerance -- DISC
leftover 69.03 -> 73.15 (+4.12), AUDIT leftover -1.95
(inside tolerance), AUDIT net +17.62, LCT P 100% / q05
58.66%, Monte Carlo PASS. App replay EXACT against
combined/Nov_PLANB4P_combined.csv (664 rows; partner walk
229 picks, 60 accepted) -- see work_29load/BUILD_RESULT.md.
November's second priority in the combined layer becomes
cycle93b (this system's incumbent), replacing cycle93.

Design data frozen in core.new8_designs ('nov_c16');
features by core.new8_features (the cf_* confirmation
columns need M15 frames); merged walk state by
core.new8_candidate.MergedWalkState.
"""

from __future__ import annotations

import pandas as pd

import core.cycle93b_best as _c93b
from core.cycle93b_best import (CYCLE93B_CHECK_HOURS,
                                is_cycle93b_check_time)

CYCLE93N_CHECK_HOURS = CYCLE93B_CHECK_HOURS
DESIGN = "nov_c16"
SYSTEM_NAME = "cycle93n"


def _m15(m15_frames):
    if m15_frames is not None:
        return m15_frames
    from core.cycle93b_best import fetch_cycle93b_m15_frames
    return fetch_cycle93b_m15_frames()


def evaluate_cycle93n_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the frozen cycle93b signals (C93-24 with
    the C06 vol_z veto applied)."""
    return _c93b.evaluate_cycle93b_signals(
        frames, check_time_utc, m15_frames=_m15(m15_frames))


def select_cycle93n_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Base selection: the frozen C93-24 selection."""
    return _c93b.select_cycle93b_entries(
        signals, open_symbols=open_symbols)


def _cand_m15(m15_frames):
    """The partner's cf_* confirmation columns need M15 for
    its five symbols; the cycle93b fetcher covers only the
    C93 set, so top up the rest via the shared path."""
    from core.new8_candidate import ensure_m15
    return ensure_m15(m15_frames, ("EURAUD", "GBPAUD",
                                   "GBPCAD", "GBPJPY",
                                   "GBPUSD"))


def candidate_rows_at(frames: dict, check_time_utc,
                      m15_frames: dict | None = None
                      ) -> pd.DataFrame:
    """C16 partner candidate signal rows at one check
    (pre-walk)."""
    from core.new8_candidate import CandidateContext
    ctx = CandidateContext(frames, _cand_m15(_m15(m15_frames)),
                           (DESIGN,))
    return ctx.signal_frame(DESIGN, check_time_utc)


def is_cycle93n_check_time(ts) -> bool:
    return is_cycle93b_check_time(ts)


def _incumbent_entries(frames, check_time_utc, m15_frames,
                       open_symbols=()):
    """The incumbent side of the merged system: the shipped
    November COMBINED layer, exactly as the research reference
    ledger (incumbent/Nov_incumbent.csv: 536 'best' rows + 68
    'second' rows) was built -- cycle93b panel entries first;
    when they are empty, the old C93-24 (cycle93) evaluated
    and selected as November's second priority. The B-4
    partner merged over THAT combined ledger in research, so
    the merge state must record both layers' picks."""
    entries = _c93b.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    if entries is not None and len(entries):
        return entries
    import core.cycle93_best as _c93
    sig = _c93.evaluate_cycle93_signals(frames, check_time_utc,
                                        m15_frames=m15_frames)
    if sig is None:
        return pd.DataFrame()
    if len(sig) == 0 and sig.attrs.get("status"):
        return sig
    return _c93.select_cycle93_entries(
        sig, open_symbols=open_symbols)


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check: the cycle93b panel
    entries (base pick + any BRIEF21 re-entry leg) plus the
    B-4 partner pick when the merged walk accepts one,
    settled through the persisted merged-walk state."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row,
                                     load_state)
    m15_frames = _m15(m15_frames)
    state = load_state(SYSTEM_NAME, (DESIGN,))
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           (DESIGN,))
    entries = _incumbent_entries(frames, check_time_utc,
                                 m15_frames, open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
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

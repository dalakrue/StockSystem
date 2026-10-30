"""Cycle 92C (NEW8 Plan B-9 Track A candidate2, design
C09) -- October IMPROVED system, integrated in scratch
2026-10-30 for Round R2 candidate OCT C14 (fold-in
pending the exact-replay gate in
work_20cyc_r2/integration/oct/gate_oct_c14.py).

Definition: the shipped October combined stream --
cycle92 (C92-24 / C155 dual-pick, core.cycle92_best) as
the best, with the cycle92e second best (NEW8 Round-4
E07, core.cycle92e_best) evaluated only when the best
produces no entry at a check (the app combined-layer
rule in core.signal_mode; the REF657 construction) --
plus the Plan B-9 candidate2 design (30 equations,
S-CLU3D ranking, no veto; B-9 feature block by
core.new8_features groups b8/b9 on top of the B-7
cross-symbol context) merged under incumbent-priority
occupancy (validate_new8.build_combined rules), exactly
as the R2 lane merged the stored partner walk over
REF657.

Validated numbers (R2 Oct C14, @2.5): combined DISC
leftover 86.96 -> 87.68, AUDIT leftover 72.41 -> 73.35,
AUDIT net +1171.05 > incumbent +1118.43; candidate 280
walk picks, 43 accepted (all at checks empty in the
incumbent); LCT P 100.00% / q05 81.05%, Monte Carlo
middle PASS, PBO 0.00% / DSR 1.0000, decay PASS. App
replay gate: see the integration verdict.

Design data frozen in core.new8_designs ('oct_b9c2');
merged walk state by core.new8_candidate.MergedWalkState
under system name 'cycle92c' (separate from any cycle92 /
cycle92e state).
"""

from __future__ import annotations

import pandas as pd

import core.cycle92_best as _c92
import core.cycle92e_best as _c92e
from core.cycle92_best import (CYCLE92_CHECK_HOURS,
                              is_cycle92_check_time)

CYCLE92C_CHECK_HOURS = CYCLE92_CHECK_HOURS
DESIGN = "oct_b9c2"
SYSTEM_NAME = "cycle92c"
_DESIGN_SYMBOLS = ("AUDCHF", "AUDNZD", "NZDCAD", "NZDCHF")


def evaluate_cycle92c_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the frozen cycle92 signals."""
    return _c92.evaluate_cycle92_signals(
        frames, check_time_utc, m15_frames=m15_frames)


def select_cycle92c_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Base selection: the frozen cycle92 selection."""
    return _c92.select_cycle92_entries(
        signals, open_symbols=open_symbols)


def _cand_m15(m15_frames):
    """The B-9 design's volm_* columns need M15 (with
    Volume) for its symbols; top up via the shared path."""
    from core.new8_candidate import ensure_m15
    return ensure_m15(m15_frames, _DESIGN_SYMBOLS)


def candidate_rows_at(frames: dict, check_time_utc,
                      m15_frames: dict | None = None
                      ) -> pd.DataFrame:
    """Plan B-9 cand2 candidate signal rows at one check
    (pre-walk)."""
    from core.new8_candidate import CandidateContext
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           (DESIGN,))
    return ctx.signal_frame(DESIGN, check_time_utc)


def is_cycle92c_check_time(ts) -> bool:
    return is_cycle92_check_time(ts)


def _incumbent_stream(frames, check_time_utc, m15_frames,
                      open_symbols):
    """The shipped October combined stream at one check:
    cycle92's entries, or the cycle92e second best's pick
    when the best stream is empty (the app combined
    layer's rule -- the stream REF657 was built from).
    Returns (frame, status_frame)."""
    sig = _c92.evaluate_cycle92_signals(
        frames, check_time_utc, m15_frames=m15_frames)
    if sig is not None and len(sig) == 0 \
            and sig.attrs.get("status"):
        return None, sig
    entries = _c92.select_cycle92_entries(
        sig, open_symbols=open_symbols) \
        if sig is not None else pd.DataFrame()
    if entries is None or len(entries) == 0:
        sig2 = _c92e.evaluate_cycle92e_signals(
            frames, check_time_utc, m15_frames=m15_frames)
        if sig2 is not None and len(sig2):
            entries = _c92e.select_cycle92e_entries(
                sig2, open_symbols=open_symbols)
    return entries, None


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check: the October
    combined-stream entries (cycle92, else cycle92e) plus
    the Plan B-9 cand2 pick when the merged walk accepts
    one, settled through this system's persisted
    merged-walk state."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row,
                                     load_state)
    from core.new8_features import frame_to_research
    from core.new8_walk import ohlc_from_frame
    entries, status = _incumbent_stream(frames, check_time_utc,
                                        m15_frames,
                                        open_symbols)
    if status is not None:
        return status
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

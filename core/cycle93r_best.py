"""Cycle 93R -- November best, updated 2026-10-29 on the
user's order from the lane reconciliation
(LANE_RECONCILIATION_20261029.md): cycle93q (93p base +
P-BRANCH C10 layer, combined with the cycle93s second
best) + the P-REPLACE Track A C04 candidate layer
(design 'nov_rp' in core.new8_designs, rp_* feature
group). Definition: the shipped November combined stream
(93q panel entries; when that stream is empty at a check,
the cycle93s second best's pick -- the app combined
layer's rule, which is the stream the research merge was
built against) plus the C04 merged-walk layer
(core.new8_candidate.MergedWalkState), which accepts
candidate picks only at checks the incumbent stream
leaves empty, under the occupancy rules of the research
build_combined.

Validated numbers (P-REPLACE Nov Track A C04, @2.5,
research lane frames): combined DISC leftover 61.60 ->
61.81 (+0.20) and AUDIT leftover 39.40 -> 39.78
(+0.38) vs the shipped cycle93q+93s combined; LCT
99.59%; Monte Carlo middle PASS; the candidate accepted
6 of 213 discovery picks (Track A verdict,
work_new8/parallel_replace). Best N unchanged 83
(divided-by-3 sizing value 27.666... in the router).

Check hours: the November grid (9, 13, 15 UTC) --
CYCLE93P_CHECK_HOURS via cycle93q.
"""

from __future__ import annotations

import pandas as pd

import core.cycle93q_best as _c93q
from core.cycle93q_best import (CYCLE93P_CHECK_HOURS,
                                evaluate_cycle93q_signals,
                                is_cycle93p_check_time,
                                select_cycle93q_entries)

CYCLE93R_CHECK_HOURS = CYCLE93P_CHECK_HOURS
DESIGN = "nov_rp"
SYSTEM_NAME = "cycle93r"
_DESIGN_SYMBOLS = ("CHFJPY", "GBPCAD", "GBPCHF", "USDCAD")


def _cand_m15(m15_frames):
    from core.new8_candidate import ensure_m15
    return ensure_m15(m15_frames, _DESIGN_SYMBOLS)


def evaluate_cycle93r_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the cycle93q chain (93p base +
    P-BRANCH C10 layer) -- the merged-walk layer adds its
    picks in panel_entries / the router's combined path."""
    return evaluate_cycle93q_signals(frames, check_time_utc,
                                     m15_frames=m15_frames)


def select_cycle93r_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    return select_cycle93q_entries(signals,
                                   open_symbols=open_symbols)


def is_cycle93r_check_time(ts) -> bool:
    return is_cycle93p_check_time(ts)


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check: the shipped
    November combined stream (cycle93q panel entries; the
    cycle93s second best's pick when that stream is
    empty) plus the P-REPLACE C04 pick when the merged
    walk accepts one, settled through this system's
    persisted merged-walk state."""
    from core.cycle93s_best import (evaluate_cycle93s_signals,
                                    select_cycle93s_entries)
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row,
                                     load_state)
    from core.new8_features import frame_to_research
    from core.new8_walk import ohlc_from_frame
    entries = _c93q.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    if entries is None or len(entries) == 0:
        sig = evaluate_cycle93s_signals(frames, check_time_utc,
                                        m15_frames=m15_frames)
        if sig is not None and len(sig):
            entries = select_cycle93s_entries(
                sig, open_symbols=open_symbols)
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

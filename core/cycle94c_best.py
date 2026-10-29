"""Cycle 94C -- December best, updated 2026-10-29 on the
user's order from the lane reconciliation
(LANE_RECONCILIATION_20261029.md): cycle94b (C94-23 +
C06 vol veto + C16 re-entry, combined with the cycle94s
second best) + the P-REGIME (B-10 revival) improvement
stack, applied in the research order:

  1. Track A C07 candidate layer (design 'dec_rg',
     pr_* feature group), merged onto the shipped
     December combined stream;
  2. Plan C C07 candidate layer (design 'dec_rgc'),
     merged onto the Track A result.

Both layers run in ONE merged walk
(core.new8_candidate.MergedWalkState over the two
designs, in that order), which is exactly the staged
research build_combined chain: each layer accepts picks
only at checks the stream so far leaves empty, under
the same occupancy rules. The incumbent stream is the
shipped December combined (cycle94b panel entries; when
that stream is empty at a check, the cycle94s second
best's pick -- the app combined layer's rule, which is
the stream the research merges were built against).

Validated numbers (P-REGIME Dec, @2.5, research lane
frames): Track A leftover DISC +0.04 / AUDIT +0.18 vs
the shipped base; Plan C on top DISC +0.05 / AUDIT
+0.00; final combined DISC leftover 71.01, AUDIT 69.68
(REVISED) -- the December winner on the user's AUDIT
tiebreak rule among the three reconciliation SMALLs.
Best N unchanged 105 (divided-by-3 sizing value 35.0
in the router). NOTE: at divided-by-3 sizing this
system's peak margin was measured at 191.95% in the
lane (report caveat, not a gate).

Check hours: the December grid (10, 11, 13 UTC) --
CYCLE94B_CHECK_HOURS via cycle94b.
"""

from __future__ import annotations

import pandas as pd

import core.cycle94b_best as _c94b
from core.cycle94b_best import (CYCLE94B_CHECK_HOURS,
                                evaluate_cycle94b_signals,
                                fetch_cycle94b_m15_frames,
                                is_cycle94b_check_time,
                                select_cycle94b_entries)

CYCLE94C_CHECK_HOURS = CYCLE94B_CHECK_HOURS
DESIGNS = ("dec_rg", "dec_rgc")
SYSTEM_NAME = "cycle94c"


def evaluate_cycle94c_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the cycle94b chain -- the merged-walk
    layers add their picks in panel_entries / the
    router's combined path."""
    return evaluate_cycle94b_signals(frames, check_time_utc,
                                     m15_frames=m15_frames)


def select_cycle94c_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    return select_cycle94b_entries(signals,
                                   open_symbols=open_symbols)


def is_cycle94c_check_time(ts) -> bool:
    return is_cycle94b_check_time(ts)


def fetch_cycle94c_m15_frames(state=None):
    return fetch_cycle94b_m15_frames(state=state)


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check: the shipped
    December combined stream (cycle94b panel entries;
    the cycle94s second best's pick when that stream is
    empty) plus any P-REGIME layer pick the merged walk
    accepts, settled through this system's persisted
    merged-walk state."""
    from core.cycle94s_best import (evaluate_cycle94s_signals,
                                    select_cycle94s_entries)
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row,
                                     load_state)
    from core.new8_features import frame_to_research
    from core.new8_walk import ohlc_from_frame
    entries = _c94b.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    if entries is None or len(entries) == 0:
        sig = evaluate_cycle94s_signals(frames, check_time_utc,
                                        m15_frames=m15_frames)
        if sig is not None and len(sig):
            entries = select_cycle94s_entries(
                sig, open_symbols=open_symbols)
    state = load_state(SYSTEM_NAME, DESIGNS)
    ctx = CandidateContext(frames, m15_frames, DESIGNS)
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

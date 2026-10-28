"""Cycle 87C (Plan B-2 Q09 non-dollar + P-VOTE C01) --
April IMPROVED system, integrated 2026-10-28 on the
user's order (app update, 4 winners).

Definition: the shipped April BRIEF21 system (cycle87b
-- C87-24 + C12 dual-pick + C16 re-entry, core
.cycle87b_best, frozen) as the incumbent, plus TWO added
candidate designs under incumbent-priority occupancy, in
the research order: first the Plan B-2 design Q09 (26
equations as mined; the 11 dollar-index equations are
EXCLUDED -- this app ships zero dollar-trading equations
under the user's 2026-10-27 dollar purge, so the design
ships its 15 FX equations only), then the P-VOTE Track A
design C01 (30 vote-share equations on the V01 pool,
S-CLU3D) merged over the Q09-combined reference.

Validated numbers (@2.5): the research base
Apr_PLANB2_combined (900 rows) = the app 87b ledger
(897) + Q09's 3 accepted picks, exactly ONE of them the
dollar-index trade (2018-04-06 18:30 UTC SELL) that this
app cannot and must not reproduce (named exception,
user's dollar purge order). The gate for this system is
therefore: every NON-dollar trade reproduced exactly, in
order -- 897 + 2 Q09 picks = 899, then P-VOTE C01 adds
its 3 accepted picks (walk 204, all on FX pairs) for the
final 902 rows of parallel_vote/combined/
Apr_PVOTE_combined.csv (which itself contains zero
dollar-index rows). P-VOTE April verdict: IMPROVED
(SMALL), DISC leftover 84.66 (+0.13 vs the B-2 base),
LCT P 81.79% / q05 75.04%, Monte Carlo PASS, PBO 10%.
App replay EXACT at both steps -- see
work_29load/UPDATE_20261028.md. April's second priority
in the combined layer stays cycle87 (the old C87-24).

Design data frozen in core.new8_designs ('apr_q09',
'apr_pvote'); merged walk state by
core.new8_candidate.MergedWalkState under system name
'cycle87c' (separate from cycle87b's state).
"""

from __future__ import annotations

import pandas as pd

import core.cycle87b_best as _c87b
from core.cycle87b_best import (CYCLE87B_CHECK_HOURS,
                                is_cycle87b_check_time)

CYCLE87C_CHECK_HOURS = CYCLE87B_CHECK_HOURS
DESIGNS = ("apr_q09", "apr_pvote")
SYSTEM_NAME = "cycle87c"
_DESIGN_SYMBOLS = ("CADCHF", "CADJPY", "CHFJPY", "EURCHF",
                   "EURNZD", "GBPAUD", "GBPJPY", "USDCHF")


def _m15(m15_frames):
    if m15_frames is not None:
        return m15_frames
    from core.cycle87_best import fetch_cycle87_m15_frames
    return fetch_cycle87_m15_frames()


def evaluate_cycle87c_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the frozen cycle87b signals."""
    return _c87b.evaluate_cycle87b_signals(
        frames, check_time_utc, m15_frames=_m15(m15_frames))


def select_cycle87c_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Base selection: the frozen cycle87b selection."""
    return _c87b.select_cycle87b_entries(
        signals, open_symbols=open_symbols)


def _cand_m15(m15_frames):
    """The P-VOTE design's M15 vote legs need M15 (with
    Volume) for its symbols; top up via the shared path."""
    from core.new8_candidate import ensure_m15
    return ensure_m15(_m15(m15_frames), _DESIGN_SYMBOLS)


def candidate_rows_at(frames: dict, check_time_utc,
                      m15_frames: dict | None = None
                      ) -> pd.DataFrame:
    """Q09 + P-VOTE candidate signal rows at one check
    (pre-walk)."""
    from core.new8_candidate import CandidateContext
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           DESIGNS)
    parts = [ctx.signal_frame(n, check_time_utc)
             for n in DESIGNS]
    parts = [p for p in parts if len(p)]
    return pd.concat(parts, ignore_index=True) if parts \
        else pd.DataFrame()


def is_cycle87c_check_time(ts) -> bool:
    return is_cycle87b_check_time(ts)


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check: the cycle87b
    panel entries plus accepted Q09 / P-VOTE picks (Q09
    merged first, then P-VOTE), settled through this
    system's persisted merged-walk state."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row,
                                     load_state)
    from core.new8_features import frame_to_research
    from core.new8_walk import ohlc_from_frame
    m15_frames = _m15(m15_frames)
    entries = _c87b.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    state = load_state(SYSTEM_NAME, DESIGNS)
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           DESIGNS)
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

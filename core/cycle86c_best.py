"""Cycle 86C -- March best, updated 2026-10-29 on the
user's order from the lane reconciliation
(LANE_RECONCILIATION_20261029.md): the P-REPLACE Track A
C06 winner (HUGE). Unlike every earlier layer, this one
REPLACES incumbent slot equations instead of adding
beside them (the addition lanes were capped by the
occupancy wall):

  Base stream: the shipped March combined (cycle86b =
  C86-24 + C150 overlay; when that stream is empty at a
  check, the cycle86s second best's pick).
  Replacement (research preplace_replace.build_replaced):
  the C06 candidate (design 'mar_rp', rp_* feature group)
  claims 11 (symbol, check-hour) slots -- AUDNZD, AUDUSD,
  CHFJPY, EURAUD, EURCHF, EURJPY, NZDCAD, NZDCHF,
  NZDUSD, USDCAD, USDJPY, all at hour 16 UTC. Incumbent
  rows at claimed slots are displaced (176 research
  rows); candidate picks merge against the KEPT
  incumbent rows only (check-busy and symbol-overlap
  judged against kept rows and accepted picks). The
  research greedy slot-revert set is EMPTY for this
  candidate. Net research effect: +148 candidate rows,
  -176 incumbent rows vs the shipped combined.

Validated numbers (P-REPLACE Mar Track A C06, @2.5,
research lane frames): combined DISC leftover 66.10 ->
78.27 and AUDIT leftover 8.84 -> 22.99 vs the shipped
cycle86b+86s combined; LCT 100.00%; Monte Carlo middle
PASS; PBO 0.00 (LOW); DSR 1.0; combined DISC entries/day
3.122. Best N unchanged 86 (divided-by-3 sizing value
28.666... in the router).

Check hours: the March grid (11, 16, 17 UTC) --
CYCLE86B_CHECK_HOURS via cycle86b. The candidate design
itself evaluates on (11, 12, 16, 17).
"""

from __future__ import annotations

import pandas as pd

import core.cycle86b_best as _c86b
from core.cycle86b_best import (CYCLE86B_CHECK_HOURS,
                                evaluate_cycle86b_signals,
                                is_cycle86b_check_time,
                                select_cycle86b_entries)

CYCLE86C_CHECK_HOURS = CYCLE86B_CHECK_HOURS
DESIGN = "mar_rp"
SYSTEM_NAME = "cycle86c"
CLAIMED_SLOTS = tuple((s, 16) for s in (
    "AUDNZD", "AUDUSD", "CHFJPY", "EURAUD", "EURCHF",
    "EURJPY", "NZDCAD", "NZDCHF", "NZDUSD", "USDCAD",
    "USDJPY"))
REVERTED_SLOTS: tuple = ()


def evaluate_cycle86c_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the cycle86b chain -- the replacement
    layer acts in panel_entries / the router's combined
    path."""
    return evaluate_cycle86b_signals(frames, check_time_utc,
                                     m15_frames=m15_frames)


def select_cycle86c_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    return select_cycle86b_entries(signals,
                                   open_symbols=open_symbols)


def is_cycle86c_check_time(ts) -> bool:
    return is_cycle86b_check_time(ts)


def _incumbent_stream(frames, check_time_utc, m15_frames,
                      open_symbols):
    """The shipped March combined stream at one check:
    cycle86b's pick, or the cycle86s second best's pick
    when the best stream is empty (the app combined
    layer's rule -- the stream the research replacement
    was built against). Returns (frame, status_frame)."""
    sig = _c86b.evaluate_cycle86b_signals(
        frames, check_time_utc, m15_frames=m15_frames)
    if sig is not None and len(sig) == 0 \
            and sig.attrs.get("status"):
        return None, sig
    entries = _c86b.select_cycle86b_entries(
        sig, open_symbols=open_symbols) \
        if sig is not None else pd.DataFrame()
    if entries is None or len(entries) == 0:
        from core.cycle86s_best import (
            evaluate_cycle86s_signals, select_cycle86s_entries)
        sig = evaluate_cycle86s_signals(frames, check_time_utc,
                                        m15_frames=m15_frames)
        if sig is not None and len(sig):
            entries = select_cycle86s_entries(
                sig, open_symbols=open_symbols)
    return entries, None


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full replaced entries for one check: the kept
    incumbent-stream rows (claimed slots displaced) plus
    the C06 candidate pick when the replaced walk accepts
    one, settled through this system's persisted
    replaced-walk state."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row,
                                     load_replaced_state)
    from core.new8_features import frame_to_research
    from core.new8_walk import ohlc_from_frame
    stream, status = _incumbent_stream(frames, check_time_utc,
                                       m15_frames,
                                       open_symbols)
    if status is not None:
        return status
    hour = int(pd.Timestamp(check_time_utc).hour)
    if stream is not None and len(stream):
        kept = stream[[(str(s), hour) not in set(CLAIMED_SLOTS)
                       for s in stream["symbol"]]]
    else:
        kept = stream
    state = load_replaced_state(SYSTEM_NAME, (DESIGN,),
                                CLAIMED_SLOTS, REVERTED_SLOTS)
    ctx = CandidateContext(frames, m15_frames, (DESIGN,))
    for sym, fr in ctx.frames.items():
        if sym not in ctx.ohlc and fr is not None and len(fr):
            try:
                rfr, _ = frame_to_research(fr)
                ctx.ohlc[sym] = ohlc_from_frame(rfr)
            except Exception:
                pass
    accepted = state.step(ctx, check_time_utc, stream)
    state.save()
    out = kept if kept is not None else pd.DataFrame()
    if accepted:
        extra = pd.DataFrame([candidate_signal_row(r)
                              for r in accepted])
        out = (pd.concat([out, extra], ignore_index=True)
               if len(out) else extra)
    return out if out is not None else pd.DataFrame()

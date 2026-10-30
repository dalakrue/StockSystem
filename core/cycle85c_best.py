"""Cycle 85C (R2 A16) -- February IMPROVED system,
integrated 2026-10-30 from 20-Cycle Round R2
(feb_planA2_s1.md, feb_combined_best_s1.md fallback form).

Definition: the shipped February system cycle85b
(C85-23 + C96-N082 + BRIEF22 C19, core.cycle85b_best,
frozen) plus the R2 A16 stack:
  1. Slot veto (eligibility, fall-through): signal rows
     with equation == FB_EURUSD_h16_1 are removed BEFORE
     the cycle85b selection, so the app's own selection
     falls through to the next eligible primary / partner
     (the C05-veto precedent form inside cycle85b). At
     research replay this walk (A01) reproduced the C08
     replay of feb_verify.md exactly (435 picks).
  2. PLANB cand2 partner (design 'feb_p38', P38, axis
     S-LEFT, d1v daily-state agreement veto): the design's
     walk merges second-priority against the vetoed base
     (accepted only at a check the base does not take,
     no symbol-interval overlap) -- 45 accepted at
     research replay. The design's two DOLLARIDX
     equations walk for occupancy only (the research
     walk's single-pick-per-check path depends on them:
     excluding them lets a GBPAUD substitute pick survive
     the merge at 2018-02-02 13:30 and breaks exact
     reproduction); their rows are excluded at the merge
     and are NEVER emitted as trades, exactly as the
     research A16 merge excluded the 8 DOLLARIDX rows.
     This system trades no dollar-index symbol.

Validated numbers (R2 Feb Plan A attempt 2, @2.5, all at
app-replay level for the base + design walk): DISC n375
net +4903.75, leftover 82.62% (incumbent 76.90%); AUDIT
n105 net +510.96, leftover 41.21% (incumbent 37.28%,
strictly greater); LCT P 96.40% / q05 71.83% (middle +
strict PASS); MC verbatim flag TRUE (DD p95 171.39 vs
own cap 189.56); PBO 0.00% / DSR 1.0000 (stated family
of 21); decay WEAKENED = the incumbent's own class.
February stays without a MONTH_SECOND_BEST entry (the
A16+X12 combined form's X12 union layer is not part of
this install). Best N unchanged (104, as C85-23 +
C96-N082).
"""

from __future__ import annotations

import pandas as pd

import core.cycle85b_best as _c85b
from core.cycle85b_best import (CYCLE85B_CHECK_HOURS,
                                is_cycle85b_check_time)

CYCLE85C_CHECK_HOURS = CYCLE85B_CHECK_HOURS
VETO_EQUATION = "FB_EURUSD_h16_1"
DESIGNS = ("feb_p38",)
SYSTEM_NAME = "cycle85c"


def evaluate_cycle85c_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the frozen cycle85b signals (the veto
    acts in selection, exactly as the research replay
    driver applied it)."""
    return _c85b.evaluate_cycle85b_signals(
        frames, check_time_utc, m15_frames=m15_frames)


def select_cycle85c_entries(signals: pd.DataFrame,
                            open_symbols=(),
                            live_count: int = 0,
                            m15_frames: dict | None = None,
                            check_time_utc=None) -> pd.DataFrame:
    """A16 selection: FB_EURUSD_h16_1 veto (fall-through)
    -> frozen cycle85b selection (C05 volr veto, primary
    pick, C19 score-gated dual partner)."""
    if signals is None or len(signals) == 0:
        return signals.iloc[0:0] if signals is not None \
            else pd.DataFrame()
    sig = signals
    if "equation" in sig.columns:
        sig = sig[sig["equation"].astype(str) != VETO_EQUATION]
        if len(sig) == 0:
            return sig.iloc[0:0]
    return _c85b.select_cycle85b_entries(
        sig, open_symbols=open_symbols, live_count=live_count,
        m15_frames=m15_frames, check_time_utc=check_time_utc)


def is_cycle85c_check_time(ts) -> bool:
    return is_cycle85b_check_time(ts)


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check: the vetoed
    cycle85b base entries plus accepted feb_p38 partner
    picks, settled through this system's persisted
    merged-walk state."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row,
                                     load_state)
    from core.new8_features import frame_to_research
    from core.new8_walk import ohlc_from_frame
    sig = evaluate_cycle85c_signals(frames, check_time_utc,
                                    m15_frames=m15_frames)
    if sig is not None and len(sig) == 0 \
            and sig.attrs.get("status"):
        return sig
    entries = select_cycle85c_entries(
        sig, open_symbols=open_symbols,
        live_count=len({str(s).upper()
                        for s in (open_symbols or ())}),
        m15_frames=m15_frames, check_time_utc=check_time_utc)
    if entries is None:
        entries = pd.DataFrame()
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
    # DOLLARIDX walk rows are occupancy-only (see module
    # docstring): never emitted as trades.
    accepted = [r for r in accepted
                if str(r["symbol"]) != "DOLLARIDX"]
    if accepted:
        extra = pd.DataFrame([candidate_signal_row(r)
                              for r in accepted])
        entries = (pd.concat([entries, extra],
                             ignore_index=True)
                   if len(entries) else extra)
    return entries if entries is not None else pd.DataFrame()

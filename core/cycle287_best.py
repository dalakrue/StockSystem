"""Cycle 287 (C287) -- September SECOND-BEST system: the
BRIEF18 Block A A1 confirmation stack at depth 3 over the
standing September system C91-15 (core.cycle91_best,
UNCHANGED and still the September default).

INTEGRATED 2026-10-25 under the user's explicit waiver order
("I can ignore chain and DSR test, continue"): this candidate
passed every other term of the standing middle battery (audit
judging, corrected LCT-middle P 100.00% / q05 100.00%, EC22
14 vs control 14, DSR 0.9806 PASS, priorities 14/16, red
lines) and was blocked ONLY by the chain floor, which the
user waived. It is NOT an old-policy validation. The
incumbent C91-15 remains the September default everywhere;
this module is an additional selectable system only.

DEFINITION (BRIEF18 September, C285-C294; engine:
fx/work_m15mine/b18_sep, stacks_a1.json depth 3 = condition
indices [73, 81, 1] of step2_trackA_lib.all_conditions(),
thresholds = the FIT-frame th_fit.json quantiles): the
incumbent C91-15 walk (sep_walk order, max 1 open trade per
symbol, X30B stop layer applied to the picks exactly as in
C91-15) where a candidate row is VETOED at pick time unless
its section-3 feature row (BRIEF16 feature table, computed
at the entry time from M15 bars, generation recipe) satisfies
ALL three stack conditions:

   1. hammer-c0   : M15 hammer flag == 1 AND d == +1
   2. pin_b-c0    : M15 pin_b flag == 1 AND d == +1
   3. rsi-q50-rev : d * (rsi14 - 50) <= 0.0

Direction term d (the September pool convention): the C197
pools carry the RESOLVED trade direction (pool direction ==
tdir, asserted in the research engine), so d = +1 for BUY
rows and -1 for SELL rows for every candidate, fallbacks
included. Conditions use the research tolerance
(threshold + 1e-12). A row whose features cannot be computed
(no M15 data / NaN) FAILS the stack, exactly as a NaN fails
cond_mask in the research engine.

VERIFIED NUMBERS (research ledgers, cost 2.5, A3 frame;
app-replay verification in FIX_NOTES_20261025_WAIVER_
INTEGRATION.md): DISC (Sep 2016-2023) n12 net +90.34 win
100.00% leftover 100.00 DD 0.00; AUDIT (Sep 2024+2025) n2
net +15.00 win 100.00% leftover 100.00 DD 0.00. Best N 83
(the incumbent's ladder). Recorded caveat: the candidate
survives on 12 + 2 trades -- the thinnest evidence of the
four waived candidates.

M15 DATA: as for C91-15, through the cycle78 data path
(local candle repository first, provider chain for misses,
memoised 10 minutes) over the C91 symbol set. Feature
values are computed over the trailing min(1600, available)
M15 bars ending at the entry time (see core.cycle274_best
for the window note).
"""

from __future__ import annotations

import pandas as pd

import core.cycle91_best as _c91
from core.cycle91_best import (CYCLE91_CHECK_HOURS,
                               is_cycle91_check_time,
                               select_cycle91_entries)
from core.cycle78_best import fetch_cycle78_m15_frames
from core.cycle274_best import stack_features

CYCLE287_CHECK_HOURS = CYCLE91_CHECK_HOURS
C287_SYMBOLS = list(_c91.C91_SYMBOLS)


def _sep_stack_pass(feat, d):
    """The C287 depth-3 stack (all three conditions,
    research cond_mask semantics; NaN fails)."""
    if feat is None:
        return False
    if not (feat['hammer'] == 1.0 and d == 1.0):
        return False
    if not (feat['pin_b'] == 1.0 and d == 1.0):
        return False
    if not (d * (feat['rsi14'] - 50.0) <= 0.0 + 1e-12):
        return False
    return True


def evaluate_cycle287_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None) -> pd.DataFrame:
    """C91-15 signals (3 FB legs removed + X30B stop layer,
    via the frozen cycle91 module) with the C287 confirmation
    stack applied: rows failing any stack condition are
    dropped, which is exactly the research walk's behaviour
    (the stack vetoes at pick time; the walk continues to the
    next row at the check)."""
    sig = _c91.evaluate_cycle91_signals(frames, check_time_utc,
                                        m15_frames=m15_frames)
    if sig is None or len(sig) == 0:
        return sig
    sig = sig.copy()
    feat_cache: dict = {}
    keep = []
    for i, row in sig.iterrows():
        sym = str(row['symbol'])
        if sym not in feat_cache:
            m15df = (m15_frames or {}).get(sym)
            feat_cache[sym] = stack_features(
                m15df, row['entry_candle'], float(row['entry_px'])) \
                if m15df is not None else None
        feat = feat_cache[sym]
        d = 1.0 if str(row['direction']) == 'BUY' else -1.0
        if _sep_stack_pass(feat, d):
            keep.append(i)
    return sig.loc[keep] if keep else sig.iloc[0:0]


def select_cycle287_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: the frozen C59-18 selection
    (as for C91-15)."""
    return select_cycle91_entries(signals, open_symbols=open_symbols)


def is_cycle287_check_time(ts) -> bool:
    return is_cycle91_check_time(ts)


_M15_FETCH_MEMO = {"ts": None, "frames": None}
_M15_FETCH_TTL_S = 600.0


def fetch_cycle287_m15_frames(state=None):
    """Use the shared current M15 data; do not retain a stale private memo."""
    return fetch_cycle78_m15_frames(state=state, symbols=C287_SYMBOLS)

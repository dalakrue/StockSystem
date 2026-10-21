"""Cycle 92 (C92-24) -- October H1 system, PROMOTED
2026-10-21 (Program 4 retry round; BRIEF6 priorities).
APP-DEFAULT ONLY: the live R4A01 signal crons are a
separate system and are not touched by this module.

C69-07 IS FROZEN as the entry engine (core.cycle69_best,
checks at 15:00 / 17:00 / 18:00 UTC, exactly 1 entry/check).
Cycle 92 changes exactly two things:

  1. Four TREND-fallback legs are REMOVED:
     FB_USDJPY_h17_0, FB_EURJPY_h18_0, FB_GBPJPY_h18_1,
     FB_AUDUSD_h17_1 (the incumbent FB layer was 365 of
     594 discovery trades, net -467.3, 55 of 56 losses,
     leftover -16.42%). FB_EURUSD_h15_0 and
     FB_GBPUSD_h15_1 are retained.
  2. Seven screened fresh legs from the Cycle-69 pool
     are ADDED at fallback-tier scores 512..506 (above
     the TREND fallbacks at -1e9, below every proven
     pick >= 941): they fill checks the proven layers
     leave empty and never displace a proven pick.
     Screen: standalone discovery n>=25, win >=97%,
     DD >=-85, positive in >=8/9 years. The added legs
     walked 103 discovery trades (+965.7, 1 loss) and
     18 unseen trades (+103.1). Their conditions need
     four feature columns the frozen engine does not
     emit (srs_k, srs_ks2, lag_s2, sem_df); they are
     computed here with the exact Cycle-69 research
     definitions (c69_prep.fresh_features) and added to
     the feature frame during evaluation.

Verified numbers (C92-24): paired LCT-middle AND
LCT-strict PASS vs C69-07 (P 100.00%, own 5th-percentile
70.20%; the incumbent's own p5 was 8.90%); unseen
leftover 62.78% vs 47.69%, win 93.75%, 2.09
entries/day; discovery net +3,231.7 vs +1,658.4
(leftover 80.26% vs 32.53%), RoMAD 2.89 vs 1.55.
DISCLOSED: raw unseen net is +296.7, 8.6 pips BELOW the
incumbent's +305.3 -- the promotion rests on the user's
stated priorities (LCT first, leftover second). Best N
83 (own sizing run: peak margin 48.03%, max DD 7.70%).
C69-07 remains selectable as cycle69.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import core.cycle69_best as _c69
from core.cycle69_best import (CYCLE69_CHECK_HOURS,
                               is_cycle69_check_time,
                               select_cycle69_entries)

CYCLE92_CHECK_HOURS = CYCLE69_CHECK_HOURS

_DROP_IDS = ("FB_USDJPY_h17_0", "FB_EURJPY_h18_0",
             "FB_GBPJPY_h18_1", "FB_AUDUSD_h17_1")


def _c(col, op, val):
    return {"col": col, "op": op, "val": val}


_FRESH_LEGS = [
    {"id": "WT_wt_zone_EURJPY_h17_BUY_1.0x8.0",
     "symbol": "EURJPY", "hour": 17, "direction": "BUY",
     "conditions": [_c("wt_1", ">", 30.0), _c("wt_s2", ">", 0.0)],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 512.0},
    {"id": "SRS_srs_zone_EURCAD_h15_SELL_0.75x8.0",
     "symbol": "EURCAD", "hour": 15, "direction": "SELL",
     "conditions": [_c("srs_k", "<", 20.0), _c("srs_ks2", "<", 0.0)],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 511.0},
    {"id": "RBW_rbw_calm_CHFJPY_h18_SELL_0.5x8.0",
     "symbol": "CHFJPY", "hour": 18, "direction": "SELL",
     "conditions": [_c("rbw_d", "<", -0.3), _c("rbw_sp", "<", 1.2)],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 510.0},
    {"id": "LAG_lag_mid_NZDCAD_h15_SELL_0.75x8.0",
     "symbol": "NZDCAD", "hour": 15, "direction": "SELL",
     "conditions": [_c("lag_rsi", "<", 0.5), _c("lag_s2", "<", 0.0)],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 509.0},
    {"id": "COMBO_wt_sem_CHFJPY_h17_SELL_0.5x8.0",
     "symbol": "CHFJPY", "hour": 17, "direction": "SELL",
     "conditions": [_c("wt_1", "<", 0.0), _c("sem_df", "<", -0.1)],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 508.0},
    {"id": "RBW_rbw_calm_NZDCAD_h18_SELL_0.75x8.0",
     "symbol": "NZDCAD", "hour": 18, "direction": "SELL",
     "conditions": [_c("rbw_d", "<", -0.3), _c("rbw_sp", "<", 1.2)],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 507.0},
    {"id": "COMBO_lag_zle_EURNZD_h18_BUY_0.3x3.0",
     "symbol": "EURNZD", "hour": 18, "direction": "BUY",
     "conditions": [_c("lag_rsi", ">", 0.5), _c("zle_d", ">", 0.2)],
     "tp_mult": 0.3, "sl_mult": 3.0, "score": 506.0},
]

C92_EQUATIONS = [e for e in _c69.CYCLE69_EQUATIONS
                 if e["id"] not in _DROP_IDS] + _FRESH_LEGS
assert len(C92_EQUATIONS) == 36, len(C92_EQUATIONS)

_ORIG_FEAT69 = _c69._symbol_feat


def _symbol_feat92(df: pd.DataFrame) -> pd.DataFrame:
    """The frozen cycle69 feature frame plus the four
    columns the fresh legs need, with the exact Cycle-69
    research definitions (c69_prep.fresh_features):
    srs_k/srs_ks2 (Stochastic RSI %K, SMA3, and its 2-bar
    change), lag_s2 (Laguerre RSI 2-bar change), sem_df
    (48-bar semivariance difference ratio)."""
    f = _ORIG_FEAT69(df)
    C = f["Close"]
    delta = C.diff()
    ag = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14,
                                 adjust=False).mean()
    al = (-delta.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14,
                                    adjust=False).mean()
    rsi = 100.0 - 100.0 / (1.0 + ag / al.replace(0.0, np.nan))
    lo = rsi.rolling(14, min_periods=14).min()
    hi = rsi.rolling(14, min_periods=14).max()
    raw = (rsi - lo) / (hi - lo).replace(0.0, np.nan) * 100.0
    k = raw.rolling(3, min_periods=3).mean()
    f["srs_k"] = k
    f["srs_ks2"] = k - k.shift(2)
    f["lag_s2"] = f["lag_rsi"] - f["lag_rsi"].shift(2)
    r = np.log(C / C.shift(1))
    up2 = (r.clip(lower=0) ** 2).rolling(48, min_periods=48).sum()
    dn2 = (r.clip(upper=0) ** 2).rolling(48, min_periods=48).sum()
    f["sem_df"] = (up2 - dn2) / (up2 + dn2).replace(0.0, np.nan)
    return f


def evaluate_cycle92_signals(frames: dict, check_time_utc,
                             m15_frames: dict | None = None) -> pd.DataFrame:
    """C69-07 signals minus the 4 cut FB legs plus the 7
    screened fresh legs. `m15_frames` is accepted for
    router uniformity and ignored (the system is pure H1)."""
    orig_eq = _c69.CYCLE69_EQUATIONS
    orig_feat = _c69._symbol_feat
    _c69.CYCLE69_EQUATIONS = C92_EQUATIONS
    _c69._symbol_feat = _symbol_feat92
    try:
        sig = _c69.evaluate_cycle69_signals(frames, check_time_utc)
    finally:
        _c69.CYCLE69_EQUATIONS = orig_eq
        _c69._symbol_feat = orig_feat
    return sig


def select_cycle92_entries(signals: pd.DataFrame,
                           open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: the frozen C69-07 selection."""
    return select_cycle69_entries(signals, open_symbols=open_symbols)


def is_cycle92_check_time(ts) -> bool:
    return is_cycle69_check_time(ts)

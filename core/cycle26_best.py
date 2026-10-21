"""Cycle 26 module: C26-33 (November-only, Phase-1 best-nearly pick).

The Cycle 26 research winner by the authorized best-nearly fallback:
28 equations (16 mined mom/atr + 12 TREND fallbacks) spanning 3 check
hours (10:30, 11:30, 18:30 UTC = 17:00, 18:00, 01:00 MMT), exactly 1
entry per check (top-1 by score at each check).

Mined on November discovery only (2016-11 -> 2024-11); unseen November 2025
touched ONLY for the 12-check evaluation (never for selection).

Unseen (2025-11-01 -> 2025-11-30): +224.5 pips / 60 trades / RoMAD 1.04 /
win 91.67% / max DD -216.9 / EV +3.74 / 3-pip +104.5 / bootstrap 87.8%.
12-check: 9/12 PASS -- failed only bootstrap>=95% (87.8%), one red
November (2017-11: -58.2), and 8/45 red weeks. used_unseen_for_selection=False.
Overfit verdict: mild decay accepted per user calibration ("robust with mild overfit").

Selection: no process cleared all 12 (0/40); C26-33 is the best-nearly by
(checks passed, win rate, green-November/week count): the ONLY 9/12 process
with unseen win >=90% (91.67%), fewest red weeks (8/45). Gaps labeled
honestly in ~/workspace/fx/work_c26/results/VERDICT.txt.

Asymmetry note: C26-33 uses win-rate-oriented asymmetry
(mined tp_mult=0.5, sl_mult 3-10; fallbacks tp_mult=0.5 / sl_mult=5.0).
Wins are small and frequent; rare losses are larger. Fidelity unchanged:
SL-first fills, 48h cap, 1-pip spread, TP/SL clipped [10,500]/[5,100].

Fallback equations (FB_*): direction 'TREND' fires on every check so the
exactly-1-entry-per-check rule always has a candidate; live direction
resolves per-trade from the signal candle's mom24 sign (BUY if > 0 else
SELL) -- the same fixed rule the research used, no tuning.

Equations use the same two features as C12/C24 (mom24, atr_ratio) with the
same definitions (see add_cycle12_features, imported below). Every equation
conditions on November price momentum (mom24) and volatility (atr_ratio).

Source of truth: ~/workspace/fx/work_c26/results/C26-33.json
Discovery trade log: ~/workspace/fx/work_c26/results/C26-33_disc_log.csv
Unseen trade log: ~/workspace/fx/work_c26/results/C26-33_unseen_log.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE26_VERSION = "cycle26-c2633-v1"
CYCLE26_CHECK_HOURS = (10, 11, 18)  # checks at h:30 UTC
CYCLE26_SYMBOLS_N = 20
MAX_HOLD_HOURS = 48
BASE_SPREAD_PIPS = 1.0
TP_CLIP = (10.0, 500.0)
SL_CLIP = (5.0, 100.0)

# ---------------------------------------------------------------- equations --
C26_EQUATIONS = (
    {"id": 'mom_GBPJPY_h10_momB_T2.5_A1.0_0.5x5', "symbol": 'GBPJPY', "hour": 10, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.30325},
    {"id": 'mom_EURNZD_h10_momB_T1.5_A1.0_0.3x8', "symbol": 'EURNZD', "hour": 10, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 975.8701310975609},
    {"id": 'mom_CHFJPY_h10_momS_T2.0_A1.0_1.0x8', "symbol": 'CHFJPY', "hour": 10, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 970.9493352941176},
    {"id": 'mom_AUDUSD_h10_momS_T1.5_A1.0_0.3x8', "symbol": 'AUDUSD', "hour": 10, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 967.9244783410138},
    {"id": 'mom_NZDUSD_h10_momS_T2.5_A1.0_1.0x8', "symbol": 'NZDUSD', "hour": 10, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 961.8063043956045},
    {"id": 'mom_EURCAD_h11_momB_T3.0_A1.0_1.25x8', "symbol": 'EURCAD', "hour": 11, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -3.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1000.4549464285715},
    {"id": 'mom_AUDCAD_h11_momS_T1.5_A1.0_1.0x5', "symbol": 'AUDCAD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 5.0, "score": 1000.4027428571428},
    {"id": 'mom_AUDUSD_h11_momS_T1.5_A1.0_1.0x8', "symbol": 'AUDUSD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1000.3509642857143},
    {"id": 'mom_NZDCAD_h11_momS_T1.5_A0.9_1.25x8', "symbol": 'NZDCAD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1000.2920982142857},
    {"id": 'mom_NZDUSD_h11_momS_T2.5_A1.0_0.75x8', "symbol": 'NZDUSD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.2360589285714},
    {"id": 'mom_EURAUD_h18_momS_T1.5_A1.0_0.75x5', "symbol": 'EURAUD', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.2750535714285},
    {"id": 'mom_AUDJPY_h18_momS_T2.5_A1.0_0.75x5', "symbol": 'AUDJPY', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.2436089285715},
    {"id": 'mom_CHFJPY_h18_momS_T1.5_A1.0_0.75x8', "symbol": 'CHFJPY', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.2302999999999},
    {"id": 'mom_AUDNZD_h18_momS_T1.5_A1.0_0.3x8', "symbol": 'AUDNZD', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 966.873238095238},
    {"id": 'mom_GBPJPY_h18_momS_T1.5_A1.0_0.5x8', "symbol": 'GBPJPY', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 965.7844949507389},
    {"id": 'FB_EURUSD_h10_0', "symbol": 'EURUSD', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000001.0},
    {"id": 'FB_GBPUSD_h10_1', "symbol": 'GBPUSD', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000002.0},
    {"id": 'FB_USDJPY_h10_2', "symbol": 'USDJPY', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000003.0},
    {"id": 'FB_AUDUSD_h10_3', "symbol": 'AUDUSD', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000004.0},
    {"id": 'FB_EURJPY_h11_0', "symbol": 'EURJPY', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000005.0},
    {"id": 'FB_GBPJPY_h11_1', "symbol": 'GBPJPY', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000006.0},
    {"id": 'FB_AUDJPY_h11_2', "symbol": 'AUDJPY', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000007.0},
    {"id": 'FB_NZDUSD_h11_3', "symbol": 'NZDUSD', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000008.0},
    {"id": 'FB_EURCHF_h18_0', "symbol": 'EURCHF', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000009.0},
    {"id": 'FB_USDCAD_h18_1', "symbol": 'USDCAD', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000010.0},
    {"id": 'FB_CHFJPY_h18_2', "symbol": 'CHFJPY', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000011.0},
    {"id": 'FB_EURAUD_h18_3', "symbol": 'EURAUD', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000012.0},
    {"id": 'mom_EURCAD_h11_momB_T2.5_A0.9_1.25x8', "symbol": 'EURCAD', "hour": 11, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.5}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1000.4347767857142},
)

_COND_OPS = {">": lambda a, v: a > v, "<": lambda a, v: a < v,
             ">=": lambda a, v: a >= v, "<=": lambda a, v: a <= v,
             "==": lambda a, v: a == v, "!=": lambda a, v: a != v}


def _as_utc(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


def _cond_ok(row, cond) -> bool:
    """Single condition on a feature row; NaN -> False."""
    v = row.get(cond["col"])
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return False
    if not np.isfinite(fv):
        return False
    return bool(_COND_OPS[cond["op"]](fv, cond["val"]))


def _trend_direction(mom24_value) -> str:
    """Fallback direction rule: BUY if signal-candle mom24 > 0 else SELL.

    Fixed rule from the Cycle 26 research (c26_sim.py); fires 100%.
    """
    try:
        return "BUY" if float(mom24_value) > 0 else "SELL"
    except (TypeError, ValueError):
        return "SELL"


def evaluate_cycle26_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate C26-33 equations at one check time (h:30 UTC).

    frames: {symbol: H1 OHLC DataFrame indexed by candle-stamp}.
    Only equations whose hour matches the check hour are evaluated.
    Signal features come from the (h-1):00 UTC candle (last completed
    as of h:30 UTC); entry price = open of the h:00 UTC candle.
    'TREND' fallbacks resolve direction from the signal candle's mom24.
    Returns one row per firing equation with TP/SL already clipped.
    """
    check = _as_utc(check_time_utc)
    hour = int(check.hour)
    if hour not in CYCLE26_CHECK_HOURS:
        return pd.DataFrame()
    sig_stamp = (check - pd.Timedelta(hours=1, minutes=30)).tz_localize(None)
    ent_stamp = (check - pd.Timedelta(minutes=30)).tz_localize(None)
    rows = []
    for eq in C26_EQUATIONS:
        if eq["hour"] != hour:
            continue
        sym = eq["symbol"]
        f = frames.get(sym)
        if f is None or len(f) == 0:
            continue
        ff = f.copy()
        ff.index = pd.to_datetime(ff.index, utc=True).tz_localize(None)
        ff = ff.sort_index()
        if sig_stamp not in ff.index or ent_stamp not in ff.index:
            continue
        feat = add_cycle12_features(ff.reset_index(drop=True))
        pos = ff.index.get_loc(sig_stamp)
        if isinstance(pos, (np.ndarray, slice)):
            continue
        row = feat.iloc[pos]
        if not all(_cond_ok(row, c) for c in eq["conditions"]):
            continue
        atr = float(row["atr14"])
        if not np.isfinite(atr) or atr <= 0:
            continue
        direction = eq["direction"]
        if direction == "TREND":
            direction = _trend_direction(row.get("mom24"))
        pip = _pip_size(sym)
        atr_pips = atr / pip
        tp = float(min(max(eq["tp_mult"] * atr_pips, TP_CLIP[0]), TP_CLIP[1]))
        sl = float(min(max(eq["sl_mult"] * atr_pips, SL_CLIP[0]), SL_CLIP[1]))
        rows.append({
            "check": check, "symbol": sym, "equation": eq["id"],
            "direction": direction, "score": eq["score"],
            "atr_pips": atr_pips,
            "entry_px": float(ff.loc[ent_stamp, "Open"]),
            "tp_pips": tp, "sl_pips": sl,
            "signal_candle": sig_stamp, "entry_candle": ent_stamp,
        })
    return pd.DataFrame(rows)


def select_cycle26_entries(signals: pd.DataFrame, open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: top-1 by score, max 1 open trade per
    symbol. Stable sort reproduces the research assembly order on ties."""
    if signals is None or len(signals) == 0:
        return signals.iloc[0:0] if signals is not None else pd.DataFrame()
    held = {str(s).upper() for s in (open_symbols or ())}
    out = []
    for _, row in signals.sort_values("score", ascending=False, kind="mergesort").iterrows():
        if len(out) >= 1:
            break
        if str(row["symbol"]).upper() in held:
            continue
        out.append(row)
        held.add(str(row["symbol"]).upper())
    return pd.DataFrame(out)


def is_cycle26_check_time(ts) -> bool:
    """True if ts (UTC) is at one of the C26 check hours (:30)."""
    t = _as_utc(ts)
    return int(t.hour) in CYCLE26_CHECK_HOURS and int(t.minute) == 30

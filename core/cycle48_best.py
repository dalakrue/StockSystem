"""Cycle 48 module: C48-02 (December-only research winner, improvement round).

30 equations (18 mined mom/atr + 12 TREND fallbacks) spanning 3 check
hours (10:30, 11:30, 13:30 UTC = 17:00, 18:00, 20:00 MMT), exactly 1
entry per check (top-1 by score at each check).

C48-02 REPLACES C27-01 as December's system. It won the Cycles 37-48
improvement program (user order 2026-10-20): 20 end-to-end processes
built from the uploaded research book's usable ideas plus the incumbent
mom/atr family, every process judged end-to-end at the 2.5-pip primary
cost; promotion only on strictly beating the incumbent under the
program's gates. Cycle 27 (C27-01) remains selectable.

At 2.5-pip cost (vs C27-01): weak ratings (star1+star2) 0 (vs 1),
unseen net +483.7 pips (vs +343.6) / win 95.45% (vs 92.42%) /
leftover 77.9% (vs 59.1%) / checks 11/12 (vs 10/12) / red months 0/9
(vs 1/9) / red weeks 8/45 (vs 10/45) / RoMAD 9.62 / Sharpe 18.34 /
max DD -50.3 / best N 105 (peak margin 46.4%, max DD 23.8%) /
P(profit) 99.9% (vs 99.2%) / entries/day 2.87 / stress net @4.5 +351.7.

Mined on December discovery only (2016-12 -> 2024-12): the mom/atr
family re-mined AT the 2.5-pip cost with week-smooth candidate
selection (score penalizes each candidate's discovery red-week count,
candidates capped at <=3 red weeks). Unseen December 2025 used ONLY
for the final evaluation (never for selection).

Asymmetry: win-rate-oriented (mined tp 0.5-1.25x / sl 3-8x; fallbacks
tp 0.3x / sl 8.0x). Wins small and frequent; rare losses larger.
Fidelity: SL-first fills, 48h cap, 1-pip spread, TP/SL clipped [10,500]/[5,100].

Fallback equations (FB_*): direction 'TREND' fires on every check so the
exactly-1-entry-per-check rule always has a candidate; live direction
resolves per-trade from the signal candle's mom24 sign (BUY if > 0 else
SELL) -- the same fixed rule the research used, no tuning.

Every equation conditions on December price momentum (mom24) and
volatility (atr_ratio), same definitions as C12/C24/C26/C27.

Source of truth: ~/workspace/fx/work_c48/results/WINNER.json
Discovery trade log: ~/workspace/fx/work_c48/results/WINNER_disc_log.csv
Unseen trade log: ~/workspace/fx/work_c48/results/WINNER_unseen_log.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE48_VERSION = "cycle48-c4802-v1"
CYCLE48_CHECK_HOURS = (10, 11, 13)  # checks at h:30 UTC
CYCLE48_SYMBOLS_N = 20
MAX_HOLD_HOURS = 48
BASE_SPREAD_PIPS = 1.0
TP_CLIP = (10.0, 500.0)
SL_CLIP = (5.0, 100.0)

# ---------------------------------------------------------------- equations --
C48_EQUATIONS = (

    {"id": 'mom_EURNZD_h10_momS_T2.5_A1.0_1.25x5.0', "symbol": 'EURNZD', "hour": 10, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 1000.5188125},
    {"id": 'mom_CHFJPY_h10_momB_T2.0_A1.0_1.25x8.0', "symbol": 'CHFJPY', "hour": 10, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1000.3685642857143},
    {"id": 'mom_USDCHF_h10_momS_T3.0_A1.0_1.25x8.0', "symbol": 'USDCHF', "hour": 10, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 3.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1000.2463892857143},
    {"id": 'mom_AUDNZD_h10_momS_T2.0_A1.0_1.25x5.0', "symbol": 'AUDNZD', "hour": 10, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 950.1842125},
    {"id": 'mom_GBPUSD_h10_momB_T2.5_A1.0_1.0x8.0', "symbol": 'GBPUSD', "hour": 10, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 929.0874214285715},
    {"id": 'mom_EURNZD_h11_momS_T2.5_A1.0_1.0x8.0', "symbol": 'EURNZD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1000.4293142857143},
    {"id": 'mom_AUDNZD_h11_momS_T0.75_A1.0_1.25x5.0', "symbol": 'AUDNZD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 1000.3575625},
    {"id": 'mom_GBPUSD_h11_momB_T3.0_A1.0_0.75x8.0', "symbol": 'GBPUSD', "hour": 11, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -3.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.2470375},
    {"id": 'mom_AUDCHF_h11_momB_T2.5_A1.0_0.75x5.0', "symbol": 'AUDCHF', "hour": 11, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.1734089285715},
    {"id": 'mom_EURGBP_h11_momS_T0.75_A0.9_1.25x8.0', "symbol": 'EURGBP', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 937.6429094155844},
    {"id": 'mom_EURNZD_h13_momS_T2.0_A1.0_0.5x3.0', "symbol": 'EURNZD', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 3.0, "score": 1000.2098964285714},
    {"id": 'mom_USDCHF_h13_momS_T2.5_A0.9_1.0x8.0', "symbol": 'USDCHF', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.5}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1000.2026642857143},
    {"id": 'mom_AUDNZD_h13_momS_T0.75_A1.0_1.25x8.0', "symbol": 'AUDNZD', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 938.6246034937888},
    {"id": 'mom_GBPUSD_h13_momB_T2.5_A1.0_1.25x5.0', "symbol": 'GBPUSD', "hour": 13, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 920.3859821428572},
    {"id": 'mom_GBPJPY_h13_momB_T2.0_A1.0_1.25x5.0', "symbol": 'GBPJPY', "hour": 13, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 912.943050595238},
    {"id": 'FB_EURUSD_h10_0', "symbol": 'EURUSD', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000001.0},
    {"id": 'FB_GBPUSD_h10_1', "symbol": 'GBPUSD', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000002.0},
    {"id": 'FB_USDJPY_h10_2', "symbol": 'USDJPY', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000003.0},
    {"id": 'FB_AUDUSD_h10_3', "symbol": 'AUDUSD', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000004.0},
    {"id": 'FB_EURJPY_h11_0', "symbol": 'EURJPY', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000005.0},
    {"id": 'FB_GBPJPY_h11_1', "symbol": 'GBPJPY', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000006.0},
    {"id": 'FB_AUDJPY_h11_2', "symbol": 'AUDJPY', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000007.0},
    {"id": 'FB_NZDUSD_h11_3', "symbol": 'NZDUSD', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000008.0},
    {"id": 'FB_EURCHF_h13_0', "symbol": 'EURCHF', "hour": 13, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000009.0},
    {"id": 'FB_USDCAD_h13_1', "symbol": 'USDCAD', "hour": 13, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000010.0},
    {"id": 'FB_CHFJPY_h13_2', "symbol": 'CHFJPY', "hour": 13, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000011.0},
    {"id": 'FB_EURAUD_h13_3', "symbol": 'EURAUD', "hour": 13, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000012.0},
    {"id": 'mom_EURNZD_h10_momS_T2.5_A1.0_1.25x8.0', "symbol": 'EURNZD', "hour": 10, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1000.5188125},
    {"id": 'mom_EURNZD_h10_momS_T2.0_A1.0_1.0x5.0', "symbol": 'EURNZD', "hour": 10, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 5.0, "score": 1000.4921642857142},
    {"id": 'mom_EURNZD_h10_momS_T2.0_A1.0_1.0x8.0', "symbol": 'EURNZD', "hour": 10, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1000.4921642857142},
)

_COND_OPS = {">": lambda a, v: a > v, "<": lambda a, v: a < v,
             ">=": lambda a, v: a >= v, "<=": lambda a, v: a <= v}


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

    Fixed rule from the Cycle 48 research; fires 100%.
    """
    try:
        return "BUY" if float(mom24_value) > 0 else "SELL"
    except (TypeError, ValueError):
        return "SELL"


def evaluate_cycle48_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate C48-02 equations at one check time (h:30 UTC).

    frames: {symbol: H1 OHLC DataFrame indexed by candle-stamp}.
    Only equations whose hour matches the check hour are evaluated.
    Signal features come from the (h-1):00 UTC candle (last completed
    as of h:30 UTC); entry price = open of the h:00 UTC candle.
    'TREND' fallbacks resolve direction from the signal candle's mom24.
    Returns one row per firing equation with TP/SL already clipped.
    """
    check = _as_utc(check_time_utc)
    hour = int(check.hour)
    if hour not in CYCLE48_CHECK_HOURS:
        return pd.DataFrame()
    sig_stamp = (check - pd.Timedelta(hours=1, minutes=30)).tz_localize(None)
    ent_stamp = (check - pd.Timedelta(minutes=30)).tz_localize(None)
    rows = []
    for eq in C48_EQUATIONS:
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


def select_cycle48_entries(signals: pd.DataFrame, open_symbols=()) -> pd.DataFrame:
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


def is_cycle48_check_time(ts) -> bool:
    """True if ts (UTC) is at one of the C48 check hours (:30)."""
    t = _as_utc(ts)
    return int(t.hour) in CYCLE48_CHECK_HOURS and int(t.minute) == 30

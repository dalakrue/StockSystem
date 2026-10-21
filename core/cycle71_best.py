"""Cycle 71 module: C71-04 (December-only system, LCT-fix round).

34 equations spanning 3 check hours (10:30, 11:30, 13:30 UTC =
17:00, 18:00, 20:00 MMT), exactly 1 entry per check -- the incumbent
C48-02 system VERBATIM (18 mined mom/atr legs + 12 TREND fallbacks,
exits frozen) plus 4 fresh legs:
  * COMBO_gmma_chv_GBPJPY_h13_SELL (two exit variants, 0.75x5.0 and
    0.75x8.0, same score -- stable order keeps the 5.0 variant
    first): Guppy GMMA separation gsep < -0.3 AND Chaikin
    Volatility chv10 > 0 AND ulcer_ratio < 1.2;
  * COMBO_srsi_shdw_EURCAD_h13_BUY: Stochastic-RSI K srsi_k < 25
    AND shadow pressure sh_press > 0.05;
  * CHV_chv_calm_tr_USDCHF_h11_SELL: chv10 < 0 AND gsep < -0.3.

C71-04 REPLACES C48-02 as December's system. It was PROMOTED
cleanly in the LCT-fix round (Cycle 71): LCT MIDDLE PASS against
C48-02 (paired P 99.98%, own 5th-percentile 31.25%; the incumbent
had failed its own LCT at P 63.22% / 19.69%), unseen Dec 2025 @2.5:
net +489.1 (vs +483.7), win 95.45%, leftover 80.8% (vs 77.9%),
weak 0 (tie -- strictly-less is impossible against a 0 incumbent,
allowed under the December rule), checks 11/12, sizing PASS
(N=105, margin 47.2%, DD 15.6%), P(profit) 100%. Discovery net
+2,902.5 vs +2,307.4, discovery leftover 47.14% vs 39.01%, all 9
year-blocks positive. Honest caveat (verdict): the unseen net
improvement is small (+5.4); the promotion rests mainly on the
discovery record and the paired LCT. Cycle 48 (C48-02) remains
selectable.

Frame notes: SL-first fills, 48h cap, max 1 open/symbol, Mon-Fri,
Dec 25 excluded (automatic in practice: the frames carry no
10:00/11:00/13:00 bars on Dec 25). Winner logs are stored at the
2.5-pip cost (net = gross - 2.5).

Fresh feature definitions (verbatim from the Cycle 71 research,
work_c71/scripts/c71_prep.py fresh_features; all causal; atr14 and
the Wilder rsi14 are the incumbent base features):
  gsep        (mean of EMA(3,5,8,10,12,15) of Close - mean of
              EMA(30,35,40,45,50,60) of Close) / ATR14; EMA =
              ewm(span, min_periods=span, adjust=False).
  chv10       Chaikin Volatility: 100 * (E - E[-10]) / E[-10] where
              E = EMA10(High-Low).
  srsi_k      SMA3 of the 14-bar stochastic of rsi14 (0..100):
              100 * (rsi14 - min14) / (max14 - min14), SMA over 3.
  ulcer_ratio Ulcer Index(14) / its trailing 720-bar rolling
              median (min 240 bars); Ulcer = RMS of the % drawdown
              from the 14-bar highest Close.
  sh_press    6-bar mean of (lower-shadow share - upper-shadow
              share) of the bar range (share = shadow length /
              (High-Low)).

Fallback equations (FB_*): direction 'TREND' fires on every check so
the exactly-1-entry-per-check rule always has a candidate; live
direction resolves per-trade from the signal candle's mom24 sign
(BUY if > 0 else SELL) -- the same fixed rule the research used.

Source of truth: ~/workspace/fx/work_c71/results/WINNER.json
Full spec: ~/workspace/fx/work_c71/results/WINNER_SPEC.json
Discovery trade log: ~/workspace/fx/work_c71/results/WINNER_disc_log.csv
Unseen trade log: ~/workspace/fx/work_c71/results/WINNER_unseen_log.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE71_VERSION = "cycle71-c7104-v1"
CYCLE71_CHECK_HOURS = (10, 11, 13)  # checks at h:30 UTC
CYCLE71_SYMBOLS_N = 15
MAX_HOLD_HOURS = 48
BASE_SPREAD_PIPS = 2.5
TP_CLIP = (10.0, 500.0)
SL_CLIP = (5.0, 100.0)

# ---------------------------------------------------------------- equations --
C71_EQUATIONS = (
    {"id": 'mom_EURNZD_h10_momS_T2.5_A1.0_1.25x5.0', "symbol": 'EURNZD', "hour": 10, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 1000.5188125},
    {"id": 'mom_CHFJPY_h10_momB_T2.0_A1.0_1.25x8.0', "symbol": 'CHFJPY', "hour": 10, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -2.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1000.3685642857143},
    {"id": 'mom_USDCHF_h10_momS_T3.0_A1.0_1.25x8.0', "symbol": 'USDCHF', "hour": 10, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 3.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1000.2463892857143},
    {"id": 'mom_AUDNZD_h10_momS_T2.0_A1.0_1.25x5.0', "symbol": 'AUDNZD', "hour": 10, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 950.1842125},
    {"id": 'mom_GBPUSD_h10_momB_T2.5_A1.0_1.0x8.0', "symbol": 'GBPUSD', "hour": 10, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 929.0874214285715},
    {"id": 'mom_EURNZD_h11_momS_T2.5_A1.0_1.0x8.0', "symbol": 'EURNZD', "hour": 11, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1000.4293142857143},
    {"id": 'mom_AUDNZD_h11_momS_T0.75_A1.0_1.25x5.0', "symbol": 'AUDNZD', "hour": 11, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 1000.3575625},
    {"id": 'mom_GBPUSD_h11_momB_T3.0_A1.0_0.75x8.0', "symbol": 'GBPUSD', "hour": 11, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -3.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.2470375},
    {"id": 'mom_AUDCHF_h11_momB_T2.5_A1.0_0.75x5.0', "symbol": 'AUDCHF', "hour": 11, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.1734089285715},
    {"id": 'mom_EURGBP_h11_momS_T0.75_A0.9_1.25x8.0', "symbol": 'EURGBP', "hour": 11, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 937.6429094155844},
    {"id": 'mom_EURNZD_h13_momS_T2.0_A1.0_0.5x3.0', "symbol": 'EURNZD', "hour": 13, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 3.0, "score": 1000.2098964285714},
    {"id": 'mom_USDCHF_h13_momS_T2.5_A0.9_1.0x8.0', "symbol": 'USDCHF', "hour": 13, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.5},
     {"col": 'atr_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1000.2026642857143},
    {"id": 'mom_AUDNZD_h13_momS_T0.75_A1.0_1.25x8.0', "symbol": 'AUDNZD', "hour": 13, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 938.6246034937888},
    {"id": 'mom_GBPUSD_h13_momB_T2.5_A1.0_1.25x5.0', "symbol": 'GBPUSD', "hour": 13, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 920.3859821428572},
    {"id": 'mom_GBPJPY_h13_momB_T2.0_A1.0_1.25x5.0', "symbol": 'GBPJPY', "hour": 13, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -2.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
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
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1000.5188125},
    {"id": 'mom_EURNZD_h10_momS_T2.0_A1.0_1.0x5.0', "symbol": 'EURNZD', "hour": 10, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 5.0, "score": 1000.4921642857142},
    {"id": 'mom_EURNZD_h10_momS_T2.0_A1.0_1.0x8.0', "symbol": 'EURNZD', "hour": 10, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1000.4921642857142},
    {"id": 'COMBO_gmma_chv_GBPJPY_h13_SELL_0.75x5.0', "symbol": 'GBPJPY', "hour": 13, "direction": 'SELL',
     "conditions": [
     {"col": 'gsep', "op": '<', "val": -0.3},
     {"col": 'chv10', "op": '>', "val": 0.0},
     {"col": 'ulcer_ratio', "op": '<', "val": 1.2}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.4026428571428},
    {"id": 'COMBO_gmma_chv_GBPJPY_h13_SELL_0.75x8.0', "symbol": 'GBPJPY', "hour": 13, "direction": 'SELL',
     "conditions": [
     {"col": 'gsep', "op": '<', "val": -0.3},
     {"col": 'chv10', "op": '>', "val": 0.0},
     {"col": 'ulcer_ratio', "op": '<', "val": 1.2}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.4026428571428},
    {"id": 'COMBO_srsi_shdw_EURCAD_h13_BUY_1.0x8.0', "symbol": 'EURCAD', "hour": 13, "direction": 'BUY',
     "conditions": [
     {"col": 'srsi_k', "op": '<', "val": 25.0},
     {"col": 'sh_press', "op": '>', "val": 0.05}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1000.33805},
    {"id": 'CHV_chv_calm_tr_USDCHF_h11_SELL_1.0x8.0', "symbol": 'USDCHF', "hour": 11, "direction": 'SELL',
     "conditions": [
     {"col": 'chv10', "op": '<', "val": 0.0},
     {"col": 'gsep', "op": '<', "val": -0.3}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1000.3166714285715},
)

_COND_OPS = {">": lambda a, v: a > v, "<": lambda a, v: a < v,
             ">=": lambda a, v: a >= v, "<=": lambda a, v: a <= v}

_FEAT_CACHE = {}


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
    """Fallback direction rule: BUY if signal-candle mom24 > 0 else SELL."""
    try:
        return "BUY" if float(mom24_value) > 0 else "SELL"
    except (TypeError, ValueError):
        return "SELL"


def _norm_frame(f):
    ff = f.copy()
    ff.index = pd.to_datetime(ff.index, utc=True).tz_localize(None)
    return ff.sort_index()


def _ema(x: pd.Series, span: int) -> pd.Series:
    return x.ewm(span=span, min_periods=span, adjust=False).mean()


def _sma(x: pd.Series, n: int) -> pd.Series:
    return x.rolling(n, min_periods=n).mean()


def _symbol_feat(sym, ff):
    """Base cycle12 features + Wilder rsi14 + the Cycle 71 fresh
    columns (gsep, chv10, srsi_k, ulcer_ratio, sh_press) for a
    normalised frame (cached). Formulas verbatim from
    work_c71/scripts/c71_prep.py."""
    key = (sym, len(ff), ff.index[0], ff.index[-1])
    hit = _FEAT_CACHE.get(key)
    if hit is not None:
        return hit
    if len(_FEAT_CACHE) > 32:
        _FEAT_CACHE.clear()
    feat = add_cycle12_features(ff.reset_index(drop=True))
    feat.index = ff.index
    O, H, L, C = ff["Open"], ff["High"], ff["Low"], ff["Close"]
    atrs = feat["atr14"].replace(0.0, np.nan)
    # --- Wilder RSI14 (incumbent base feature) ---
    delta = C.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    ag = gain.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean()
    al = loss.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean()
    rs = ag / al.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    feat["rsi14"] = rsi
    rng = (H - L).replace(0.0, np.nan)
    # --- Stochastic RSI K ---
    lo14 = rsi.rolling(14, min_periods=14).min()
    hi14 = rsi.rolling(14, min_periods=14).max()
    stoch_rsi = (rsi - lo14) / (hi14 - lo14).replace(0.0, np.nan) * 100.0
    feat["srsi_k"] = _sma(stoch_rsi, 3)
    # --- Chaikin Volatility ---
    erng = _ema(H - L, 10)
    feat["chv10"] = (erng - erng.shift(10)) / erng.shift(10) * 100.0
    # --- Guppy GMMA separation ---
    shorts = sum(_ema(C, n) for n in (3, 5, 8, 10, 12, 15)) / 6.0
    longs = sum(_ema(C, n) for n in (30, 35, 40, 45, 50, 60)) / 6.0
    feat["gsep"] = (shorts - longs) / atrs
    # --- Ulcer Index ratio ---
    hi_c = C.rolling(14, min_periods=14).max()
    dd_pct = (C - hi_c) / hi_c.replace(0.0, np.nan) * 100.0
    ulcer = np.sqrt((dd_pct ** 2).rolling(14, min_periods=14).mean())
    feat["ulcer_ratio"] = ulcer / ulcer.rolling(720, min_periods=240).median()
    # --- Shadow pressure ---
    up_sh = (H - pd.concat([O, C], axis=1).max(axis=1)) / rng
    lo_sh = (pd.concat([O, C], axis=1).min(axis=1) - L) / rng
    feat["sh_press"] = _sma(lo_sh, 6) - _sma(up_sh, 6)
    _FEAT_CACHE[key] = feat
    return feat


def evaluate_cycle71_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate C71-04 equations at one check time (h:30 UTC).

    frames: {symbol: H1 OHLC DataFrame indexed by candle-stamp}.
    Only equations whose hour matches the check hour are evaluated.
    Signal features come from the (h-1):00 UTC candle (last completed
    as of h:30 UTC); entry price = open of the h:00 UTC candle.
    TP/SL distances scale off ATR14, clipped to the standard
    [10,500] / [5,100] pip clips. 'TREND' fallbacks resolve
    direction from the signal candle's mom24.
    """
    check = _as_utc(check_time_utc)
    hour = int(check.hour)
    if hour not in CYCLE71_CHECK_HOURS:
        return pd.DataFrame()
    sig_stamp = (check - pd.Timedelta(hours=1, minutes=30)).tz_localize(None)
    ent_stamp = (check - pd.Timedelta(minutes=30)).tz_localize(None)
    frames_norm = {}
    for s, f in (frames or {}).items():
        if f is None or len(f) == 0:
            continue
        frames_norm[str(s).upper()] = _norm_frame(f)
    rows = []
    for eq in C71_EQUATIONS:
        if eq["hour"] != hour:
            continue
        sym = eq["symbol"]
        ff = frames_norm.get(sym)
        if ff is None:
            continue
        if sig_stamp not in ff.index or ent_stamp not in ff.index:
            continue
        feat = _symbol_feat(sym, ff)
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


def select_cycle71_entries(signals: pd.DataFrame, open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: top-1 by score, max 1 open trade per
    symbol. Stable sort reproduces the research assembly order on ties
    (notably the two COMBO_gmma_chv exit variants share a score; the
    0.75x5.0 variant is listed first and wins)."""
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


def is_cycle71_check_time(ts) -> bool:
    """True if ts (UTC) is at one of the C71 check hours (:30)."""
    t = _as_utc(ts)
    return int(t.hour) in CYCLE71_CHECK_HOURS and int(t.minute) == 30

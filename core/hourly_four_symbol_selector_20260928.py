"""Hourly four-symbol opportunity selector for Middle Regime ranking/Finder.

Goals:
- Keep the existing S1-S110 strategy conditions intact and admit genuine
  S111-S120 rescue hits.
- Guarantee up to four selected symbols per completed snapshot when at least
  four symbols are available.
- Prioritize genuine S1-S120 hits, then fill remaining slots by the strongest
  non-hit candidates using a causal soft score.
- Publish price-based 24-hour TP/SL estimates, never pip-only values.

The fill layer is intentionally labelled RANK-FILL so it is not confused with
an actual S1-S120 trigger.  This makes the four-slot execution policy visible
without falsifying the underlying strategy audit.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import math
import re

import numpy as np
import pandas as pd

SELECTOR_VERSION = "hourly-four-selector-v4-20261002-pair-quality"
SELECTOR_MAX_SYMBOLS = 4
MAX_HOLD_HOURS = 24
ENTRY_FILTER_RELAXATION = 0.40
ENTRY_FILTER_MULTIPLIER = 1.0 - ENTRY_FILTER_RELAXATION
LOW_FREQUENCY_COVERAGE_SYMBOLS = frozenset({
    "EURUSD", "AUDUSD", "AUDNZD", "AUDJPY", "NZDUSD",
    "GBPUSD", "GBPJPY", "USDCHF", "USDJPY", "EURGBP",
})


def _num(series: Any, index=None, default=np.nan) -> pd.Series:
    if isinstance(series, pd.Series):
        out = pd.to_numeric(series, errors="coerce")
    else:
        out = pd.Series(series, index=index, dtype=float)
        out = pd.to_numeric(out, errors="coerce")
    if index is not None:
        out = out.reindex(index)
    return out.fillna(default) if default is not None else out


def _timeframe_bars(timeframe: str | None) -> int:
    tf = str(timeframe or "H1").upper().strip()
    if tf.startswith("M"):
        try:
            minutes = int(tf[1:])
            return max(1, math.ceil(1440 / minutes))
        except Exception:
            return 24
    if tf.startswith("H"):
        try:
            hours = int(tf[1:])
            return max(1, math.ceil(24 / hours))
        except Exception:
            return 24
    if tf in {"D1", "DAY", "1D"}:
        return 1
    return 24


def _price_decimals(symbol: Any, price: float) -> int:
    name = str(symbol or "").upper()
    if any(token in name for token in ("XAU", "GOLD", "XAG", "SILVER")):
        return 2
    if not np.isfinite(price):
        return 5
    ap = abs(float(price))
    if ap >= 1000:
        return 2
    if ap >= 100:
        return 2
    if ap >= 10:
        return 3
    if ap >= 1:
        return 5
    return 6


def price_string(value: Any, symbol: Any = "", reference_price: Any = np.nan) -> str:
    try:
        v = float(value)
    except Exception:
        return "—"
    if not np.isfinite(v):
        return "—"
    try:
        ref = float(reference_price)
    except Exception:
        ref = v
    decimals = _price_decimals(symbol, ref)
    return f"{v:.{decimals}f}"


def _atr_series(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev).abs(), (low - prev).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean().replace(0, np.nan)


def _pip_size(symbol: Any) -> float:
    name = str(symbol or "").upper().replace("/", "")
    if any(token in name for token in ("XAU", "GOLD")):
        return 0.10
    if "JPY" in name:
        return 0.01
    return 0.0001


def _directional_mfe_proxy(high: pd.Series, low: pd.Series, close: pd.Series, sign: pd.Series, bars: int) -> pd.Series:
    """Causal historical 24h maximum-favourable-excursion proxy.

    The forward excursion for a historical origin is only allowed into the
    target calculation after that complete forward window has finished.  This
    gives the live row a completed-history distribution without reading any
    future candle for the row being scored.
    """
    if bars <= 1:
        buy = (high - close).clip(lower=0)
        sell = (close - low).clip(lower=0)
    else:
        buy = high.rolling(bars, min_periods=bars).max().shift(-(bars - 1)) - close
        sell = close - low.rolling(bars, min_periods=bars).min().shift(-(bars - 1))
    buy = buy.clip(lower=0)
    sell = sell.clip(lower=0)
    origin_sign = sign.astype(float)
    origin_mfe = pd.Series(np.where(origin_sign.gt(0), buy, np.where(origin_sign.lt(0), sell, np.nan)), index=close.index)
    return origin_mfe.shift(bars)


def _legacy_dynamic_24h_targets(
    df: pd.DataFrame,
    bias: pd.Series | str,
    *,
    timeframe: str = "H1",
    symbol: pd.Series | str | None = None,
) -> pd.DataFrame:
    """Attach a causal, 24-hour maximum-plausible price TP/SL model.

    The target is built from completed historical 24h excursions, realized
    range quantiles, volatility, directional efficiency, trend strength and
    available breakout room.  It is deliberately a *24h target*, not an open-
    ended trend target.  No target is allowed to imply a holding period longer
    than MAX_HOLD_HOURS.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(index=getattr(df, "index", None))

    out = df.copy()
    idx = out.index
    high = _num(out.get("high", pd.Series(np.nan, index=idx)), idx)
    low = _num(out.get("low", pd.Series(np.nan, index=idx)), idx)
    close = _num(out.get("close", pd.Series(np.nan, index=idx)), idx)
    op = _num(out.get("open", pd.Series(np.nan, index=idx)), idx)
    valid = high.notna() & low.notna() & close.notna() & close.gt(0)

    if isinstance(bias, pd.Series):
        bias_s = bias.reindex(idx).astype(str).str.upper().str.strip()
    else:
        bias_s = pd.Series(str(bias or "NEUTRAL").upper(), index=idx)
    sign = pd.Series(np.where(bias_s.eq("BUY"), 1.0, np.where(bias_s.eq("SELL"), -1.0, 0.0)), index=idx)

    if isinstance(symbol, pd.Series):
        symbol_s = symbol.reindex(idx).astype(str)
    else:
        symbol_s = pd.Series(str(symbol or ""), index=idx)

    bars24 = _timeframe_bars(timeframe)
    atr_raw = _atr_series(high, low, close)
    tr = pd.concat(
        [(high-low).abs(), (high-close.shift(1)).abs(), (low-close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    atr_fallback = tr.rolling(48, min_periods=8).median().fillna(tr.expanding(min_periods=1).mean())
    atr = atr_raw.fillna(atr_fallback).replace(0, np.nan)

    returns = np.log(close.where(close.gt(0))).diff()
    range24 = high.rolling(bars24, min_periods=max(2, min(bars24, 8))).max() - low.rolling(bars24, min_periods=max(2, min(bars24, 8))).min()
    prior_range24 = range24.shift(1)
    range_p75 = prior_range24.rolling(120, min_periods=16).quantile(0.75)
    range_p85 = prior_range24.rolling(120, min_periods=16).quantile(0.85)
    range_p90 = prior_range24.rolling(120, min_periods=16).quantile(0.90)

    sigma24 = returns.shift(1).rolling(max(6, bars24), min_periods=max(4, min(bars24, 8))).std() * math.sqrt(max(1, bars24))
    sigma_move = (close * sigma24).replace([np.inf, -np.inf], np.nan)

    look = max(6, min(24, bars24))
    net_move = (close - close.shift(look)).abs()
    path_move = close.diff().abs().rolling(look, min_periods=max(4, look // 2)).sum()
    efficiency = net_move.div(path_move.replace(0, np.nan)).clip(0, 1).fillna(0)

    adx = _num(out.get("ADX", pd.Series(np.nan, index=idx)), idx)
    adx_strength = ((adx - 16.0) / 24.0).clip(0, 1).fillna(0)
    trend_score = (0.55 * adx_strength + 0.45 * efficiency).clip(0, 1)
    trend_factor = 0.94 + 0.22 * trend_score

    historical_mfe = _directional_mfe_proxy(high, low, close, sign, bars24)
    mfe_p75 = historical_mfe.rolling(120, min_periods=16).quantile(0.75)
    mfe_p85 = historical_mfe.rolling(120, min_periods=16).quantile(0.85)
    mfe_p90 = historical_mfe.rolling(120, min_periods=16).quantile(0.90)

    prior_swing_hi = high.rolling(max(48, bars24 * 2), min_periods=max(12, bars24)).max().shift(1)
    prior_swing_lo = low.rolling(max(48, bars24 * 2), min_periods=max(12, bars24)).min().shift(1)
    breakout_room = pd.Series(
        np.where(sign.gt(0), (prior_swing_hi-close).clip(lower=0),
                 np.where(sign.lt(0), (close-prior_swing_lo).clip(lower=0), 0.0)),
        index=idx,
    )

    momentum = (sign * (close - close.shift(6))).clip(lower=0)
    momentum_scale = (momentum / atr.replace(0, np.nan)).clip(0, 3).fillna(0)
    directional_boost = (1.0 + 0.08 * trend_score + 0.05 * (momentum_scale / 3.0)).clip(0.92, 1.14)

    # Maximum-plausible 24h candidate: use the high side of several independent
    # causal distributions, then cap with the 90th percentile envelope. This is
    # intentionally more ambitious than the old ATR-only target but remains
    # bounded to the next 24 hours.
    candidates = pd.concat([
        mfe_p85 * 1.02,
        range_p85 * 0.90,
        sigma_move * 2.00,
        atr * 3.30,
        breakout_room * 1.05,
        mfe_p75 * (1.05 + 0.10 * trend_score),
    ], axis=1)
    candidate = candidates.max(axis=1, skipna=True) * directional_boost * trend_factor

    caps = pd.concat([
        mfe_p90 * 1.08,
        range_p90 * 1.12,
        sigma_move * 2.85,
        atr * 7.50,
    ], axis=1)
    cap = caps.min(axis=1, skipna=True)
    fallback_cap = pd.concat([range24 * 1.10, sigma_move * 2.60, atr * 6.50], axis=1).max(axis=1, skipna=True)
    cap = cap.fillna(fallback_cap)
    tp_distance = candidate.where(candidate.gt(0), fallback_cap)
    tp_distance = tp_distance.fillna(atr * 3.0)
    tp_distance = tp_distance.clip(lower=atr * 2.05)
    tp_distance = tp_distance.where(cap.isna() | cap.le(0), np.minimum(tp_distance, cap))
    tp_distance = tp_distance.where(tp_distance.gt(0), (tr * 3).clip(lower=0))

    # Structure + volatility stop: tight enough to protect ROMAD, but outside
    # normal pullback noise for the current Middle-bias direction.
    swing_n = max(8, min(16, bars24 * 2))
    recent_low = low.rolling(swing_n, min_periods=max(3, min(swing_n, 6))).min()
    recent_high = high.rolling(swing_n, min_periods=max(3, min(swing_n, 6))).max()
    structure_buy = (close - recent_low + 0.15 * atr).clip(lower=atr * 0.85, upper=atr * 2.15)
    structure_sell = (recent_high - close + 0.15 * atr).clip(lower=atr * 0.85, upper=atr * 2.15)
    sl_distance = pd.Series(
        np.where(sign.gt(0), structure_buy, np.where(sign.lt(0), structure_sell, atr * 1.10)),
        index=idx,
    )
    sl_distance = sl_distance.combine_first(atr * 1.10).clip(lower=atr * 0.85, upper=atr * 2.15)

    # Keep the projected target compatible with the 24h horizon by estimating
    # the time needed at a conservative fraction of current ATR/efficiency.
    expected_hourly_move = atr * (0.68 + 0.30 * trend_score + 0.16 * efficiency)
    expected_hourly_move = expected_hourly_move.replace(0, np.nan)
    horizon_distance_cap = expected_hourly_move * float(MAX_HOLD_HOURS)
    tp_distance = tp_distance.where(
        horizon_distance_cap.isna() | horizon_distance_cap.le(0),
        np.minimum(tp_distance, horizon_distance_cap),
    )
    target_horizon = tp_distance.div(expected_hourly_move).replace([np.inf, -np.inf], np.nan).clip(lower=2, upper=MAX_HOLD_HOURS)
    target_horizon = target_horizon.fillna(MAX_HOLD_HOURS)

    # Confidence is a model coverage score, not a win probability.
    coverage = pd.concat([
        historical_mfe.notna().astype(float),
        range_p85.notna().astype(float),
        sigma_move.notna().astype(float),
        atr.notna().astype(float),
    ], axis=1).mean(axis=1)
    tp_confidence = (100 * (0.55 * coverage + 0.30 * trend_score + 0.15 * efficiency)).clip(0, 100)

    tp_price = close + sign * tp_distance
    sl_price = close - sign * sl_distance
    neutral_tp = close + tp_distance
    neutral_sl = close - sl_distance
    tp_price = pd.Series(np.where(sign.eq(0), neutral_tp, tp_price), index=idx)
    sl_price = pd.Series(np.where(sign.eq(0), neutral_sl, sl_price), index=idx)

    pip_sizes = pd.Series([_pip_size(v) for v in symbol_s], index=idx, dtype=float)
    tp_pips = tp_distance.div(pip_sizes.replace(0, np.nan))
    sl_pips = sl_distance.div(pip_sizes.replace(0, np.nan))
    target_noise = _num(out.get("Entry Noise Ratio", pd.Series(1.0, index=idx)), idx, default=1.0).clip(0, 5)
    estimated_round_trip_cost_pips = pd.Series(2.0, index=idx)
    net_pip_potential = (tp_pips - estimated_round_trip_cost_pips).clip(lower=0)
    romad_proxy = net_pip_potential.div(
        sl_pips.mul(1.0 + 0.60 * target_noise + 0.40 * (1.0 - trend_score)),
    ).replace([np.inf, -np.inf], np.nan).clip(0, 10)

    out["24H Historical Range"] = range24
    out["24H Range P75"] = range_p75
    out["24H Range P85"] = range_p85
    out["24H Range P90"] = range_p90
    out["24H Historical MFE P75"] = mfe_p75
    out["24H Historical MFE P85"] = mfe_p85
    out["24H Historical MFE P90"] = mfe_p90
    out["24H Volatility Move"] = sigma_move
    out["24H Directional Efficiency"] = efficiency
    out["24H Breakout Room"] = breakout_room
    out["24H TP Distance"] = tp_distance
    out["24H TP Upper Envelope"] = cap
    out["24H SL Distance"] = sl_distance
    out["Suggested TP"] = tp_price
    out["Suggested SL"] = sl_price
    out["Suggested TP Price"] = tp_price
    out["Suggested SL Price"] = sl_price
    out["TP Target Horizon Hours"] = target_horizon
    out["24H TP Confidence"] = tp_confidence.round(1)
    out["Suggested TP Pips"] = tp_pips
    out["Suggested SL Pips"] = sl_pips
    out["24H Estimated Net Pip Potential"] = net_pip_potential.round(2)
    out["24H ROMAD Proxy"] = romad_proxy.round(3)
    out["Max Hold Hours"] = MAX_HOLD_HOURS
    out["Time Exit Enabled"] = True
    out["Time Exit Hours"] = MAX_HOLD_HOURS
    out["Exit Scenario"] = "Dynamic TP + Middle Bias Exit"
    out["TP Estimate Basis"] = np.where(
        mfe_p85.notna(), "24H historical MFE P85 + range/volatility/trend",
        np.where(range_p85.notna(), "24H P85 range + volatility + trend", "ATR + structure fallback"),
    )
    out["TP Price Display"] = [price_string(v, s, p) for v, s, p in zip(tp_price, symbol_s, close)]
    out["SL Price Display"] = [price_string(v, s, p) for v, s, p in zip(sl_price, symbol_s, close)]
    out["TP:SL Price Ratio"] = tp_distance.div(sl_distance.replace(0, np.nan))
    out["TP Within 24H"] = valid & tp_distance.gt(0) & target_horizon.le(MAX_HOLD_HOURS)
    return out


def add_dynamic_24h_targets(
    df: pd.DataFrame,
    bias: pd.Series | str,
    *,
    timeframe: str = "H1",
    symbol: pd.Series | str | None = None,
) -> pd.DataFrame:
    """Attach the shared structural, causal 4H-24H TP/SL pair model.

    The public function name is preserved for every existing live/Finder/
    worker/backtest caller.  The former ATR-only implementation remains above
    as a regression reference but is no longer selected.
    """
    from core.advanced_tpsl_engine_20261002 import add_advanced_tpsl_targets

    return add_advanced_tpsl_targets(
        df,
        bias,
        timeframe=timeframe,
        symbol=symbol,
    )


def middle_bias_exit_decision(
    position_side: str,
    current_middle_bias: str,
    *,
    position_age_hours: float | int | None = None,
) -> dict[str, Any]:
    """Return the strategy's main exit decision for an open position.

    Priority is explicit and deterministic: a 24h time cap is absolute; before
    that, a lost/reversed Middle Regime Bias exits the position; otherwise the
    strategy remains eligible to hold toward its Dynamic 24h TP.
    """
    side = str(position_side or "").upper().strip()
    bias_s = str(current_middle_bias or "").upper().strip()
    try:
        age = max(0.0, float(position_age_hours))
    except Exception:
        age = 0.0
    if age >= MAX_HOLD_HOURS:
        return {
            "action": "EXIT",
            "reason": "24H TIME CAP",
            "exit_method": "TIME_EXIT",
            "priority": 1,
            "max_hold_hours": MAX_HOLD_HOURS,
        }
    if side in {"BUY", "SELL"} and bias_s != side:
        return {
            "action": "EXIT",
            "reason": "MIDDLE BIAS LOST / REVERSED",
            "exit_method": "MIDDLE_BIAS_EXIT",
            "priority": 2,
            "max_hold_hours": MAX_HOLD_HOURS,
        }
    return {
        "action": "HOLD_TO_DYNAMIC_TP",
        "reason": "MIDDLE BIAS ALIGNED",
        "exit_method": "DYNAMIC_TP_PLUS_MIDDLE_BIAS_EXIT",
        "priority": 3,
        "max_hold_hours": MAX_HOLD_HOURS,
    }

def _strategy_labels(row: pd.Series) -> list[str]:
    labels: list[str] = []
    for column in row.index:
        if str(column).endswith(" Entry Condition") and str(column).startswith("S"):
            value = str(row.get(column, "False")).strip().lower() in {"true", "1", "1.0"}
            if value:
                labels.append(str(column).split()[0])
    return labels


def attach_hourly_four_selection(
    frame: pd.DataFrame,
    *,
    timestamp_columns: tuple[str, ...] = ("Completed Candle", "Datetime", "_FinderDatetime"),
    max_symbols: int = SELECTOR_MAX_SYMBOLS,
    coverage_state: dict | None = None,
    copy: bool = True,
) -> pd.DataFrame:
    """Select the hourly opportunity set with strategy-first quality balancing.

    Actual S1-S120 hits remain the only genuine strategy origin.  Among those
    hits, the selector now balances recent coverage so low-frequency symbols
    with many valid signals are not systematically starved.  Coverage bonus is
    only active when the candidate still clears strong quality/risk gates, so it
    cannot turn a weak row into a false strategy signal.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    out = frame.copy() if copy else frame
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated(keep="last")].copy()
    out.reset_index(drop=True, inplace=True)
    from core.compact_strategy_decision_20260930 import annotate_middle_bias_exits, apply_exit_notice, compact_entry
    out = annotate_middle_bias_exits(out, copy=False)
    idx = out.index

    ts_col = next((c for c in timestamp_columns if c in out.columns), None)
    if ts_col is not None:
        timestamps = pd.to_datetime(out[ts_col], errors="coerce", utc=True)
        group_key = timestamps.dt.floor("h")
    else:
        group_key = pd.Series(pd.Timestamp("1970-01-01", tz="UTC"), index=idx)

    condition_cols = [c for c in out.columns if re.fullmatch(r"S\d+ Entry Condition", str(c))]
    score_cols = [c for c in out.columns if re.fullmatch(r"S\d+ Score", str(c))]
    if condition_cols:
        cond_df = pd.DataFrame({
            c: out[c].astype(str).str.strip().str.lower().isin({"true", "1", "1.0"}) for c in condition_cols
        }, index=idx)
        hit_count = cond_df.sum(axis=1).astype(int)
    else:
        hit_count = _num(out.get("Strategy Hit Count", pd.Series(0, index=idx)), idx, default=0).astype(int)
    if score_cols:
        score_df = pd.DataFrame({c: pd.to_numeric(out[c], errors="coerce").fillna(0) for c in score_cols}, index=idx)
        best_score = score_df.max(axis=1).fillna(0)
    else:
        best_score = _num(out.get("Best Strategy Score", pd.Series(0, index=idx)), idx, default=0)

    near_score = _num(out.get("Near Entry Score", pd.Series(0, index=idx)), idx, default=0).clip(0, 100)
    alignment = pd.Series(0.0, index=idx)
    if "Lower Regime Bias" in out and "Middle Regime Bias" in out and "Higher Standard Regime Bias" in out:
        b1 = out["Lower Regime Bias"].astype(str).str.upper()
        b2 = out["Middle Regime Bias"].astype(str).str.upper()
        b3 = out["Higher Standard Regime Bias"].astype(str).str.upper()
        alignment = ((b1.eq(b2).astype(int) + b2.eq(b3).astype(int) + b1.eq(b3).astype(int)) / 3 * 100).astype(float)
    elif "Middle Regime Bias" in out:
        alignment = out["Middle Regime Bias"].astype(str).str.upper().isin({"BUY", "SELL"}).astype(float) * 60

    rr = _num(out.get("TP:SL Price Ratio", pd.Series(0, index=idx)), idx, default=0).clip(0, 8)
    tp_potential = _num(out.get("24H TP Distance", pd.Series(0, index=idx)), idx, default=0)
    net_pip_potential = _num(out.get("24H Estimated Net Pip Potential", pd.Series(0, index=idx)), idx, default=0).clip(0, 5000)
    romad_proxy = _num(out.get("24H ROMAD Proxy", pd.Series(0, index=idx)), idx, default=0).clip(0, 10)
    atr = _num(out.get("ATR", pd.Series(np.nan, index=idx)), idx, default=np.nan)
    tp_vs_atr = tp_potential.div(atr.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0).clip(0, 10)
    noise = _num(out.get("Entry Noise Ratio", pd.Series(1.0, index=idx)), idx, default=1.0).clip(0, 5)
    sl_vs_atr = _num(out.get("24H SL Distance", pd.Series(0.0, index=idx)), idx, default=0).div(atr.replace(0, np.nan)).fillna(0).clip(0, 5)

    pair_quality = _num(out.get("TP/SL Pair Quality Score", pd.Series(50.0, index=idx)), idx, default=50.0).clip(0, 100)
    sl_cap_passed = out.get("SL Risk Cap Passed", pd.Series(True, index=idx)).astype(str).str.lower().isin({"true", "1", "1.0"})
    liquidity_quality = _num(out.get("SL Liquidity Safety Score", pd.Series(50.0, index=idx)), idx, default=50.0).clip(0, 100)
    rebound_rate = _num(out.get("SL Rebound To TP Rate", pd.Series(20.0, index=idx)), idx, default=20.0).clip(0, 100)
    risk_quality = (
        24 * rr.sub(1.20).div(2.80).clip(0, 1)
        + 18 * (1 - noise.sub(1.0).div(1.3).clip(0, 1))
        + 12 * (1 - sl_vs_atr.sub(1.0).div(1.9).clip(0, 1))
        + 25 * pair_quality.div(100)
        + 12 * liquidity_quality.div(100)
        + 9 * (1 - rebound_rate.div(25).clip(0, 1))
    ).where(sl_cap_passed, 0.35 * pair_quality).clip(0, 100)
    candidate_quality = (
        best_score * 0.34 + near_score * 0.18 + alignment * 0.12
        + risk_quality * 0.18 + pair_quality * 0.18
    ).clip(0, 100)

    out["Strategy Hit Count"] = hit_count
    out["Best Strategy Score"] = best_score.round(1)
    out["Near Entry Score"] = near_score.round(1)
    out["Risk Quality Score"] = risk_quality.round(1)
    out["Candidate Quality Score"] = candidate_quality.round(1)
    out["Hourly Selection Score"] = 0.0
    out["Hourly 4 Entry"] = False
    out["Hourly Selection Rank"] = pd.Series(pd.NA, index=idx, dtype="Int64")
    out["Hourly Entry Origin"] = "NOT SELECTED"
    out["Hourly Selected Count"] = 0
    out["Strategy Decision"] = "None"
    out["Coverage Priority"] = 0.0

    symbol_series = out.get("Symbol", pd.Series("", index=idx)).astype(str).str.upper()
    middle_bias = out.get("Middle Regime Bias", pd.Series("NEUTRAL", index=idx)).astype(str).str.upper()
    tp_display = out.get("TP Price Display", pd.Series("—", index=idx)).astype(str)
    sl_display = out.get("SL Price Display", pd.Series("—", index=idx)).astype(str)

    symbol_values = symbol_series.to_numpy()
    hit_values = hit_count.to_numpy()
    state = coverage_state if coverage_state is not None else {}
    prior_opportunities = state.setdefault("opportunities", {})
    prior_selected = state.setdefault("selected", {})
    selected_rows: list[tuple[Any, int, int]] = []

    temp = pd.DataFrame({
        "group": group_key,
        "symbol": symbol_series,
        "hit_count": hit_count,
        "best_score": best_score,
        "near_score": near_score,
        "alignment": alignment,
        "rr": rr,
        "net_pip_potential": net_pip_potential,
        "romad_proxy": romad_proxy,
        "risk_quality": risk_quality,
        "pair_quality": pair_quality,
        "candidate_quality": candidate_quality,
        "tp_vs_atr": tp_vs_atr,
        "noise": noise,
        "index": idx,
    }, index=idx)

    for group_value, group in temp.groupby("group", dropna=False, sort=True):
        if group.empty:
            continue
        rows = []
        for rec in group.itertuples(index=False, name=None):
            rec = dict(zip(group.columns, rec))
            sym = str(rec["symbol"]).upper()
            hits = int(rec["hit_count"])
            previous_opportunities = prior_opportunities.get(sym, 0)
            previous_selected = prior_selected.get(sym, 0)
            coverage_ratio = previous_selected / max(previous_opportunities, 1)
            coverage_need = max(0.0, min(1.0, (0.50 - coverage_ratio) / 0.50)) if previous_opportunities else 0.60

            # LOWER ENTRY COVERAGE MODE: use one exact 40% reduction for the
            # selector's quality floors. The strategy audit applies the same
            # reduction to S1-S120 shared admissibility filters.
            strong_quality = (
                hits > 0
                and float(rec["best_score"]) >= 75 * ENTRY_FILTER_MULTIPLIER
                and float(rec["near_score"]) >= 65 * ENTRY_FILTER_MULTIPLIER
                and float(rec["risk_quality"]) >= 65 * ENTRY_FILTER_MULTIPLIER
                and float(rec["rr"]) >= 2.0 * ENTRY_FILTER_MULTIPLIER
            )
            low_frequency_bonus = 0.0
            if sym in LOW_FREQUENCY_COVERAGE_SYMBOLS and strong_quality:
                low_frequency_bonus = 85.0 + 120.0 * coverage_need
            elif strong_quality and coverage_ratio < 0.25:
                low_frequency_bonus = 35.0 * coverage_need

            # Risk-adjusted selection utility: high-quality real hits dominate;
            # coverage is a tie-breaker for starved symbols, not a replacement
            # for an actual strategy condition.
            utility = (
                (1000.0 if hits > 0 else 0.0)
                + hits * 48.0
                + float(rec["best_score"]) * 2.65
                + float(rec["near_score"]) * 1.20
                + float(rec["alignment"]) * 0.85
                + min(float(rec["rr"]), 5.0) * 18.0
                + min(float(rec["tp_vs_atr"]), 7.0) * 2.5
                + min(float(rec["net_pip_potential"]), 250.0) * 0.20
                + min(float(rec["romad_proxy"]), 10.0) * 22.0
                + float(rec["risk_quality"]) * 1.25
                + float(rec["pair_quality"]) * 1.35
                + low_frequency_bonus
                - max(0.0, float(rec["noise"]) - 1.5) * 22.0
            )
            coverage_priority = 1.0 if (sym in LOW_FREQUENCY_COVERAGE_SYMBOLS and strong_quality and coverage_ratio < 0.50) else 0.0
            rows.append((rec["index"], utility, low_frequency_bonus, coverage_ratio, coverage_priority))

        ranked = sorted(rows, key=lambda x: (-x[1], x[0]))
        slot_count = max(1, min(int(max_symbols), len(ranked)))
        chosen = ranked[:slot_count]

        # Strategy-only coverage floor: when a report-identified low-frequency
        # symbol has a genuine strong S1-S120 hit and has received less than 50%
        # of its prior valid opportunity snapshots, allow one high-quality
        # replacement for the weakest selected candidate. This raises frequency
        # without admitting weak/no-strategy rows.
        quota_candidates = [r for r in ranked[slot_count:] if r[4] > 0]
        if quota_candidates and chosen:
            weakest_pos = min(range(len(chosen)), key=lambda j: chosen[j][1])
            weakest = chosen[weakest_pos]
            for candidate in quota_candidates:
                if candidate[1] >= weakest[1] * 0.78:
                    chosen[weakest_pos] = candidate
                    break
            chosen = sorted(chosen, key=lambda x: (-x[1], x[0]))

        n_chosen = len(chosen)
        chosen_set = {r[0] for r in chosen}
        for rank_pos, (row_idx, utility, bonus, _coverage_ratio, _coverage_priority) in enumerate(chosen, start=1):
            selected_rows.append((row_idx, rank_pos, n_chosen, round(float(utility), 2), round(float(bonus), 2)))
            prior_selected[str(symbol_values[row_idx]).upper()] = prior_selected.get(str(symbol_values[row_idx]).upper(), 0) + 1
        # Every strategy hit counts as an eligible opportunity after the group
        # is scored, even if another symbol wins the current hourly slots.
        for row_idx, _, _, _, _ in rows:
            sym = str(symbol_values[row_idx]).upper()
            if int(hit_values[row_idx]) > 0:
                prior_opportunities[sym] = prior_opportunities.get(sym, 0) + 1

    if selected_rows:
        rows = np.asarray(selected_rows, dtype=float)
        chosen_indices = rows[:, 0].astype(int)
        out.loc[chosen_indices, "Hourly 4 Entry"] = True
        out.loc[chosen_indices, "Hourly Selection Rank"] = rows[:, 1].astype(int)
        out.loc[chosen_indices, "Hourly Selected Count"] = rows[:, 2].astype(int)
        out.loc[chosen_indices, "Hourly Selection Score"] = rows[:, 3]
        out.loc[chosen_indices, "Coverage Priority"] = rows[:, 4]
        out.loc[chosen_indices, "Hourly Entry Origin"] = np.where(hit_values[chosen_indices] > 0, "STRATEGY", "RANK-FILL")
        chosen_tp, chosen_sl = [], []
        tp_values = _num(out.get("Suggested TP", pd.Series(np.nan, index=idx)), idx).to_numpy()
        sl_values = _num(out.get("Suggested SL", pd.Series(np.nan, index=idx)), idx).to_numpy()
        for i in chosen_indices:
            tp = tp_display.iloc[i]
            sl = sl_display.iloc[i]
            chosen_tp.append(price_string(tp_values[i], symbol_values[i]) if tp == "—" else tp)
            chosen_sl.append(price_string(sl_values[i], symbol_values[i]) if sl == "—" else sl)
        if "TP Price Display" not in out:
            out["TP Price Display"] = "—"
        if "SL Price Display" not in out:
            out["SL Price Display"] = "—"
        out.loc[chosen_indices, "TP Price Display"] = chosen_tp
        out.loc[chosen_indices, "SL Price Display"] = chosen_sl
        out.loc[chosen_indices, "Strategy Decision"] = [
            compact_entry(bias, hits, tp, sl) for bias, hits, tp, sl in zip(
                middle_bias.to_numpy()[chosen_indices], hit_values[chosen_indices], chosen_tp, chosen_sl)
        ]

    out = apply_exit_notice(out, recompute=False, copy=False)

    out["_selected_sort"] = out["Hourly 4 Entry"].astype(int)
    out["_rank_sort"] = pd.to_numeric(out["Hourly Selection Rank"], errors="coerce").fillna(9999)
    out["_group_sort"] = group_key
    out = out.sort_values(
        ["_group_sort", "_selected_sort", "_rank_sort", "Hourly Selection Score", "Symbol"],
        ascending=[True, False, True, False, True],
        kind="mergesort",
    )
    out.drop(columns=["_group_sort", "_selected_sort", "_rank_sort"], inplace=True, errors="ignore")
    return out.reset_index(drop=True)


__all__ = [
    "SELECTOR_VERSION",
    "SELECTOR_MAX_SYMBOLS",
    "MAX_HOLD_HOURS",
    "LOW_FREQUENCY_COVERAGE_SYMBOLS",
    "price_string",
    "add_dynamic_24h_targets",
    "middle_bias_exit_decision",
    "attach_hourly_four_selection",
]

"""Causal multi-horizon structural TP/SL pair engine.

The engine only consumes completed OHLC bars.  Forward paths are calculated
for historical origins and released to the model only after the complete
horizon has elapsed.  Same-candle TP/SL ambiguity is treated as SL-first.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


HORIZON_HOURS = (4, 6, 8, 12, 16, 20, 24)
TP_MULTIPLIERS = (0.90, 1.20, 1.50, 1.85, 2.25, 2.70, 3.20)
SL_MULTIPLIERS = (1.10, 1.35, 1.60, 1.90, 2.15, 2.50, 2.90)
# A research-efficient frontier of conservative, balanced and higher-RR pairs.
# Evaluating the full Cartesian grid added no structural information but made a
# two-year multi-symbol build several times slower.
PAIR_GRID = (
    (0.90, 1.10), (1.20, 1.35), (1.50, 1.35), (1.50, 1.60),
    (1.85, 1.60), (1.85, 1.90), (2.25, 1.90), (2.25, 2.15),
    (2.70, 2.15), (2.70, 2.50), (3.20, 2.50), (3.20, 2.90),
)
PAIR_HISTORY_WINDOW = 240
PAIR_MIN_SAMPLES = 24
MAX_HOLD_HOURS = 24


def _num(value: Any, index: pd.Index, default: float = np.nan) -> pd.Series:
    if isinstance(value, pd.Series):
        result = pd.to_numeric(value, errors="coerce").reindex(index)
    else:
        result = pd.to_numeric(pd.Series(value, index=index), errors="coerce")
    return result.fillna(default) if default is not None else result


def _timeframe_hours(timeframe: str | None) -> float:
    text = str(timeframe or "H1").upper().strip()
    if text.startswith("M"):
        try:
            return max(1.0 / 60.0, int(text[1:]) / 60.0)
        except Exception:
            return 1.0
    if text.startswith("H"):
        try:
            return max(1.0, float(int(text[1:])))
        except Exception:
            return 1.0
    if text in {"D1", "1D", "DAY"}:
        return 24.0
    return 1.0


def _bars_for_hours(hours: int, timeframe: str | None) -> int:
    return max(1, int(math.ceil(float(hours) / _timeframe_hours(timeframe))))


def _pip_size(symbol: Any) -> float:
    name = str(symbol or "").upper().replace("/", "")
    if any(token in name for token in ("XAU", "GOLD")):
        return 0.10
    if "JPY" in name:
        return 0.01
    return 0.0001


def _price_decimals(symbol: Any, price: float) -> int:
    name = str(symbol or "").upper()
    if any(token in name for token in ("XAU", "GOLD", "XAG", "SILVER")):
        return 2
    if not np.isfinite(price):
        return 5
    value = abs(float(price))
    return 2 if value >= 100 else 3 if value >= 10 else 5 if value >= 1 else 6


def _price_string(value: Any, symbol: Any, reference: Any) -> str:
    try:
        number = float(value)
        ref = float(reference)
    except Exception:
        return "—"
    if not np.isfinite(number):
        return "—"
    return f"{number:.{_price_decimals(symbol, ref)}f}"


def _atr(high: pd.Series, low: pd.Series, close: pd.Series) -> tuple[pd.Series, pd.Series]:
    previous = close.shift(1)
    true_range = pd.concat(
        ((high - low).abs(), (high - previous).abs(), (low - previous).abs()),
        axis=1,
    ).max(axis=1)
    value = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    fallback = true_range.rolling(48, min_periods=8).median().fillna(
        true_range.expanding(min_periods=1).mean()
    )
    return value.fillna(fallback).replace(0, np.nan), true_range


def _released_excursions(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    sign: pd.Series,
    bars: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return MFE/MAE/range only when the historical future window is complete."""
    future_high = high.rolling(bars, min_periods=bars).max().shift(-bars)
    future_low = low.rolling(bars, min_periods=bars).min().shift(-bars)
    origin_mfe = pd.Series(
        np.where(sign.gt(0), future_high - close, np.where(sign.lt(0), close - future_low, np.nan)),
        index=close.index,
    ).clip(lower=0)
    origin_mae = pd.Series(
        np.where(sign.gt(0), close - future_low, np.where(sign.lt(0), future_high - close, np.nan)),
        index=close.index,
    ).clip(lower=0)
    origin_range = (future_high - future_low).clip(lower=0)
    # At row t+bars the complete t+1..t+bars path has closed and may be used.
    return origin_mfe.shift(bars), origin_mae.shift(bars), origin_range.shift(bars)


def _rolling_quantile(series: pd.Series, quantile: float) -> pd.Series:
    return series.rolling(PAIR_HISTORY_WINDOW, min_periods=PAIR_MIN_SAMPLES).quantile(quantile)


def _first_touch_times(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    atr: pd.Series,
    sign: pd.Series,
    max_bars: int,
) -> tuple[dict[float, np.ndarray], dict[float, np.ndarray]]:
    """Vectorized future first-touch times for the fixed research grid."""
    n = len(close)
    tp_times = {value: np.full(n, np.inf, dtype=np.float32) for value in TP_MULTIPLIERS}
    sl_times = {value: np.full(n, np.inf, dtype=np.float32) for value in SL_MULTIPLIERS}
    entry = close.to_numpy(dtype=float)
    atr_values = atr.to_numpy(dtype=float)
    direction = sign.to_numpy(dtype=float)
    valid_origin = np.isfinite(entry) & np.isfinite(atr_values) & (atr_values > 0) & (direction != 0)
    for step in range(1, max_bars + 1):
        future_high = high.shift(-step).to_numpy(dtype=float)
        future_low = low.shift(-step).to_numpy(dtype=float)
        for multiple, result in tp_times.items():
            threshold = entry + direction * multiple * atr_values
            touched = np.where(direction > 0, future_high >= threshold, future_low <= threshold)
            mask = valid_origin & np.isfinite(future_high) & np.isfinite(future_low) & touched & np.isinf(result)
            result[mask] = step
        for multiple, result in sl_times.items():
            threshold = entry - direction * multiple * atr_values
            touched = np.where(direction > 0, future_low <= threshold, future_high >= threshold)
            mask = valid_origin & np.isfinite(future_high) & np.isfinite(future_low) & touched & np.isinf(result)
            result[mask] = step
    return tp_times, sl_times


def _released_pair_statistics(
    tp_time: np.ndarray,
    sl_time: np.ndarray,
    bars: int,
    index: pd.Index,
) -> dict[str, pd.Series]:
    n = len(index)
    complete = np.arange(n) + bars < n
    tp_hit = tp_time <= bars
    sl_hit = sl_time <= bars
    ambiguous = complete & tp_hit & sl_hit & (tp_time == sl_time)
    # Conservative rule: equality is always SL-first.
    tp_first = complete & tp_hit & (~sl_hit | (tp_time < sl_time))
    sl_first = complete & sl_hit & (~tp_hit | (sl_time <= tp_time))
    neither = complete & ~tp_hit & ~sl_hit
    rebound = complete & sl_hit & tp_hit & (tp_time > sl_time)
    tp_hours = np.where(tp_first, tp_time, np.nan)

    def released(values: np.ndarray) -> pd.Series:
        source = pd.Series(np.where(complete, values, np.nan), index=index, dtype=float)
        return source.shift(bars)

    tp_s = released(tp_first.astype(float))
    sl_s = released(sl_first.astype(float))
    neither_s = released(neither.astype(float))
    ambiguous_s = released(ambiguous.astype(float))
    rebound_s = released(rebound.astype(float))
    tp_hours_s = released(tp_hours)
    sample = tp_s.rolling(PAIR_HISTORY_WINDOW, min_periods=1).count()
    return {
        "sample": sample,
        "tp_rate": tp_s.rolling(PAIR_HISTORY_WINDOW, min_periods=PAIR_MIN_SAMPLES).mean(),
        "sl_rate": sl_s.rolling(PAIR_HISTORY_WINDOW, min_periods=PAIR_MIN_SAMPLES).mean(),
        "neither_rate": neither_s.rolling(PAIR_HISTORY_WINDOW, min_periods=PAIR_MIN_SAMPLES).mean(),
        "ambiguous_count": ambiguous_s.rolling(PAIR_HISTORY_WINDOW, min_periods=1).sum(),
        "rebound_rate": rebound_s.rolling(PAIR_HISTORY_WINDOW, min_periods=PAIR_MIN_SAMPLES).mean(),
        "tp_median_bars": tp_hours_s.rolling(PAIR_HISTORY_WINDOW, min_periods=PAIR_MIN_SAMPLES).median(),
        "tp_p75_bars": tp_hours_s.rolling(PAIR_HISTORY_WINDOW, min_periods=PAIR_MIN_SAMPLES).quantile(0.75),
    }


def add_advanced_tpsl_targets(
    frame: pd.DataFrame,
    bias: pd.Series | str,
    *,
    timeframe: str = "H1",
    symbol: pd.Series | str | None = None,
) -> pd.DataFrame:
    """Attach structural SL and causal 4H–24H first-touch pair optimization."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(index=getattr(frame, "index", None))

    out = frame.copy()
    index = out.index
    high = _num(out.get("high", pd.Series(np.nan, index=index)), index)
    low = _num(out.get("low", pd.Series(np.nan, index=index)), index)
    close = _num(out.get("close", pd.Series(np.nan, index=index)), index)
    op = _num(out.get("open", pd.Series(np.nan, index=index)), index)
    if isinstance(bias, pd.Series):
        bias_s = bias.reindex(index).astype(str).str.upper().str.strip()
    else:
        bias_s = pd.Series(str(bias or "NEUTRAL").upper(), index=index)
    sign = pd.Series(np.where(bias_s.eq("BUY"), 1.0, np.where(bias_s.eq("SELL"), -1.0, 0.0)), index=index)
    if isinstance(symbol, pd.Series):
        symbol_s = symbol.reindex(index).astype(str)
    else:
        symbol_s = pd.Series(str(symbol or ""), index=index)

    atr, true_range = _atr(high, low, close)
    valid_bar = (
        np.isfinite(pd.concat((op, high, low, close), axis=1)).all(axis=1)
        & high.ge(pd.concat((op, close, low), axis=1).max(axis=1))
        & low.le(pd.concat((op, close, high), axis=1).min(axis=1))
        & close.gt(0)
    )
    returns = np.log(close.where(close.gt(0))).diff()
    noise_ratio = true_range.div(atr.shift(1)).replace([np.inf, -np.inf], np.nan)
    noise_p75 = noise_ratio.shift(1).rolling(48, min_periods=12).quantile(0.75).fillna(1.0)
    efficiency_look = max(6, _bars_for_hours(12, timeframe))
    net_move = (close - close.shift(efficiency_look)).abs()
    path_move = close.diff().abs().rolling(efficiency_look, min_periods=max(3, efficiency_look // 2)).sum()
    efficiency = net_move.div(path_move.replace(0, np.nan)).clip(0, 1).fillna(0)
    adx = _num(out.get("ADX", pd.Series(np.nan, index=index)), index)
    adx_strength = ((adx - 16.0) / 24.0).clip(0, 1).fillna(0)
    trend_quality = (0.55 * adx_strength + 0.45 * efficiency).clip(0, 1)

    # Confirmed swing points: the centre bar is two bars old, so both right-hand
    # confirmation bars are completed before the level is published.
    swing_low_event = low.shift(2).where(
        (low.shift(2) < low.shift(3)) & (low.shift(2) <= low.shift(4))
        & (low.shift(2) <= low.shift(1)) & (low.shift(2) <= low)
    )
    swing_high_event = high.shift(2).where(
        (high.shift(2) > high.shift(3)) & (high.shift(2) >= high.shift(4))
        & (high.shift(2) >= high.shift(1)) & (high.shift(2) >= high)
    )
    confirmed_swing_low = swing_low_event.ffill(limit=48)
    confirmed_swing_high = swing_high_event.ffill(limit=48)
    recent_sweep_low = low.shift(1).rolling(8, min_periods=4).min()
    recent_sweep_high = high.shift(1).rolling(8, min_periods=4).max()
    previous_24_low = low.shift(1).rolling(_bars_for_hours(24, timeframe), min_periods=4).min()
    previous_24_high = high.shift(1).rolling(_bars_for_hours(24, timeframe), min_periods=4).max()
    ema20 = close.ewm(span=20, adjust=False, min_periods=7).mean()
    ema50 = close.ewm(span=50, adjust=False, min_periods=17).mean()

    equal_window = max(4, min(12, _bars_for_hours(12, timeframe)))
    low_cluster_mid = low.shift(1).rolling(equal_window, min_periods=4).median()
    high_cluster_mid = high.shift(1).rolling(equal_window, min_periods=4).median()
    low_cluster_spread = low.shift(1).rolling(equal_window, min_periods=4).std()
    high_cluster_spread = high.shift(1).rolling(equal_window, min_periods=4).std()
    equal_low_cluster = low_cluster_mid.where(low_cluster_spread.le(0.16 * atr))
    equal_high_cluster = high_cluster_mid.where(high_cluster_spread.le(0.16 * atr))

    prior_low_20 = low.shift(2).rolling(20, min_periods=10).min()
    prior_high_20 = high.shift(2).rolling(20, min_periods=10).max()
    broke_up = close.shift(1).gt(prior_high_20.shift(1))
    broke_down = close.shift(1).lt(prior_low_20.shift(1))
    breakout_support = prior_high_20.where(broke_up).ffill(limit=12)
    breakout_resistance = prior_low_20.where(broke_down).ffill(limit=12)

    buy_overshoot = (recent_sweep_low - low).clip(lower=0)
    sell_overshoot = (high - recent_sweep_high).clip(lower=0)
    directional_overshoot = pd.Series(
        np.where(sign.gt(0), buy_overshoot, np.where(sign.lt(0), sell_overshoot, np.nan)),
        index=index,
    )
    wick_overshoot_p80 = directional_overshoot.shift(1).rolling(160, min_periods=24).quantile(0.80)
    pip_sizes = pd.Series([_pip_size(value) for value in symbol_s], index=index, dtype=float)
    spread_price = 2.0 * pip_sizes
    adaptive_buffer = pd.concat(
        (0.20 * atr, wick_overshoot_p80, spread_price + 0.08 * atr * noise_p75.clip(0, 2.5)),
        axis=1,
    ).max(axis=1).clip(upper=0.35 * atr)

    buy_levels = pd.concat(
        (confirmed_swing_low, recent_sweep_low, equal_low_cluster, previous_24_low,
         breakout_support, ema20.where(ema20.lt(close)), ema50.where(ema50.lt(close))),
        axis=1,
    )
    sell_levels = pd.concat(
        (confirmed_swing_high, recent_sweep_high, equal_high_cluster, previous_24_high,
         breakout_resistance, ema20.where(ema20.gt(close)), ema50.where(ema50.gt(close))),
        axis=1,
    )
    buy_distances = buy_levels.rsub(close, axis=0).where(lambda values: values.gt(0))
    sell_distances = sell_levels.sub(close, axis=0).where(lambda values: values.gt(0))
    # Use the nearest usable confirmed invalidation, not the farthest level in
    # the lookback. Very small distances describe spread/noise, not structure.
    buy_structural = buy_distances.where(
        buy_distances.ge(0.25 * atr, axis=0) & buy_distances.le(3.5 * atr, axis=0)
    ).min(axis=1, skipna=True)
    sell_structural = sell_distances.where(
        sell_distances.ge(0.25 * atr, axis=0) & sell_distances.le(3.5 * atr, axis=0)
    ).min(axis=1, skipna=True)

    horizon_bars = {hours: _bars_for_hours(hours, timeframe) for hours in HORIZON_HOURS}
    released: dict[int, dict[str, pd.Series]] = {}
    quantiles = (0.50, 0.70, 0.75, 0.80, 0.85, 0.90)
    for hours, bars in horizon_bars.items():
        mfe, mae, path_range = _released_excursions(high, low, close, sign, bars)
        item: dict[str, pd.Series] = {"mfe": mfe, "mae": mae, "range": path_range}
        for quantile in quantiles:
            key = int(round(quantile * 100))
            item[f"mfe_p{key}"] = _rolling_quantile(mfe, quantile)
            item[f"mae_p{key}"] = _rolling_quantile(mae, quantile)
            item[f"range_p{key}"] = _rolling_quantile(path_range, quantile)
        released[hours] = item

    mae_p80_24 = released[24]["mae_p80"]
    base_structural = pd.Series(
        np.where(sign.gt(0), buy_structural, np.where(sign.lt(0), sell_structural, np.nan)),
        index=index,
    )
    cluster_distance = pd.Series(
        np.where(sign.gt(0), close - equal_low_cluster, np.where(sign.lt(0), equal_high_cluster - close, np.nan)),
        index=index,
    )
    protected_cluster_distance = cluster_distance.where(
        cluster_distance.gt(0) & cluster_distance.le(3.5 * atr)
    )
    required_structural_distance = pd.concat(
        (
            base_structural + adaptive_buffer,
            protected_cluster_distance + adaptive_buffer,
            mae_p80_24 + 0.10 * atr,
            1.05 * atr,
        ), axis=1
    ).max(axis=1, skipna=True)
    allowed_max_multiple = (2.15 + 0.55 * noise_p75.sub(0.8).div(1.4).clip(0, 1) + 0.20 * (1 - trend_quality)).clip(2.15, 2.90)
    allowed_max_sl = allowed_max_multiple * atr
    sl_risk_cap_passed = required_structural_distance.le(allowed_max_sl)
    required_multiple = required_structural_distance.div(atr.replace(0, np.nan)).clip(lower=0)

    # Liquidity safety explicitly checks the stop against the nearest repeated
    # stop cluster.  Required structural distance already includes its level.
    cluster_clearance = required_structural_distance - cluster_distance
    liquidity_safety = (
        100 * cluster_clearance.div(adaptive_buffer.replace(0, np.nan)).clip(0, 1)
    ).where(cluster_distance.notna(), 85.0).fillna(60.0)

    # Exact first-touch histories are practical through 96 bars. H1 uses 24;
    # very small timeframes retain causal excursion statistics as fallback.
    max_requested_bars = max(horizon_bars.values())
    exact_path_bars = min(max_requested_bars, 96)
    tp_times, sl_times = _first_touch_times(high, low, close, atr, sign, exact_path_bars)
    timeframe_hours = _timeframe_hours(timeframe)
    spread_in_atr = spread_price.div(atr.replace(0, np.nan)).fillna(0)

    horizon_results: list[dict[str, Any]] = []
    for hours in HORIZON_HOURS:
        bars = horizon_bars[hours]
        pair_rows: list[dict[str, Any]] = []
        for tp_multiple, sl_multiple in PAIR_GRID:
                if bars <= exact_path_bars:
                    stats = _released_pair_statistics(tp_times[tp_multiple], sl_times[sl_multiple], bars, index)
                else:
                    mfe = released[hours]["mfe"]
                    mae = released[hours]["mae"]
                    complete = mfe.notna() & mae.notna()
                    tp_event = (mfe >= tp_multiple * atr).where(complete).astype(float)
                    sl_event = (mae >= sl_multiple * atr).where(complete).astype(float)
                    sample = tp_event.rolling(PAIR_HISTORY_WINDOW, min_periods=1).count()
                    stats = {
                        "sample": sample,
                        "tp_rate": tp_event.rolling(PAIR_HISTORY_WINDOW, min_periods=PAIR_MIN_SAMPLES).mean(),
                        "sl_rate": sl_event.rolling(PAIR_HISTORY_WINDOW, min_periods=PAIR_MIN_SAMPLES).mean(),
                        "neither_rate": pd.Series(np.nan, index=index),
                        "ambiguous_count": pd.Series(0.0, index=index),
                        "rebound_rate": pd.Series(np.nan, index=index),
                        "tp_median_bars": pd.Series(np.nan, index=index),
                        "tp_p75_bars": pd.Series(np.nan, index=index),
                    }
                tp_rate = stats["tp_rate"].fillna(0)
                sl_rate = stats["sl_rate"].fillna(0)
                rebound_rate = stats["rebound_rate"].fillna(0.20)
                sample_quality = stats["sample"].div(80).clip(0, 1)
                rr = tp_multiple / sl_multiple
                expected_atr = tp_rate * tp_multiple - sl_rate * sl_multiple - spread_in_atr
                romad = expected_atr.div((sl_rate.clip(lower=0.08) * sl_multiple)).clip(-5, 10)
                mfe_support = released[hours]["mfe_p75"].div((tp_multiple * atr).replace(0, np.nan)).clip(0, 1).fillna(0)
                rebound_quality = (1 - rebound_rate.div(0.25)).clip(0, 1)
                pair_quality = (
                    24 * tp_rate
                    + 13 * (1 - sl_rate)
                    + 13 * rebound_quality
                    + 12 * min(rr / 2.5, 1.0)
                    + 13 * expected_atr.add(0.5).div(2.5).clip(0, 1)
                    + 10 * romad.add(1).div(4).clip(0, 1)
                    + 8 * mfe_support
                    + 7 * sample_quality
                ).clip(0, 100)
                structural_ok = required_multiple.le(sl_multiple + 0.05)
                risk_ok = sl_multiple <= allowed_max_multiple + 0.02
                utility = (
                    1.35 * pair_quality + 34 * expected_atr + 5 * romad
                    - 0.38 * hours - 42 * rebound_rate
                ).where(structural_ok & risk_ok, -1_000_000.0)
                pair_rows.append({
                    "tp_multiple": tp_multiple,
                    "sl_multiple": sl_multiple,
                    "utility": utility,
                    "quality": pair_quality,
                    "expected_atr": expected_atr,
                    "romad": romad,
                    **stats,
                })
        utility_matrix = np.column_stack([row["utility"].to_numpy(dtype=float) for row in pair_rows])
        best_pair = np.nanargmax(np.where(np.isfinite(utility_matrix), utility_matrix, -1_000_000.0), axis=1)

        def choose(field: str, dtype=float) -> np.ndarray:
            matrix = np.column_stack([np.asarray(row[field], dtype=dtype) if not isinstance(row[field], pd.Series)
                                      else row[field].to_numpy(dtype=dtype) for row in pair_rows])
            return matrix[np.arange(len(index)), best_pair]

        horizon_results.append({
            "hours": hours,
            "utility": utility_matrix[np.arange(len(index)), best_pair],
            "tp_multiple": np.asarray([pair_rows[value]["tp_multiple"] for value in best_pair], dtype=float),
            "sl_multiple": np.asarray([pair_rows[value]["sl_multiple"] for value in best_pair], dtype=float),
            "quality": choose("quality"),
            "expected_atr": choose("expected_atr"),
            "romad": choose("romad"),
            "sample": choose("sample"),
            "tp_rate": choose("tp_rate"),
            "sl_rate": choose("sl_rate"),
            "neither_rate": choose("neither_rate"),
            "ambiguous_count": choose("ambiguous_count"),
            "rebound_rate": choose("rebound_rate"),
            "tp_median_bars": choose("tp_median_bars"),
            "tp_p75_bars": choose("tp_p75_bars"),
        })

    horizon_utility = np.column_stack([item["utility"] for item in horizon_results])
    raw_best_utility = np.nanmax(horizon_utility, axis=1)
    tolerance = np.maximum(np.abs(raw_best_utility) * 0.07, 3.0)
    near_best = horizon_utility >= (raw_best_utility[:, None] - tolerance[:, None])
    # Horizon list is shortest-to-longest, so argmax implements the requested
    # 93%-quality early-profit preference deterministically.
    selected_horizon_index = np.argmax(near_best, axis=1)

    def select_horizon(field: str) -> np.ndarray:
        matrix = np.column_stack([np.asarray(item[field]) for item in horizon_results])
        return matrix[np.arange(len(index)), selected_horizon_index]

    preferred_hours = np.asarray([HORIZON_HOURS[value] for value in selected_horizon_index], dtype=float)
    tp_multiple = select_horizon("tp_multiple").astype(float)
    sl_multiple = select_horizon("sl_multiple").astype(float)
    pair_quality = select_horizon("quality").astype(float)
    sample_count = select_horizon("sample").astype(float)
    tp_first_rate = select_horizon("tp_rate").astype(float)
    sl_first_rate = select_horizon("sl_rate").astype(float)
    neither_rate = select_horizon("neither_rate").astype(float)
    ambiguous_count = select_horizon("ambiguous_count").astype(float)
    rebound_rate = select_horizon("rebound_rate").astype(float)
    median_reach_hours = select_horizon("tp_median_bars").astype(float) * timeframe_hours
    p75_reach_hours = select_horizon("tp_p75_bars").astype(float) * timeframe_hours
    expected_atr = select_horizon("expected_atr").astype(float)
    selected_romad = select_horizon("romad").astype(float)

    selected_mfe_p75 = np.column_stack(
        [released[hours]["mfe_p75"].to_numpy(dtype=float) for hours in HORIZON_HOURS]
    )[np.arange(len(index)), selected_horizon_index]
    selected_mfe_p90 = np.column_stack(
        [released[hours]["mfe_p90"].to_numpy(dtype=float) for hours in HORIZON_HOURS]
    )[np.arange(len(index)), selected_horizon_index]
    empirical_tp = 0.70 * pd.Series(selected_mfe_p75, index=index)
    empirical_floor = 0.60 * pd.Series(selected_mfe_p75, index=index)
    empirical_cap = 0.90 * pd.Series(selected_mfe_p90, index=index)
    grid_tp = pd.Series(tp_multiple, index=index) * atr
    raw_tp_distance = (0.50 * grid_tp + 0.50 * empirical_tp).where(empirical_tp.notna(), grid_tp)
    raw_tp_distance = raw_tp_distance.where(
        empirical_floor.isna(), raw_tp_distance.clip(lower=empirical_floor)
    )
    raw_tp_distance = raw_tp_distance.where(
        empirical_cap.isna(), raw_tp_distance.clip(upper=empirical_cap)
    )
    selected_sl_grid = pd.Series(sl_multiple, index=index) * atr
    sl_distance = pd.concat((selected_sl_grid, required_structural_distance), axis=1).max(axis=1, skipna=True)

    prior_barrier_high = high.shift(1).rolling(max(24, _bars_for_hours(48, timeframe)), min_periods=12).max()
    prior_barrier_low = low.shift(1).rolling(max(24, _bars_for_hours(48, timeframe)), min_periods=12).min()
    barrier_price = pd.Series(
        np.where(sign.gt(0), prior_barrier_high, np.where(sign.lt(0), prior_barrier_low, np.nan)),
        index=index,
    )
    barrier_distance = (sign * (barrier_price - close)).clip(lower=0)
    barrier_strength = (
        100 * (1 - barrier_distance.div(3.0 * atr).clip(0, 1))
        * (0.55 + 0.45 * (1 - efficiency))
    ).clip(0, 100).fillna(0)
    breakout_evidence = (trend_quality.ge(0.72) & (sign * close.diff()).gt(0.55 * atr)).fillna(False)
    beyond_barrier = raw_tp_distance.gt(barrier_distance) & barrier_distance.gt(0)
    tp_distance = raw_tp_distance.where(
        ~(beyond_barrier & barrier_strength.ge(55) & ~breakout_evidence),
        0.92 * barrier_distance,
    )
    barrier_passed = (
        ~beyond_barrier
        | barrier_strength.lt(55)
        | breakout_evidence
        | tp_distance.lt(barrier_distance)
    )

    tp_price = close + sign * tp_distance
    sl_price = close - sign * sl_distance
    invalid_direction = ~bias_s.isin(["BUY", "SELL"])
    tp_price = tp_price.mask(invalid_direction)
    sl_price = sl_price.mask(invalid_direction)
    tp_distance = tp_distance.mask(invalid_direction)
    sl_distance = sl_distance.mask(invalid_direction)

    tp_pips = tp_distance.div(pip_sizes.replace(0, np.nan))
    sl_pips = sl_distance.div(pip_sizes.replace(0, np.nan))
    expected_net_pips = (pd.Series(expected_atr, index=index) * atr).div(pip_sizes.replace(0, np.nan)) - 2.0
    rr = tp_distance.div(sl_distance.replace(0, np.nan))
    sample_quality = pd.Series(sample_count, index=index).div(80).clip(0, 1)
    rebound_quality = (100 * (1 - pd.Series(rebound_rate, index=index).div(0.25))).clip(0, 100)
    sl_structural_quality = (
        100 * (1 - (sl_distance - required_structural_distance).abs().div(1.5 * atr).clip(0, 1))
    ).fillna(0)
    sl_quality = (
        0.38 * sl_structural_quality
        + 0.28 * liquidity_safety
        + 0.24 * rebound_quality
        + 10 * sample_quality
    ).clip(0, 100)
    tp_quality = (
        pd.Series(pair_quality, index=index) * 0.70
        + barrier_passed.astype(float) * 15
        + (1 - preferred_hours / 24.0) * 10
        + sample_quality * 5
    ).clip(0, 100)
    pair_quality_final = (
        0.42 * pd.Series(pair_quality, index=index)
        + 0.24 * sl_quality
        + 0.20 * tp_quality
        + 0.08 * (rr.div(2.5).clip(0, 1) * 100)
        + 0.06 * sample_quality * 100
    ).clip(0, 100)
    pair_quality_final = pair_quality_final.where(sl_risk_cap_passed, pair_quality_final * 0.35)
    quality_level = pd.cut(
        pair_quality_final,
        bins=[-np.inf, 49.999, 64.999, 79.999, np.inf],
        labels=["POOR", "CAUTION", "GOOD", "HIGH"],
    ).astype(str)
    quality_reason = np.select(
        [~sl_risk_cap_passed, pd.Series(rebound_rate, index=index).gt(0.20), ~barrier_passed, sample_count < PAIR_MIN_SAMPLES],
        ["Required structural SL exceeds adaptive risk cap", "Post-SL rebound rate is too high",
         "Target is obstructed by a strong structural barrier", "Insufficient causal pair-history samples"],
        default="Structural SL, first-touch path and target horizon passed",
    )
    sl_reject_reason = np.where(
        sl_risk_cap_passed,
        "",
        "Required structural invalidation is outside allowed maximum SL risk",
    )

    bars24 = horizon_bars[24]
    range24 = high.rolling(bars24, min_periods=max(2, min(8, bars24))).max() - low.rolling(
        bars24, min_periods=max(2, min(8, bars24))
    ).min()
    sigma24 = returns.shift(1).rolling(max(6, bars24), min_periods=max(4, min(8, bars24))).std() * math.sqrt(max(1, bars24))
    volatility_move = close * sigma24
    breakout_room = barrier_distance

    target_columns: dict[str, Any] = {
        "24H Historical Range": range24,
        "24H Range P75": released[24]["range_p75"],
        "24H Range P85": released[24]["range_p85"],
        "24H Range P90": released[24]["range_p90"],
        "24H Historical MFE P75": released[24]["mfe_p75"],
        "24H Historical MFE P85": released[24]["mfe_p85"],
        "24H Historical MFE P90": released[24]["mfe_p90"],
        "24H Historical MAE P75": released[24]["mae_p75"],
        "24H Historical MAE P80": released[24]["mae_p80"],
        "24H Historical MAE P90": released[24]["mae_p90"],
    }
    for hours in HORIZON_HOURS:
        for quantile in quantiles:
            key = int(round(quantile * 100))
            target_columns[f"{hours}H Historical MFE P{key}"] = released[hours][f"mfe_p{key}"]
            target_columns[f"{hours}H Historical MAE P{key}"] = released[hours][f"mae_p{key}"]
        target_columns[f"{hours}H Historical Range P75"] = released[hours]["range_p75"]
    target_columns.update({
        "24H Volatility Move": volatility_move,
        "24H Directional Efficiency": efficiency,
        "24H Breakout Room": breakout_room,
        "24H TP Distance": tp_distance,
        "Selected Horizon Historical MFE P75": pd.Series(selected_mfe_p75, index=index),
        "Selected Horizon Historical MFE P90": pd.Series(selected_mfe_p90, index=index),
        "TP Historical MFE Utilization": tp_distance.div(
            pd.Series(selected_mfe_p75, index=index).replace(0, np.nan)
        ),
        "24H TP Upper Envelope": released[24]["mfe_p90"],
        "24H SL Distance": sl_distance,
        "Suggested TP": tp_price,
        "Suggested SL": sl_price,
        "Suggested TP Price": tp_price,
        "Suggested SL Price": sl_price,
        "TP Target Horizon Hours": preferred_hours,
        "Preferred TP Horizon": [f"{int(value)}H" for value in preferred_hours],
        "Expected TP Hours": np.where(np.isfinite(median_reach_hours), median_reach_hours, preferred_hours),
        "TP Median Reach Hours": median_reach_hours,
        "TP P75 Reach Hours": p75_reach_hours,
        "24H TP Confidence": pair_quality_final.round(1),
        "Suggested TP Pips": tp_pips,
        "Suggested SL Pips": sl_pips,
        "24H Estimated Net Pip Potential": expected_net_pips.round(2),
        "24H ROMAD Proxy": pd.Series(selected_romad, index=index).round(3),
        "Max Hold Hours": MAX_HOLD_HOURS,
        "Time Exit Enabled": True,
        "Time Exit Hours": MAX_HOLD_HOURS,
        "Exit Scenario": "Dynamic TP + Middle Bias Exit",
        "TP Estimate Basis": "Causal multi-horizon first-touch pair + structural barrier",
        "TP Price Display": [_price_string(value, sym, price) for value, sym, price in zip(tp_price, symbol_s, close)],
        "SL Price Display": [_price_string(value, sym, price) for value, sym, price in zip(sl_price, symbol_s, close)],
        "TP:SL Price Ratio": rr,
        "TP Within 24H": valid_bar & tp_distance.gt(0) & pd.Series(preferred_hours, index=index).le(24),
        "Required Structural SL": required_structural_distance,
        "Allowed Maximum SL": allowed_max_sl,
        "SL Risk Cap Passed": sl_risk_cap_passed.fillna(False),
        "SL Reject Reason": sl_reject_reason,
        "SL Liquidity Cluster Price": pd.Series(
            np.where(sign.gt(0), equal_low_cluster, np.where(sign.lt(0), equal_high_cluster, np.nan)), index=index
        ),
        "SL Adaptive Invalidation Buffer": adaptive_buffer,
        "SL Structural Quality Score": sl_structural_quality.round(1),
        "SL Liquidity Safety Score": liquidity_safety.round(1),
        "SL Rebound To TP Rate": (100 * pd.Series(rebound_rate, index=index)).round(2),
        "SL Rebound Sample Count": pd.Series(sample_count, index=index).round().astype("Int64"),
        "SL False Stop Quality": rebound_quality.round(1),
        "Suggested SL Quality Score": sl_quality.round(1),
        "TP First Rate": (100 * pd.Series(tp_first_rate, index=index)).round(2),
        "SL First Rate": (100 * pd.Series(sl_first_rate, index=index)).round(2),
        "Neither Touch Rate": (100 * pd.Series(neither_rate, index=index)).round(2),
        "Same Candle Ambiguous Count": pd.Series(ambiguous_count, index=index).round().astype("Int64"),
        "Nearest TP Barrier Price": barrier_price,
        "TP Barrier Distance": barrier_distance,
        "TP Barrier Strength": barrier_strength.round(1),
        "TP Beyond Barrier": beyond_barrier,
        "TP Barrier Quality Passed": barrier_passed,
        "TP Quality Score": tp_quality.round(1),
        "SL Quality Score": sl_quality.round(1),
        "TP/SL Pair Quality Score": pair_quality_final.round(1),
        "TP/SL Quality Level": quality_level,
        "TP/SL Quality Reason": quality_reason,
        "TP/SL Sample Count": pd.Series(sample_count, index=index).round().astype("Int64"),
        "TP/SL Expected ATR": pd.Series(expected_atr, index=index).round(4),
        "TP/SL Engine": "structural-multihorizon-first-touch-v1-20261002",
    })
    # One concat avoids pandas block fragmentation on two-year symbol frames.
    additions = pd.DataFrame(target_columns, index=index)
    out = out.drop(columns=[column for column in additions if column in out], errors="ignore")
    return pd.concat((out, additions), axis=1)


__all__ = [
    "HORIZON_HOURS", "PAIR_MIN_SAMPLES", "MAX_HOLD_HOURS",
    "add_advanced_tpsl_targets", "_released_excursions", "_released_pair_statistics",
]

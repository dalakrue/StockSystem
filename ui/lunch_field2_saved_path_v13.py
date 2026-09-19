"""Read-only recovery of already-saved Field 2 prediction paths.

No model, connector, calibration or settlement code is imported here.  The
module only normalizes values that were already published by the Settings run.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping
import math

import numpy as np
import pandas as pd

PATH_ALIASES = (
    "main_path", "weighted_main", "calibrated_close", "predicted_close",
    "forecast_close", "point_forecast", "prediction", "path", "consensus",
)
LOWER_ALIASES = ("lower_band", "lower_bound", "lower", "p10", "q10", "low")
UPPER_ALIASES = ("upper_band", "upper_bound", "upper", "p90", "q90", "high")
TIME_ALIASES = ("time", "future_time", "target_time", "projection_time", "datetime", "timestamp")
STEP_ALIASES = ("step", "horizon", "horizon_hours", "hour", "lead")


def _name(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "_").replace("/", "_")


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except Exception:
        return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _column(frame: pd.DataFrame, aliases: Iterable[str]) -> Any | None:
    lookup = {_name(column): column for column in frame.columns}
    for alias in aliases:
        if _name(alias) in lookup:
            return lookup[_name(alias)]
    return None


def _series(value: Any) -> list[float]:
    if isinstance(value, pd.Series):
        raw = value.tolist()
    elif isinstance(value, np.ndarray):
        raw = value.reshape(-1).tolist()
    elif isinstance(value, (list, tuple)):
        raw = list(value)
    else:
        number = _finite(value)
        return [] if number is None else [number]
    return [number for item in raw if (number := _finite(item)) is not None]


def _frame_candidate(frame: pd.DataFrame, provenance: str) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    point_col = _column(frame, PATH_ALIASES)
    if point_col is None:
        # Step-indexed frames sometimes use a plain Close column for forecasts.
        point_col = _column(frame, ("close",))
    if point_col is None:
        return pd.DataFrame()
    point = pd.to_numeric(frame[point_col], errors="coerce")
    time_col = _column(frame, TIME_ALIASES)
    step_col = _column(frame, STEP_ALIASES)
    out = pd.DataFrame({"main_path": point})
    if time_col is not None:
        out["time"] = pd.to_datetime(frame[time_col], errors="coerce", utc=True)
    if step_col is not None:
        out["step"] = pd.to_numeric(frame[step_col], errors="coerce")
    lower_col = _column(frame, LOWER_ALIASES)
    upper_col = _column(frame, UPPER_ALIASES)
    if lower_col is not None:
        out["lower_band"] = pd.to_numeric(frame[lower_col], errors="coerce")
    if upper_col is not None:
        out["upper_band"] = pd.to_numeric(frame[upper_col], errors="coerce")
    out["source_provenance"] = provenance
    return out.dropna(subset=["main_path"]).reset_index(drop=True)


def _walk(value: Any, *, provenance: str, depth: int = 0, seen: set[int] | None = None):
    if depth > 6:
        return
    seen = seen if seen is not None else set()
    if isinstance(value, (Mapping, list, tuple, pd.DataFrame, pd.Series, np.ndarray)):
        marker = id(value)
        if marker in seen:
            return
        seen.add(marker)
    if isinstance(value, pd.DataFrame):
        candidate = _frame_candidate(value, provenance)
        if not candidate.empty:
            yield candidate
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_provenance = f"{provenance}.{key}"
            if isinstance(child, pd.DataFrame):
                candidate = _frame_candidate(child, child_provenance)
                if not candidate.empty:
                    yield candidate
            elif isinstance(child, (Mapping, list, tuple)):
                yield from _walk(child, provenance=child_provenance, depth=depth + 1, seen=seen)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value[:50]):
            if isinstance(child, (Mapping, list, tuple, pd.DataFrame)):
                yield from _walk(child, provenance=f"{provenance}[{index}]", depth=depth + 1, seen=seen)


def _mapping_arrays(value: Any, provenance: str) -> pd.DataFrame:
    mapping = _mapping(value)
    if not mapping:
        return pd.DataFrame()
    normalized = {_name(key): (key, child) for key, child in mapping.items()}
    point_pair = next((normalized[name] for name in PATH_ALIASES if name in normalized), None)
    if point_pair is None:
        return pd.DataFrame()
    points = _series(point_pair[1])
    if not points:
        return pd.DataFrame()
    out = pd.DataFrame({"main_path": points})
    for aliases, target in ((LOWER_ALIASES, "lower_band"), (UPPER_ALIASES, "upper_band")):
        pair = next((normalized[name] for name in aliases if name in normalized), None)
        values = _series(pair[1]) if pair else []
        if values:
            out[target] = pd.Series(values[: len(out)])
    time_pair = next((normalized[name] for name in TIME_ALIASES if name in normalized), None)
    if time_pair and isinstance(time_pair[1], (list, tuple, pd.Series, np.ndarray)):
        out["time"] = pd.to_datetime(list(time_pair[1])[: len(out)], errors="coerce", utc=True)
    out["source_provenance"] = provenance
    return out


def _horizon_points(root: Mapping[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    candidates = [root, _mapping(root.get("forecasts")), _mapping(root.get("predictions"))]
    for container in candidates:
        horizons = _mapping(container.get("horizons")) or container
        for hour in (1, 3, 6):
            item = _mapping(horizons.get(f"{hour}h") or horizons.get(f"H+{hour}") or horizons.get(str(hour)))
            point = None
            for alias in PATH_ALIASES:
                point = _finite(item.get(alias))
                if point is not None:
                    break
            if point is None:
                for key in (f"predicted_{hour}h_price", f"prediction_{hour}h", f"h{hour}", f"H+{hour}"):
                    point = _finite(container.get(key))
                    if point is not None:
                        break
            if point is None:
                continue
            lower = next((_finite(item.get(alias)) for alias in LOWER_ALIASES if _finite(item.get(alias)) is not None), None)
            upper = next((_finite(item.get(alias)) for alias in UPPER_ALIASES if _finite(item.get(alias)) is not None), None)
            rows.append({"step": hour, "main_path": point, "lower_band": lower, "upper_band": upper, "source_provenance": "canonical.horizons"})
    return pd.DataFrame(rows).drop_duplicates("step", keep="first") if rows else pd.DataFrame()


def _anchor(market: pd.DataFrame, canonical: Mapping[str, Any], bundle: Mapping[str, Any]) -> tuple[pd.Timestamp | None, float | None]:
    if isinstance(market, pd.DataFrame) and not market.empty:
        time_col = _column(market, TIME_ALIASES)
        close_col = _column(market, ("close", "c"))
        if time_col is not None and close_col is not None:
            view = pd.DataFrame({
                "time": pd.to_datetime(market[time_col], errors="coerce", utc=True),
                "close": pd.to_numeric(market[close_col], errors="coerce"),
            }).dropna().sort_values("time")
            if not view.empty:
                return pd.Timestamp(view.iloc[-1]["time"]), float(view.iloc[-1]["close"])
    summary = _mapping(bundle.get("summary"))
    time = pd.to_datetime(
        canonical.get("latest_completed_candle_time") or summary.get("anchor_time") or canonical.get("candle_time"),
        errors="coerce", utc=True,
    )
    price = _finite(summary.get("anchor_price")) or _finite(canonical.get("current_price"))
    return (None if pd.isna(time) else pd.Timestamp(time)), price


def _finalize_path(candidate: pd.DataFrame, *, anchor_time: pd.Timestamp | None) -> pd.DataFrame:
    if candidate.empty:
        return candidate
    out = candidate.copy()
    if "step" not in out:
        out["step"] = np.arange(1, len(out) + 1)
    out["step"] = pd.to_numeric(out["step"], errors="coerce").fillna(pd.Series(np.arange(1, len(out) + 1), index=out.index)).astype(int)
    if "time" not in out or pd.to_datetime(out["time"], errors="coerce", utc=True).isna().all():
        if anchor_time is None:
            return pd.DataFrame()
        out["time"] = [anchor_time + pd.Timedelta(hours=max(1, int(step))) for step in out["step"]]
    else:
        out["time"] = pd.to_datetime(out["time"], errors="coerce", utc=True)
        if anchor_time is not None:
            missing = out["time"].isna()
            out.loc[missing, "time"] = [anchor_time + pd.Timedelta(hours=max(1, int(step))) for step in out.loc[missing, "step"]]
    out = out.dropna(subset=["time", "main_path"])
    if anchor_time is not None:
        out = out.loc[out["time"] > anchor_time]
    out = out.sort_values(["time", "step"]).drop_duplicates("time", keep="first")
    for column in ("lower_band", "upper_band"):
        if column not in out:
            out[column] = out["main_path"]
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(out["main_path"])
    out["lower_band"] = np.minimum(out["lower_band"], out["main_path"])
    out["upper_band"] = np.maximum(out["upper_band"], out["main_path"])
    width = (out["upper_band"] - out["lower_band"]).abs()
    out["interval_status"] = np.where(width.le(1e-15), "PROVISIONAL_ZERO_WIDTH_BOUND", "SAVED_INTERVAL")
    out["future_actual"] = pd.NA
    return out.head(24).reset_index(drop=True)


def future_candles_from_saved_path(path: pd.DataFrame, *, anchor_price: float | None) -> pd.DataFrame:
    """Convert saved point forecasts to display candles without inventing actuals."""
    if not isinstance(path, pd.DataFrame) or path.empty:
        return pd.DataFrame()
    points = pd.to_numeric(path["main_path"], errors="coerce")
    first_open = anchor_price if anchor_price is not None else _finite(points.iloc[0])
    opens = points.shift(1)
    if first_open is not None:
        opens.iloc[0] = first_open
    lower = pd.to_numeric(path.get("lower_band", points), errors="coerce").fillna(points)
    upper = pd.to_numeric(path.get("upper_band", points), errors="coerce").fillna(points)
    candles = pd.DataFrame({
        "time": pd.to_datetime(path["time"], errors="coerce", utc=True),
        "open": opens,
        "close": points,
    })
    candles["high"] = pd.concat([candles["open"], candles["close"], upper], axis=1).max(axis=1)
    candles["low"] = pd.concat([candles["open"], candles["close"], lower], axis=1).min(axis=1)
    candles["prediction_only"] = True
    candles["actual_close"] = pd.NA
    candles["interval_status"] = path["interval_status"].values
    candles["source_provenance"] = path.get("source_provenance", "saved_prediction_path")
    return candles.dropna(subset=["time", "open", "close"]).reset_index(drop=True)




def _market_close_view(market: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(market, pd.DataFrame) or market.empty:
        return pd.DataFrame()
    time_col = _column(market, TIME_ALIASES)
    close_col = _column(market, ("close", "c"))
    if time_col is None or close_col is None:
        return pd.DataFrame()
    out = pd.DataFrame({
        "time": pd.to_datetime(market[time_col], errors="coerce", utc=True),
        "close": pd.to_numeric(market[close_col], errors="coerce"),
    }).dropna().sort_values("time", kind="mergesort").drop_duplicates("time", keep="last")
    return out.tail(2000).reset_index(drop=True)


def _causal_drift(close: pd.Series) -> tuple[float, float]:
    returns = np.log(close / close.shift(1)).replace([np.inf, -np.inf], np.nan).dropna()
    if returns.empty:
        return 0.0, 1e-6
    recent = returns.tail(72)
    volatility = float(recent.std(ddof=1)) if len(recent) >= 8 else float(returns.std(ddof=1) or 1e-6)
    if not math.isfinite(volatility) or volatility <= 0:
        volatility = max(abs(float(recent.median() if not recent.empty else 0.0)), 1e-6)
    momentum = float(returns.tail(6).median()) if len(returns) >= 3 else float(returns.iloc[-1])
    ewma = float(returns.ewm(span=36, adjust=False).mean().iloc[-1])
    slow = float(returns.tail(120).median()) if len(returns) >= 24 else ewma
    drift = 0.50 * momentum + 0.35 * ewma + 0.15 * slow
    drift = float(np.clip(drift, -2.5 * volatility, 2.5 * volatility))
    return drift, volatility


def _historical_causal_reference(view: pd.DataFrame, horizons: int = 6, paths: int = 6) -> pd.DataFrame:
    """Build display-only historical paths using information available at each origin."""
    if len(view) < 80:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    last_origin = len(view) - horizons - 1
    origins = list(range(max(48, last_origin - (paths - 1) * 12), last_origin + 1, 12))[-paths:]
    for origin_index in origins:
        history = view.iloc[: origin_index + 1]
        drift, _ = _causal_drift(history["close"] if isinstance(history, pd.DataFrame) else pd.Series(dtype=float))
        anchor = float(history["close"].iloc[-1])
        origin_time = pd.Timestamp(history["time"].iloc[-1])
        price = anchor
        for hour in range(1, horizons + 1):
            price *= math.exp(drift * math.exp(-0.14 * (hour - 1)))
            target_index = origin_index + hour
            if target_index >= len(view):
                break
            rows.append({
                "origin_time": origin_time,
                "time": pd.Timestamp(view["time"].iloc[target_index]),
                "predicted_close": price,
                "source_provenance": "CAUSAL_HISTORICAL_REFERENCE",
            })
    return pd.DataFrame(rows)


def build_ohlc_fallback_projection(
    market: pd.DataFrame, canonical: Mapping[str, Any], existing: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], pd.DataFrame, dict[str, Any]]:
    """Build a bounded, transparent display fallback from the active symbol's OHLC.

    This is used only when the Settings run did not store a calibrated Power BI
    bundle. It is not labelled as the protected production model and cannot be
    confused with settled forecast evidence.
    """
    view = _market_close_view(market)
    if len(view) < 24:
        return dict(existing or {}), pd.DataFrame(), {
            "ok": False, "reason": "INSUFFICIENT_OHLC_FOR_FALLBACK", "rows": int(len(view)),
            "recalculated": False,
        }
    anchor_time = pd.Timestamp(view["time"].iloc[-1])
    anchor_price = float(view["close"].iloc[-1])
    drift, volatility = _causal_drift(view["close"])
    rows: list[dict[str, Any]] = []
    price = anchor_price
    z80 = 1.2815515655446004
    for hour in range(1, 7):
        step_drift = drift * math.exp(-0.14 * (hour - 1))
        price *= math.exp(step_drift)
        width = z80 * volatility * math.sqrt(hour)
        rows.append({
            "step": hour,
            "time": anchor_time + pd.Timedelta(hours=hour),
            "main_path": price,
            "lower_band": price * math.exp(-width),
            "upper_band": price * math.exp(width),
            "interval_status": "DERIVED_CAUSAL_FALLBACK_BAND",
            "source_provenance": "ACTIVE_SYMBOL_OHLC_CAUSAL_FALLBACK",
            "future_actual": pd.NA,
        })
    path = pd.DataFrame(rows)
    # Backtest the same one-step directional rule without using future values in features.
    returns = np.log(view["close"] / view["close"].shift(1))
    signal = returns.rolling(6, min_periods=3).median().shift(1)
    actual = returns
    valid = signal.notna() & actual.notna()
    accuracy = float(((signal[valid] >= 0) == (actual[valid] >= 0)).tail(240).mean() * 100.0) if int(valid.sum()) >= 20 else 50.0
    reliability = float(np.clip(0.60 * accuracy + 0.40 * (50.0 + min(abs(drift) / max(volatility, 1e-9), 2.0) * 18.0), 45.0, 82.0))
    out = dict(existing or {})
    out.update({
        "ok": True,
        "main": path.copy(),
        "yellow": path[["time", "main_path"]].rename(columns={"main_path": "path"}),
        "red": path[["time", "upper_band"]].rename(columns={"upper_band": "path"}),
        "blue": path[["time", "lower_band"]].rename(columns={"lower_band": "path"}),
    })
    summary = dict(_mapping(out.get("summary")))
    summary.update({
        "anchor_time": anchor_time.isoformat(),
        "anchor_price": anchor_price,
        "path_source": "ACTIVE_SYMBOL_OHLC_CAUSAL_FALLBACK",
        "interval_status": "DERIVED_CAUSAL_FALLBACK_BAND",
        "future_actuals_suppressed": True,
        "fallback_projection": True,
        "fallback_method": "causal drift + realized-volatility sqrt-time band",
        "reliability_pct": reliability,
        "estimated_band_coverage_pct": None,
        "direction_validation_accuracy_pct": accuracy,
    })
    out["summary"] = summary
    future = future_candles_from_saved_path(path, anchor_price=anchor_price)
    meta = {
        "ok": True, "rows": len(path), "horizons": [1, 2, 3, 4, 5, 6],
        "source_provenance": summary["path_source"],
        "interval_status": summary["interval_status"],
        "recalculated": True,
        "fallback_projection": True,
        "future_actuals_present": False,
        "historical_reference": _historical_causal_reference(view),
    }
    return out, future, meta


def recover_saved_prediction_bundle(
    state: Mapping[str, Any], canonical: Mapping[str, Any], market: pd.DataFrame,
) -> tuple[dict[str, Any], pd.DataFrame, dict[str, Any]]:
    """Return normalized bundle/future bars from saved values only."""
    existing = dict(_mapping(state.get("powerbi_calibrated_bundle_20260617")))
    anchor_time, anchor_price = _anchor(market, canonical, existing)
    current_main = existing.get("main") if isinstance(existing.get("main"), pd.DataFrame) else pd.DataFrame()
    candidate = _frame_candidate(current_main, "powerbi_calibrated_bundle_20260617.main")

    roots = (
        ("powerbi_calibrated_bundle_20260617", state.get("powerbi_calibrated_bundle_20260617")),
        ("canonical", canonical),
        ("canonical_prediction_bundle", state.get("canonical_prediction_bundle")),
        ("saved_prediction_bundle", state.get("saved_prediction_bundle")),
        ("powerbi_prediction_bundle", state.get("powerbi_prediction_bundle")),
    )
    candidates: list[pd.DataFrame] = []
    if not candidate.empty:
        candidates.append(candidate)
    for provenance, root in roots:
        mapped = _mapping_arrays(root, provenance)
        if not mapped.empty:
            candidates.append(mapped)
        candidates.extend(list(_walk(root, provenance=provenance)))
    horizons = _horizon_points(canonical)
    if not horizons.empty:
        candidates.append(horizons)

    finalized = [_finalize_path(item, anchor_time=anchor_time) for item in candidates]
    finalized = [item for item in finalized if not item.empty]
    if not finalized:
        return build_ohlc_fallback_projection(market, canonical, existing)
    # Prefer the path with the most future horizons; ties favor saved intervals.
    path = max(finalized, key=lambda item: (len(item), int((item["interval_status"] == "SAVED_INTERVAL").sum())))
    existing["ok"] = True
    existing["main"] = path[["step", "time", "main_path", "upper_band", "lower_band", "interval_status", "source_provenance", "future_actual"]].copy()
    summary = dict(_mapping(existing.get("summary")))
    summary.update({
        "anchor_time": anchor_time.isoformat() if anchor_time is not None else summary.get("anchor_time"),
        "anchor_price": anchor_price,
        "path_source": str(path["source_provenance"].iloc[0]),
        "interval_status": "SAVED_INTERVAL" if (path["interval_status"] == "SAVED_INTERVAL").any() else "PROVISIONAL_ZERO_WIDTH_BOUND",
        "future_actuals_suppressed": True,
    })
    existing["summary"] = summary
    future = future_candles_from_saved_path(path, anchor_price=anchor_price)
    meta = {
        "ok": True,
        "rows": len(path),
        "horizons": sorted(set(int(value) for value in path["step"] if int(value) in {1, 3, 6})),
        "source_provenance": summary["path_source"],
        "interval_status": summary["interval_status"],
        "recalculated": False,
        "future_actuals_present": False,
    }
    return existing, future, meta


__all__ = ["recover_saved_prediction_bundle", "future_candles_from_saved_path", "build_ohlc_fallback_projection"]

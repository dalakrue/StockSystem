"""Per-symbol Field 2 publication adapter.

Production forecast formulas remain authoritative.  This module first freezes
an already-published Field 2 bundle.  Only when no usable display bundle exists
it creates a clearly labelled causal display fallback from the selected
symbol's real completed candles.  The fallback never calls itself calibrated
and never changes a production decision or rank.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from hashlib import sha256
from typing import Any
import json

import numpy as np
import pandas as pd

from core.timeframe_window_contract_20260706 import normalize_timeframe, TIMEFRAME_SECONDS

BUNDLE_KEY = "powerbi_child_bundle_20260706"
VERSION = "powerbi-child-publication-20260706-v1"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _canonical(state: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        value = get_canonical(state)
        if isinstance(value, Mapping):
            return dict(value)
    except Exception:
        pass
    for key in ("canonical_decision_result_20260617", "canonical_result_20260617", "last_valid_canonical_decision_result_20260617"):
        value = state.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _identity(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, str]:
    symbol = str(canonical.get("symbol") or state.get("calculation_symbol_20260702") or state.get("active_snapshot_symbol_20260702") or "").upper()
    timeframe = normalize_timeframe(canonical.get("timeframe") or state.get("timeframe") or "H4")
    completed = canonical.get("completed_broker_candle") or canonical.get("broker_candle_time") or canonical.get("latest_completed_candle_time") or canonical.get("completed_candle")
    stamp = pd.to_datetime(completed, errors="coerce", utc=True)
    completed_iso = "" if pd.isna(stamp) else pd.Timestamp(stamp).isoformat()
    generation = canonical.get("generation_id") or canonical.get("calculation_generation") or state.get("successful_calculation_generation_20260617")
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "parent_run_id": str(state.get("multi_symbol_parent_run_id_20260701") or ""),
        "child_run_id": str(_mapping(state.get("multi_symbol_child_run_active_20260701")).get("child_run_id") or state.get("multi_symbol_current_child_id_20260701") or ""),
        "canonical_run_id": str(canonical.get("run_id") or canonical.get("canonical_calculation_id") or ""),
        "run_id": str(canonical.get("run_id") or canonical.get("canonical_calculation_id") or ""),
        "generation_id": str(generation or ""),
        "snapshot_hash": str(canonical.get("snapshot_hash") or canonical.get("source_snapshot_hash") or ""),
        "source_id": str(canonical.get("source_id") or canonical.get("data_source_id") or canonical.get("source_snapshot_hash") or ""),
        "source_signature": str(state.get("last_completed_source_signature_20260628") or canonical.get("data_signature") or ""),
        "completed_broker_candle": completed_iso,
    }


def _source_frame(state: Mapping[str, Any]) -> pd.DataFrame:
    for key in ("canonical_completed_ohlc_df_20260617", "last_df", "dv_pp_df", "lunch_5layer_powerbi_df"):
        frame = state.get(key)
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            return frame.copy()
    return pd.DataFrame()


def _normalized_ohlc(frame: pd.DataFrame, *, cutoff: str = "") -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    work = frame.copy()
    lookup = {str(c).strip().lower().replace("_", " "): c for c in work.columns}
    time_col = next((lookup.get(k) for k in ("time", "datetime", "timestamp", "open time", "broker timestamp") if lookup.get(k) is not None), None)
    if time_col is None and isinstance(work.index, pd.DatetimeIndex):
        work = work.reset_index().rename(columns={work.index.name or "index": "time"})
        time_col = "time"
    if time_col is None:
        return pd.DataFrame()
    aliases = {"open": ("open", "o"), "high": ("high", "h"), "low": ("low", "l"), "close": ("close", "c"), "volume": ("volume", "tick volume", "v")}
    out = pd.DataFrame({"time": pd.to_datetime(work[time_col], errors="coerce", utc=True)})
    for target, names in aliases.items():
        source = next((lookup.get(name) for name in names if lookup.get(name) is not None), None)
        out[target] = pd.to_numeric(work[source], errors="coerce") if source is not None else np.nan
    out = out.dropna(subset=["time", "open", "high", "low", "close"]).drop_duplicates("time", keep="last").sort_values("time")
    if cutoff:
        stamp = pd.to_datetime(cutoff, errors="coerce", utc=True)
        if pd.notna(stamp):
            out = out.loc[out["time"].le(stamp)]
    return out.reset_index(drop=True)


def _extract_existing(state: Mapping[str, Any], canonical: Mapping[str, Any], identity: Mapping[str, str]) -> dict[str, Any] | None:
    candidates = [
        canonical.get("powerbi"), canonical.get("projection"), canonical.get("forecasts"),
        state.get("powerbi_calibrated_bundle_20260617"), state.get("lunch_5layer_powerbi_result"),
        state.get("powerbi_projection_result_20260619"), state.get("powerbi_projection_cache_20260619"),
        state.get("cached_powerbi_projection_20260619"), state.get(BUNDLE_KEY),
    ]
    for candidate in candidates:
        if not isinstance(candidate, Mapping) or not candidate:
            continue
        candidate_symbol = str(candidate.get("symbol") or identity["symbol"]).upper()
        candidate_tf = normalize_timeframe(candidate.get("timeframe") or identity["timeframe"])
        if candidate_symbol != identity["symbol"] or candidate_tf != identity["timeframe"]:
            continue
        bundle = dict(candidate)
        main = bundle.get("main")
        has_main = (isinstance(main, pd.DataFrame) and not main.empty) or (isinstance(main, (list, tuple)) and bool(main))
        has_path = bool(
            bundle.get("future_path") or bundle.get("projected_path") or bundle.get("predicted_prices")
            or bundle.get("forecast_close") is not None or has_main
        )
        if not has_path:
            continue
        bundle.update({key: value for key, value in identity.items() if value})
        bundle["ok"] = True
        bundle["status"] = str(bundle.get("status") or "PUBLISHED")
        bundle["publication_type"] = str(bundle.get("publication_type") or "PRODUCTION_PUBLISHED")
        bundle["calibration_status"] = str(bundle.get("calibration_status") or bundle.get("Probability Calibration Status") or "PUBLISHED_STATUS_UNSPECIFIED")
        bundle["version"] = VERSION
        return bundle
    return None


def _fallback_bundle(state: Mapping[str, Any], identity: Mapping[str, str]) -> dict[str, Any]:
    frame = _normalized_ohlc(_source_frame(state), cutoff=identity.get("completed_broker_candle", ""))
    if len(frame) < 8:
        raise ValueError(f"Field 2 requires real completed candles; found {len(frame)}")
    close = frame["close"].astype(float)
    returns = np.log(close).diff().dropna()
    drift = float(returns.tail(min(24, len(returns))).median()) if not returns.empty else 0.0
    sigma = float(returns.tail(min(120, len(returns))).std(ddof=1)) if len(returns) > 1 else 0.0
    sigma = max(0.0, sigma if np.isfinite(sigma) else 0.0)
    last = float(close.iloc[-1])
    seconds = TIMEFRAME_SECONDS[identity["timeframe"]]
    origin = pd.Timestamp(frame["time"].iloc[-1])
    configured = (1, 2, 3, 6, 12, 24)
    path: list[dict[str, Any]] = []
    for bars in configured:
        point = float(last * np.exp(drift * bars))
        width = float(last * (np.exp(1.96 * sigma * np.sqrt(bars)) - 1.0))
        path.append({
            "horizon_bars": bars,
            "horizon_hours": bars * seconds / 3600.0,
            "timeframe_seconds": seconds,
            "target_time": (origin + pd.Timedelta(seconds=seconds * bars)).isoformat(),
            "predicted_price": point,
            "lower_bound": max(0.0, point - width),
            "upper_bound": point + width,
        })
    direction = "BUY" if path[0]["predicted_price"] > last else "SELL" if path[0]["predicted_price"] < last else "WAIT"
    probability = float(np.clip(50.0 + abs(drift) / max(sigma, 1e-12) * 10.0, 50.0, 75.0))
    history = frame.tail(120)[["time", "open", "high", "low", "close", "volume"]].copy()
    # SQLite/cache JSON is written with allow_nan=False.  Preserve genuinely
    # missing provider volume as JSON null rather than fabricating zero or
    # leaking a non-standard NaN token into the child publication.
    history = history.astype(object).where(pd.notna(history), None)
    payload = {
        **dict(identity),
        "ok": True,
        "status": "PUBLISHED_CAUSAL_DISPLAY_FALLBACK",
        "publication_type": "CAUSAL_DISPLAY_FALLBACK",
        "fallback": True,
        "calibrated": False,
        "calibration_status": "NOT_CALIBRATED",
        "historical_input_path": history.to_dict("records"),
        "current_candle": history.iloc[-1].to_dict(),
        "future_path": path,
        "current_price": last,
        "last_close": last,
        "predicted_prices": {f"H+{item['horizon_bars']}": item["predicted_price"] for item in path},
        "upper_bands": {f"H+{item['horizon_bars']}": item["upper_bound"] for item in path},
        "lower_bands": {f"H+{item['horizon_bars']}": item["lower_bound"] for item in path},
        "direction": direction,
        "direction_probability": probability,
        "confidence": probability,
        "reliability": "FALLBACK_NOT_CALIBRATED",
        "error": None,
        "uncertainty": None,
        "prediction_origin_broker_time": identity["completed_broker_candle"],
        "version": VERSION,
    }
    payload["bundle_hash"] = sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return payload


def build_and_store_powerbi_bundle(state: MutableMapping[str, Any], *, allow_causal_fallback: bool = True) -> dict[str, Any]:
    canonical = _canonical(state)
    identity = _identity(state, canonical)
    missing = [key for key in ("symbol", "timeframe", "canonical_run_id", "generation_id", "snapshot_hash", "source_id", "completed_broker_candle") if not identity.get(key)]
    if missing:
        return {"ok": False, "status": "CANONICAL_IDENTITY_INCOMPLETE", "missing": missing}
    bundle = _extract_existing(state, canonical, identity)
    if bundle is None and allow_causal_fallback:
        try:
            bundle = _fallback_bundle(state, identity)
        except Exception as exc:
            return {"ok": False, "status": "REAL_CANDLE_FALLBACK_UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"}
    if bundle is None:
        return {"ok": False, "status": "NO_PUBLISHED_POWERBI_BUNDLE"}
    state[BUNDLE_KEY] = bundle
    # Compatibility mirrors are display-only and remain tied to this child.
    state["powerbi_calibrated_bundle_20260617"] = bundle
    state["powerbi_projection_result_20260619"] = bundle
    return {"ok": True, "status": "PUBLISHED", "bundle": bundle, "fallback": bool(bundle.get("fallback"))}


def validate_powerbi_bundle(bundle: Any, *, symbol: Any, timeframe: Any) -> dict[str, Any]:
    value = dict(bundle) if isinstance(bundle, Mapping) else {}
    required = ("symbol", "timeframe", "run_id", "generation_id", "snapshot_hash", "completed_broker_candle", "source_id")
    missing = [key for key in required if not value.get(key)]
    exact = str(value.get("symbol") or "").upper() == str(symbol or "").upper() and normalize_timeframe(value.get("timeframe")) == normalize_timeframe(timeframe)
    def _usable_path(candidate: Any) -> bool:
        if isinstance(candidate, pd.DataFrame):
            return not candidate.empty
        if isinstance(candidate, Mapping):
            return bool(candidate)
        if isinstance(candidate, (list, tuple)):
            return bool(candidate)
        if candidate is None:
            return False
        try:
            return not bool(pd.isna(candidate))
        except Exception:
            return True

    has_path = any(
        _usable_path(value.get(key))
        for key in ("main", "future_path", "projected_path", "predicted_prices", "forecast_close")
    )
    ok = not missing and exact and has_path
    return {"ok": ok, "status": "PASS" if ok else "FAILED_VALIDATION", "missing": missing, "exact_symbol_timeframe": exact, "has_path": has_path}


__all__ = ["BUNDLE_KEY", "VERSION", "build_and_store_powerbi_bundle", "validate_powerbi_bundle"]

"""Safe same-candle reuse for Settings Quick Run Fields 1-3.

A completed immutable generation is reused only when the refreshed source still
ends at the exact same completed H1 candle and all three required caches exist.
This avoids recomputing identical logic while never reusing a stale candle.
"""
from __future__ import annotations

import time
from typing import Any, Mapping, MutableMapping

import pandas as pd


def _canonical(state: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        value = get_canonical(state)
        if isinstance(value, Mapping):
            return value
    except Exception:
        pass
    return {}


def _latest_frame_time(state: Mapping[str, Any]) -> pd.Timestamp | None:
    for key in (
        "last_df",
        "canonical_completed_ohlc_df_20260617",
        "dv_pp_df",
        "lunch_5layer_powerbi_df",
    ):
        frame = state.get(key)
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        normalized = {str(c).strip().lower().replace("_", " "): c for c in frame.columns}
        column = next((normalized.get(name) for name in ("time", "datetime", "timestamp", "date") if normalized.get(name) is not None), None)
        if column is None and isinstance(frame.index, pd.DatetimeIndex):
            parsed = pd.to_datetime(frame.index, errors="coerce", utc=True)
        elif column is not None:
            parsed = pd.to_datetime(frame[column], errors="coerce", utc=True)
        else:
            continue
        valid = parsed.dropna()
        if len(valid):
            return pd.Timestamp(valid.max()).tz_convert("UTC")
    return None


def _canonical_time(canonical: Mapping[str, Any]) -> pd.Timestamp | None:
    market = canonical.get("market") if isinstance(canonical.get("market"), Mapping) else {}
    for value in (
        canonical.get("latest_completed_candle_time"),
        market.get("latest_completed_candle_time"),
        canonical.get("broker_candle_time"),
    ):
        parsed = pd.to_datetime(value, errors="coerce", utc=True)
        if not pd.isna(parsed):
            return pd.Timestamp(parsed).tz_convert("UTC")
    return None


def _metric_ready(state: Mapping[str, Any]) -> bool:
    for key in ("lunch_metric_result_cache", "full_metric_result_cache_20260618"):
        value = state.get(key)
        if isinstance(value, Mapping) and value.get("ok"):
            return True
    return False


def _powerbi_ready(state: Mapping[str, Any]) -> bool:
    """Require a complete, finite, current-generation Field 2 cache before reuse."""
    bundle = state.get("powerbi_calibrated_bundle_20260617")
    if not isinstance(bundle, Mapping) or not bundle.get("ok"):
        return False
    main = bundle.get("main")
    summary = bundle.get("summary") if isinstance(bundle.get("summary"), Mapping) else {}
    if not isinstance(main, pd.DataFrame) or main.empty:
        return False
    names = {str(c).strip().lower().replace("_", " "): c for c in main.columns}
    time_col = next((names.get(k) for k in ("time", "future time", "target time", "projection time") if names.get(k) is not None), None)
    value_col = next((names.get(k) for k in ("central price", "calibrated close", "predicted close", "path", "main path") if names.get(k) is not None), None)
    if time_col is None or value_col is None:
        return False
    times = pd.to_datetime(main[time_col], errors="coerce", utc=True)
    values = pd.to_numeric(main[value_col], errors="coerce")
    if times.isna().any() or values.isna().any() or not values.map(lambda x: bool(pd.notna(x)) and abs(float(x)) != float("inf")).all():
        return False
    required_summary = ("anchor_price",)
    if any(summary.get(key) in (None, "") for key in required_summary):
        return False
    canonical = _canonical(state)
    expected = {
        "run_id": str(canonical.get("run_id") or ""),
        "generation_id": str(canonical.get("generation_id") or canonical.get("calculation_generation") or ""),
        "snapshot_hash": str(canonical.get("snapshot_hash") or state.get("canonical_snapshot_hash_20260617") or ""),
    }
    for key, expected_value in expected.items():
        actual = str(bundle.get(key) or summary.get(key) or "")
        if expected_value and actual and actual != expected_value:
            return False
    return True


def _regime_ready(state: Mapping[str, Any]) -> bool:
    value = state.get("regime_standard_detail_tables_published_20260618")
    if isinstance(value, Mapping) and any(isinstance(v, pd.DataFrame) and not v.empty for v in value.values()):
        return True
    value = state.get("regime_window_analytics_20260618")
    return isinstance(value, Mapping) and bool(value.get("ok"))


def try_reuse_quick_fields_123(state: MutableMapping[str, Any]) -> dict[str, Any] | None:
    started = time.perf_counter()
    canonical = _canonical(state)
    if not canonical:
        return None
    source_time = _latest_frame_time(state)
    published_time = _canonical_time(canonical)
    if source_time is None or published_time is None or source_time != published_time:
        return None
    if not (_metric_ready(state) and _powerbi_ready(state) and _regime_ready(state)):
        return None
    # Reuse requires the complete immutable source contract, not candle time alone.
    try:
        from core.quick_source_signature_20260626 import SIGNATURE_KEY, build_quick_source_signature
        current_signature = build_quick_source_signature(state, canonical)
        published_signature = state.get(SIGNATURE_KEY)
        if not isinstance(published_signature, Mapping):
            return None
        if str(current_signature.get("source_signature") or "") != str(published_signature.get("source_signature") or ""):
            return None
    except Exception:
        return None

    try:
        from core.daily_locked_regime_20260625 import ensure_daily_locked_regime
        ensure_daily_locked_regime(state, canonical)
    except Exception:
        pass

    status = {
        "ok": True,
        "canonical": {
            "ok": True,
            "run_id": canonical.get("run_id"),
            "calculation_generation": canonical.get("calculation_generation"),
            "decision": (canonical.get("final_decision") or {}).get("final_decision") if isinstance(canonical.get("final_decision"), Mapping) else None,
            "reused_same_completed_h1": True,
        },
        "metric": {"ok": True, "cache_status": "REUSED_SAME_COMPLETED_H1"},
        "powerbi": {"ok": True, "cache_status": "REUSED_SAME_COMPLETED_H1"},
        "regime": {"ok": True, "cache_status": "REUSED_SAME_COMPLETED_H1"},
        "calculation_scope": "QUICK_FIELDS_1_2_3",
        "quick_reuse": True,
        "latest_completed_candle_time": published_time.isoformat(),
        "run_id": canonical.get("run_id"),
        "calculation_generation": canonical.get("calculation_generation"),
        "readiness": {
            "ready": True,
            "scope": "QUICK_FIELDS_1_2_3",
            "components": {
                "field_1": {"ready": True, "detail": "Exact immutable cache reused"},
                "field_2": {"ready": True, "detail": "Exact immutable cache reused"},
                "field_3": {"ready": True, "detail": "Exact immutable cache reused"},
            },
        },
        "errors": [],
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "built_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    state["settings_run_status_20260617"] = status
    state["settings_run_complete_20260617"] = True
    return status


__all__ = ["try_reuse_quick_fields_123"]

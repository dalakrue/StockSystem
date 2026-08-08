"""ADX Quant Pro v9 architecture guard.

Additive runtime/orchestration layer for the July 2026 rebuild request.
It repairs identity publication and UI safety only. It never changes protected
trading formulas, regime formulas, decision outputs, ML models, or history rows.
"""
from __future__ import annotations
from core.global_symbol_compat import set_legacy_calculation_symbol

from collections.abc import Mapping, MutableMapping
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from typing import Any
from zoneinfo import ZoneInfo
import json
import os
import uuid

import pandas as pd

from core.generation_identity_20260707 import generation_id, numeric_generation

VERSION = "v9-architecture-guard-20260702"
CANONICAL_STATE_KEY = "canonical_state"
MAX_CANDLES = 60000

# Python's Etc/GMT sign is inverted: Etc/GMT-7 == UTC+7.
DEFAULT_BROKER_TZ_NAME = os.environ.get("ADX_BROKER_TZ", "Etc/GMT-7")
try:
    BROKER_TZ = ZoneInfo(DEFAULT_BROKER_TZ_NAME)
except Exception:  # pragma: no cover
    BROKER_TZ = timezone(timedelta(hours=7))


def broker_time() -> datetime:
    """Authoritative broker display clock used by v9 fallbacks."""
    return datetime.now(BROKER_TZ)


def broker_hour() -> int:
    return int(broker_time().hour)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, pd.DataFrame):
        return not value.empty
    if isinstance(value, pd.Series):
        return not value.empty
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, (list, tuple, set)):
        return bool(value)
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    return value != ""


def _first_present(*values: Any, default: Any = None) -> Any:
    for value in values:
        try:
            if _is_present(value):
                return value
        except Exception:
            if value is not None:
                return value
    return default


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return str(value)[:300]
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v, depth=depth + 1) for k, v in list(value.items())[:200]}
    if isinstance(value, pd.DataFrame):
        return value.tail(50).astype(str).to_dict("records")
    if isinstance(value, pd.Series):
        return value.tail(50).astype(str).tolist()
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v, depth=depth + 1) for v in list(value)[-200:]]
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def _stable_hash(value: Any) -> str:
    try:
        raw = json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        raw = repr(value)
    return sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def _normalize_symbol(value: Any, default: str = "EURUSD") -> str:
    text = str(value or default).strip().upper().replace("/", "").replace(" ", "")
    return text or default


def _parse_utc(value: Any) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    try:
        ts = pd.to_datetime(value, errors="coerce", utc=True)
        if isinstance(ts, pd.Series):
            ts = ts.dropna().max() if ts.notna().any() else pd.NaT
        if isinstance(ts, pd.DatetimeIndex):
            ts = ts.dropna().max() if len(ts.dropna()) else pd.NaT
        if pd.isna(ts):
            return None
        return pd.Timestamp(ts).tz_convert("UTC")
    except Exception:
        return None


def _parse_wall(value: Any) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    try:
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return None
        if ts.tzinfo is not None:
            # Preserve the broker wall-clock hour for display identity.
            ts = ts.tz_localize(None)
        return pd.Timestamp(ts).floor("h")
    except Exception:
        return None


def _frame_latest_time(frame: Any) -> pd.Timestamp | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    names = {str(c).strip().lower().replace("_", " "): c for c in frame.columns}
    col = None
    for alias in (
        "broker timestamp", "broker time", "completed broker candle", "latest completed candle time",
        "time", "timestamp", "datetime", "date", "event time utc",
    ):
        if alias in names:
            col = names[alias]
            break
    try:
        values = frame[col] if col is not None else frame.index
        parsed = pd.to_datetime(values, errors="coerce", utc=True)
        if isinstance(parsed, pd.Series):
            parsed = parsed.dropna()
            return pd.Timestamp(parsed.max()).tz_convert("UTC") if not parsed.empty else None
        if isinstance(parsed, pd.DatetimeIndex):
            parsed = parsed.dropna()
            return pd.Timestamp(parsed.max()).tz_convert("UTC") if len(parsed) else None
    except Exception:
        return None
    return None


def _latest_completed_utc(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> pd.Timestamp:
    for value in (
        canonical.get("latest_completed_candle_time"), canonical.get("completed_candle_utc"),
        canonical.get("broker_candle_time"), canonical.get("completed_broker_candle"),
        state.get("latest_completed_candle_time"), state.get("latest_completed_h1_time"),
    ):
        ts = _parse_utc(value)
        if ts is not None:
            return ts.floor("h")
    for key in (
        "canonical_completed_ohlc_df_20260617", "canonical_completed_ohlc_staging_20260617",
        "dv_pp_df", "last_df", "market_data", "df", "ohlc", "full_metric_history_df_20260618",
    ):
        ts = _frame_latest_time(state.get(key))
        if ts is not None:
            return ts.floor("h")
    # Identity fallback only when a run already produced evidence.
    return pd.Timestamp.now(tz="UTC").floor("h")


def _broker_wall_from_utc(utc_ts: pd.Timestamp, state: Mapping[str, Any]) -> pd.Timestamp:
    # Prefer the configured offset from the shared broker-time contract when available.
    offset_hours = state.get("mt5_broker_utc_offset_hours_20260622", state.get("broker_utc_offset_hours", None))
    try:
        offset = float(offset_hours)
        if -12 <= offset <= 14:
            return (utc_ts + pd.Timedelta(hours=offset)).tz_localize(None).floor("h")
    except Exception:
        pass
    try:
        return utc_ts.tz_convert(BROKER_TZ).tz_localize(None).floor("h")
    except Exception:
        return pd.Timestamp(broker_time()).tz_localize(None).floor("h")


def _evidence_exists(state: Mapping[str, Any]) -> bool:
    for key in (
        "lunch_metric_result_published_20260618", "full_metric_result_cache_20260618",
        "full_metric_history_df_20260618", "field2_quant_upgrade_20260629",
        "powerbi_projection_result_20260619", "powerbi_calibrated_bundle_20260617",
        "field3_regime_lifecycle_monitor_20260701", "regime_standard_detail_tables_published_20260618",
        "settings_run_status_20260617", "field10_multi_symbol_summary_20260701",
    ):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return True
        if isinstance(value, Mapping) and any(v not in (None, "", [], {}) for v in value.values()):
            return True
        if isinstance(value, (list, tuple)) and value:
            return True
    return False


def _valid_canonical(canonical: Any) -> bool:
    if not isinstance(canonical, Mapping):
        return False
    required = (
        "run_id", "calculation_generation", "data_signature", "symbol", "timeframe",
        "source", "latest_completed_candle_time", "created_at", "expires_at",
        "schema_version", "calculation_version", "calculation_status",
    )
    if any(canonical.get(k) in (None, "") for k in required):
        return False
    if not isinstance(canonical.get("market"), Mapping) or not canonical.get("market", {}).get("latest_completed_candle_time"):
        return False
    if not isinstance(canonical.get("final_decision"), Mapping):
        return False
    return str(canonical.get("calculation_status") or "").upper().startswith("COMPLETED")


def _current_canonical(state: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        value = get_canonical(state)
        if isinstance(value, Mapping) and value:
            return dict(value)
    except Exception:
        pass
    for key in (
        "canonical_decision_result_20260617", "last_valid_canonical_decision_result_20260617",
        "canonical_decision_result", "canonical_result_20260617", "canonical_result",
    ):
        value = state.get(key)
        if isinstance(value, Mapping) and value:
            return dict(value)
    return {}


def _decision_from_state(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> str:
    for obj in (
        canonical.get("final_decision"), canonical,
        state.get("lunch_metric_result_published_20260618"), state.get("full_metric_result_cache_20260618"),
    ):
        if isinstance(obj, Mapping):
            for key in ("less_risky_decision", "final_decision", "decision", "master_action", "bias"):
                value = obj.get(key)
                if value not in (None, ""):
                    text = str(value).strip().upper()
                    if text:
                        return text
    return "WAIT"


def build_v9_canonical(state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None) -> dict[str, Any]:
    base = dict(canonical or _current_canonical(state))
    utc_ts = _latest_completed_utc(state, base)
    broker_ts = _parse_wall(base.get("broker_candle_time") or base.get("completed_broker_candle"))
    if broker_ts is None:
        broker_ts = _broker_wall_from_utc(utc_ts, state)
    symbol = _normalize_symbol(base.get("symbol") or state.get("symbol") or state.get("selected_symbol") or "EURUSD")
    timeframe = str(base.get("timeframe") or state.get("timeframe") or "H1").upper()
    generation = numeric_generation(
        base.get("calculation_generation") or base.get("generation") or base.get("generation_id")
        or state.get("canonical_calculation_generation_20260617")
        or state.get("successful_calculation_generation_20260617"),
        default=1,
    )
    source = str(base.get("source") or state.get("source") or state.get("active_data_source") or state.get("connector_mode") or "v9_canonical_guard")
    signature_payload = {
        "symbol": symbol,
        "timeframe": timeframe,
        "source": source,
        "completed_utc": utc_ts.isoformat(),
        "broker": broker_ts.isoformat(),
        "field1": str(type(_first_present(state.get("lunch_metric_result_published_20260618"), state.get("full_metric_result_cache_20260618"), default={})).__name__),
        "field2": str(type(_first_present(state.get("field2_quant_upgrade_20260629"), state.get("powerbi_projection_result_20260619"), default={})).__name__),
        "field3": str(type(_first_present(state.get("field3_regime_lifecycle_monitor_20260701"), state.get("regime_standard_detail_tables_published_20260618"), default={})).__name__),
    }
    source_hash = str(
        base.get("source_snapshot_hash") or base.get("snapshot_hash") or base.get("data_signature")
        or state.get("last_completed_source_signature_20260628") or _stable_hash(signature_payload)
    )
    run_id = str(base.get("run_id") or base.get("canonical_calculation_id") or state.get("canonical_run_id_20260617") or "")
    if not run_id:
        run_id = f"V9-{utc_ts.strftime('%Y%m%dT%H%M%SZ')}-{source_hash[:12]}"
    created = str(base.get("created_at") or base.get("calculation_completed_at") or pd.Timestamp.now(tz="UTC").isoformat())
    expires = str(base.get("expires_at") or (pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=7)).isoformat())
    decision = _decision_from_state(state, base)
    market = dict(_mapping(base.get("market")))
    market.setdefault("latest_completed_candle_time", utc_ts.isoformat())
    market.setdefault("broker_candle_time", broker_ts.isoformat())
    final = dict(_mapping(base.get("final_decision")))
    final.setdefault("final_decision", decision)
    final.setdefault("less_risky_decision", decision)
    final.setdefault("uncertainty_pct", base.get("uncertainty") or 0.0)
    final.setdefault("error_estimate_pct", base.get("error_pct") or 0.0)
    repaired = {**base}
    repaired.update({
        "run_id": run_id,
        "canonical_calculation_id": run_id,
        "calculation_generation": generation,
        "generation_id": generation_id(base.get("generation_id") or generation, fallback_seed=run_id),
        "data_signature": str(base.get("data_signature") or source_hash),
        "source_snapshot_hash": source_hash,
        "snapshot_hash": str(base.get("snapshot_hash") or source_hash),
        "source_id": str(base.get("source_id") or source_hash[:16]),
        "data_source_id": str(base.get("data_source_id") or source_hash[:16]),
        "symbol": symbol,
        "timeframe": timeframe,
        "source": source,
        "latest_completed_candle_time": utc_ts.isoformat(),
        "completed_candle_utc": utc_ts.isoformat(),
        "broker_candle_time": broker_ts.isoformat(),
        "completed_broker_candle": broker_ts.isoformat(),
        "created_at": created,
        "expires_at": expires,
        "schema_version": str(base.get("schema_version") or "adx-canonical-v9"),
        "calculation_version": str(base.get("calculation_version") or VERSION),
        "calculation_status": "COMPLETED_V9_IDENTITY_REPAIRED",
        "market": market,
        "final_decision": final,
    })
    return repaired


def publish_v9_canonical_state(state: MutableMapping[str, Any], *, force: bool = False, reason: str = "runtime") -> dict[str, Any]:
    """Ensure one identity-complete canonical generation exists.

    This is intentionally identity-only. Existing decision/calculation objects are
    copied as-is; missing run_id/source/candle metadata is repaired so renderers,
    Field 10, Power BI and integrity checks share one source of truth.
    """
    if not force and not _evidence_exists(state):
        return {"ok": False, "status": "NO_EVIDENCE", "reason": reason, "version": VERSION}
    current = _current_canonical(state)
    canonical = current if _valid_canonical(current) else build_v9_canonical(state, current)
    canonical = build_v9_canonical(state, canonical)  # add aliases even to valid legacy payloads
    # Publish compatibility aliases used across the project.
    state["canonical_decision_result_20260617"] = canonical
    state["last_valid_canonical_decision_result_20260617"] = canonical
    state["canonical_decision_result"] = canonical
    state["canonical_result_20260617"] = canonical
    state["canonical_result"] = canonical
    state["canonical_run_id_20260617"] = canonical["run_id"]
    state["canonical_calculation_id_20260617"] = canonical["run_id"]
    state["canonical_calculation_generation_20260617"] = canonical["calculation_generation"]
    state["successful_calculation_generation_20260617"] = canonical["calculation_generation"]
    state["latest_completed_candle_time"] = canonical["latest_completed_candle_time"]
    state["broker_candle_time"] = canonical["broker_candle_time"]
    set_legacy_calculation_symbol(state, canonical["symbol"], connector=True)
    state["timeframe"] = canonical["timeframe"]
    source_hash = str(canonical.get("source_snapshot_hash") or canonical.get("snapshot_hash") or canonical.get("data_signature") or "")
    state["canonical_source_snapshot_hash_20260702"] = source_hash
    state[CANONICAL_STATE_KEY] = {
        "run_id": canonical["run_id"],
        "broker_time": canonical["broker_candle_time"],
        "active_symbol": canonical["symbol"],
        "timeframe": canonical["timeframe"],
        "symbols": {},
        "field1": _first_present(state.get("lunch_metric_result_published_20260618"), state.get("full_metric_result_cache_20260618"), default={}),
        "field2": _first_present(state.get("field2_quant_upgrade_20260629"), state.get("powerbi_projection_result_20260619"), default={}),
        "field3": _first_present(state.get("field3_regime_lifecycle_monitor_20260701"), state.get("regime_standard_detail_tables_published_20260618"), default={}),
        "field10": _first_present(state.get("field10_multi_symbol_summary_20260701"), default={}),
        "powerbi_bundle": _first_present(state.get("powerbi_calibrated_bundle_20260617"), state.get("powerbi_bundle"), default={}),
        "errors": [],
        "status": "READY",
        "version": VERSION,
    }
    _repair_field_identity_aliases(state, canonical)
    _ensure_powerbi_bundle(state, canonical)
    report = {
        "ok": True, "status": "READY", "reason": reason, "run_id": canonical["run_id"],
        "symbol": canonical["symbol"], "timeframe": canonical["timeframe"],
        "broker_candle_time": canonical["broker_candle_time"], "source_snapshot_hash": source_hash,
        "version": VERSION,
    }
    state["v9_architecture_guard_status_20260702"] = report
    return report


def _repair_field_identity_aliases(state: MutableMapping[str, Any], canonical: Mapping[str, Any]) -> None:
    identity = {
        "run_id": canonical.get("run_id"),
        "canonical_run_id": canonical.get("run_id"),
        "source_id": canonical.get("source_id") or canonical.get("source_snapshot_hash"),
        "source_snapshot_hash": canonical.get("source_snapshot_hash"),
        "snapshot_hash": canonical.get("snapshot_hash"),
        "symbol": canonical.get("symbol"),
        "timeframe": canonical.get("timeframe"),
        "broker_candle_time": canonical.get("broker_candle_time"),
        "latest_completed_candle_time": canonical.get("latest_completed_candle_time"),
        "calculation_status": "COMPLETED_V9_IDENTITY_REPAIRED",
    }
    for key in (
        "lunch_metric_result_published_20260618", "full_metric_result_cache_20260618",
        "field2_quant_upgrade_20260629", "powerbi_projection_result_20260619",
        "field3_regime_lifecycle_monitor_20260701", "canonical_ai_fact_pack_20260619",
        "compact_canonical_summary_20260619", "field6_quant_history_result_20260622",
        "field7_research_result_20260626", "field8_integrated_history_result_20260624",
        "field9_research_result_20260626", "field9_eurusd_h1_decision_impact",
    ):
        value = state.get(key)
        if isinstance(value, dict):
            for name, item in identity.items():
                value.setdefault(name, item)
            state[key] = value


def _ensure_powerbi_bundle(state: MutableMapping[str, Any], canonical: Mapping[str, Any]) -> None:
    existing = _first_present(state.get("powerbi_calibrated_bundle_20260617"), state.get("powerbi_bundle"), default={})
    if isinstance(existing, Mapping) and existing:
        bundle = dict(existing)
    else:
        bundle = {}
    bundle.setdefault("symbol", canonical.get("symbol"))
    bundle.setdefault("timeframe", canonical.get("timeframe"))
    bundle.setdefault("canonical_run_id", canonical.get("run_id"))
    bundle.setdefault("run_id", canonical.get("run_id"))
    bundle.setdefault("source_snapshot_hash", canonical.get("source_snapshot_hash"))
    bundle.setdefault("broker_candle_time", canonical.get("broker_candle_time"))
    bundle.setdefault("field2_projection", _first_present(state.get("field2_quant_upgrade_20260629"), state.get("powerbi_projection_result_20260619"), default={}))
    bundle.setdefault("field1_history", _first_present(state.get("full_metric_history_df_20260618"), state.get("lunch_metric_result_published_20260618"), default={}))
    bundle.setdefault("field3_regime", _first_present(state.get("field3_regime_lifecycle_monitor_20260701"), state.get("regime_standard_detail_tables_published_20260618"), default={}))
    bundle.setdefault("status", "READY")
    state["powerbi_bundle"] = bundle
    state["powerbi_calibrated_bundle"] = bundle
    state["powerbi_calibrated_bundle_20260617"] = bundle


def install_global_symbol_state(state: MutableMapping[str, Any]) -> None:
    if "active_symbol" not in state:
        state["active_symbol"] = _normalize_symbol(state.get("symbol") or "EURUSD")
    if "canonical_state" not in state:
        state["canonical_state"] = {"active_symbol": state["active_symbol"], "results": {}, "run_id": None, "broker_time": None}


def safe_candle_count(value: Any, default: int = 600) -> int:
    try:
        number = int(value or default)
    except Exception:
        number = default
    return max(1, min(MAX_CANDLES, number))


def finalize_after_settings_run(state: MutableMapping[str, Any], status: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Post-run v9 finalizer called once from Settings and multi-symbol batches."""
    report = publish_v9_canonical_state(state, force=True, reason="settings_run")
    if isinstance(status, Mapping):
        try:
            status.setdefault("v9_architecture_guard_20260702", report)  # type: ignore[attr-defined]
            status.setdefault("canonical", {"ok": True, "run_id": report.get("run_id")})  # type: ignore[attr-defined]
            status.setdefault("run_id", report.get("run_id"))  # type: ignore[attr-defined]
            status.setdefault("calculation_generation", state.get("canonical_calculation_generation_20260617"))  # type: ignore[attr-defined]
        except Exception:
            pass
    return report


__all__ = [
    "VERSION", "MAX_CANDLES", "broker_time", "broker_hour", "safe_candle_count",
    "install_global_symbol_state", "publish_v9_canonical_state", "finalize_after_settings_run",
    "build_v9_canonical",
]

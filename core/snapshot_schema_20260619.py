"""Immutable canonical run-snapshot schema and end-to-end identity checks."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

from core.generation_identity_20260707 import numeric_generation

SNAPSHOT_KEY = "canonical_run_snapshot_20260619"
SCHEMA_VERSION = "adx-run-snapshot-1.0.0"


def _json_safe(value: Any, depth: int = 0) -> Any:
    if depth > 6:
        return str(type(value).__name__)
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v, depth + 1) for k, v in value.items() if str(k) not in {"full_metric_history", "priority_table", "canonical_priority_table"}}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v, depth + 1) for v in value[:200]]
    if hasattr(value, "shape") and hasattr(value, "columns"):
        return {"type": "DataFrame", "shape": list(value.shape), "columns": [str(c) for c in value.columns]}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def canonical_checksum(payload: Mapping[str, Any]) -> str:
    safe = _json_safe({k: v for k, v in payload.items() if k != "checksum"})
    raw = json.dumps(safe, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, tuple):
        return tuple(_freeze(v) for v in value)
    # DataFrames and other heavyweight objects remain referenced, not copied.
    return value


@dataclass(frozen=True)
class RunSnapshot:
    run_id: str
    generation: int
    symbol: str
    timeframe: str
    calculation_started_at: str
    calculation_completed_at: str
    completed_candle: str
    status: str
    schema_version: str
    checksum: str
    metrics: Mapping[str, Any]
    full_metric_history: Any
    regime: Mapping[str, Any]
    prediction: Mapping[str, Any]
    reliability: Mapping[str, Any]
    priority: Mapping[str, Any]
    finder: Mapping[str, Any]
    nlp: Mapping[str, Any]
    risk_plan: Mapping[str, Any]

    def identity(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "calculation_generation": self.generation, "checksum": self.checksum, "schema_version": self.schema_version}


def build_run_snapshot(canonical: Mapping[str, Any]) -> RunSnapshot:
    now = datetime.now(timezone.utc).isoformat()
    final = canonical.get("final_decision") if isinstance(canonical.get("final_decision"), Mapping) else {}
    metrics = {
        "master": canonical.get("master_score"), "entry": canonical.get("entry_score"),
        "hold": canonical.get("hold_safety"), "tp": canonical.get("tp_quality"),
        "exit_risk": canonical.get("exit_risk"), "decision": final.get("final_decision"),
        "less_risky_decision": final.get("less_risky_decision"),
    }
    checksum = str(canonical.get("checksum") or canonical_checksum(canonical))
    full_history = canonical.get("full_metric_history")
    if full_history is None:
        full_history = {"storage": "disk-backed", "authority": "Full Metric Detail + History"}
    return RunSnapshot(
        run_id=str(canonical.get("run_id") or canonical.get("canonical_calculation_id") or ""),
        generation=numeric_generation(canonical.get("calculation_generation") or canonical.get("generation_id"), default=1),
        symbol=str(canonical.get("symbol") or "EURUSD"), timeframe=str(canonical.get("timeframe") or "H1"),
        calculation_started_at=str(canonical.get("calculation_started_at") or canonical.get("created_at") or now),
        calculation_completed_at=str(canonical.get("calculation_completed_at") or canonical.get("created_at") or now),
        completed_candle=str(canonical.get("latest_completed_candle_time") or (canonical.get("market") or {}).get("latest_completed_candle_time") or ""),
        status=str(canonical.get("calculation_status") or ""), schema_version=SCHEMA_VERSION, checksum=checksum,
        metrics=_freeze(metrics), full_metric_history=_freeze(full_history),
        regime=_freeze(canonical.get("regime") or {}), prediction=_freeze(canonical.get("forecasts") or canonical.get("prediction") or {}),
        reliability=_freeze(canonical.get("reliability") or {}), priority=_freeze(canonical.get("priority") or {}),
        finder=_freeze({"top_two": canonical.get("top_two_daily_candidates") or [], "priority_table_ref": "canonical_priority_table_20260617"}),
        nlp=_freeze(canonical.get("nlp") or {}), risk_plan=_freeze(canonical.get("risk_plan") or {}),
    )


def verify_display_generation(state: Mapping[str, Any], component: Mapping[str, Any] | None = None) -> dict[str, Any]:
    canonical = state.get("canonical_decision_result_20260617")
    canonical = canonical if isinstance(canonical, Mapping) else {}
    expected_run = canonical.get("run_id")
    expected_gen = canonical.get("calculation_generation")
    component = component if isinstance(component, Mapping) else state.get("runtime_context_20260617")
    component = component if isinstance(component, Mapping) else {}
    got_run = component.get("run_id") or component.get("canonical_run_id") or expected_run
    got_gen = component.get("calculation_generation") or component.get("canonical_generation") or expected_gen
    ok = bool(expected_run and expected_gen and str(got_run) == str(expected_run) and str(got_gen) == str(expected_gen))
    return {"ok": ok, "expected_run_id": expected_run, "expected_generation": expected_gen, "displayed_run_id": got_run, "displayed_generation": got_gen, "status": "CURRENT" if ok else "STALE_RELOAD_REQUIRED"}


__all__ = ["RunSnapshot", "SNAPSHOT_KEY", "SCHEMA_VERSION", "canonical_checksum", "build_run_snapshot", "verify_display_generation"]

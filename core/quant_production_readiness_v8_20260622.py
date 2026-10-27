"""Quant Production Readiness Score with critical READY blocking."""
from __future__ import annotations
from typing import Any, Mapping

VERSION = "quant-readiness-v8-20260622"
CHECK_NAMES = (
    "schema", "nulls_and_infinities", "duplicate_timestamps", "monotonic_timestamps", "completed_candle_watermark",
    "broker_time_resolution", "field1_synchronization", "cross_table_synchronization", "data_freshness",
    "training_serving_feature_compatibility", "prediction_bounds", "band_ordering", "settlement_completeness",
    "leakage_scan", "calibration_sample_size", "drift_state", "database_migration", "connector_health",
    "cache_bounds", "ui_transaction_lock", "copy_export_generation_identity", "rollback_availability",
)
CRITICAL = {"schema", "completed_candle_watermark", "broker_time_resolution", "field1_synchronization", "cross_table_synchronization", "leakage_scan", "database_migration", "rollback_availability"}


def build_readiness(checks: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for name in CHECK_NAMES:
        raw = checks.get(name, "NOT APPLICABLE")
        if isinstance(raw, Mapping):
            status = str(raw.get("status", "NOT APPLICABLE")).upper(); detail = str(raw.get("detail", raw.get("reason", "")))
        elif isinstance(raw, bool): status, detail = ("PASS" if raw else "FAIL"), ""
        else: status, detail = str(raw).upper(), ""
        if status not in {"PASS", "WARN", "FAIL", "NOT APPLICABLE"}: status = "WARN"
        rows.append({"check": name, "status": status, "critical": name in CRITICAL, "detail": detail})
    critical_failures = [r for r in rows if r["critical"] and r["status"] == "FAIL"]
    failures = [r for r in rows if r["status"] == "FAIL"]; warnings = [r for r in rows if r["status"] == "WARN"]
    visible = "BLOCKED" if critical_failures else "CAUTION" if failures or warnings else "READY"
    pass_count = sum(r["status"] == "PASS" for r in rows); applicable = sum(r["status"] != "NOT APPLICABLE" for r in rows)
    return {"version": VERSION, "visible_status": visible, "score_pct": round(100.0 * pass_count / max(applicable, 1), 2), "checks": rows, "critical_failure_count": len(critical_failures), "failure_count": len(failures), "warning_count": len(warnings)}

__all__ = ["build_readiness", "CHECK_NAMES", "CRITICAL", "VERSION"]

"""Cross-table event-time/generation validation for all Lunch histories."""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping
import pandas as pd

from core.shared_broker_time_20260622 import CONTRACT_VERSION, latest_history_utc, shared_broker_time_provider

LOGIC_VERSION = "cross-table-sync-20260622-v1"

KNOWN_HISTORY_KEYS = (
    "full_metric_history_df_20260618", "protected_decision_history_20260622",
    "canonical_priority_table_20260617", "field6_combined_history_20260622",
    "sentiment_history_20260622", "research_sentiment_history_20260622",
    "regime_overall_history_20260618", "regime_alpha_delta_history_20260618",
    "reliability_history_20260618", "similar_day_history_20260619",
    "prediction_outcome_history_20260617", "powerbi_projection_history_20260619",
)


def _values(frame: pd.DataFrame, names: tuple[str, ...]) -> set[str]:
    normalized = {str(c).strip().lower(): c for c in frame.columns}
    for name in names:
        col = normalized.get(name.lower())
        if col is not None:
            return {str(v) for v in frame[col].dropna().astype(str).unique()}
    return set()


def _frame_report(name: str, frame: pd.DataFrame, contract: Mapping[str, Any]) -> dict[str, Any]:
    latest = latest_history_utc(frame)
    expected = pd.to_datetime(contract.get("latest_completed_h1_utc"), errors="coerce", utc=True)
    difference = abs((latest - expected).total_seconds()) / 60.0 if latest is not None and pd.notna(expected) else None
    calc = _values(frame, ("calculation_id", "canonical_calculation_id", "run_id"))
    gen = _values(frame, ("generation", "calculation_generation"))
    symbol = _values(frame, ("symbol",))
    timeframe = _values(frame, ("timeframe",))
    offset = _values(frame, ("broker_offset_minutes",))
    version = _values(frame, ("contract_version", "timestamp_contract_version"))
    checks = {
        "watermark_match": difference is not None and difference < 1.0,
        "calculation_id_match": not calc or calc == {str(contract.get("calculation_id"))},
        "generation_match": not gen or gen == {str(contract.get("calculation_generation"))},
        "symbol_match": not symbol or symbol == {str(contract.get("symbol"))},
        "timeframe_match": not timeframe or timeframe == {str(contract.get("timeframe"))},
        "broker_offset_match": not offset or offset == {str(contract.get("broker_offset_minutes"))},
        "contract_version_match": not version or version == {CONTRACT_VERSION},
    }
    status = "SYNCED" if all(checks.values()) else "OUT OF SYNC"
    return {
        "table": name, "status": status,
        "latest_completed_h1_utc": latest.isoformat() if latest is not None else None,
        "latest_broker_candle": contract.get("broker_time_display"),
        "difference_minutes": round(difference, 2) if difference is not None else None,
        **checks,
    }


def validate_cross_table_sync(
    state: Mapping[str, Any],
    *,
    canonical: Mapping[str, Any] | None = None,
    frames: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    contract = shared_broker_time_provider(state, canonical=canonical)
    selected: dict[str, pd.DataFrame] = {}
    for name, value in dict(frames or {}).items():
        if isinstance(value, pd.DataFrame) and not value.empty:
            selected[str(name)] = value
    for key in KNOWN_HISTORY_KEYS:
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty and key not in selected:
            selected[key] = value
    table_reports = {name: _frame_report(name, frame, contract) for name, frame in selected.items()}
    if not contract.get("broker_clock_available") or not contract.get("latest_completed_h1_utc"):
        status = "UNAVAILABLE"
    elif not table_reports:
        status = "STALE"
    elif all(item.get("status") == "SYNCED" for item in table_reports.values()):
        status = "SYNCED"
    else:
        status = "OUT OF SYNC"
    return {
        "status": status,
        "contract_version": CONTRACT_VERSION,
        "validation_version": LOGIC_VERSION,
        "latest_completed_h1_utc": contract.get("latest_completed_h1_utc"),
        "latest_broker_candle": contract.get("broker_time_display"),
        "calculation_id": contract.get("calculation_id"),
        "generation": contract.get("calculation_generation"),
        "symbol": contract.get("symbol"),
        "timeframe": contract.get("timeframe"),
        "broker_offset_minutes": contract.get("broker_offset_minutes"),
        "tables": table_reports,
        "table_count": len(table_reports),
    }


def publish_cross_table_sync(state: MutableMapping[str, Any], *, canonical: Mapping[str, Any] | None = None, frames: Mapping[str, Any] | None = None) -> dict[str, Any]:
    report = validate_cross_table_sync(state, canonical=canonical, frames=frames)
    state["lunch_cross_table_sync_20260622"] = report
    return report


__all__ = ["KNOWN_HISTORY_KEYS", "validate_cross_table_sync", "publish_cross_table_sync"]

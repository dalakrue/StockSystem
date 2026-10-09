"""Atomic core-history synchronization and post-publication verification.

The engine is additive.  It copies only already-published canonical values into
history evidence rows, ensures a minimum row exists for the current generation,
and verifies the SQLite commit.  It never changes calculation or strategy logic.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Mapping, MutableMapping

import pandas as pd

from core.history_identity_20260620 import canonical_history_identity
from core.generation_identity_20260707 import numeric_generation
from services.canonical_snapshot_store import DB_PATH

CORE_HISTORY_TABLES = (
    "full_metric_overall_history",
    "powerbi_prediction_ledger",
    "reliability_conflict_history",
    "regime_overall_history",
)
LOGIC_VERSION = "history-sync-engine-20260622-v1"


def _m(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _row(canonical: Mapping[str, Any], *, condition: str, metric_name: str, value: Any = None, payload: Mapping[str, Any] | None = None, horizon: int | None = None, target_time: Any = None) -> dict[str, Any]:
    identity = canonical_history_identity(
        canonical,
        condition=condition,
        horizon=horizon,
        target_time=target_time,
        settled_status="PENDING" if target_time is not None else "COMPLETED",
        logic_version=LOGIC_VERSION,
    )
    number = None
    try:
        number = float(value)
    except Exception:
        pass
    return {
        **identity,
        "metric_name": metric_name,
        "value_numeric": number,
        "value_text": None if number is not None or value is None else str(value),
        "payload": dict(payload or {}),
        "cache_status": "FORCED_CURRENT_GENERATION",
    }


def ensure_core_history_rows(canonical: Mapping[str, Any], bundle: Mapping[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    """Ensure the current generation has core history rows before atomic commit."""
    output: dict[str, Any] = {}
    for name, rows in dict(bundle or {}).items():
        key = str(name)
        # Purpose-built atomic sub-bundles are mappings of table->rows. Preserve
        # that structure instead of converting mapping keys into a row list.
        if key.startswith("__") and isinstance(rows, Mapping):
            output[key] = {str(table): list(table_rows or []) for table, table_rows in rows.items()}
        else:
            output[key] = list(rows or [])
    final = _m(canonical.get("final_decision"))
    regime = _m(canonical.get("regime"))
    reliability = _m(canonical.get("reliability"))
    forecasts = _m(_m(canonical.get("forecasts")).get("horizons"))

    if not output.get("full_metric_overall_history"):
        output.setdefault("full_metric_overall_history", []).append(_row(
            canonical,
            condition="CURRENT_GENERATION",
            metric_name="full_metric",
            value=canonical.get("master_score"),
            payload={
                "decision": final.get("final_decision"),
                "direction": final.get("directional_market_view"),
                "master_score": canonical.get("master_score"),
                "entry_score": canonical.get("entry_score"),
                "hold_safety": canonical.get("hold_safety"),
                "exit_risk": canonical.get("exit_risk"),
                "tp_quality": canonical.get("tp_quality"),
                "trend_capacity_remaining": canonical.get("trend_capacity_remaining"),
            },
        ))

    if not output.get("regime_overall_history"):
        output.setdefault("regime_overall_history", []).append(_row(
            canonical,
            condition="CURRENT_GENERATION",
            metric_name="major_regime",
            value=regime.get("major_regime"),
            payload=dict(regime),
        ))

    if not output.get("reliability_conflict_history"):
        output.setdefault("reliability_conflict_history", []).append(_row(
            canonical,
            condition="CURRENT_GENERATION",
            metric_name="reliability",
            value=reliability.get("score") or reliability.get("calibrated_score_0_100"),
            payload={
                "reliability": dict(reliability),
                "conflict_status": final.get("conflict_status") or final.get("conflict_warning"),
            },
        ))

    if not output.get("powerbi_prediction_ledger"):
        completed = pd.to_datetime(canonical.get("latest_completed_candle_time"), errors="coerce", utc=True)
        for key, raw in forecasts.items():
            item = _m(raw)
            digits = "".join(ch for ch in str(key) if ch.isdigit())
            try:
                horizon = int(digits or item.get("horizon_hours") or item.get("horizon"))
            except Exception:
                continue
            if horizon < 1 or horizon > 36:
                continue
            target = completed + pd.Timedelta(hours=horizon) if pd.notna(completed) else None
            point = item.get("point_forecast") or item.get("median") or item.get("forecast_close")
            output.setdefault("powerbi_prediction_ledger", []).append(_row(
                canonical,
                condition=f"H+{horizon}",
                metric_name="forecast_close",
                value=point,
                payload={
                    "direction": item.get("direction"),
                    "lower_bound": item.get("lower_bound") or item.get("lower"),
                    "upper_bound": item.get("upper_bound") or item.get("upper"),
                    "confidence": item.get("confidence") or item.get("reliability"),
                },
                horizon=horizon,
                target_time=target,
            ))
    return output


def verify_core_history_commit(canonical: Mapping[str, Any], *, db_path=DB_PATH, table_names=None) -> dict[str, Any]:
    """Verify watermarks for the requested populated history tables.

    The default remains the four calculation-critical histories. Callers that
    publish a larger bundle may pass only table names that actually contain rows.
    """
    expected = pd.to_datetime(canonical.get("latest_completed_candle_time"), errors="coerce", utc=True)
    expected_iso = expected.isoformat() if pd.notna(expected) else None
    result: dict[str, Any] = {"ok": True, "expected_latest_completed_h1": expected_iso, "tables": {}}
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    try:
        requested_tables = tuple(dict.fromkeys(str(name) for name in (table_names or CORE_HISTORY_TABLES)))
        for table in requested_tables:
            try:
                row = conn.execute(
                    "SELECT latest_completed_h1,last_calculation_id,last_generation,updated_at FROM history_watermarks WHERE table_name=?",
                    (table,),
                ).fetchone()
            except sqlite3.Error as exc:
                row = None
                result["tables"][table] = {"synced": False, "error": f"{type(exc).__name__}: {exc}", "difference_minutes": None}
                result["ok"] = False
                continue
            latest = pd.to_datetime(row[0], errors="coerce", utc=True) if row else pd.NaT
            difference = abs(float((latest - expected).total_seconds())) / 60.0 if row and pd.notna(latest) and pd.notna(expected) else None
            synced = difference is not None and difference < 1.0
            result["tables"][table] = {
                "synced": synced,
                "latest_completed_h1": row[0] if row else None,
                "calculation_id": row[1] if row else None,
                "generation": row[2] if row else None,
                "updated_at": row[3] if row else None,
                "difference_minutes": round(difference, 2) if difference is not None else None,
            }
            result["ok"] = bool(result["ok"] and synced)
    finally:
        conn.close()
    result["status"] = "SYNCED" if result["ok"] else "OUT OF SYNC"
    return result


def refresh_published_history_state(state: MutableMapping[str, Any], canonical: Mapping[str, Any], verification: Mapping[str, Any]) -> None:
    """Invalidate reconstructable stale UI payloads after a successful commit."""
    identity = str(canonical.get("canonical_calculation_id") or canonical.get("run_id") or "")
    generation = numeric_generation(canonical.get("calculation_generation") or canonical.get("generation_id"), default=1)
    for key in list(state.keys()):
        text = str(key)
        if text.startswith((
            "canonical_copy_short_payload_", "canonical_copy_all_payload_",
            "canonical_export_json_payload_", "lunch_copy_payload_",
        )):
            state.pop(key, None)
    state["history_refresh_generation_20260622"] = generation
    state["history_refresh_calculation_id_20260622"] = identity
    state["history_sync_verification_20260622"] = dict(verification)
    state["history_refresh_complete_20260622"] = bool(verification.get("ok"))
    state["copy_payload_generation_20260622"] = generation


__all__ = [
    "CORE_HISTORY_TABLES", "ensure_core_history_rows", "verify_core_history_commit",
    "refresh_published_history_state",
]

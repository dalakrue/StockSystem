"""Complete per-symbol child publication and reload validation.

A Field-10-only database row is never treated as a complete Field 1/2 child.
The runtime cache remains the full object store; SQLite stores its immutable
identity, coverage, component-completion gates and the selected-symbol Field 2
bundle for deterministic reload checks.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import sqlite3

import pandas as pd

from core.powerbi_child_bundle_20260706 import BUNDLE_KEY, validate_powerbi_bundle
from core.timeframe_window_contract_20260706 import (
    calculation_eligibility, coverage_metadata, required_candles, normalize_timeframe,
    validate_timeframe_spacing,
)
from core.timeframe_identity_migration_20260706 import migrate_timeframe_identity

VERSION = "complete-child-publication-20260706-v1"


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, allow_nan=False)


def _canonical(state: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        value = get_canonical(state)
        if isinstance(value, Mapping) and bool(value):
            return dict(value)
    except Exception:
        pass
    for key in ("canonical_decision_result_20260617", "canonical_result_20260617", "last_valid_canonical_decision_result_20260617"):
        value = state.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _source_frame(state: Mapping[str, Any]) -> pd.DataFrame:
    for key in ("canonical_completed_ohlc_df_20260617", "last_df", "dv_pp_df", "lunch_5layer_powerbi_df"):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value
    return pd.DataFrame()


def _matching_completion_receipt(state: Mapping[str, Any], identity: Mapping[str, Any]) -> dict[str, Any]:
    receipt = state.get("child_component_completion_receipt_20260722")
    if not isinstance(receipt, Mapping):
        return {}
    checks = {
        "symbol": str(receipt.get("symbol") or "").upper() == str(identity.get("symbol") or "").upper(),
        "timeframe": normalize_timeframe(receipt.get("timeframe") or "H4") == normalize_timeframe(identity.get("timeframe") or "H4"),
        "parent_run_id": str(receipt.get("parent_run_id") or "") == str(identity.get("parent_run_id") or ""),
        "child_run_id": str(receipt.get("child_run_id") or "") == str(identity.get("child_run_id") or ""),
    }
    return dict(receipt) if all(checks.values()) else {}


def _has_field1(state: Mapping[str, Any]) -> bool:
    keys = (
        "field1_table1_decision_history_20260628", "full_metric_history_df_20260618",
        "lunch_metric_result_cache", "full_metric_result_cache_20260618",
        "lunch_metric_result_published_20260618", "lunch_metric_result_20260619",
        "field1_table4_current_20260627",
    )
    return any((isinstance(state.get(k), pd.DataFrame) and not state.get(k).empty) or (isinstance(state.get(k), Mapping) and bool(state.get(k))) for k in keys)


def _has_field3(state: Mapping[str, Any]) -> bool:
    """Accept genuine published Field 3 evidence in its supported containers.

    Older validation accepted mappings only. Several current Field 3 publishers
    store the exact standard table as a DataFrame or nest DataFrames below a
    mapping, which caused false FAILED_VALIDATION results after a successful
    calculation. Empty/unavailable markers still fail this gate.
    """
    def usable(value: Any) -> bool:
        if isinstance(value, pd.DataFrame):
            return not value.empty
        if isinstance(value, Mapping):
            status = str(value.get("status") or value.get("publication_status") or "").upper()
            if status in {"FAILED", "UNAVAILABLE", "MISSING", "INSUFFICIENT", "NOT_AVAILABLE"}:
                return False
            if any(usable(item) for item in value.values()):
                return True
            return bool(value) and status in {"AVAILABLE", "COMPLETED", "PUBLISHED", "PASS", "READY"}
        if isinstance(value, (list, tuple)):
            return any(usable(item) for item in value)
        return False

    keys = (
        "regime_standard_detail_tables_published_20260618",
        "regime_standard_detail_tables_20260617",
        "regime_standard_table_20260617",
        "field3_regime_lifecycle_monitor_20260701",
        "field3_local_symbol_snapshot_20260703",
    )
    return any(usable(state.get(key)) for key in keys)


def _marker_matches_symbol(value: Any, symbol: str) -> bool:
    if isinstance(value, pd.DataFrame) and not value.empty:
        for column in ("Symbol", "symbol", "Calculation Symbol"):
            if column in value.columns:
                return value[column].astype(str).str.upper().eq(symbol).any()
        return False
    if isinstance(value, Mapping):
        marker_symbol = str(value.get("symbol") or value.get("Symbol") or value.get("calculation_symbol") or "").upper()
        marker_status = str(value.get("completion_status") or value.get("publication_status") or value.get("status") or "").upper()
        return marker_symbol == symbol and (bool(value.get("ok")) or marker_status in {"COMPLETED", "INSERTED", "ALREADY_EXISTS_VALID", "REPAIRED_FROM_VALID_SNAPSHOT"})
    return False


def _has_field10_db(db_path: Path | str | None, identity: Mapping[str, Any]) -> bool:
    """Verify this exact child's Field 10 publication in SQLite.

    Field 10 is published after the runtime cache is first written.  Reload
    validation therefore must consult the append-only exact-identity database,
    not require a later in-memory marker to have been serialized into the cache.
    """
    if not db_path:
        return False
    path = Path(db_path)
    if not path.is_file():
        return False
    parent = str(identity.get("parent_run_id") or "")
    child = str(identity.get("child_run_id") or "")
    symbol = str(identity.get("symbol") or "").upper()
    timeframe = str(identity.get("timeframe") or "").upper()
    canonical = str(identity.get("canonical_run_id") or "")
    snapshot_hash = str(identity.get("snapshot_hash") or "")
    completed = str(identity.get("completed_candle") or "")
    if not all((parent, child, symbol, timeframe, canonical, snapshot_hash, completed)):
        return False
    try:
        with sqlite3.connect(str(path), timeout=10) as conn:
            conn.execute("PRAGMA busy_timeout=10000")
            registry = conn.execute(
                """SELECT publication_status FROM child_generation_registry
                   WHERE parent_run_id=? AND child_run_id=? AND symbol=? AND timeframe=?
                     AND canonical_run_id=? AND snapshot_hash=? AND completed_broker_candle=?
                   LIMIT 1""",
                (parent, child, symbol, timeframe, canonical, snapshot_hash, completed),
            ).fetchone()
            if not registry or str(registry[0] or "").upper() not in {
                "COMPLETED", "INSERTED", "ALREADY_EXISTS_VALID", "REPAIRED_FROM_VALID_SNAPSHOT"
            }:
                return False
            integrated = conn.execute(
                """SELECT 1 FROM field10_integrated_evidence_history
                   WHERE parent_run_id=? AND child_run_id=? AND symbol=? AND timeframe=?
                     AND canonical_run_id=? AND snapshot_hash=? AND broker_timestamp=?
                   LIMIT 1""",
                (parent, child, symbol, timeframe, canonical, snapshot_hash, completed),
            ).fetchone()
            return bool(integrated)
    except sqlite3.Error:
        return False


def _has_field10(state: Mapping[str, Any], symbol: str, *, db_path: Path | str | None = None, identity: Mapping[str, Any] | None = None) -> bool:
    frame = state.get("field10_multi_symbol_summary_20260701")
    if isinstance(frame, pd.DataFrame) and not frame.empty and "Symbol" in frame.columns:
        if frame["Symbol"].astype(str).str.upper().eq(symbol).any():
            return True
    if _marker_matches_symbol(state.get("field10_table4_publication_status_20260702"), symbol):
        return True
    if _marker_matches_symbol(state.get("field10_integrated_current_20260702"), symbol):
        return True
    return _has_field10_db(db_path, identity or {})


def identity_from_state(state: Mapping[str, Any]) -> dict[str, str]:
    canonical = _canonical(state)
    child = state.get("multi_symbol_child_run_active_20260701")
    child = child if isinstance(child, Mapping) else {}
    symbol = str(canonical.get("symbol") or state.get("calculation_symbol_20260702") or state.get("active_snapshot_symbol_20260702") or "").upper()
    timeframe = normalize_timeframe(canonical.get("timeframe") or state.get("timeframe") or "H4")
    completed = canonical.get("completed_broker_candle") or canonical.get("broker_candle_time") or canonical.get("latest_completed_candle_time") or canonical.get("completed_candle")
    stamp = pd.to_datetime(completed, errors="coerce", utc=True)
    generation = canonical.get("generation_id") or canonical.get("calculation_generation") or state.get("successful_calculation_generation_20260617")
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "parent_run_id": str(child.get("parent_run_id") or state.get("multi_symbol_parent_run_id_20260701") or ""),
        "child_run_id": str(child.get("child_run_id") or state.get("multi_symbol_current_child_id_20260701") or ""),
        "canonical_run_id": str(canonical.get("run_id") or canonical.get("canonical_calculation_id") or ""),
        "generation_id": str(generation or ""),
        "snapshot_hash": str(canonical.get("snapshot_hash") or canonical.get("source_snapshot_hash") or ""),
        "source_id": str(canonical.get("source_id") or canonical.get("data_source_id") or canonical.get("source_snapshot_hash") or ""),
        "source_signature": str(state.get("last_completed_source_signature_20260628") or canonical.get("data_signature") or ""),
        "completed_candle": "" if pd.isna(stamp) else pd.Timestamp(stamp).isoformat(),
    }


def validate_child_state(
    state: Mapping[str, Any], *, runtime_snapshot_path: Path | str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    identity = identity_from_state(state)
    required_identity = ("symbol", "timeframe", "parent_run_id", "child_run_id", "canonical_run_id", "generation_id", "snapshot_hash", "source_id", "completed_candle")
    missing = [key for key in required_identity if not identity.get(key)]
    frame = _source_frame(state)
    required = required_candles(identity["timeframe"], "higher")
    available = int(len(frame))
    coverage = coverage_metadata(timeframe=identity["timeframe"], available=available, required=required)
    eligibility = calculation_eligibility(timeframe=identity["timeframe"], available=available, required=required)
    spacing = validate_timeframe_spacing(frame, timeframe=identity["timeframe"])
    powerbi = state.get(BUNDLE_KEY) or state.get("powerbi_calibrated_bundle_20260617")
    field2 = validate_powerbi_bundle(powerbi, symbol=identity["symbol"], timeframe=identity["timeframe"])
    receipt = _matching_completion_receipt(state, identity)
    field1 = _has_field1(state) or bool(receipt.get("field1_complete"))
    field2_complete = bool(field2.get("ok")) or bool(receipt.get("field2_complete"))
    field3 = _has_field3(state) or bool(receipt.get("field3_complete"))
    field10 = _has_field10(state, identity["symbol"], db_path=db_path, identity=identity)
    cache_exists = bool(runtime_snapshot_path and Path(runtime_snapshot_path).is_file())
    component_gates = {
        "identity": not bool(missing),
        "history_eligibility": bool(eligibility.get("eligible")),
        "timeframe_spacing": bool(spacing.get("ok")),
        "field1": bool(field1),
        "field2": bool(field2_complete),
        "field3": bool(field3),
        "field10": bool(field10),
        "runtime_snapshot": bool(cache_exists),
    }
    failed_components = [name for name, passed in component_gates.items() if not passed]
    ok = not failed_components
    return {
        "ok": bool(ok),
        "status": "COMPLETED" if ok else "FAILED_VALIDATION",
        "identity": identity,
        "missing_identity": missing,
        "available_candles": available,
        "required_candles": required,
        "minimum_calculation_candles": eligibility.get("minimum_calculation_candles"),
        "validation_mode": eligibility.get("mode"),
        "full_history": eligibility.get("full_history"),
        "coverage": coverage,
        "spacing": spacing,
        "field1_complete": field1,
        "field2_complete": bool(field2_complete),
        "field2_validation": field2,
        "exact_component_receipt": receipt,
        "field3_complete": field3,
        "field10_complete": field10,
        "runtime_snapshot_exists": cache_exists,
        "component_gates": component_gates,
        "failed_components": failed_components,
    }


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publish_complete_child(state: MutableMapping[str, Any], *, runtime_snapshot_path: Path | str, db_path: Path | str) -> dict[str, Any]:
    migration = migrate_timeframe_identity(db_path, create_backup=False)
    path = Path(runtime_snapshot_path)
    validation = validate_child_state(state, runtime_snapshot_path=path, db_path=db_path)
    identity = validation["identity"]
    now = pd.Timestamp.now(tz="UTC").isoformat()
    checksum = _sha256(path) if path.is_file() else ""
    bundle = state.get(BUNDLE_KEY) or state.get("powerbi_calibrated_bundle_20260617") or {}
    bundle_json = _json(dict(bundle)) if isinstance(bundle, Mapping) else "{}"
    bundle_hash = sha256(bundle_json.encode("utf-8")).hexdigest()
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute(
            """INSERT OR REPLACE INTO child_snapshot_publication_20260706(
                parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,generation_id,snapshot_hash,
                source_id,source_signature,completed_candle,runtime_snapshot_path,runtime_snapshot_sha256,
                available_candles,required_candles,coverage_percent,field1_complete,field2_complete,
                field3_complete,field10_complete,reload_validation_passed,publication_status,validation_json,
                created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                identity.get("parent_run_id"), identity.get("child_run_id"), identity.get("symbol"), identity.get("timeframe"),
                identity.get("canonical_run_id"), identity.get("generation_id"), identity.get("snapshot_hash"), identity.get("source_id"),
                identity.get("source_signature"), identity.get("completed_candle"), str(path.resolve()), checksum,
                validation.get("available_candles", 0), validation.get("required_candles", 0),
                validation.get("coverage", {}).get("Coverage Percent", 0.0), int(validation.get("field1_complete", False)),
                int(validation.get("field2_complete", False)), int(validation.get("field3_complete", False)),
                int(validation.get("field10_complete", False)), 0,
                ("PENDING_RELOAD" if validation.get("ok") else "FAILED_VALIDATION"), _json(validation), now, now,
            ),
        )
        if isinstance(bundle, Mapping) and bundle:
            conn.execute(
                """INSERT OR REPLACE INTO field2_powerbi_publication_20260706(
                    symbol,timeframe,completed_candle,parent_run_id,child_run_id,canonical_run_id,generation_id,
                    snapshot_hash,source_id,source_signature,publication_type,calibration_status,bundle_json,bundle_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    identity.get("symbol"), identity.get("timeframe"), identity.get("completed_candle"), identity.get("parent_run_id"),
                    identity.get("child_run_id"), identity.get("canonical_run_id"), identity.get("generation_id"), identity.get("snapshot_hash"),
                    identity.get("source_id"), identity.get("source_signature"), str(bundle.get("publication_type") or "UNKNOWN"),
                    str(bundle.get("calibration_status") or "UNKNOWN"), bundle_json, bundle_hash, now,
                ),
            )
        conn.commit()
    return {"ok": bool(validation.get("ok")), "status": ("PENDING_RELOAD" if validation.get("ok") else "FAILED_VALIDATION"), "validation": validation, "migration": migration, "runtime_snapshot_sha256": checksum}


def latest_publication(*, symbol: Any, timeframe: Any, db_path: Path | str, completed_only: bool = True) -> dict[str, Any]:
    tf = normalize_timeframe(timeframe)
    where = "AND publication_status='COMPLETED'" if completed_only else ""
    with sqlite3.connect(str(db_path), timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            f"""SELECT * FROM child_snapshot_publication_20260706
                WHERE UPPER(symbol)=? AND UPPER(timeframe)=? {where}
                ORDER BY completed_candle DESC,updated_at DESC LIMIT 1""",
            (str(symbol).upper(), tf),
        ).fetchone()
    return dict(row) if row else {}


def mark_reload_validation(*, publication: Mapping[str, Any], db_path: Path | str, passed: bool, detail: Mapping[str, Any]) -> None:
    with sqlite3.connect(str(db_path), timeout=10) as conn:
        conn.execute(
            """UPDATE child_snapshot_publication_20260706 SET reload_validation_passed=?,publication_status=?,validation_json=?,updated_at=?
               WHERE symbol=? AND timeframe=? AND completed_candle=? AND parent_run_id=? AND child_run_id=?
                 AND canonical_run_id=? AND generation_id=? AND snapshot_hash=?""",
            (
                int(passed), ("COMPLETED" if passed else "FAILED_VALIDATION"), _json(dict(detail)), pd.Timestamp.now(tz="UTC").isoformat(),
                publication.get("symbol"), publication.get("timeframe"), publication.get("completed_candle"),
                publication.get("parent_run_id"), publication.get("child_run_id"), publication.get("canonical_run_id"),
                publication.get("generation_id"), publication.get("snapshot_hash"),
            ),
        )
        conn.commit()


__all__ = ["VERSION", "identity_from_state", "validate_child_state", "publish_complete_child", "latest_publication", "mark_reload_validation"]

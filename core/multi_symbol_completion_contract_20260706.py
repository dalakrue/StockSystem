"""Strict completion contract for multi-symbol Settings runs.

A run is successful only when every selected symbol has a validated child
publication and the user-visible Field 10 result contains one usable row for
every selected symbol.  The module is read-only with respect to calculation
logic; it validates persisted outputs and records an additive audit report.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any
from datetime import datetime, timezone
import json
import sqlite3
from hashlib import sha256

import pandas as pd

VERSION = "multi-symbol-completion-contract-20260707-v2"
REPORT_KEY = "multi_symbol_completion_contract_20260706"

_FAILURE_TOKENS = (
    "NO VALIDATED",
    "INSUFFICIENT",
    "LOCAL HISTORY REQUIRED",
    "BELOW MINIMUM",
    "FAILED",
    "UNAVAILABLE",
    "MISSING",
    "FALLBACK L7",
)


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "").replace(" ", "")


def _selected(values: Sequence[Any] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        symbol = _normalize_symbol(value)
        if symbol and symbol not in out:
            out.append(symbol)
    return out


def _effective_status(item: Mapping[str, Any] | None) -> str:
    item = item if isinstance(item, Mapping) else {}
    return str(item.get("state") or item.get("publication_status") or item.get("status") or "WAITING").upper()


def _bad_text(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    text = str(value).strip().upper()
    return not text or any(token in text for token in _FAILURE_TOKENS)


def _usable_field10_rows(frame: pd.DataFrame, selected_symbols: Sequence[str]) -> tuple[dict[str, bool], dict[str, list[str]]]:
    selected = _selected(selected_symbols)
    usable = {symbol: False for symbol in selected}
    reasons: dict[str, list[str]] = {symbol: [] for symbol in selected}
    if not isinstance(frame, pd.DataFrame) or frame.empty or "Symbol" not in frame.columns:
        for symbol in selected:
            reasons[symbol].append("No Field 10 row was published")
        return usable, reasons

    normalized = frame.copy()
    normalized["__symbol"] = normalized["Symbol"].map(_normalize_symbol)
    critical_groups = {
        "rank": ("Rank", "Daily Rank", "Eligible Rank", "Comparative Rank"),
        "direction": ("Higher-Standard Bias", "Higher Standard Bias", "Stable Daily Bias", "Less-Risky Bias", "Final Action"),
        "quality": ("Data Quality", "Data Quality Grade", "Quality", "Validation Status", "Snapshot Status"),
    }

    for symbol in selected:
        rows = normalized.loc[normalized["__symbol"].eq(symbol)]
        if rows.empty:
            reasons[symbol].append("Selected symbol is absent from Field 10")
            continue
        if len(rows) != 1:
            reasons[symbol].append(f"Expected exactly one Field 10 row, found {len(rows)}")
            continue
        row = rows.iloc[0]
        symbol_reasons: list[str] = []
        for label, candidates in critical_groups.items():
            present = [name for name in candidates if name in rows.columns]
            if not present:
                symbol_reasons.append(f"{label} column is absent")
                continue
            values = [row.get(name) for name in present]
            if all(_bad_text(value) for value in values):
                symbol_reasons.append(f"{label} is missing or unvalidated")
        reliability_columns = [name for name in ("Reliability Score", "Higher Reliability", "Reliability", "Trust Score", "Data Quality Score") if name in rows.columns]
        if reliability_columns and all(_bad_text(row.get(name)) for name in reliability_columns):
            symbol_reasons.append("reliability is explicitly unavailable or insufficient")
        for status_column in ("Data Status", "Snapshot Status", "Publication Status", "Calculation Status", "Status"):
            if status_column in rows.columns and _bad_text(row.get(status_column)):
                symbol_reasons.append(f"{status_column}: {row.get(status_column)}")
        reasons[symbol] = list(dict.fromkeys(symbol_reasons))
        usable[symbol] = not reasons[symbol]
    return usable, reasons


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _database_path():
    from core.multi_symbol_field10_20260701 import DB_PATH
    return DB_PATH


def _persist_completion_result(report: Mapping[str, Any], frame: pd.DataFrame) -> None:
    """Persist visible completion evidence at the explicit run boundary."""
    from core.data.deployment_migrations_20260705 import migrate_deployment_schema

    path = _database_path()
    migrate_deployment_schema(path)
    parent_run_id = str(report.get("parent_run_id") or "").strip()
    if not parent_run_id:
        return
    now = datetime.now(timezone.utc).isoformat()
    failure = {
        "child_failures": report.get("child_failures") or {},
        "missing_saved_symbol_caches": report.get("missing_saved_symbol_caches") or [],
        "missing_or_invalid_field10_symbols": report.get("missing_or_invalid_field10_symbols") or [],
        "field10_failure_reasons": report.get("field10_failure_reasons") or {},
    }
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO multi_symbol_completion_audit_20260706(
                   parent_run_id,status,selected_symbols_json,completed_child_count,
                   field10_row_count,failure_json,report_json,created_at
               ) VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(parent_run_id) DO UPDATE SET
                   status=excluded.status,
                   selected_symbols_json=excluded.selected_symbols_json,
                   completed_child_count=excluded.completed_child_count,
                   field10_row_count=excluded.field10_row_count,
                   failure_json=excluded.failure_json,
                   report_json=excluded.report_json,
                   created_at=excluded.created_at""",
            (
                parent_run_id,
                str(report.get("status") or "UNKNOWN"),
                json.dumps(_jsonable(report.get("selected_symbols") or []), ensure_ascii=False),
                int(report.get("completed_child_count") or 0),
                int(report.get("field10_row_count") or 0),
                json.dumps(_jsonable(failure), ensure_ascii=False),
                json.dumps(_jsonable(report), ensure_ascii=False),
                now,
            ),
        )
        if report.get("ok") and isinstance(frame, pd.DataFrame) and not frame.empty and "Symbol" in frame.columns:
            conn.execute("DELETE FROM field10_latest_run_result_20260706 WHERE parent_run_id=?", (parent_run_id,))
            rank_column = next((name for name in ("Rank", "Final Rank", "Daily Rank", "Comparative Rank") if name in frame.columns), None)
            for _, source_row in frame.iterrows():
                record = _jsonable(source_row.to_dict())
                symbol = _normalize_symbol(record.get("Symbol"))
                if not symbol:
                    continue
                rank_value = None
                if rank_column:
                    try:
                        rank_value = float(record.get(rank_column))
                    except Exception:
                        rank_value = None
                conn.execute(
                    """INSERT OR REPLACE INTO field10_latest_run_result_20260706(
                           parent_run_id,symbol,rank_value,result_json,validation_status,created_at
                       ) VALUES(?,?,?,?,?,?)""",
                    (
                        parent_run_id,
                        symbol,
                        rank_value,
                        json.dumps(record, ensure_ascii=False, default=str),
                        "PASS",
                        now,
                    ),
                )

            selected = _selected(report.get("selected_symbols") or [])
            timeframe = str(report.get("timeframe") or "H4").strip().upper() or "H4"
            generation_raw = report.get("generation")
            try:
                generation = int(generation_raw)
            except Exception:
                generation = int(conn.execute("SELECT COALESCE(MAX(generation),0)+1 FROM canonical_runs").fetchone()[0])
            depth = str(report.get("calculation_depth") or "UNKNOWN").upper()
            main_symbol = _normalize_symbol(report.get("main_symbol") or (selected[0] if selected else ""))
            universe_hash = sha256((timeframe + "|" + "|".join(selected)).encode("utf-8")).hexdigest()
            row_checksums: list[str] = []
            for _, source_row in frame.iterrows():
                record = _jsonable(source_row.to_dict())
                symbol = _normalize_symbol(record.get("Symbol"))
                if symbol not in selected:
                    continue
                row_timeframe = str(record.get("Timeframe") or timeframe).strip().upper()
                latest = next((record.get(name) for name in ("Latest Completed Broker Candle", "Completed Broker Candle", "Completed Candle", "Time") if record.get(name) not in (None, "")), now)
                payload_json = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
                row_checksum = sha256(f"{parent_run_id}|{generation}|{symbol}|{row_timeframe}|{payload_json}".encode("utf-8")).hexdigest()
                row_checksums.append(row_checksum)
                conn.execute(
                    """INSERT OR REPLACE INTO field10_symbol_rows(
                           run_id,generation,symbol,timeframe,latest_completed_candle,
                           publication_status,row_payload_json,checksum,created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (parent_run_id,generation,symbol,row_timeframe,str(latest),"PUBLISHED",payload_json,row_checksum,now),
                )
                quality = {
                    "data_quality": record.get("Data Quality Grade") or record.get("Data Quality"),
                    "sample_count": record.get("Sample Count") or record.get("Genuine Candle Rows"),
                    "optional_evidence": record.get("Optional Evidence Availability"),
                }
                conn.execute(
                    """INSERT OR REPLACE INTO symbol_calculation_snapshots(
                           run_id,generation,symbol,timeframe,latest_completed_candle,
                           calculation_depth,status,field1_payload_reference,field2_payload_reference,
                           field3_payload_reference,field10_payload_reference,quality_metadata_json,created_at,checksum
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (parent_run_id,generation,symbol,row_timeframe,str(latest),depth,"PUBLISHED",None,None,
                     f"field3:{row_checksum}",f"field10:{row_checksum}",json.dumps(quality,sort_keys=True,default=str),now,row_checksum),
                )
            run_checksum = sha256((parent_run_id + "|" + str(generation) + "|" + universe_hash + "|" + "|".join(sorted(row_checksums))).encode("utf-8")).hexdigest()
            conn.execute(
                """INSERT OR REPLACE INTO canonical_runs(
                       run_id,generation,main_symbol,timeframe,selected_universe_hash,
                       configured_symbols_json,loaded_symbols_json,completed_symbols_json,failed_symbols_json,
                       calculation_depth,publication_status,started_at,completed_at,checksum,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (parent_run_id,generation,main_symbol,timeframe,universe_hash,json.dumps(selected),json.dumps(selected),
                 json.dumps(selected),json.dumps([]),depth,"PUBLISHED",str(report.get("started_at") or now),now,run_checksum,2026070704),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_persisted_complete_run(parent_run_id: str | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load the latest strict-complete Field 10 universe from SQLite."""
    path = _database_path()
    if not path.exists():
        return pd.DataFrame(), {}
    conn = sqlite3.connect(str(path), timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        if parent_run_id:
            audit = conn.execute(
                "SELECT * FROM multi_symbol_completion_audit_20260706 WHERE parent_run_id=? AND status='COMPLETE_ALL_SELECTED_SYMBOLS'",
                (str(parent_run_id),),
            ).fetchone()
        else:
            audit = conn.execute(
                "SELECT * FROM multi_symbol_completion_audit_20260706 WHERE status='COMPLETE_ALL_SELECTED_SYMBOLS' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        if audit is None:
            return pd.DataFrame(), {}
        run_id = str(audit["parent_run_id"])
        rows = conn.execute(
            "SELECT result_json FROM field10_latest_run_result_20260706 WHERE parent_run_id=? ORDER BY rank_value IS NULL, rank_value, symbol",
            (run_id,),
        ).fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            try:
                value = json.loads(row["result_json"])
                if isinstance(value, dict):
                    records.append(value)
            except Exception:
                continue
        report = json.loads(audit["report_json"]) if audit["report_json"] else {}
        return pd.DataFrame(records), report if isinstance(report, dict) else {}
    except sqlite3.Error:
        return pd.DataFrame(), {}
    finally:
        conn.close()


def validate_multi_symbol_completion(
    state: MutableMapping[str, Any] | Mapping[str, Any],
    manifest: Mapping[str, Any] | None = None,
    *,
    selected_symbols: Sequence[Any] | None = None,
    field10_frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Validate all child publications and the visible Field 10 result universe."""
    manifest = dict(manifest or {})
    selected = _selected(selected_symbols or manifest.get("selected_symbols") or state.get("multi_symbol_selected_20260701") or [])
    status_map = manifest.get("symbol_status") if isinstance(manifest.get("symbol_status"), Mapping) else {}

    child_status: dict[str, str] = {}
    child_failures: dict[str, str] = {}
    for symbol in selected:
        status = _effective_status(status_map.get(symbol) if isinstance(status_map, Mapping) else {})
        child_status[symbol] = status
        if status != "COMPLETED":
            child_failures[symbol] = status

    cache_ready: set[str] = set()
    try:
        from core.multi_symbol_field10_20260701 import available_saved_symbols
        cache_ready = set(_selected(available_saved_symbols(selected)))
    except Exception:
        cache_ready = set()
    missing_cache = [symbol for symbol in selected if symbol not in cache_ready]

    source_frame = field10_frame
    snapshot_metadata: dict[str, Any] = {}
    if not isinstance(source_frame, pd.DataFrame):
        try:
            from core.field10_daily_snapshot_contract_20260702 import load_current_daily_snapshot
            bundle = load_current_daily_snapshot()
            current = bundle.get("current")
            snapshot_metadata = dict(bundle.get("metadata") or {})
            source_frame = current if isinstance(current, pd.DataFrame) else pd.DataFrame()
        except Exception as exc:
            source_frame = pd.DataFrame()
            snapshot_metadata = {"load_error": f"{type(exc).__name__}: {exc}"}

    # The current run summary is the authoritative source for the run that just
    # finished. A same-day locked snapshot may belong to an earlier symbol
    # universe or parent run, so row count alone is not enough to prove that it
    # represents the calculation whose progress bar is being completed now.
    expected_parent_run_id = str(manifest.get("parent_run_id") or "").strip()
    snapshot_parent_run_id = str(
        snapshot_metadata.get("parent_run_id")
        or (snapshot_metadata.get("metadata") or {}).get("parent_run_id")
        or ""
    ).strip()
    source_symbols = (
        {_normalize_symbol(v) for v in source_frame.get("Symbol", pd.Series(dtype=object)).tolist()}
        if isinstance(source_frame, pd.DataFrame)
        else set()
    )
    snapshot_run_mismatch = bool(
        expected_parent_run_id
        and snapshot_parent_run_id
        and snapshot_parent_run_id != expected_parent_run_id
    )
    snapshot_metadata["expected_parent_run_id"] = expected_parent_run_id
    snapshot_metadata["snapshot_parent_run_id"] = snapshot_parent_run_id
    snapshot_metadata["snapshot_run_matches_current"] = not snapshot_run_mismatch
    try:
        if (
            not isinstance(source_frame, pd.DataFrame)
            or set(selected) - source_symbols
            or snapshot_run_mismatch
        ):
            from core.multi_symbol_field10_20260701 import load_field10_tables
            tables = load_field10_tables(
                state if isinstance(state, MutableMapping) else dict(state),
                parent_run_id=str(manifest.get("parent_run_id") or ""),
                symbol=selected[0] if selected else None,
            )
            summary = tables.get("summary")
            if isinstance(summary, pd.DataFrame) and not summary.empty:
                source_frame = summary.copy()
                snapshot_metadata = {**snapshot_metadata, "display_source": "LATEST_RUN_SUMMARY"}
                try:
                    from core.system_continuous_validation_20260702 import build_field3_higher_standard_multi_symbol_table
                    field3, field3_report = build_field3_higher_standard_multi_symbol_table(
                        state, selected_symbols=selected, parent_run_id=str(manifest.get("parent_run_id") or "")
                    )
                    if isinstance(field3, pd.DataFrame) and not field3.empty:
                        left = source_frame.copy()
                        left["Symbol"] = left["Symbol"].map(_normalize_symbol)
                        right = field3.copy()
                        right["Symbol"] = right["Symbol"].map(_normalize_symbol)
                        prefer = [
                            "Symbol", "Rank", "Comparative Score", "Higher Standard Regime",
                            "Higher-Standard Bias", "Less-Risky Bias", "Reliability",
                            "Regime Probability", "Transition Risk 3H", "Transition Risk 6H",
                            "Transition Risk 24H", "Expected Return 12H (%)",
                            "Expected Return 24H (%)", "Expected Return 36H (%)",
                            "Sample Count", "Data Quality", "Evidence Source",
                            "Snapshot Status", "Completed Broker Candle",
                        ]
                        right = right[[column for column in prefer if column in right.columns]]
                        duplicate = [column for column in right.columns if column != "Symbol" and column in left.columns]
                        left = left.drop(columns=duplicate, errors="ignore")
                        source_frame = left.merge(right, on="Symbol", how="left")
                        if "Reliability" in source_frame.columns and "Reliability Score" not in source_frame.columns:
                            source_frame["Reliability Score"] = source_frame["Reliability"]
                        source_frame["Data Status"] = source_frame.get("Status", "COMPLETED")
                        snapshot_metadata["field3_merge"] = field3_report
                except Exception as merge_exc:
                    snapshot_metadata["field3_merge_error"] = f"{type(merge_exc).__name__}: {merge_exc}"
    except Exception as exc:
        snapshot_metadata["summary_load_error"] = f"{type(exc).__name__}: {exc}"

    expected_timeframe = str(manifest.get("timeframe") or state.get("timeframe") or state.get("selected_timeframe") or "H4").strip().upper()
    timeframe_mismatches: dict[str, str] = {}
    duplicate_symbols: list[str] = []
    if isinstance(source_frame, pd.DataFrame) and not source_frame.empty and "Symbol" in source_frame.columns:
        normalized_symbols = source_frame["Symbol"].map(_normalize_symbol)
        duplicate_symbols = sorted({symbol for symbol in selected if int(normalized_symbols.eq(symbol).sum()) > 1})
        timeframe_column = next((name for name in ("Timeframe", "Canonical Timeframe", "Selected Timeframe") if name in source_frame.columns), None)
        if timeframe_column:
            for symbol in selected:
                rows = source_frame.loc[normalized_symbols.eq(symbol)]
                if rows.empty:
                    continue
                observed = {str(value).strip().upper() for value in rows[timeframe_column].dropna().tolist() if str(value).strip()}
                if observed and observed != {expected_timeframe}:
                    timeframe_mismatches[symbol] = ",".join(sorted(observed))

    usable, row_reasons = _usable_field10_rows(source_frame if isinstance(source_frame, pd.DataFrame) else pd.DataFrame(), selected)
    for symbol in duplicate_symbols:
        usable[symbol] = False
        row_reasons.setdefault(symbol, []).append("Duplicate Field 10 rows for exact symbol")
    for symbol, observed in timeframe_mismatches.items():
        usable[symbol] = False
        row_reasons.setdefault(symbol, []).append(f"TIMEFRAME_IDENTITY_MISMATCH: expected {expected_timeframe}, observed {observed}")
    missing_or_invalid_rows = [symbol for symbol in selected if not usable.get(symbol)]
    row_symbols = (
        [_normalize_symbol(value) for value in source_frame["Symbol"].tolist()]
        if isinstance(source_frame, pd.DataFrame) and not source_frame.empty and "Symbol" in source_frame.columns
        else []
    )

    ok = bool(selected) and not child_failures and not missing_cache and not missing_or_invalid_rows
    if ok and isinstance(source_frame, pd.DataFrame):
        try:
            state["field10_latest_complete_run_table_20260706"] = source_frame.copy()  # type: ignore[index]
            state["field10_latest_complete_run_id_20260706"] = str(manifest.get("parent_run_id") or "")  # type: ignore[index]
        except Exception:
            pass

    report = {
        "ok": ok,
        "parent_run_id": str(manifest.get("parent_run_id") or ""),
        "status": "COMPLETE_ALL_SELECTED_SYMBOLS" if ok else "INCOMPLETE_SELECTED_SYMBOL_RESULTS",
        "selected_symbols": selected,
        "selected_count": len(selected),
        "completed_child_count": sum(status == "COMPLETED" for status in child_status.values()),
        "field10_row_count": len(set(row_symbols) & set(selected)),
        "field10_symbols": [symbol for symbol in selected if symbol in row_symbols],
        "child_status": child_status,
        "child_failures": child_failures,
        "missing_saved_symbol_caches": missing_cache,
        "missing_or_invalid_field10_symbols": missing_or_invalid_rows,
        "field10_failure_reasons": {symbol: row_reasons.get(symbol, []) for symbol in missing_or_invalid_rows},
        "snapshot_metadata": snapshot_metadata,
        "success_message_allowed": ok,
        "open_lunch_allowed": ok,
        "progress_percent": 100.0 if ok else 99.0,
        "timeframe": expected_timeframe,
        "generation": manifest.get("generation") or manifest.get("publication_generation"),
        "calculation_depth": manifest.get("calculation_depth") or manifest.get("scope") or state.get("settings_calculation_scope_20260625"),
        "main_symbol": manifest.get("main_symbol") or state.get("multi_symbol_main_symbol_20260702") or (selected[0] if selected else ""),
        "started_at": manifest.get("started_at"),
        "duplicate_field10_symbols": duplicate_symbols,
        "timeframe_mismatches": timeframe_mismatches,
        "version": VERSION,
    }
    report["database_persistence"] = "NOT_REQUESTED_READ_ONLY_VALIDATION"
    try:
        state[REPORT_KEY] = report  # type: ignore[index]
    except Exception:
        pass
    return report


def apply_completion_contract(
    state: MutableMapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Return a manifest whose success state reflects the strict UI contract."""
    out = dict(manifest)
    report = validate_multi_symbol_completion(state, out)
    if report.get("ok"):
        try:
            frame = state.get("field10_latest_complete_run_table_20260706")
            _persist_completion_result(report, frame if isinstance(frame, pd.DataFrame) else pd.DataFrame())
            report["database_persistence"] = "SAVED"
        except Exception as persist_exc:
            report["database_persistence"] = "FAILED"
            report["database_persistence_error"] = f"{type(persist_exc).__name__}: {persist_exc}"
            report["ok"] = False
            report["status"] = "INCOMPLETE_PERSISTENCE"
            report["success_message_allowed"] = False
            report["open_lunch_allowed"] = False
            report["progress_percent"] = 99.0
    out["completion_contract"] = report
    if not report.get("ok"):
        out["ok"] = False
        out["status"] = "PARTIAL"
        out["failed_symbols"] = max(
            int(out.get("failed_symbols") or 0),
            len(report.get("missing_or_invalid_field10_symbols") or []),
            len(report.get("child_failures") or {}),
        )
        out["completion_failure_reason"] = (
            "Field 10 does not yet contain validated result data for every selected symbol. "
            "The run remains below 100% and Lunch is not opened."
        )
    else:
        out["ok"] = True
        out["status"] = "COMPLETED"
        out["completed_symbols"] = len(report.get("selected_symbols") or [])
        out["failed_symbols"] = 0
    state[REPORT_KEY] = report
    return out


__all__ = [
    "VERSION", "REPORT_KEY", "validate_multi_symbol_completion", "apply_completion_contract",
    "load_persisted_complete_run",
]

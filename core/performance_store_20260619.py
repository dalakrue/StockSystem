"""Bounded SQLite-backed display/history store for the active canonical run.

The calculation engine remains unchanged.  This layer persists large historical
DataFrames after a successful publication and lets renderers query only the
columns/rows they display.  SQLite is used because it is in the Python standard
library and works on Streamlit Cloud without a new binary dependency.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

import pandas as pd

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "adx_runtime_store.sqlite3"
FRAME_REFS_KEY = "disk_backed_frame_refs_20260619"
TIMINGS_KEY = "performance_timings_20260619"
STORE_SCHEMA_VERSION = "1.0.0"
MAX_GENERATIONS = 2
MOBILE_ROWS = 48
DESKTOP_ROWS = 100


NESTED_HISTORY_ROOT_KEYS = (
    "full_metric_authority_20260618", "lunch_metric_result_cache",
    "full_metric_result_cache_20260618", "research_pack_20260612",
    "final_synced_research_merge_pack_20260612", "final_merged_intelligence_pack_20260612",
    "dv_pp_base_result", "powerbi_calibrated_bundle_20260617",
)

HISTORY_KEYS = (
    "full_metric_history_df_20260618",
    "canonical_priority_table_20260617",
    "adx_hourly_priority_calibrated_20260615",
    "three_center_priority_sorted_20260614",
    "reliability_dynamic_priority_table_20260614",
    "lunch_quick_decision_merged_table_20260617",
    "finder_readonly_priority_table_20260618",
    "full_metric_regime_history_df",
    "major_regime_history_df",
    "dv_pp_projection_history",
    "dv_pp_bt_hist",
    "dv_pp_regime_hist",
    "home_reversal_25d_scan",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _quote(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _table_name(calculation_id: str, logical_key: str) -> str:
    digest = hashlib.sha256(f"{calculation_id}|{logical_key}".encode("utf-8", errors="ignore")).hexdigest()[:24]
    return f"f_{digest}"


def _connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA busy_timeout=30000")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS frame_manifest (
            calculation_id TEXT NOT NULL,
            logical_key TEXT NOT NULL,
            table_name TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            columns_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (calculation_id, logical_key)
        );
        CREATE INDEX IF NOT EXISTS idx_frame_manifest_calc ON frame_manifest(calculation_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS canonical_summary (
            calculation_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            fact_pack_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ai_conversation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            calculation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ai_conversation_calc ON ai_conversation(calculation_id, id DESC);
        """
    )
    conn.commit()


@contextmanager
def timed(state: MutableMapping[str, Any] | None, name: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        if state is not None:
            record_timing(state, name, time.perf_counter() - start)


def record_timing(state: MutableMapping[str, Any], name: str, seconds: float, **extra: Any) -> None:
    rows = state.get(TIMINGS_KEY)
    if not isinstance(rows, list):
        rows = []
    rows.append({"name": str(name), "seconds": round(float(seconds), 6), "at": _utc_now(), **extra})
    state[TIMINGS_KEY] = rows[-80:]


def _sql_safe_frame(frame: pd.DataFrame) -> pd.DataFrame:
    # A single shallow copy is required because to_sql may coerce object values.
    work = frame.copy(deep=False)
    for column in work.columns:
        series = work[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            work[column] = pd.to_datetime(series, errors="coerce", utc=True).astype("string")
        elif series.dtype == "object":
            sample = series.dropna().head(20)
            if any(isinstance(v, (dict, list, tuple, set)) for v in sample):
                work[column] = series.map(lambda v: json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list, tuple, set)) else v)
    return work


def persist_frame(
    calculation_id: str,
    logical_key: str,
    frame: pd.DataFrame,
    *,
    db_path: Path | str = DB_PATH,
) -> dict[str, Any]:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    table = _table_name(calculation_id, logical_key)
    work = _sql_safe_frame(frame)
    columns = [str(c) for c in work.columns]
    conn = _connect(db_path)
    try:
        with conn:
            work.to_sql(table, conn, if_exists="replace", index=False, method="multi", chunksize=500)
            conn.execute(
                "INSERT OR REPLACE INTO frame_manifest(calculation_id, logical_key, table_name, row_count, columns_json, created_at) VALUES(?,?,?,?,?,?)",
                (str(calculation_id), str(logical_key), table, int(len(work)), json.dumps(columns), _utc_now()),
            )
        return {"calculation_id": calculation_id, "logical_key": logical_key, "table_name": table, "rows": int(len(work)), "columns": columns}
    finally:
        conn.close()


def frame_manifest(calculation_id: str, logical_key: str, *, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT table_name,row_count,columns_json,created_at FROM frame_manifest WHERE calculation_id=? AND logical_key=?",
            (str(calculation_id), str(logical_key)),
        ).fetchone()
        if not row:
            return {}
        return {"table_name": row[0], "row_count": int(row[1]), "columns": json.loads(row[2]), "created_at": row[3]}
    finally:
        conn.close()


def query_frame(
    calculation_id: str,
    logical_key: str,
    *,
    columns: Sequence[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
    order_by: str | None = None,
    descending: bool = True,
    where_equals: Mapping[str, Any] | None = None,
    date_equals: Mapping[str, Any] | None = None,
    db_path: Path | str = DB_PATH,
) -> pd.DataFrame:
    manifest = frame_manifest(calculation_id, logical_key, db_path=db_path)
    if not manifest:
        return pd.DataFrame()
    available = [str(c) for c in manifest.get("columns", [])]
    selected = [str(c) for c in (columns or available) if str(c) in available]
    if not selected:
        return pd.DataFrame()
    select_sql = ",".join(_quote(c) for c in selected)
    sql = f"SELECT {select_sql} FROM {_quote(manifest['table_name'])}"
    params: list[Any] = []
    clauses: list[str] = []
    for column, value in dict(where_equals or {}).items():
        if str(column) in available:
            clauses.append(f"CAST({_quote(str(column))} AS TEXT) = ?")
            params.append(str(value))
    for column, value in dict(date_equals or {}).items():
        if str(column) in available:
            clauses.append(f"substr(CAST({_quote(str(column))} AS TEXT),1,10) = ?")
            params.append(str(value)[:10])
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    if order_by and order_by in available:
        sql += f" ORDER BY {_quote(order_by)} {'DESC' if descending else 'ASC'}"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([max(0, int(limit)), max(0, int(offset))])
    conn = _connect(db_path)
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def export_frame(calculation_id: str, logical_key: str, *, db_path: Path | str = DB_PATH) -> pd.DataFrame:
    """Full export query.  Normal render paths must call query_frame with LIMIT."""
    return query_frame(calculation_id, logical_key, db_path=db_path)


def persist_summary(
    calculation_id: str,
    summary: Mapping[str, Any],
    fact_pack: Mapping[str, Any],
    *,
    db_path: Path | str = DB_PATH,
) -> None:
    conn = _connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO canonical_summary(calculation_id,payload_json,fact_pack_json,created_at) VALUES(?,?,?,?)",
                (
                    str(calculation_id),
                    json.dumps(dict(summary), ensure_ascii=False, default=str, separators=(",", ":")),
                    json.dumps(dict(fact_pack), ensure_ascii=False, default=str, separators=(",", ":")),
                    _utc_now(),
                ),
            )
    finally:
        conn.close()


def load_summary(calculation_id: str, *, db_path: Path | str = DB_PATH) -> tuple[dict[str, Any], dict[str, Any]]:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT payload_json,fact_pack_json FROM canonical_summary WHERE calculation_id=?", (str(calculation_id),)).fetchone()
        if not row:
            return {}, {}
        return json.loads(row[0]), json.loads(row[1])
    finally:
        conn.close()


def load_latest_summary(*, db_path: Path | str = DB_PATH) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load the newest persisted compact summary/fact pack.

    This is a read-only recovery path for the AI Assistant after a Streamlit
    rerun, connector disconnect, or rejected new generation. It never runs the
    protected calculator.
    """
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT payload_json,fact_pack_json FROM canonical_summary ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return {}, {}
        return json.loads(row[0]), json.loads(row[1])
    except Exception:
        return {}, {}
    finally:
        conn.close()


def append_ai_message(calculation_id: str, role: str, content: str, metadata: Mapping[str, Any] | None = None, *, db_path: Path | str = DB_PATH) -> None:
    conn = _connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO ai_conversation(calculation_id,role,content,metadata_json,created_at) VALUES(?,?,?,?,?)",
                (str(calculation_id), str(role), str(content), json.dumps(dict(metadata or {}), ensure_ascii=False, default=str), _utc_now()),
            )
    finally:
        conn.close()


def load_ai_messages(calculation_id: str, *, limit: int = 20, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT role,content,metadata_json,created_at FROM ai_conversation WHERE calculation_id=? ORDER BY id DESC LIMIT ?",
            (str(calculation_id), max(1, int(limit))),
        ).fetchall()
        result = []
        for role, content, metadata_json, created_at in reversed(rows):
            try:
                metadata = json.loads(metadata_json)
            except Exception:
                metadata = {}
            result.append({"role": role, "content": content, "meta": metadata, "created_at": created_at})
        return result
    finally:
        conn.close()


def _time_column(frame: pd.DataFrame) -> str | None:
    aliases = ("Time", "time", "Datetime", "Date", "candle time", "latest_completed_candle_time", "End")
    return next((name for name in aliases if name in frame.columns), None)


def compact_display_frame(frame: pd.DataFrame, *, limit: int = DESKTOP_ROWS) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    time_col = _time_column(frame)
    if time_col:
        parsed = pd.to_datetime(frame[time_col], errors="coerce", utc=True)
        order = parsed.sort_values(ascending=False, kind="stable").index[:limit]
        return frame.loc[order].reset_index(drop=True)
    return frame.head(limit).reset_index(drop=True)


def spool_history_frames(
    state: MutableMapping[str, Any],
    calculation_id: str,
    *,
    phone_mode: bool = False,
    db_path: Path | str = DB_PATH,
) -> dict[str, Any]:
    refs = state.get(FRAME_REFS_KEY)
    if not isinstance(refs, dict):
        refs = {}
    results: dict[str, Any] = {}
    seen_objects: dict[int, dict[str, Any]] = {}
    memory_limit = MOBILE_ROWS if phone_mode else DESKTOP_ROWS
    for key in HISTORY_KEYS:
        value = state.get(key)
        if not isinstance(value, pd.DataFrame) or value.empty:
            continue
        object_id = id(value)
        if object_id in seen_objects:
            original = dict(seen_objects[object_id])
            conn = _connect(db_path)
            try:
                with conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO frame_manifest(calculation_id,logical_key,table_name,row_count,columns_json,created_at) VALUES(?,?,?,?,?,?)",
                        (str(calculation_id), str(key), original["table_name"], int(original["rows"]), json.dumps(original["columns"]), _utc_now()),
                    )
            finally:
                conn.close()
            ref = {**original, "logical_key": key}
            refs[key] = ref
            state[key] = compact_display_frame(value, limit=memory_limit)
            results[key] = {**ref, "deduplicated_alias": True}
            continue
        ref = persist_frame(calculation_id, key, value, db_path=db_path)
        refs[key] = ref
        seen_objects[object_id] = ref
        # Keep only a display page in session; full history remains in SQLite.
        state[key] = compact_display_frame(value, limit=memory_limit)
        results[key] = ref
    state[FRAME_REFS_KEY] = refs
    _evict_old_generations(calculation_id, db_path=db_path)
    return results



def spool_nested_history_frames(
    state: MutableMapping[str, Any], calculation_id: str, *, phone_mode: bool = False,
    db_path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Persist and compact large DataFrames nested in known historical containers."""
    limit = MOBILE_ROWS if phone_mode else DESKTOP_ROWS
    results: dict[str, Any] = {}
    seen: set[int] = set()

    def walk(value: Any, path: str, depth: int = 0) -> Any:
        if depth > 6:
            return value
        if isinstance(value, pd.DataFrame):
            if value.empty or len(value) <= limit:
                return value
            oid = id(value)
            logical = "nested__" + re.sub(r"[^A-Za-z0-9_]+", "_", path)[:140]
            if oid not in seen:
                results[logical] = persist_frame(calculation_id, logical, value, db_path=db_path)
                seen.add(oid)
            return compact_display_frame(value, limit=limit)
        if isinstance(value, dict):
            for key in list(value.keys()):
                value[key] = walk(value[key], f"{path}.{key}", depth + 1)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, (dict, list, pd.DataFrame)):
                    value[i] = walk(item, f"{path}[{i}]", depth + 1)
        return value

    for key in NESTED_HISTORY_ROOT_KEYS:
        root = state.get(key)
        if isinstance(root, (dict, list)):
            state[key] = walk(root, key)
    return results


def compact_adapter_frames(state: MutableMapping[str, Any], *, phone_mode: bool = False) -> None:
    """Replace full DataFrame references nested in the shared adapter with one display page."""
    limit = MOBILE_ROWS if phone_mode else DESKTOP_ROWS
    for adapter_key in ("adx_shared_calc_result_20260615", "shared_calc_result"):
        adapter = state.get(adapter_key)
        if not isinstance(adapter, dict):
            continue
        priority = adapter.get("priority")
        if isinstance(priority, dict) and isinstance(priority.get("table"), pd.DataFrame):
            priority["table"] = compact_display_frame(priority["table"], limit=limit)
        if isinstance(adapter.get("hourly_priority_table"), pd.DataFrame):
            adapter["hourly_priority_table"] = compact_display_frame(adapter["hourly_priority_table"], limit=limit)
        history = adapter.get("history")
        if isinstance(history, dict):
            for key, value in list(history.items()):
                if isinstance(value, pd.DataFrame) and len(value) > limit:
                    history[key] = compact_display_frame(value, limit=limit)


def _evict_old_generations(active_calculation_id: str, *, db_path: Path | str = DB_PATH) -> None:
    conn = _connect(db_path)
    try:
        generations = [row[0] for row in conn.execute(
            "SELECT calculation_id, MAX(created_at) FROM frame_manifest GROUP BY calculation_id ORDER BY MAX(created_at) DESC"
        ).fetchall()]
        keep = set(generations[:MAX_GENERATIONS]) | {str(active_calculation_id)}
        for calc_id in generations:
            if calc_id in keep:
                continue
            tables = [row[0] for row in conn.execute("SELECT table_name FROM frame_manifest WHERE calculation_id=?", (calc_id,)).fetchall()]
            with conn:
                for table in tables:
                    conn.execute(f"DROP TABLE IF EXISTS {_quote(table)}")
                conn.execute("DELETE FROM frame_manifest WHERE calculation_id=?", (calc_id,))
                conn.execute("DELETE FROM canonical_summary WHERE calculation_id=?", (calc_id,))
                conn.execute("DELETE FROM ai_conversation WHERE calculation_id=?", (calc_id,))
    finally:
        conn.close()


def session_dataframe_audit(state: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for key, value in state.items():
        if isinstance(value, pd.DataFrame):
            memory = int(value.memory_usage(index=True, deep=True).sum())
            rows.append({"key": str(key), "rows": int(len(value)), "columns": int(len(value.columns)), "bytes": memory})
    large = [row for row in rows if row["rows"] > DESKTOP_ROWS or row["bytes"] > 1_000_000]
    return {"dataframe_count": len(rows), "large_dataframe_count": len(large), "total_bytes": sum(row["bytes"] for row in rows), "large": large}


__all__ = [
    "DB_PATH", "FRAME_REFS_KEY", "TIMINGS_KEY", "HISTORY_KEYS", "timed", "record_timing",
    "persist_frame", "query_frame", "export_frame", "frame_manifest", "persist_summary", "load_summary", "load_latest_summary",
    "append_ai_message", "load_ai_messages", "spool_history_frames", "spool_nested_history_frames", "compact_display_frame", "compact_adapter_frames", "session_dataframe_audit",
]

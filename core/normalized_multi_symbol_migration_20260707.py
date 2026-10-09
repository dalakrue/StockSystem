"""Normalized three-selector, load-attempt, candle and publication schema.

The migration is additive and idempotent.  Legacy JSON preference rows and the
existing ``candles`` table remain intact; unambiguous rows are copied into the
normalized tables, while ambiguous legacy data is quarantined instead of being
assigned to a guessed symbol or timeframe.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence
import json
import sqlite3

MIGRATION_VERSION = 2026072701
MIGRATION_NAME = "normalized_three_selector_top30_publication_v2"
GROUPS = {
    "first": ("First Multi-Symbol Selector", "ALL_CALCULATION_DEPTHS", 10),
    "second": ("Second Multi-Symbol Selector", "ALL_CALCULATION_DEPTHS", 10),
    "third": ("Third Multi-Symbol Selector", "ALL_CALCULATION_DEPTHS", 10),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _transaction(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _schema_checksum(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT type,name,tbl_name,COALESCE(sql,'') FROM sqlite_master "
        "WHERE name IN ('selector_groups','selector_selections','selector_load_attempts','candle_store',"
        "'symbol_calculation_snapshots','canonical_runs','field10_symbol_rows','news_sentiment_evidence',"
        "'legacy_identity_quarantine') ORDER BY type,name"
    ).fetchall()
    return sha256(json.dumps(rows, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "").replace("_", "").replace(" ", "")


def _normalize_timeframe(value: Any) -> str:
    raw = str(value or "H4").strip().upper().replace(" ", "")
    return {"4H": "H4", "1H": "H1", "60MIN": "H1", "240MIN": "H4"}.get(raw, raw or "H4")


def _dedupe(values: Any, limit: int = 6) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Sequence):
        return []
    result: list[str] = []
    for value in values:
        symbol = _normalize_symbol(value)
        if symbol and symbol not in result:
            result.append(symbol)
        if len(result) >= limit:
            break
    return result


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS normalized_schema_migrations(
            version INTEGER PRIMARY KEY,
            migration_name TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            completion_checksum TEXT NOT NULL,
            details_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS selector_groups(
            group_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            run_owner TEXT NOT NULL,
            max_symbols INTEGER NOT NULL CHECK(max_symbols BETWEEN 1 AND 18),
            current_state_initialized INTEGER NOT NULL DEFAULT 0 CHECK(current_state_initialized IN (0,1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS selector_selections(
            selection_id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT NOT NULL REFERENCES selector_groups(group_id),
            position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 18),
            symbol TEXT NOT NULL,
            selected_timeframe TEXT NOT NULL,
            is_current INTEGER NOT NULL CHECK(is_current IN (0,1)),
            selected_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_selector_current_position
            ON selector_selections(group_id,position) WHERE is_current=1;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_selector_current_symbol
            ON selector_selections(group_id,symbol) WHERE is_current=1;
        CREATE INDEX IF NOT EXISTS idx_selector_current_tf
            ON selector_selections(group_id,selected_timeframe,is_current,position);

        CREATE TABLE IF NOT EXISTS selector_load_attempts(
            attempt_id TEXT PRIMARY KEY,
            load_id TEXT NOT NULL,
            group_id TEXT NOT NULL REFERENCES selector_groups(group_id),
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            provider TEXT,
            attempt_number INTEGER NOT NULL DEFAULT 1,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            rows_received INTEGER NOT NULL DEFAULT 0,
            completed_rows INTEGER NOT NULL DEFAULT 0,
            latest_completed_candle TEXT,
            failure_code TEXT,
            failure_message TEXT,
            retryable INTEGER NOT NULL DEFAULT 0,
            source_type TEXT NOT NULL,
            selection_signature TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_selector_attempt_symbol_tf
            ON selector_load_attempts(group_id,symbol,timeframe,finished_at DESC);
        CREATE INDEX IF NOT EXISTS idx_selector_attempt_load
            ON selector_load_attempts(load_id,group_id,status);

        CREATE TABLE IF NOT EXISTS candle_store(
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            completed_open_time TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL,
            provider TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            quality_status TEXT NOT NULL,
            is_completed INTEGER NOT NULL CHECK(is_completed IN (0,1)),
            schema_version INTEGER NOT NULL,
            PRIMARY KEY(symbol,timeframe,completed_open_time)
        );
        CREATE INDEX IF NOT EXISTS idx_candle_store_latest
            ON candle_store(symbol,timeframe,is_completed,completed_open_time DESC);

        CREATE TABLE IF NOT EXISTS symbol_calculation_snapshots(
            run_id TEXT NOT NULL,
            generation INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            latest_completed_candle TEXT NOT NULL,
            calculation_depth TEXT NOT NULL,
            status TEXT NOT NULL,
            field1_payload_reference TEXT,
            field2_payload_reference TEXT,
            field3_payload_reference TEXT,
            field10_payload_reference TEXT,
            quality_metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            checksum TEXT NOT NULL,
            PRIMARY KEY(run_id,generation,symbol,timeframe)
        );
        CREATE INDEX IF NOT EXISTS idx_symbol_snapshot_latest
            ON symbol_calculation_snapshots(symbol,timeframe,created_at DESC);

        CREATE TABLE IF NOT EXISTS canonical_runs(
            run_id TEXT NOT NULL,
            generation INTEGER NOT NULL,
            main_symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            selected_universe_hash TEXT NOT NULL,
            configured_symbols_json TEXT NOT NULL,
            loaded_symbols_json TEXT NOT NULL,
            completed_symbols_json TEXT NOT NULL,
            failed_symbols_json TEXT NOT NULL,
            calculation_depth TEXT NOT NULL,
            publication_status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            checksum TEXT,
            schema_version INTEGER NOT NULL,
            PRIMARY KEY(run_id,generation)
        );
        CREATE INDEX IF NOT EXISTS idx_canonical_runs_latest
            ON canonical_runs(publication_status,completed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_canonical_runs_tf
            ON canonical_runs(timeframe,completed_at DESC);

        CREATE TABLE IF NOT EXISTS field10_symbol_rows(
            run_id TEXT NOT NULL,
            generation INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            latest_completed_candle TEXT NOT NULL,
            publication_status TEXT NOT NULL,
            row_payload_json TEXT NOT NULL,
            checksum TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(run_id,generation,symbol,timeframe)
        );
        CREATE INDEX IF NOT EXISTS idx_field10_rows_latest
            ON field10_symbol_rows(symbol,timeframe,created_at DESC);

        CREATE TABLE IF NOT EXISTS news_sentiment_evidence(
            run_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            event_news_id TEXT NOT NULL,
            title TEXT NOT NULL,
            published_time TEXT,
            impact REAL,
            relevance REAL,
            sentiment REAL,
            absorption_status TEXT NOT NULL,
            evidence_source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(run_id,symbol,event_news_id)
        );
        CREATE INDEX IF NOT EXISTS idx_news_evidence_symbol
            ON news_sentiment_evidence(symbol,published_time DESC);

        CREATE TABLE IF NOT EXISTS legacy_identity_quarantine(
            quarantine_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_table TEXT NOT NULL,
            source_identity TEXT,
            reason_code TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            quarantined_at TEXT NOT NULL
        );
        """
    )
    if "current_state_initialized" not in _columns(conn, "selector_groups"):
        conn.execute("ALTER TABLE selector_groups ADD COLUMN current_state_initialized INTEGER NOT NULL DEFAULT 0")


def _seed_groups(conn: sqlite3.Connection, now: str) -> None:
    for group_id, (display_name, run_owner, max_symbols) in GROUPS.items():
        conn.execute(
            """INSERT INTO selector_groups(group_id,display_name,run_owner,max_symbols,current_state_initialized,created_at,updated_at)
               VALUES(?,?,?,?,0,?,?) ON CONFLICT(group_id) DO UPDATE SET
               display_name=excluded.display_name,run_owner=excluded.run_owner,
               max_symbols=excluded.max_symbols,updated_at=excluded.updated_at""",
            (group_id, display_name, run_owner, max_symbols, now, now),
        )


def replace_current_selections(
    db_path: str | Path,
    groups: Mapping[str, Any],
    timeframe: Any,
    *,
    updated_at: str | None = None,
) -> None:
    """Persist exactly the three current selector lists, including explicit empties."""
    path = Path(db_path)
    now = updated_at or _utc_now()
    tf = _normalize_timeframe(timeframe)
    with _transaction(path) as conn:
        _create_schema(conn)
        _seed_groups(conn, now)
        for group_id in GROUPS:
            raw = None
            if isinstance(groups, Mapping):
                raw = groups[group_id] if group_id in groups else groups.get(group_id.upper())
            selected = _dedupe(raw, GROUPS[group_id][2])
            conn.execute("UPDATE selector_selections SET is_current=0,updated_at=? WHERE group_id=? AND is_current=1", (now, group_id))
            conn.execute("UPDATE selector_groups SET current_state_initialized=1,updated_at=? WHERE group_id=?", (now, group_id))
            for position, symbol in enumerate(selected, start=1):
                conn.execute(
                    """INSERT INTO selector_selections(
                           group_id,position,symbol,selected_timeframe,is_current,selected_at,updated_at)
                       VALUES(?,?,?,?,1,?,?)""",
                    (group_id, position, symbol, tf, now, now),
                )


def load_current_selections(db_path: str | Path) -> dict[str, list[str]] | None:
    path = Path(db_path)
    if not path.exists():
        return None
    try:
        with sqlite3.connect(str(path), timeout=10) as conn:
            tables = _tables(conn)
            if "selector_groups" not in tables or "selector_selections" not in tables:
                return None
            initialized = conn.execute(
                "SELECT group_id,current_state_initialized FROM selector_groups WHERE group_id IN ('first','second','third')"
            ).fetchall()
            initialized_map = {str(row[0]): int(row[1] or 0) for row in initialized}
            if not all(initialized_map.get(group_id) == 1 for group_id in GROUPS):
                return None
            result: dict[str, list[str]] = {}
            for group_id in GROUPS:
                rows = conn.execute(
                    """SELECT symbol FROM selector_selections
                       WHERE group_id=? AND is_current=1 ORDER BY position""",
                    (group_id,),
                ).fetchall()
                # Presence of selector_groups means an empty row set is an intentional empty selection.
                result[group_id] = [_normalize_symbol(row[0]) for row in rows if _normalize_symbol(row[0])]
            result["normalized"] = True  # type: ignore[assignment]
            return result
    except sqlite3.Error:
        return None


def persist_load_attempts(db_path: str | Path, record: Mapping[str, Any]) -> None:
    """Persist one final per-symbol attempt plus provider-attempt detail when available."""
    path = Path(db_path)
    now = _utc_now()
    group_id = str(record.get("group") or "second").strip().lower()
    load_id = str(record.get("load_id") or "")
    timeframe = _normalize_timeframe(record.get("timeframe"))
    signature = str(record.get("selection_signature") or "")
    validations = record.get("validations") if isinstance(record.get("validations"), Mapping) else {}
    report = record.get("report") if isinstance(record.get("report"), Mapping) else {}
    results = report.get("results") if isinstance(report.get("results"), Mapping) else {}
    retry_counts = record.get("retry_count_by_symbol") if isinstance(record.get("retry_count_by_symbol"), Mapping) else {}
    requested = _dedupe(record.get("requested_symbols") or [], 18)
    with _transaction(path) as conn:
        _create_schema(conn)
        _seed_groups(conn, now)
        for symbol in requested:
            validation = validations.get(symbol) if isinstance(validations.get(symbol), Mapping) else {}
            payload = results.get(symbol) if isinstance(results.get(symbol), Mapping) else {}
            attempts = payload.get("attempts") if isinstance(payload.get("attempts"), list) else []
            attempt_number = int(retry_counts.get(symbol) or max(1, len(attempts) or 1))
            status = "READY" if validation.get("ok") else "FAILED"
            failure_code = None if validation.get("ok") else str(validation.get("failure_code") or "VALIDATION_WARNING")
            failure_message = None if validation.get("ok") else str(validation.get("reason") or "")
            provider = str(validation.get("provider") or payload.get("provider") or "UNKNOWN")
            latest = payload.get("latest_completed_candle")
            source_type = "LOCAL_CACHE" if "CACHE" in provider.upper() or provider.upper() == "SQLITE" else "LIVE_PROVIDER"
            attempt_id = sha256(f"{load_id}|{group_id}|{symbol}|{timeframe}|{attempt_number}".encode()).hexdigest()
            conn.execute(
                """INSERT OR REPLACE INTO selector_load_attempts(
                       attempt_id,load_id,group_id,symbol,timeframe,provider,attempt_number,
                       started_at,finished_at,status,rows_received,completed_rows,
                       latest_completed_candle,failure_code,failure_message,retryable,
                       source_type,selection_signature)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    attempt_id, load_id, group_id, symbol, timeframe, provider, attempt_number,
                    str(record.get("loaded_at") or now), now, status,
                    int(validation.get("rows") or 0), int(validation.get("rows") or 0),
                    None if latest is None else str(latest), failure_code, failure_message,
                    0 if validation.get("failure_code") in {"SYMBOL_NOT_SUPPORTED", "TIMEFRAME_NOT_SUPPORTED"} else (0 if validation.get("ok") else 1),
                    source_type, signature,
                ),
            )


def migrate_normalized_multi_symbol_schema(db_path: str | Path) -> dict[str, Any]:
    path = Path(db_path)
    now = _utc_now()
    details: dict[str, Any] = {"version": MIGRATION_VERSION, "migration_name": MIGRATION_NAME}
    with _transaction(path) as conn:
        _create_schema(conn)
        _seed_groups(conn, now)
        tables = _tables(conn)

        # Backfill current selectors only when the legacy row has explicit JSON identities.
        if "runtime_symbol_groups_20260706" in tables:
            row = conn.execute(
                """SELECT first_symbols_json,second_symbols_json,third_symbols_json
                   FROM runtime_symbol_groups_20260706 WHERE preference_id=1"""
            ).fetchone()
            current_count = conn.execute("SELECT COUNT(*) FROM selector_selections WHERE is_current=1").fetchone()[0]
            if row and not current_count:
                parsed: dict[str, list[str]] = {}
                for group_id, raw in zip(GROUPS, row):
                    try:
                        parsed[group_id] = _dedupe(json.loads(raw or "[]"), GROUPS[group_id][2])
                    except Exception:
                        conn.execute(
                            """INSERT INTO legacy_identity_quarantine(source_table,source_identity,reason_code,payload_json,quarantined_at)
                               VALUES(?,?,?,?,?)""",
                            ("runtime_symbol_groups_20260706", group_id, "INVALID_SELECTOR_JSON", json.dumps({"raw": raw}, default=str), now),
                        )
                        parsed[group_id] = []
                for group_id, selected in parsed.items():
                    for position, symbol in enumerate(selected, start=1):
                        conn.execute(
                            """INSERT INTO selector_selections(
                                   group_id,position,symbol,selected_timeframe,is_current,selected_at,updated_at)
                               VALUES(?,?,?,?,1,?,?)""",
                            (group_id, position, symbol, "UNKNOWN", now, now),
                        )
                conn.execute("UPDATE selector_groups SET current_state_initialized=1,updated_at=?", (now,))
                details["selector_rows_backfilled"] = sum(len(v) for v in parsed.values())
                details["selector_state_initialized_from_legacy"] = True

        # Backfill unambiguous completed candles.  The existing unique identity is reused.
        if "candles" in tables:
            cols = _columns(conn, "candles")
            required = {"symbol", "timeframe", "broker_open_time", "open", "high", "low", "close", "provider", "fetched_at", "is_complete"}
            if required.issubset(cols):
                conn.execute(
                    """INSERT OR IGNORE INTO candle_store(
                           symbol,timeframe,completed_open_time,open,high,low,close,volume,provider,
                           fetched_at,quality_status,is_completed,schema_version)
                       SELECT UPPER(REPLACE(REPLACE(REPLACE(symbol,'/',''),'_',''),' ','')),
                              UPPER(timeframe),broker_open_time,open,high,low,close,volume,provider,
                              fetched_at,COALESCE(validation_status,'UNKNOWN'),is_complete,?
                       FROM candles
                       WHERE symbol IS NOT NULL AND TRIM(symbol)<>''
                         AND timeframe IS NOT NULL AND TRIM(timeframe)<>''
                         AND broker_open_time IS NOT NULL AND TRIM(broker_open_time)<>''""",
                    (MIGRATION_VERSION,),
                )
                details["candle_rows_backfilled"] = int(conn.execute("SELECT changes()").fetchone()[0])

        checksum = _schema_checksum(conn)
        details["completion_checksum"] = checksum
        conn.execute(
            """INSERT INTO normalized_schema_migrations(version,migration_name,applied_at,completion_checksum,details_json)
               VALUES(?,?,?,?,?) ON CONFLICT(version) DO UPDATE SET
               migration_name=excluded.migration_name,applied_at=excluded.applied_at,
               completion_checksum=excluded.completion_checksum,details_json=excluded.details_json""",
            (MIGRATION_VERSION, MIGRATION_NAME, now, checksum, json.dumps(details, sort_keys=True)),
        )
    return {"ok": True, "database": str(path), **details}


__all__ = [
    "MIGRATION_VERSION", "MIGRATION_NAME", "migrate_normalized_multi_symbol_schema",
    "replace_current_selections", "load_current_selections", "persist_load_attempts",
]

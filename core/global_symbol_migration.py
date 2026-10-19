"""Transactional schema migration for the single global symbol authority.

The migration is additive and idempotent.  Legacy rows are imported only when
symbol, timeframe and publication identity are explicit; ambiguous rows are
quarantined instead of being relabelled or assigned to a default symbol.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import sqlite3

MIGRATION_VERSION = 2026072203
MIGRATION_NAME = "global_symbol_domain_and_field3_v2"

_SCHEMA_SQL = r"""
CREATE TABLE IF NOT EXISTS global_symbol_schema_migrations(
    version INTEGER PRIMARY KEY,
    migration_name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS canonical_symbol_universe_v2(
    universe_id TEXT PRIMARY KEY,
    generation INTEGER NOT NULL,
    timeframe TEXT NOT NULL,
    configured_hash TEXT NOT NULL,
    configured_symbols_json TEXT NOT NULL,
    selection_version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    parent_run_id TEXT,
    snapshot_hash TEXT,
    latest_completed_candle TEXT,
    calculation_depth TEXT,
    publication_status TEXT NOT NULL DEFAULT 'CONFIGURED',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(generation, timeframe, configured_hash)
);
CREATE TABLE IF NOT EXISTS canonical_symbol_universe_member_v2(
    universe_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    position INTEGER NOT NULL,
    requested INTEGER NOT NULL DEFAULT 1 CHECK(requested IN (0,1)),
    loaded INTEGER NOT NULL DEFAULT 0 CHECK(loaded IN (0,1)),
    completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0,1)),
    provider TEXT,
    provider_symbol TEXT,
    candle_count INTEGER NOT NULL DEFAULT 0,
    latest_completed_candle TEXT,
    candle_hash TEXT,
    data_quality_grade TEXT,
    failure_code TEXT,
    failure_message TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(universe_id, symbol),
    FOREIGN KEY(universe_id) REFERENCES canonical_symbol_universe_v2(universe_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS canonical_display_selection_v2(
    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
    universe_id TEXT NOT NULL,
    active_symbol TEXT NOT NULL,
    selection_version INTEGER NOT NULL,
    selected_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(universe_id, active_symbol)
      REFERENCES canonical_symbol_universe_member_v2(universe_id, symbol)
      DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE IF NOT EXISTS field3_regime_evidence_v2(
    parent_run_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    standard TEXT NOT NULL CHECK(standard IN ('LOWER','MIDDLE','HIGHER')),
    window_bars INTEGER NOT NULL,
    regime_state TEXT NOT NULL,
    bias TEXT NOT NULL,
    posterior_probability REAL,
    persistence_probability REAL,
    expected_duration REAL,
    regime_age INTEGER,
    changepoint_probability REAL,
    transition_risk REAL,
    calibrated_reliability REAL,
    sample_count INTEGER NOT NULL,
    data_quality_grade TEXT NOT NULL,
    latest_completed_candle TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(parent_run_id, generation, symbol, timeframe, standard)
);
CREATE TABLE IF NOT EXISTS field3_symbol_rank_v2(
    parent_run_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    lower_score REAL,
    middle_score REAL,
    higher_score REAL,
    agreement_score REAL,
    conflict_penalty REAL,
    correlation_penalty REAL,
    spillover_penalty REAL,
    composite_score REAL,
    decision_strength REAL,
    final_bias TEXT NOT NULL,
    calibrated_reliability REAL,
    entry_permission TEXT NOT NULL,
    block_reason TEXT,
    rank INTEGER,
    latest_completed_candle TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(parent_run_id, generation, symbol, timeframe)
);
CREATE TABLE IF NOT EXISTS global_symbol_migration_quarantine(
    quarantine_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_table TEXT NOT NULL,
    source_identity TEXT,
    reason TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    quarantined_at TEXT NOT NULL,
    UNIQUE(source_table, source_identity, reason)
);
CREATE TABLE IF NOT EXISTS global_symbol_lifecycle_event_v2(
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    universe_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('CONFIGURED','LOADING','LOADED','CALCULATING','COMPLETED','PUBLISHED','FAILED','BLOCKED')),
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(universe_id) REFERENCES canonical_symbol_universe_v2(universe_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_global_symbol_lifecycle_v2
    ON global_symbol_lifecycle_event_v2(universe_id,event_id);
CREATE INDEX IF NOT EXISTS idx_symbol_universe_status_v2
    ON canonical_symbol_universe_v2(publication_status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_symbol_member_completed_v2
    ON canonical_symbol_universe_member_v2(universe_id, completed, loaded, position);
CREATE INDEX IF NOT EXISTS idx_field3_rank_generation_v2
    ON field3_symbol_rank_v2(generation, timeframe, rank);
"""
SCHEMA_CHECKSUM = hashlib.sha256(_SCHEMA_SQL.encode("utf-8")).hexdigest()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(r[1]) for r in conn.execute(f'PRAGMA table_info("{table}")')}


@contextmanager
def _transaction(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()



def _execute_schema(conn: sqlite3.Connection) -> None:
    """Execute additive DDL inside the caller transaction without executescript's implicit commit."""
    for statement in _SCHEMA_SQL.split(";"):
        sql = statement.strip()
        if sql:
            conn.execute(sql)


def _quarantine(conn: sqlite3.Connection, table: str, identity: str, reason: str, payload: Any) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO global_symbol_migration_quarantine(
               source_table,source_identity,reason,payload_json,quarantined_at)
           VALUES(?,?,?,?,?)""",
        (table, identity, reason, json.dumps(payload, default=str, ensure_ascii=False), _utcnow()),
    )


def _migrate_runtime_preference(conn: sqlite3.Connection) -> int:
    """Import only an explicit configured universe; it is not marked loaded."""
    if not _table_exists(conn, "runtime_preferences"):
        return 0
    cols = _columns(conn, "runtime_preferences")
    if not {"selected_symbols_json", "timeframe"}.issubset(cols):
        return 0
    row = conn.execute("SELECT selected_symbols_json,timeframe FROM runtime_preferences WHERE preference_id=1").fetchone()
    if not row:
        return 0
    try:
        symbols = [str(x).strip().upper().replace("/", "") for x in json.loads(row[0] or "[]") if str(x).strip()]
    except Exception:
        _quarantine(conn, "runtime_preferences", "1", "INVALID_SELECTED_SYMBOLS_JSON", {"raw": row[0], "timeframe": row[1]})
        return 0
    timeframe = str(row[1] or "").strip().upper()
    if not symbols or not timeframe:
        _quarantine(conn, "runtime_preferences", "1", "AMBIGUOUS_CONFIGURED_UNIVERSE", {"symbols": symbols, "timeframe": timeframe})
        return 0
    configured_hash = hashlib.sha256((timeframe + "|" + "|".join(symbols)).encode()).hexdigest()
    universe_id = "legacy-config-" + configured_hash[:20]
    now = _utcnow()
    conn.execute(
        """INSERT OR IGNORE INTO canonical_symbol_universe_v2(
               universe_id,generation,timeframe,configured_hash,configured_symbols_json,
               selection_version,status,publication_status,created_at,updated_at)
           VALUES(?,?,?,?,?,1,'CONFIGURED','CONFIGURED',?,?)""",
        (universe_id, 0, timeframe, configured_hash, json.dumps(symbols), now, now),
    )
    for pos, symbol in enumerate(symbols):
        conn.execute(
            """INSERT OR IGNORE INTO canonical_symbol_universe_member_v2(
                   universe_id,symbol,position,requested,loaded,completed,updated_at)
               VALUES(?,?,?,1,0,0,?)""",
            (universe_id, symbol, pos, now),
        )
    return 1


def _json_symbols(raw: Any) -> list[str]:
    try:
        values = json.loads(raw or "[]") if isinstance(raw, str) else list(raw or [])
    except Exception:
        return []
    out: list[str] = []
    for value in values:
        symbol = str(value or "").strip().upper().replace("/", "").replace(" ", "")
        if symbol and symbol not in out:
            out.append(symbol)
    return out


def _generation_number(value: Any) -> int:
    text = str(value or "0").strip().upper().lstrip("G")
    try:
        return max(0, int(text))
    except Exception:
        return 0


def _migrate_canonical_run_identity(conn: sqlite3.Connection) -> int:
    """Import exact legacy run/member identity as LOADED, never as v2 Field 3 completed."""
    if not _table_exists(conn, "canonical_run_identity"):
        return 0
    cols = _columns(conn, "canonical_run_identity")
    required = {"parent_run_id", "timeframe", "canonical_symbols_json", "loaded_symbols_json", "snapshot_hash", "broker_candle_time"}
    if not required.issubset(cols):
        return 0
    rows = conn.execute(
        "SELECT parent_run_id,generation,snapshot_hash,broker_candle_time,timeframe,canonical_symbols_json,loaded_symbols_json,degraded_symbols_json,missing_symbols_json,status,updated_at FROM canonical_run_identity ORDER BY updated_at"
    ).fetchall()
    imported = 0
    evidence_cols = _columns(conn, "canonical_symbol_evidence")
    for row in rows:
        parent_run_id, generation_raw, snapshot_hash, candle, timeframe, configured_raw, loaded_raw, degraded_raw, missing_raw, status, updated_at = row
        configured = _json_symbols(configured_raw)
        loaded = _json_symbols(loaded_raw)
        timeframe = str(timeframe or "").strip().upper()
        if not parent_run_id or not configured or not timeframe:
            _quarantine(conn, "canonical_run_identity", str(parent_run_id or updated_at), "AMBIGUOUS_CANONICAL_RUN_IDENTITY", dict(zip(["parent_run_id","generation","snapshot_hash","candle","timeframe","configured","loaded"], row[:7])))
            continue
        if set(loaded) - set(configured):
            _quarantine(conn, "canonical_run_identity", str(parent_run_id), "LOADED_NOT_SUBSET_OF_CONFIGURED", {"configured": configured, "loaded": loaded})
            continue
        configured_hash = hashlib.sha256((timeframe + "|" + "|".join(configured)).encode()).hexdigest()
        universe_id = "legacy-run-" + hashlib.sha256((str(parent_run_id)+"|"+timeframe+"|"+str(snapshot_hash)).encode()).hexdigest()[:24]
        now = str(updated_at or _utcnow())
        generation = _generation_number(generation_raw)
        conn.execute(
            """INSERT OR IGNORE INTO canonical_symbol_universe_v2(
                   universe_id,generation,timeframe,configured_hash,configured_symbols_json,selection_version,status,
                   parent_run_id,snapshot_hash,latest_completed_candle,calculation_depth,publication_status,created_at,updated_at)
               VALUES(?,?,?,?,?,1,'LOADED',?,?,?,'LEGACY_MIGRATION','LOADED',?,?)""",
            (universe_id,generation,timeframe,configured_hash,json.dumps(configured),str(parent_run_id),str(snapshot_hash or ""),str(candle or ""),now,now),
        )
        for pos, symbol in enumerate(configured):
            evidence = None
            if required and {"parent_run_id","symbol","timeframe"}.issubset(evidence_cols):
                evidence = conn.execute(
                    "SELECT provider_used,provider_symbol,candle_count,latest_candle_time,data_quality_grade,loaded_status,failure_reason FROM canonical_symbol_evidence WHERE parent_run_id=? AND symbol=? AND timeframe=? ORDER BY created_at DESC LIMIT 1",
                    (parent_run_id,symbol,timeframe),
                ).fetchone()
            is_loaded = symbol in loaded
            provider = evidence[0] if evidence else None
            provider_symbol = evidence[1] if evidence else symbol
            candle_count = int(evidence[2] or 0) if evidence else 0
            latest = evidence[3] if evidence else candle
            grade = evidence[4] if evidence else None
            failure = None if is_loaded else ((evidence[6] if evidence else None) or ("LEGACY_MISSING_OR_DEGRADED" if symbol in _json_symbols(missing_raw) + _json_symbols(degraded_raw) else "LEGACY_NOT_LOADED"))
            conn.execute(
                """INSERT OR IGNORE INTO canonical_symbol_universe_member_v2(
                       universe_id,symbol,position,requested,loaded,completed,provider,provider_symbol,candle_count,
                       latest_completed_candle,candle_hash,data_quality_grade,failure_code,failure_message,updated_at)
                   VALUES(?,?,?,1,?,0,?,?,?,?,NULL,?,?,?,?)""",
                (universe_id,symbol,pos,1 if is_loaded else 0,provider,provider_symbol,candle_count,latest,grade,
                 None if is_loaded else "LEGACY_LOAD_NOT_COMPLETED",failure,now),
            )
        imported += 1
    return imported


def _migrate_explicit_canonical_runs(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "canonical_runs"):
        return 0
    cols = _columns(conn, "canonical_runs")
    required = {"run_id","generation","timeframe","configured_symbols_json","loaded_symbols_json","completed_symbols_json","publication_status"}
    if not required.issubset(cols):
        return 0
    imported = 0
    for row in conn.execute("SELECT run_id,generation,timeframe,configured_symbols_json,loaded_symbols_json,completed_symbols_json,failed_symbols_json,calculation_depth,publication_status,completed_at,checksum FROM canonical_runs"):
        run_id,generation,timeframe,cfg_raw,loaded_raw,completed_raw,failed_raw,depth,pub,completed_at,checksum=row
        configured,loaded,completed=_json_symbols(cfg_raw),_json_symbols(loaded_raw),_json_symbols(completed_raw)
        timeframe=str(timeframe or '').upper()
        if not run_id or not configured or not timeframe or set(loaded)-set(configured) or set(completed)-set(loaded):
            _quarantine(conn,"canonical_runs",str(run_id),"AMBIGUOUS_OR_INVALID_CANONICAL_RUN",{"configured":configured,"loaded":loaded,"completed":completed,"timeframe":timeframe})
            continue
        configured_hash=hashlib.sha256((timeframe+'|'+'|'.join(configured)).encode()).hexdigest()
        universe_id='legacy-canonical-'+hashlib.sha256((str(run_id)+'|'+timeframe).encode()).hexdigest()[:24]
        now=str(completed_at or _utcnow())
        publication='PUBLISHED' if str(pub).upper() in {'PUBLISHED','COMPLETED'} and completed else 'LOADED'
        conn.execute("""INSERT OR IGNORE INTO canonical_symbol_universe_v2(
            universe_id,generation,timeframe,configured_hash,configured_symbols_json,selection_version,status,parent_run_id,snapshot_hash,
            calculation_depth,publication_status,created_at,updated_at) VALUES(?,?,?,?,?,1,?,?,?,?,?,?,?)""",
            (universe_id,int(generation or 0),timeframe,configured_hash,json.dumps(configured),publication,str(run_id),str(checksum or ''),str(depth or ''),publication,now,now))
        failed_map={}
        try: failed_map=json.loads(failed_raw or '{}') if isinstance(failed_raw,str) else dict(failed_raw or {})
        except Exception: failed_map={}
        for pos,symbol in enumerate(configured):
            failure=failed_map.get(symbol)
            conn.execute("""INSERT OR IGNORE INTO canonical_symbol_universe_member_v2(
                universe_id,symbol,position,requested,loaded,completed,provider_symbol,candle_count,failure_code,failure_message,updated_at)
                VALUES(?,?,?,1,?,?,?,0,?,?,?)""",
                (universe_id,symbol,pos,1 if symbol in loaded else 0,1 if symbol in completed else 0,symbol,None if symbol in loaded else 'LEGACY_FAILED',str(failure or '') if not symbol in loaded else None,now))
        imported += 1
    return imported


def _quarantine_legacy_field3(conn: sqlite3.Connection) -> int:
    """Never promote the known copied-standard legacy Field 3 into v2 evidence."""
    if not _table_exists(conn, "field3_multisymbol_regime"):
        return 0
    try:
        cur = conn.execute("SELECT rowid,* FROM field3_multisymbol_regime LIMIT 5000")
        names = [d[0] for d in cur.description or []]
        rows = cur.fetchall()
    except Exception:
        return 0
    count = 0
    for row in rows:
        payload = dict(zip(names,row)) if names else {"row":list(row)}
        ident = str(payload.get("rowid") or hashlib.sha256(repr(row).encode()).hexdigest()[:20])
        _quarantine(conn,"field3_multisymbol_regime",ident,"LEGACY_FIELD3_NOT_IMPORTED_STANDARDS_NOT_PROVEN_INDEPENDENT",payload)
        count += 1
    return count


def migrate_global_symbol_schema(db_path: str | Path, *, fail_after_schema: bool = False) -> dict[str, Any]:
    """Apply the global-domain migration exactly once and verify its checksum.

    ``fail_after_schema`` exists solely for rollback tests.
    """
    path = Path(db_path)
    with _transaction(path) as conn:
        _execute_schema(conn)
        existing = conn.execute(
            "SELECT checksum FROM global_symbol_schema_migrations WHERE version=?", (MIGRATION_VERSION,)
        ).fetchone()
        if existing and str(existing[0]) != SCHEMA_CHECKSUM:
            raise RuntimeError("GLOBAL_SYMBOL_SCHEMA_CHECKSUM_MISMATCH")
        if fail_after_schema:
            raise RuntimeError("INJECTED_GLOBAL_SYMBOL_MIGRATION_FAILURE")
        if existing:
            imported_preferences = imported_identity = imported_runs = quarantined = 0
        else:
            imported_preferences = _migrate_runtime_preference(conn)
            imported_identity = _migrate_canonical_run_identity(conn)
            imported_runs = _migrate_explicit_canonical_runs(conn)
            quarantined = _quarantine_legacy_field3(conn)
        conn.execute(
            """INSERT INTO global_symbol_schema_migrations(version,migration_name,checksum,applied_at)
               VALUES(?,?,?,?) ON CONFLICT(version) DO UPDATE SET
               migration_name=excluded.migration_name,
               checksum=excluded.checksum""",
            (MIGRATION_VERSION, MIGRATION_NAME, SCHEMA_CHECKSUM, _utcnow()),
        )
    return {
        "ok": True,
        "version": MIGRATION_VERSION,
        "name": MIGRATION_NAME,
        "checksum": SCHEMA_CHECKSUM,
        "database": str(path),
        "legacy_configured_universes_imported": imported_preferences,
        "legacy_identity_universes_imported": imported_identity,
        "legacy_canonical_runs_imported": imported_runs,
        "ambiguous_rows_quarantined": quarantined,
    }


__all__ = [
    "MIGRATION_VERSION", "MIGRATION_NAME", "SCHEMA_CHECKSUM", "migrate_global_symbol_schema",
]

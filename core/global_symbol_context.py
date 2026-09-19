"""Single public authority for configured, loaded, completed and display symbols."""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import sqlite3
import threading
import uuid

from core.global_symbol_migration import migrate_global_symbol_schema

try:
    from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
except Exception:  # pragma: no cover
    DEFAULT_DB_PATH = Path("data/multi_symbol_field10_20260701.sqlite3")

CONTEXT_STATE_KEY = "global_symbol_context_v2"
CONTEXT_VERSION = 2
_SELECTION_LOCK = threading.RLock()
_VALID_PUBLICATIONS = ("PUBLISHED", "COMPLETED", "LOADED")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "").replace("_", "").replace(" ", "")


def normalize_timeframe(value: Any) -> str:
    raw = str(value or "").strip().upper().replace("4H", "H4").replace("1H", "H1")
    return raw


def _ordered_unique(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Sequence):
        return []
    out: list[str] = []
    for value in values:
        symbol = normalize_symbol(value)
        if symbol and symbol not in out:
            out.append(symbol)
    return out


def _hash_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class GlobalSymbolContext:
    universe_id: str = ""
    generation: int = 0
    timeframe: str = ""
    configured_symbols: tuple[str, ...] = field(default_factory=tuple)
    loaded_symbols: tuple[str, ...] = field(default_factory=tuple)
    completed_symbols: tuple[str, ...] = field(default_factory=tuple)
    failed_symbols: Mapping[str, str] = field(default_factory=dict)
    active_display_symbol: str = ""
    parent_run_id: str = ""
    snapshot_hash: str = ""
    latest_completed_candle: str = ""
    selection_hash: str = ""
    calculation_depth: str = ""
    publication_status: str = "EMPTY"
    version: int = CONTEXT_VERSION
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["configured_symbols"] = list(self.configured_symbols)
        out["loaded_symbols"] = list(self.loaded_symbols)
        out["completed_symbols"] = list(self.completed_symbols)
        out["failed_symbols"] = dict(self.failed_symbols)
        return out


_EMPTY = GlobalSymbolContext(updated_at=_utcnow())


def _connect(path: Path) -> sqlite3.Connection:
    migrate_global_symbol_schema(path)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def _record_lifecycle_event(conn: sqlite3.Connection, universe_id: str, status: str, details: Mapping[str, Any] | None = None) -> None:
    conn.execute(
        "INSERT INTO global_symbol_lifecycle_event_v2(universe_id,status,details_json,created_at) VALUES(?,?,?,?)",
        (universe_id, status, json.dumps(dict(details or {}), sort_keys=True, default=str), _utcnow()),
    )


def _transition_universe(
    universe_id: str,
    status: str,
    *,
    state: MutableMapping[str, Any] | None = None,
    db_path: str | Path | None = None,
    details: Mapping[str, Any] | None = None,
) -> GlobalSymbolContext:
    allowed = {"LOADING", "CALCULATING", "FAILED", "BLOCKED"}
    if status not in allowed:
        raise ValueError(f"UNSUPPORTED_EXPLICIT_LIFECYCLE_STATUS:{status}")
    path = Path(db_path or DEFAULT_DB_PATH)
    with _SELECTION_LOCK, _connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT universe_id FROM canonical_symbol_universe_v2 WHERE universe_id=?", (universe_id,)).fetchone()
        if not row:
            raise KeyError("UNKNOWN_UNIVERSE_ID")
        now = _utcnow()
        conn.execute("UPDATE canonical_symbol_universe_v2 SET status=?,publication_status=?,updated_at=? WHERE universe_id=?",
                     (status, status, now, universe_id))
        _record_lifecycle_event(conn, universe_id, status, details)
        conn.commit()
        context = _context_from_conn(conn, universe_id)
    _publish_to_state(state, context)
    return context


def mark_universe_loading(universe_id: str, *, state: MutableMapping[str, Any] | None = None,
                          db_path: str | Path | None = None, details: Mapping[str, Any] | None = None) -> GlobalSymbolContext:
    return _transition_universe(universe_id, "LOADING", state=state, db_path=db_path, details=details)


def mark_universe_calculating(universe_id: str, *, state: MutableMapping[str, Any] | None = None,
                              db_path: str | Path | None = None, details: Mapping[str, Any] | None = None) -> GlobalSymbolContext:
    return _transition_universe(universe_id, "CALCULATING", state=state, db_path=db_path, details=details)


def _context_from_conn(conn: sqlite3.Connection, universe_id: str | None = None) -> GlobalSymbolContext:
    if universe_id:
        row = conn.execute("SELECT * FROM canonical_symbol_universe_v2 WHERE universe_id=?", (universe_id,)).fetchone()
    else:
        row = conn.execute(
            """SELECT * FROM canonical_symbol_universe_v2
               WHERE publication_status IN ('PUBLISHED','COMPLETED','LOADED','LOADING','CALCULATING','CONFIGURED')
               ORDER BY CASE publication_status WHEN 'PUBLISHED' THEN 0 WHEN 'COMPLETED' THEN 1 WHEN 'LOADED' THEN 2 ELSE 3 END,
                        generation DESC, updated_at DESC LIMIT 1"""
        ).fetchone()
    if not row:
        return _EMPTY
    members = conn.execute(
        "SELECT * FROM canonical_symbol_universe_member_v2 WHERE universe_id=? ORDER BY position,symbol", (row["universe_id"],)
    ).fetchall()
    configured = tuple(str(m["symbol"]) for m in members if int(m["requested"] or 0))
    loaded = tuple(str(m["symbol"]) for m in members if int(m["loaded"] or 0))
    completed = tuple(str(m["symbol"]) for m in members if int(m["completed"] or 0))
    failed = {
        str(m["symbol"]): str(m["failure_code"] or m["failure_message"] or "FAILED")
        for m in members if m["failure_code"] or m["failure_message"]
    }
    selection = conn.execute("SELECT * FROM canonical_display_selection_v2 WHERE singleton_id=1").fetchone()
    active = ""
    if selection and str(selection["universe_id"]) == str(row["universe_id"]):
        candidate = normalize_symbol(selection["active_symbol"])
        if candidate in completed or (not completed and candidate in loaded):
            active = candidate
    eligible = completed or loaded
    if not active and eligible:
        active = eligible[0]
    selection_hash = _hash_json({
        "universe_id": row["universe_id"], "selection_version": row["selection_version"], "active": active,
    })
    return GlobalSymbolContext(
        universe_id=str(row["universe_id"]), generation=int(row["generation"] or 0), timeframe=str(row["timeframe"] or ""),
        configured_symbols=configured, loaded_symbols=loaded, completed_symbols=completed, failed_symbols=failed,
        active_display_symbol=active, parent_run_id=str(row["parent_run_id"] or ""), snapshot_hash=str(row["snapshot_hash"] or ""),
        latest_completed_candle=str(row["latest_completed_candle"] or ""), selection_hash=selection_hash,
        calculation_depth=str(row["calculation_depth"] or ""), publication_status=str(row["publication_status"] or row["status"] or "EMPTY"),
        version=CONTEXT_VERSION, updated_at=str(row["updated_at"] or ""),
    )


def _publish_to_state(state: MutableMapping[str, Any] | None, context: GlobalSymbolContext) -> None:
    if not isinstance(state, MutableMapping):
        return
    state[CONTEXT_STATE_KEY] = context.to_dict()
    try:
        from core.global_symbol_compat import mirror_context_to_legacy_state
        mirror_context_to_legacy_state(state, context)
    except Exception:
        pass


def validate_symbol_context(context: GlobalSymbolContext, *, require_published: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    if context.configured_symbols and not context.universe_id:
        errors.append("CONFIGURED_WITHOUT_UNIVERSE_ID")
    if set(context.loaded_symbols) - set(context.configured_symbols):
        errors.append("LOADED_NOT_SUBSET_OF_CONFIGURED")
    if set(context.completed_symbols) - set(context.loaded_symbols):
        errors.append("COMPLETED_NOT_SUBSET_OF_LOADED")
    eligible = set(context.completed_symbols or context.loaded_symbols)
    if context.active_display_symbol and context.active_display_symbol not in eligible:
        errors.append("ACTIVE_SYMBOL_NOT_ELIGIBLE")
    if require_published and context.publication_status != "PUBLISHED":
        errors.append("CONTEXT_NOT_PUBLISHED")
    return {"ok": not errors, "errors": errors, "context": context.to_dict()}


def get_global_symbol_context(state: Mapping[str, Any] | None = None, *, db_path: str | Path | None = None, restore: bool = True) -> GlobalSymbolContext:
    if isinstance(state, Mapping):
        raw = state.get(CONTEXT_STATE_KEY)
        if isinstance(raw, Mapping) and raw.get("universe_id"):
            try:
                ctx = GlobalSymbolContext(
                    universe_id=str(raw.get("universe_id") or ""), generation=int(raw.get("generation") or 0),
                    timeframe=str(raw.get("timeframe") or ""), configured_symbols=tuple(_ordered_unique(raw.get("configured_symbols"))),
                    loaded_symbols=tuple(_ordered_unique(raw.get("loaded_symbols"))), completed_symbols=tuple(_ordered_unique(raw.get("completed_symbols"))),
                    failed_symbols=dict(raw.get("failed_symbols") or {}), active_display_symbol=normalize_symbol(raw.get("active_display_symbol")),
                    parent_run_id=str(raw.get("parent_run_id") or ""), snapshot_hash=str(raw.get("snapshot_hash") or ""),
                    latest_completed_candle=str(raw.get("latest_completed_candle") or ""), selection_hash=str(raw.get("selection_hash") or ""),
                    calculation_depth=str(raw.get("calculation_depth") or ""), publication_status=str(raw.get("publication_status") or "EMPTY"),
                    version=int(raw.get("version") or CONTEXT_VERSION), updated_at=str(raw.get("updated_at") or ""),
                )
                if validate_symbol_context(ctx)["ok"]:
                    return ctx
            except Exception:
                pass
    if restore:
        return restore_latest_context(state if isinstance(state, MutableMapping) else None, db_path=db_path)
    return _EMPTY


def configure_universe(symbols: Sequence[Any], timeframe: Any, *, state: MutableMapping[str, Any] | None = None, db_path: str | Path | None = None) -> GlobalSymbolContext:
    configured = _ordered_unique(symbols)
    tf = normalize_timeframe(timeframe)
    if not configured:
        raise ValueError("CONFIGURED_SYMBOLS_EMPTY")
    if not tf:
        raise ValueError("TIMEFRAME_EMPTY")
    path = Path(db_path or DEFAULT_DB_PATH)
    configured_hash = _hash_json({"timeframe": tf, "symbols": configured})
    now = _utcnow()
    with _SELECTION_LOCK, _connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        reusable = conn.execute(
            """SELECT universe_id FROM canonical_symbol_universe_v2
               WHERE configured_hash=? AND timeframe=? AND publication_status IN ('CONFIGURED','LOADING','LOADED','CALCULATING')
               ORDER BY generation DESC,updated_at DESC LIMIT 1""", (configured_hash, tf)
        ).fetchone()
        if reusable:
            conn.commit()
            ctx = _context_from_conn(conn, str(reusable[0]))
            _publish_to_state(state, ctx)
            return ctx
        generation = int(conn.execute("SELECT COALESCE(MAX(generation),0)+1 FROM canonical_symbol_universe_v2").fetchone()[0])
        universe_id = f"U{generation}-{configured_hash[:16]}-{uuid.uuid4().hex[:8]}"
        conn.execute(
            """INSERT INTO canonical_symbol_universe_v2(
                   universe_id,generation,timeframe,configured_hash,configured_symbols_json,selection_version,
                   status,publication_status,created_at,updated_at)
               VALUES(?,?,?,?,?,1,'CONFIGURED','CONFIGURED',?,?)""",
            (universe_id, generation, tf, configured_hash, json.dumps(configured), now, now),
        )
        for pos, symbol in enumerate(configured):
            conn.execute(
                """INSERT INTO canonical_symbol_universe_member_v2(
                       universe_id,symbol,position,requested,loaded,completed,updated_at)
                   VALUES(?,?,?,1,0,0,?)""", (universe_id, symbol, pos, now),
            )
        _record_lifecycle_event(conn, universe_id, "CONFIGURED", {"symbols": configured, "timeframe": tf})
        conn.commit()
        ctx = _context_from_conn(conn, universe_id)
    _publish_to_state(state, ctx)
    return ctx


def _member_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        return dict(payload)
    return {"symbol": payload}


def publish_loaded_universe(
    universe_id: str,
    loaded_members: Sequence[Any] | Mapping[str, Any],
    *, failed_members: Mapping[str, Any] | None = None,
    state: MutableMapping[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> GlobalSymbolContext:
    path = Path(db_path or DEFAULT_DB_PATH)
    if isinstance(loaded_members, Mapping):
        items = [(normalize_symbol(k), _member_payload(v)) for k, v in loaded_members.items()]
    else:
        items = [(normalize_symbol(_member_payload(v).get("symbol") or v), _member_payload(v)) for v in loaded_members]
    failed_members = failed_members or {}
    now = _utcnow()
    with _SELECTION_LOCK, _connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM canonical_symbol_universe_v2 WHERE universe_id=?", (universe_id,)).fetchone()
        if not row:
            raise KeyError("UNKNOWN_UNIVERSE_ID")
        configured = {r[0] for r in conn.execute("SELECT symbol FROM canonical_symbol_universe_member_v2 WHERE universe_id=?", (universe_id,))}
        for symbol, payload in items:
            if symbol not in configured:
                raise ValueError(f"LOADED_SYMBOL_NOT_CONFIGURED:{symbol}")
            conn.execute(
                """UPDATE canonical_symbol_universe_member_v2 SET loaded=1, provider=?,provider_symbol=?,
                       candle_count=?,latest_completed_candle=?,candle_hash=?,data_quality_grade=?,
                       failure_code=NULL,failure_message=NULL,updated_at=? WHERE universe_id=? AND symbol=?""",
                (payload.get("provider"), payload.get("provider_symbol") or symbol, int(payload.get("candle_count") or 0),
                 payload.get("latest_completed_candle"), payload.get("candle_hash") or payload.get("source_data_hash"),
                 payload.get("data_quality_grade"), now, universe_id, symbol),
            )
        for raw_symbol, reason in failed_members.items():
            symbol = normalize_symbol(raw_symbol)
            if symbol not in configured:
                continue
            if isinstance(reason, Mapping):
                code = reason.get("failure_code") or reason.get("code") or "LOAD_FAILED"
                message = reason.get("failure_message") or reason.get("message") or str(code)
            else:
                code, message = "LOAD_FAILED", str(reason)
            conn.execute(
                """UPDATE canonical_symbol_universe_member_v2 SET loaded=0,completed=0,failure_code=?,failure_message=?,updated_at=?
                   WHERE universe_id=? AND symbol=?""", (code, message, now, universe_id, symbol),
            )
        conn.execute(
            "UPDATE canonical_symbol_universe_v2 SET status='LOADED',publication_status='LOADED',updated_at=? WHERE universe_id=?",
            (now, universe_id),
        )
        _record_lifecycle_event(conn, universe_id, "LOADED", {
            "loaded_symbols": [symbol for symbol, _ in items],
            "failed_symbols": sorted(normalize_symbol(symbol) for symbol in failed_members),
        })
        conn.commit()
        ctx = _context_from_conn(conn, universe_id)
    _publish_to_state(state, ctx)
    return ctx


def publish_completed_generation(
    universe_id: str,
    completed_members: Sequence[Any] | Mapping[str, Any],
    *, parent_run_id: str,
    snapshot_hash: str,
    latest_completed_candle: str,
    calculation_depth: str,
    state: MutableMapping[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> GlobalSymbolContext:
    path = Path(db_path or DEFAULT_DB_PATH)
    if isinstance(completed_members, Mapping):
        items = [(normalize_symbol(k), _member_payload(v)) for k, v in completed_members.items()]
    else:
        items = [(normalize_symbol(_member_payload(v).get("symbol") or v), _member_payload(v)) for v in completed_members]
    now = _utcnow()
    with _SELECTION_LOCK, _connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM canonical_symbol_universe_v2 WHERE universe_id=?", (universe_id,)).fetchone()
        if not row:
            raise KeyError("UNKNOWN_UNIVERSE_ID")
        exact_candles: set[str] = set()
        for symbol, payload in items:
            member = conn.execute(
                "SELECT * FROM canonical_symbol_universe_member_v2 WHERE universe_id=? AND symbol=?", (universe_id, symbol)
            ).fetchone()
            if not member or not int(member["loaded"] or 0):
                raise ValueError(f"COMPLETED_SYMBOL_NOT_LOADED:{symbol}")
            candle = str(payload.get("latest_completed_candle") or latest_completed_candle or "")
            timeframe = str(payload.get("timeframe") or row["timeframe"] or "")
            if timeframe != str(row["timeframe"]):
                raise ValueError(f"TIMEFRAME_IDENTITY_MISMATCH:{symbol}:{timeframe}:{row['timeframe']}")
            if candle:
                exact_candles.add(candle)
            if payload.get("source_data_hash") and member["candle_hash"] and str(payload.get("source_data_hash")) != str(member["candle_hash"]):
                raise ValueError(f"SOURCE_DATA_HASH_MISMATCH:{symbol}")
            conn.execute(
                """UPDATE canonical_symbol_universe_member_v2 SET completed=1,latest_completed_candle=?,
                       candle_hash=COALESCE(?,candle_hash),data_quality_grade=COALESCE(?,data_quality_grade),updated_at=?
                   WHERE universe_id=? AND symbol=?""",
                (candle, payload.get("source_data_hash"), payload.get("data_quality_grade"), now, universe_id, symbol),
            )
        if len(exact_candles) > 1:
            raise ValueError("MIXED_COMPLETED_CANDLE_CUTOFFS")
        conn.execute(
            """UPDATE canonical_symbol_universe_v2 SET status='COMPLETED',publication_status='COMPLETED',
                   parent_run_id=?,snapshot_hash=?,latest_completed_candle=?,calculation_depth=?,updated_at=?
               WHERE universe_id=?""",
            (parent_run_id, snapshot_hash, latest_completed_candle, calculation_depth, now, universe_id),
        )
        _record_lifecycle_event(conn, universe_id, "COMPLETED", {
            "parent_run_id": parent_run_id, "snapshot_hash": snapshot_hash,
            "completed_symbols": [symbol for symbol, _ in items],
            "latest_completed_candle": latest_completed_candle,
        })
        conn.execute(
            "UPDATE canonical_symbol_universe_v2 SET status='PUBLISHED',publication_status='PUBLISHED',updated_at=? WHERE universe_id=?",
            (now, universe_id),
        )
        _record_lifecycle_event(conn, universe_id, "PUBLISHED", {
            "parent_run_id": parent_run_id, "snapshot_hash": snapshot_hash,
            "calculation_depth": calculation_depth,
        })
        eligible = [r[0] for r in conn.execute(
            "SELECT symbol FROM canonical_symbol_universe_member_v2 WHERE universe_id=? AND completed=1 ORDER BY position", (universe_id,)
        )]
        current = conn.execute("SELECT active_symbol FROM canonical_display_selection_v2 WHERE singleton_id=1").fetchone()
        active = normalize_symbol(current[0]) if current else ""
        if active not in eligible and eligible:
            active = eligible[0]
            version = int(row["selection_version"] or 0) + 1
            conn.execute(
                """INSERT INTO canonical_display_selection_v2(singleton_id,universe_id,active_symbol,selection_version,selected_at,updated_at)
                   VALUES(1,?,?,?,?,?) ON CONFLICT(singleton_id) DO UPDATE SET
                   universe_id=excluded.universe_id,active_symbol=excluded.active_symbol,
                   selection_version=excluded.selection_version,selected_at=excluded.selected_at,updated_at=excluded.updated_at""",
                (universe_id, active, version, now, now),
            )
            conn.execute("UPDATE canonical_symbol_universe_v2 SET selection_version=? WHERE universe_id=?", (version, universe_id))
        conn.commit()
        ctx = _context_from_conn(conn, universe_id)
    _publish_to_state(state, ctx)
    return ctx


def select_active_display_symbol(
    symbol: Any,
    *,
    state: MutableMapping[str, Any] | None = None,
    universe_id: str | None = None,
    db_path: str | Path | None = None,
) -> GlobalSymbolContext:
    """Atomically update display identity only—never provider or calculation identity."""
    sym = normalize_symbol(symbol)
    path = Path(db_path or DEFAULT_DB_PATH)
    with _SELECTION_LOCK, _connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        ctx = _context_from_conn(conn, universe_id)
        if not ctx.universe_id:
            raise RuntimeError("NO_GLOBAL_SYMBOL_UNIVERSE")
        eligible = tuple(ctx.completed_symbols or ctx.loaded_symbols)
        if sym not in eligible:
            raise ValueError(f"DISPLAY_SYMBOL_NOT_COMPLETED_OR_LOADED:{sym}")
        version = int(conn.execute(
            "SELECT selection_version FROM canonical_symbol_universe_v2 WHERE universe_id=?", (ctx.universe_id,)
        ).fetchone()[0]) + 1
        now = _utcnow()
        conn.execute(
            """INSERT INTO canonical_display_selection_v2(singleton_id,universe_id,active_symbol,selection_version,selected_at,updated_at)
               VALUES(1,?,?,?,?,?) ON CONFLICT(singleton_id) DO UPDATE SET
               universe_id=excluded.universe_id,active_symbol=excluded.active_symbol,
               selection_version=excluded.selection_version,selected_at=excluded.selected_at,updated_at=excluded.updated_at""",
            (ctx.universe_id, sym, version, now, now),
        )
        conn.execute("UPDATE canonical_symbol_universe_v2 SET selection_version=?,updated_at=? WHERE universe_id=?", (version, now, ctx.universe_id))
        conn.commit()
        updated = _context_from_conn(conn, ctx.universe_id)
    _publish_to_state(state, updated)
    if isinstance(state, MutableMapping):
        for key in list(state):
            if str(key).startswith(("display_cache_", "copy_payload_cache_", "direct_current_copy_payloads_")):
                state.pop(key, None)
        state["global_symbol_display_changed_at_v2"] = _utcnow()
        try:
            from core.global_symbol_exports import refresh_global_export_payloads
            refresh_global_export_payloads(state, updated)
        except Exception as exc:
            state["global_symbol_export_refresh_warning_v2"] = f"{type(exc).__name__}: {exc}"
    return updated


def restore_latest_context(state: MutableMapping[str, Any] | None = None, *, db_path: str | Path | None = None) -> GlobalSymbolContext:
    path = Path(db_path or DEFAULT_DB_PATH)
    try:
        with _SELECTION_LOCK, _connect(path) as conn:
            ctx = _context_from_conn(conn)
    except Exception:
        ctx = _EMPTY
    _publish_to_state(state, ctx)
    return ctx


def loaded_selector_options(context: GlobalSymbolContext) -> list[str]:
    """Only symbols with successful saved evidence are selectable."""
    return list(context.completed_symbols or context.loaded_symbols)


__all__ = [
    "GlobalSymbolContext", "CONTEXT_STATE_KEY", "CONTEXT_VERSION", "normalize_symbol", "normalize_timeframe",
    "get_global_symbol_context", "configure_universe", "mark_universe_loading", "publish_loaded_universe",
    "mark_universe_calculating", "publish_completed_generation", "select_active_display_symbol",
    "validate_symbol_context", "restore_latest_context", "loaded_selector_options",
]

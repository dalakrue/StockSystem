"""Three independent Settings symbol groups with cumulative completed results.

The calculation engine still receives one ordinary ``multi_symbol_selected``
list per button press.  This module only decides which group owns each button
and keeps a separate cumulative display universe so later runs never erase
previously published symbol results.
"""
from __future__ import annotations
from core.global_symbol_compat import set_legacy_calculation_symbol, set_legacy_configured_symbols

from collections.abc import Mapping, MutableMapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import sqlite3

# Backward-compatible default for the second and third selectors. The first
# selector has a larger user-requested capacity.
MAX_SYMBOLS_PER_GROUP = 6
FIRST_GROUP_MAX_SYMBOLS = 10
SECOND_GROUP_MAX_SYMBOLS = 10
THIRD_GROUP_MAX_SYMBOLS = 10
GROUP_LIMITS = {
    "FIRST": FIRST_GROUP_MAX_SYMBOLS,
    "SECOND": SECOND_GROUP_MAX_SYMBOLS,
    "THIRD": THIRD_GROUP_MAX_SYMBOLS,
}


def group_symbol_limit(group: Any) -> int:
    return int(GROUP_LIMITS.get(str(group or "SECOND").strip().upper(), MAX_SYMBOLS_PER_GROUP))
FIRST_GROUP_KEY = "multi_symbol_first_selected_20260706"
SECOND_GROUP_KEY = "multi_symbol_second_selected_20260706"
THIRD_GROUP_KEY = "multi_symbol_third_selected_20260706"
CONFIGURED_UNION_KEY = "multi_symbol_configured_union_20260706"
COMPLETED_UNION_KEY = "multi_symbol_completed_union_20260706"
ACTIVE_GROUP_KEY = "multi_symbol_active_run_group_20260706"
ACTIVE_GROUP_SYMBOLS_KEY = "multi_symbol_active_run_symbols_20260706"
GROUP_PROFILE_VERSION = 20260727

GROUP_KEYS = {
    "FIRST": FIRST_GROUP_KEY,
    "SECOND": SECOND_GROUP_KEY,
    "THIRD": THIRD_GROUP_KEY,
}
# Guest/startup choices requested by the mobile workflow.  They are defaults,
# not locks: current session selections and saved preferences always win.
DEFAULT_GROUPS = {
    "FIRST": ["XAUUSD", "AUDUSD", "EURAUD", "EURCAD", "EURCHF", "EURGBP", "USDCHF", "NZDUSD", "GBPCHF", "GBPAUD"],
    "SECOND": ["GBPUSD", "USDCAD", "USDJPY", "EURJPY", "GBPJPY", "EURUSD", "EURNZD", "GBPCAD", "AUDJPY", "XAGUSD"],
    "THIRD": ["AUDCAD", "AUDCHF", "AUDNZD", "CADCHF", "CADJPY", "CHFJPY", "NZDCAD", "NZDCHF", "NZDJPY", "DXY"],
}
SCOPE_TO_GROUP = {
    "LUNCH_CORE": "FIRST",
    "QUICK": "SECOND",
    "FULL": "THIRD",
}


def normalize_symbol(value: Any) -> str:
    raw = str(value or "").strip().upper().replace("/", "").replace("_", "").replace(" ", "")
    aliases = {
        "XBTUSD": "BTCUSD", "BTCUSDT": "BTCUSD", "GOLD": "XAUUSD",
        "USTEC": "NAS100", "US100": "NAS100", "NDX": "NAS100",
        "SPX500": "US500", "SP500": "US500", "GSPC": "US500",
    }
    return aliases.get(raw, raw)


def normalize_symbols(values: Any, *, limit: int | None = None) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Sequence):
        values = []
    result: list[str] = []
    for value in values:
        symbol = normalize_symbol(value)
        if symbol and symbol not in result:
            result.append(symbol)
        if limit is not None and len(result) >= max(0, int(limit)):
            break
    return result


def union_symbols(*groups: Any) -> list[str]:
    result: list[str] = []
    for group in groups:
        for symbol in normalize_symbols(group):
            if symbol not in result:
                result.append(symbol)
    return result


def split_into_groups(values: Any) -> dict[str, list[str]]:
    symbols = normalize_symbols(values)
    first_end = FIRST_GROUP_MAX_SYMBOLS
    second_end = first_end + SECOND_GROUP_MAX_SYMBOLS
    third_end = second_end + THIRD_GROUP_MAX_SYMBOLS
    return {
        "FIRST": symbols[:first_end],
        "SECOND": symbols[first_end:second_end],
        "THIRD": symbols[second_end:third_end],
    }


def configured_groups(state: Mapping[str, Any]) -> dict[str, list[str]]:
    return {
        name: normalize_symbols(state.get(key), limit=group_symbol_limit(name))
        for name, key in GROUP_KEYS.items()
    }


def initialize_groups(state: MutableMapping[str, Any], fallback_symbols: Any = None, persisted: Mapping[str, Any] | None = None) -> dict[str, list[str]]:
    """Initialize each group once without reviving an explicitly empty selection.

    The previous implementation used truthiness (``current or persisted or
    defaults``).  An intentional empty list was therefore treated as missing and
    repopulated on the next Streamlit rerun.  Presence of the group key, not list
    truthiness, is now authoritative.
    """
    persisted = persisted if isinstance(persisted, Mapping) else {}
    fallback = normalize_symbols(fallback_symbols or state.get("multi_symbol_selected_20260701") or [])
    split = split_into_groups(fallback)
    persisted_is_authoritative = bool(persisted.get("normalized"))
    for name, key in GROUP_KEYS.items():
        if key in state:
            selected = normalize_symbols(state.get(key), limit=group_symbol_limit(name))
        elif persisted_is_authoritative or name.lower() in persisted or name in persisted:
            raw = persisted.get(name.lower()) if name.lower() in persisted else persisted.get(name)
            selected = normalize_symbols(raw, limit=group_symbol_limit(name))
        else:
            selected = normalize_symbols(DEFAULT_GROUPS.get(name) or split.get(name) or [], limit=group_symbol_limit(name))
        state[key] = list(selected)
    groups = configured_groups(state)
    state[CONFIGURED_UNION_KEY] = union_symbols(groups["FIRST"], groups["SECOND"], groups["THIRD"])
    return groups


def symbols_for_scope(state: Mapping[str, Any], scope: Any) -> list[str]:
    group = SCOPE_TO_GROUP.get(str(scope or "").upper(), "SECOND")
    return configured_groups(state).get(group, [])


def default_symbols_for_scope(scope: Any) -> list[str]:
    """Return startup suggestions only; never silently activate them for a run."""
    group = SCOPE_TO_GROUP.get(str(scope or "").upper(), "SECOND")
    return list(DEFAULT_GROUPS.get(group, DEFAULT_GROUPS["SECOND"]))


def resolve_run_symbols(state: Mapping[str, Any], scope: Any) -> list[str]:
    """Return only the user's currently configured symbols for the scope."""
    return symbols_for_scope(state, scope)


def group_for_scope(scope: Any) -> str:
    return SCOPE_TO_GROUP.get(str(scope or "").upper(), "SECOND")


def _payload(result: Any) -> Mapping[str, Any]:
    if not isinstance(result, Mapping):
        return {}
    nested = result.get("result_payload")
    return nested if isinstance(nested, Mapping) else result


def completed_from_result(symbols: Any, result: Any) -> list[str]:
    requested = normalize_symbols(symbols)
    payload = _payload(result)
    statuses = payload.get("symbol_status")
    if isinstance(statuses, Mapping):
        complete: list[str] = []
        for symbol in requested:
            row = statuses.get(symbol)
            if not isinstance(row, Mapping):
                continue
            status = str(row.get("state") or row.get("publication_status") or row.get("status") or "").upper()
            if status == "COMPLETED":
                complete.append(symbol)
        if complete:
            return complete
    outer_status = result.get("status") if isinstance(result, Mapping) else ""
    status = str(payload.get("status") or outer_status or "").upper()
    failed = int(payload.get("failed_symbols") or 0) if payload else 0
    completed_count = payload.get("completed_symbols") if payload else None
    if status == "COMPLETED" and not failed:
        return requested
    if isinstance(completed_count, int) and completed_count == len(requested) and not failed:
        return requested
    return []


def record_completed_symbols(state: MutableMapping[str, Any], symbols: Any, result: Any) -> list[str]:
    completed = completed_from_result(symbols, result)
    existing = normalize_symbols(state.get(COMPLETED_UNION_KEY) or [])
    merged = union_symbols(existing, completed)
    state[COMPLETED_UNION_KEY] = merged
    state["multi_symbol_display_universe_20260706"] = list(merged)
    return merged


def mark_run_group(state: MutableMapping[str, Any], scope: Any, symbols: Any) -> tuple[str, list[str]]:
    group = group_for_scope(scope)
    # A run button controls calculation depth, not one selector subset. The
    # active transaction may contain the cumulative union loaded by all three
    # selectors; each selector can hold up to 10 symbols and the canonical transaction uses the first 30 unique symbols.
    selected = normalize_symbols(symbols)
    state[ACTIVE_GROUP_KEY] = group
    state[ACTIVE_GROUP_SYMBOLS_KEY] = list(selected)
    set_legacy_configured_symbols(state, list(selected))
    if selected:
        state["requested_symbol_20260629"] = selected[0]
        set_legacy_calculation_symbol(state, selected[0], connector=True)
    return group, selected



def discover_completed_symbols(db_path: str | Path) -> list[str]:
    """Recover already-published symbols when upgrading an existing database.

    The preference row is new in this repair, so the first app start must seed
    its cumulative universe from append-only production tables rather than
    hiding valid results calculated before this version was installed.
    """
    path = Path(db_path)
    if not path.exists():
        return []
    discovered: list[str] = []
    try:
        with sqlite3.connect(str(path), timeout=8) as conn:
            conn.execute("PRAGMA busy_timeout=8000")
            tables = {str(row[0]) for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            queries = []
            if "field10_daily_higher_lock" in tables:
                queries.append(
                    "SELECT symbol FROM field10_daily_higher_lock "
                    "WHERE broker_day=(SELECT MAX(broker_day) FROM field10_daily_higher_lock) "
                    "AND symbol IS NOT NULL AND TRIM(symbol)<>'' "
                    "ORDER BY rank ASC, symbol"
                )
            if "field10_daily_snapshot_symbol" in tables:
                queries.append(
                    "SELECT symbol FROM field10_daily_snapshot_symbol "
                    "WHERE broker_day=(SELECT MAX(broker_day) FROM field10_daily_snapshot_symbol) "
                    "AND symbol IS NOT NULL AND TRIM(symbol)<>'' "
                    "ORDER BY daily_rank ASC, symbol"
                )
            for query in queries:
                try:
                    discovered.extend(row[0] for row in conn.execute(query).fetchall())
                except sqlite3.Error:
                    continue
            if not normalize_symbols(discovered) and "multi_symbol_runs" in tables:
                columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(multi_symbol_runs)").fetchall()}
                status_filter = (
                    " WHERE UPPER(COALESCE(status,''))='COMPLETED'"
                    if "status" in columns else ""
                )
                try:
                    discovered.extend(row[0] for row in conn.execute(
                        "SELECT symbol FROM multi_symbol_runs" + status_filter + " ORDER BY rowid DESC LIMIT 18"
                    ).fetchall())
                except sqlite3.Error:
                    pass
    except Exception:
        return []
    return normalize_symbols(discovered)

def load_group_preferences(db_path: str | Path) -> dict[str, Any]:
    path = Path(db_path)
    if not path.exists():
        return {}
    # Prefer normalized current rows.  Empty groups are meaningful and must not
    # be replaced by startup defaults after a session restart.
    try:
        from core.normalized_multi_symbol_migration_20260707 import load_current_selections
        normalized = load_current_selections(path)
        if isinstance(normalized, Mapping):
            result = dict(normalized)
            try:
                with sqlite3.connect(str(path), timeout=5) as conn:
                    row = conn.execute(
                        "SELECT completed_symbols_json,profile_version FROM runtime_symbol_groups_20260706 WHERE preference_id=1"
                    ).fetchone()
                result["completed"] = json.loads(row[0] or "[]") if row else []
                result["profile_version"] = int(row[1] or 0) if row else GROUP_PROFILE_VERSION
            except Exception:
                result.setdefault("completed", [])
                result.setdefault("profile_version", GROUP_PROFILE_VERSION)
            # This release intentionally upgrades the old empty starter profile
            # to the requested 10 + 10 + 10 Top-30 defaults exactly once.
            if (
                int(result.get("profile_version") or 0) < GROUP_PROFILE_VERSION
                and not any(result.get(name) for name in ("first", "second", "third"))
            ):
                result.update({
                    "first": list(DEFAULT_GROUPS["FIRST"]),
                    "second": list(DEFAULT_GROUPS["SECOND"]),
                    "third": list(DEFAULT_GROUPS["THIRD"]),
                    "profile_version": GROUP_PROFILE_VERSION,
                })
            return result
    except Exception:
        pass
    try:
        with sqlite3.connect(str(path), timeout=5) as conn:
            row = conn.execute(
                """SELECT first_symbols_json,second_symbols_json,third_symbols_json,
                          completed_symbols_json,profile_version
                   FROM runtime_symbol_groups_20260706 WHERE preference_id=1"""
            ).fetchone()
        if not row:
            return {}
        return {
            "first": json.loads(row[0] or "[]"),
            "second": json.loads(row[1] or "[]"),
            "third": json.loads(row[2] or "[]"),
            "completed": json.loads(row[3] or "[]"),
            "profile_version": int(row[4] or 0),
        }
    except Exception:
        return {}


def save_group_preferences(db_path: str | Path, state_or_groups: Mapping[str, Any], *, completed: Any = None) -> None:
    path = Path(db_path)
    try:
        from core.data.deployment_migrations_20260705 import migrate_deployment_schema
        migrate_deployment_schema(path)
    except Exception:
        # The legacy lazy CREATE below remains a deployment-safe fallback.
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    if any(key in state_or_groups for key in GROUP_KEYS.values()):
        groups = configured_groups(state_or_groups)
        completed_symbols = normalize_symbols(completed if completed is not None else state_or_groups.get(COMPLETED_UNION_KEY) or [])
    else:
        groups = {}
        for name in GROUP_KEYS:
            if name in state_or_groups:
                raw = state_or_groups[name]
            elif name.lower() in state_or_groups:
                raw = state_or_groups[name.lower()]
            else:
                raw = []
            groups[name] = normalize_symbols(raw, limit=group_symbol_limit(name))
        completed_symbols = normalize_symbols(completed or state_or_groups.get("completed") or [])
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(path), timeout=10) as conn:
        conn.execute("PRAGMA busy_timeout=8000")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS runtime_symbol_groups_20260706(
                   preference_id INTEGER PRIMARY KEY CHECK(preference_id=1),
                   first_symbols_json TEXT NOT NULL,
                   second_symbols_json TEXT NOT NULL,
                   third_symbols_json TEXT NOT NULL,
                   completed_symbols_json TEXT NOT NULL,
                   updated_at TEXT NOT NULL,
                   profile_version INTEGER NOT NULL
               )"""
        )
        conn.execute(
            """INSERT INTO runtime_symbol_groups_20260706(
                   preference_id,first_symbols_json,second_symbols_json,third_symbols_json,
                   completed_symbols_json,updated_at,profile_version)
               VALUES(1,?,?,?,?,?,?) ON CONFLICT(preference_id) DO UPDATE SET
                   first_symbols_json=excluded.first_symbols_json,
                   second_symbols_json=excluded.second_symbols_json,
                   third_symbols_json=excluded.third_symbols_json,
                   completed_symbols_json=excluded.completed_symbols_json,
                   updated_at=excluded.updated_at,profile_version=excluded.profile_version""",
            (
                json.dumps(groups["FIRST"]), json.dumps(groups["SECOND"]), json.dumps(groups["THIRD"]),
                json.dumps(completed_symbols), now, GROUP_PROFILE_VERSION,
            ),
        )
        conn.commit()
    try:
        from core.normalized_multi_symbol_migration_20260707 import replace_current_selections
        replace_current_selections(
            path, groups,
            state_or_groups.get("timeframe") or state_or_groups.get("selected_timeframe") or "H4",
            updated_at=now,
        )
    except Exception:
        # Legacy JSON persistence remains valid; normalized migration is retried
        # at startup and on the next save.
        pass


__all__ = [
    "MAX_SYMBOLS_PER_GROUP", "FIRST_GROUP_MAX_SYMBOLS", "SECOND_GROUP_MAX_SYMBOLS",
    "THIRD_GROUP_MAX_SYMBOLS", "GROUP_LIMITS", "group_symbol_limit",
    "FIRST_GROUP_KEY", "SECOND_GROUP_KEY", "THIRD_GROUP_KEY",
    "CONFIGURED_UNION_KEY", "COMPLETED_UNION_KEY", "ACTIVE_GROUP_KEY", "ACTIVE_GROUP_SYMBOLS_KEY",
    "GROUP_KEYS", "DEFAULT_GROUPS", "SCOPE_TO_GROUP", "normalize_symbols", "union_symbols", "split_into_groups",
    "configured_groups", "initialize_groups", "symbols_for_scope", "default_symbols_for_scope", "resolve_run_symbols", "group_for_scope",
    "record_completed_symbols", "mark_run_group", "discover_completed_symbols",
    "load_group_preferences", "save_group_preferences",
]

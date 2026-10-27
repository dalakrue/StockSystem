"""Single authority for selected symbols, timeframe, and completed-candle identity.

The module is intentionally Streamlit-optional so it can be used by migrations,
tests, connector code, and UI code without creating widget side effects.
"""
from __future__ import annotations
from core.global_symbol_compat import set_legacy_calculation_symbol, set_legacy_configured_symbols

from collections.abc import Mapping, MutableMapping, Sequence
from datetime import datetime, timezone
from typing import Any
import json
import sqlite3
from pathlib import Path

from core.timeframe_window_contract_20260706 import TIMEFRAME_SECONDS as SHARED_TIMEFRAME_SECONDS, selected_timeframe

TOP_10_CURRENCY_PAIRS: tuple[str, ...] = (
    "EURUSD", "USDJPY", "AUDUSD", "GBPUSD", "USDCAD",
    "USDCHF", "EURJPY", "GBPJPY", "EURGBP", "NZDUSD",
)
SUPPORTED_TIMEFRAMES: tuple[str, ...] = tuple(SHARED_TIMEFRAME_SECONDS)
TIMEFRAME_SECONDS: dict[str, int] = dict(SHARED_TIMEFRAME_SECONDS)
SELECTED_KEY = "multi_symbol_selected_20260701"
TIMEFRAME_KEY = "timeframe"
CANONICAL_SELECTION_KEY = "canonical_runtime_selection_20260705"
FIRST_LOAD_KEY = "top10_default_initialized_20260705"
SELECTION_PROFILE_VERSION = 20260706
DEFAULT_TIMEFRAME = "H4"


def normalize_symbol(value: Any, default: str = "EURUSD") -> str:
    raw = str(value or default).strip().upper().replace("/", "").replace(" ", "")
    aliases = {
        "XBTUSD": "BTCUSD", "BTCUSDT": "BTCUSD", "GOLD": "XAUUSD",
        "USTEC": "NAS100", "US100": "NAS100", "NDX": "NAS100",
        "SPX500": "US500", "SP500": "US500", "GSPC": "US500",
    }
    return aliases.get(raw, raw) or default


def normalize_symbols(values: Any, *, default_top10: bool = False) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Sequence):
        values = []
    out: list[str] = []
    for value in values:
        symbol = normalize_symbol(value)
        if symbol and symbol not in out:
            out.append(symbol)
    return out or (list(TOP_10_CURRENCY_PAIRS) if default_top10 else [])


def normalize_timeframe(value: Any, default: str = DEFAULT_TIMEFRAME) -> str:
    raw = str(value or default).strip().upper().replace(" ", "")
    aliases = {"1H": "H1", "4H": "H4", "60MIN": "H1", "240MIN": "H4", "1DAY": "D1"}
    raw = aliases.get(raw, raw)
    return raw if raw in SUPPORTED_TIMEFRAMES else default


def timeframe_seconds(timeframe: Any) -> int:
    return TIMEFRAME_SECONDS[normalize_timeframe(timeframe)]


def latest_completed_candle(
    now: datetime | None = None,
    timeframe: Any = DEFAULT_TIMEFRAME,
    *,
    settlement_delay_minutes: int = 3,
) -> datetime:
    """Return the latest fully settled UTC candle open time.

    H4 boundaries are aligned to 00:00/04:00/08:00/... UTC. A configurable
    settlement delay prevents fetching the candle while the provider is still
    publishing it.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    seconds = timeframe_seconds(timeframe)
    adjusted_epoch = int(now.timestamp()) - max(0, int(settlement_delay_minutes)) * 60
    current_open_epoch = adjusted_epoch - (adjusted_epoch % seconds)
    completed_open_epoch = current_open_epoch - seconds
    return datetime.fromtimestamp(completed_open_epoch, tz=timezone.utc)


def cache_identity(symbol: Any, timeframe: Any, completed: datetime | str | None = None) -> str:
    completed_dt = completed or latest_completed_candle(timeframe=timeframe)
    if isinstance(completed_dt, datetime):
        completed_text = completed_dt.astimezone(timezone.utc).isoformat()
    else:
        completed_text = str(completed_dt)
    return f"{normalize_symbol(symbol)}|{normalize_timeframe(timeframe)}|{completed_text}"


def synchronize_runtime_selection(
    state: MutableMapping[str, Any],
    *,
    default_top10_on_first_load: bool = False,
    persisted: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Mirror the durable GlobalSymbolContext into legacy runtime state.

    This function is a compatibility facade, not a symbol authority.  It never
    creates a Top-10/EURUSD universe and never changes connector/calculation
    identity merely because the display symbol changed.
    """
    persisted = persisted if isinstance(persisted, Mapping) else {}
    try:
        persisted_profile_current = int(persisted.get("selection_profile_version") or 0) >= SELECTION_PROFILE_VERSION
    except Exception:
        persisted_profile_current = False
    raw_state_context = state.get("global_symbol_context_v2")
    state_has_authoritative_context = isinstance(raw_state_context, Mapping) and bool(raw_state_context.get("universe_id"))
    try:
        from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH as _DB
        from core.global_symbol_context import get_global_symbol_context
        from core.global_symbol_compat import mirror_context_to_legacy_state
        # A current persisted profile must beat fresh-session placeholder values
        # such as the default H4/EURUSD. Only an already-published context in the
        # supplied state may override it. This prevents external/default state
        # from silently changing the user's saved global selection.
        if persisted_profile_current and not state_has_authoritative_context:
            context = None
        else:
            context = get_global_symbol_context(state, db_path=_DB, restore=True)
    except Exception:
        context = None

    if context is not None and getattr(context, "universe_id", ""):
        selected = list(context.configured_symbols)
        timeframe = normalize_timeframe(context.timeframe, default=DEFAULT_TIMEFRAME)
        active = normalize_symbol(context.active_display_symbol, default="")
        mirror_context_to_legacy_state(state, context)
    else:
        current = normalize_symbols(state.get(SELECTED_KEY), default_top10=False)
        saved = normalize_symbols(persisted.get("selected_symbols"), default_top10=False)
        # Current durable preferences outrank fresh-session placeholder widget
        # defaults. An intentional current selection still outranks persistence.
        selected = current or (saved if persisted_profile_current else [])
        state_has_intentional_selection = bool(current)
        timeframe_candidate = (
            state.get("selected_timeframe") if state_has_intentional_selection else None
        ) or (
            persisted.get("timeframe") if persisted_profile_current else None
        ) or state.get(TIMEFRAME_KEY) or DEFAULT_TIMEFRAME
        timeframe = normalize_timeframe(timeframe_candidate, default=DEFAULT_TIMEFRAME)
        active_candidate = (
            persisted.get("active_display_symbol") if persisted_profile_current else None
        ) or state.get("canonical_display_symbol_20260709") or state.get("lunch_display_symbol_20260702")
        active = normalize_symbol(active_candidate, default="")
        if active not in selected:
            active = ""
        set_legacy_configured_symbols(state, selected)
        if active:
            for key in ("canonical_display_symbol_20260709", "lunch_display_symbol_20260702", "multi_symbol_active_20260701"):
                state[key] = active

    # Connector/calculation are independent transactional identities.  Preserve
    # them if they are already present; do not synthesize one from display state.
    connector = normalize_symbol(state.get("connector_symbol_20260702") or state.get("connector_symbol"), default="")
    calculation = normalize_symbol(state.get("calculation_symbol_20260702") or state.get("calculation_symbol"), default="")
    main = normalize_symbol(state.get("multi_symbol_main_symbol_20260702") or state.get("settings_main_symbol"), default="")
    if main and main not in selected:
        main = ""

    state[TIMEFRAME_KEY] = timeframe
    state["selected_timeframe"] = timeframe
    state[FIRST_LOAD_KEY] = True
    completed = str(getattr(context, "latest_completed_candle", "") or "") if context is not None else ""
    canonical = {
        "selected_symbols": list(selected),
        "main_symbol": main,
        "settings_main_symbol": main,
        "connector_symbol": connector,
        "calculation_symbol": calculation,
        "lunch_display_symbol": active,
        "active_snapshot_symbol": active,
        "active_symbol": active,
        "timeframe": timeframe,
        "latest_completed_candle": completed,
        "universe_id": str(getattr(context, "universe_id", "") or "") if context is not None else "",
        "generation": int(getattr(context, "generation", 0) or 0) if context is not None else 0,
        "snapshot_hash": str(getattr(context, "snapshot_hash", "") or "") if context is not None else "",
        "publication_status": str(getattr(context, "publication_status", "EMPTY") or "EMPTY") if context is not None else "EMPTY",
    }
    state[CANONICAL_SELECTION_KEY] = canonical
    return canonical


def load_runtime_preferences(db_path: str | Path) -> dict[str, Any]:
    path = Path(db_path)
    if not path.exists():
        return {}
    try:
        with sqlite3.connect(str(path), timeout=5) as conn:
            columns = {str(item[1]) for item in conn.execute("PRAGMA table_info(runtime_preferences)").fetchall()}
            version_expr = "selection_profile_version" if "selection_profile_version" in columns else "0"
            active_expr = "active_display_symbol" if "active_display_symbol" in columns else "NULL"
            row = conn.execute(
                f"SELECT selected_symbols_json,timeframe,{version_expr},{active_expr} FROM runtime_preferences WHERE preference_id=1"
            ).fetchone()
        if not row:
            return {}
        return {
            "selected_symbols": json.loads(row[0] or "[]"),
            "timeframe": row[1] or DEFAULT_TIMEFRAME,
            "selection_profile_version": int(row[2] or 0),
            "active_display_symbol": normalize_symbol(row[3]) if len(row) > 3 and row[3] else None,
        }
    except Exception:
        return {}


def save_runtime_preferences(db_path: str | Path, selected_symbols: Sequence[Any], timeframe: Any) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    symbols = normalize_symbols(selected_symbols, default_top10=True)
    tf = normalize_timeframe(timeframe)
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(path), timeout=10) as conn:
        conn.execute("PRAGMA busy_timeout=8000")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS runtime_preferences(
                   preference_id INTEGER PRIMARY KEY CHECK(preference_id=1),
                   selected_symbols_json TEXT NOT NULL,
                   timeframe TEXT NOT NULL,
                   updated_at TEXT NOT NULL
               )"""
        )
        columns = {str(item[1]) for item in conn.execute("PRAGMA table_info(runtime_preferences)").fetchall()}
        if "selection_profile_version" not in columns:
            conn.execute("ALTER TABLE runtime_preferences ADD COLUMN selection_profile_version INTEGER NOT NULL DEFAULT 0")
        if "active_display_symbol" not in columns:
            conn.execute("ALTER TABLE runtime_preferences ADD COLUMN active_display_symbol TEXT")
        conn.execute(
            """INSERT INTO runtime_preferences(
                   preference_id,selected_symbols_json,timeframe,updated_at,selection_profile_version)
               VALUES(1,?,?,?,?) ON CONFLICT(preference_id) DO UPDATE SET
               selected_symbols_json=excluded.selected_symbols_json,
               timeframe=excluded.timeframe,updated_at=excluded.updated_at,
               selection_profile_version=excluded.selection_profile_version""",
            (json.dumps(symbols), tf, now, SELECTION_PROFILE_VERSION),
        )
        conn.commit()


def save_active_display_symbol(db_path: str | Path, symbol: Any) -> None:
    """Persist the cross-tab display symbol without changing the loaded universe."""
    path = Path(db_path)
    if not path.exists():
        return
    sym = normalize_symbol(symbol)
    with sqlite3.connect(str(path), timeout=10) as conn:
        conn.execute("PRAGMA busy_timeout=8000")
        columns = {str(item[1]) for item in conn.execute("PRAGMA table_info(runtime_preferences)").fetchall()}
        if not columns:
            return
        if "active_display_symbol" not in columns:
            conn.execute("ALTER TABLE runtime_preferences ADD COLUMN active_display_symbol TEXT")
        conn.execute("UPDATE runtime_preferences SET active_display_symbol=? WHERE preference_id=1", (sym,))
        conn.commit()


__all__ = [
    "TOP_10_CURRENCY_PAIRS", "SUPPORTED_TIMEFRAMES", "TIMEFRAME_SECONDS",
    "SELECTED_KEY", "CANONICAL_SELECTION_KEY", "normalize_symbol",
    "normalize_symbols", "normalize_timeframe", "timeframe_seconds",
    "latest_completed_candle", "cache_identity", "synchronize_runtime_selection",
    "load_runtime_preferences", "save_runtime_preferences", "save_active_display_symbol", "SELECTION_PROFILE_VERSION", "DEFAULT_TIMEFRAME",
]

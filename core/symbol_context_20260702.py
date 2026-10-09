"""Authoritative immutable symbol identity contract for Settings and Lunch.

The project still contains legacy readers of ``session_state['symbol']``.  That
key is treated only as a compatibility mirror for the currently activated
snapshot.  It is never the authority for Settings, connector ownership, Lunch
selection, child calculation identity, or publication identity.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any
import json

import pandas as pd

MAIN_SYMBOL_KEY = "multi_symbol_main_symbol_20260702"
SELECTED_SYMBOLS_KEY = "multi_symbol_selected_20260701"
LUNCH_DISPLAY_SYMBOL_KEY = "lunch_display_symbol_20260702"
ACTIVE_SNAPSHOT_SYMBOL_KEY = "active_snapshot_symbol_20260702"
CONNECTOR_SYMBOL_KEY = "connector_symbol_20260702"
CALCULATION_SYMBOL_KEY = "calculation_symbol_20260702"
PARENT_RUN_KEY = "multi_symbol_parent_run_id_20260701"
CHILD_RUN_KEY = "multi_symbol_child_run_active_20260701"
GENERATION_REGISTRY_STATE_KEY = "generation_registry_active_20260702"

# Kept local to avoid importing the heavy multi-symbol engine from Settings.
SUPPORTED_SYMBOLS: tuple[str, ...] = (
    "EURUSD", "USDJPY", "AUDUSD", "GBPUSD", "USDCAD", "USDCHF", "EURJPY", "GBPJPY", "EURGBP", "NZDUSD",
    "EURCHF", "EURAUD", "EURCAD", "EURNZD", "GBPCHF", "GBPAUD", "GBPCAD", "AUDJPY",
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "GOOGL", "AVGO", "JPM", "AMD",
    "NAS100", "US500", "US30", "DAX40", "UK100", "JPN225", "HK50", "FRA40", "AUS200", "EU50",
    "XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD", "COPPER",
    "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BNBUSD", "ADAUSD", "DOGEUSD", "AVAXUSD", "DOTUSD", "LINKUSD",
)


def _normalize_raw(value: Any) -> str:
    raw = str(value or "").strip().upper().replace("/", "").replace(" ", "")
    aliases = {
        "XBTUSD": "BTCUSD", "BTCUSDT": "BTCUSD", "GOLD": "XAUUSD",
        "USTEC": "NAS100", "US100": "NAS100", "NDX": "NAS100", "NASDAQ100": "NAS100",
        "SPX500": "US500", "SP500": "US500", "SPX": "US500", "GSPC": "US500", "^GSPC": "US500",
    }
    return aliases.get(raw, raw)


def normalize_symbol(value: Any, default: str = "EURUSD") -> str:
    normalized = _normalize_raw(value) or _normalize_raw(default) or "EURUSD"
    if normalized in SUPPORTED_SYMBOLS:
        return normalized
    fallback = _normalize_raw(default)
    return fallback if fallback in SUPPORTED_SYMBOLS else "EURUSD"


def normalize_selected(values: Any, *, main: str | None = None) -> tuple[str, ...]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Sequence):
        values = []
    ordered: list[str] = []
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        symbol = _normalize_raw(raw)
        if symbol in SUPPORTED_SYMBOLS and symbol not in ordered:
            ordered.append(symbol)
    if main:
        main_symbol = normalize_symbol(main)
        ordered = [main_symbol, *[symbol for symbol in ordered if symbol != main_symbol]]
    return tuple(ordered)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _canonical(state: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        from core.canonical_lookup_20260626 import resolve_canonical
        return resolve_canonical(state)
    except Exception:
        for key in ("canonical_decision_result_20260617", "canonical_result_20260617", "last_valid_canonical_decision_result_20260617"):
            value = state.get(key)
            if isinstance(value, Mapping):
                return value
    return {}


def _iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp):
            return None
        return stamp.isoformat()
    except Exception:
        return str(value)


def _valid_generation_symbols(state: Mapping[str, Any]) -> tuple[str, ...]:
    manifest = _mapping(state.get("multi_symbol_manifest_20260701"))
    statuses = _mapping(manifest.get("symbol_status"))
    completed = [
        normalize_symbol(symbol)
        for symbol, detail in statuses.items()
        if str(_mapping(detail).get("status") or "").upper() == "COMPLETED"
    ]
    registry = _mapping(state.get(GENERATION_REGISTRY_STATE_KEY))
    registry_symbols = registry.get("selected_symbols") or registry.get("completed_symbols") or []
    for symbol in normalize_selected(registry_symbols):
        if symbol not in completed:
            completed.append(symbol)
    return tuple(completed)


@dataclass(frozen=True, slots=True)
class SymbolContext:
    settings_main_symbol: str
    connector_symbol: str
    calculation_symbol: str | None
    lunch_display_symbol: str
    active_snapshot_symbol: str
    selected_symbols: tuple[str, ...]
    timeframe: str
    parent_run_id: str | None
    child_run_id: str | None
    canonical_run_id: str | None
    source_id: str | None
    snapshot_hash: str | None
    completed_broker_candle: str | None
    generation_status: str
    valid_until: str | None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["selected_symbols"] = list(self.selected_symbols)
        return data

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), default=str)
        return sha256(payload.encode("utf-8")).hexdigest()

    def copy_fingerprint(self, schema_version: str = "copy-schema-20260702-v1") -> str:
        payload = {
            "copy_schema_version": schema_version,
            "parent_run_id": self.parent_run_id,
            "child_run_id": self.child_run_id,
            "lunch_display_symbol": self.lunch_display_symbol,
            "canonical_run_id": self.canonical_run_id,
            "snapshot_hash": self.snapshot_hash,
            "completed_broker_candle": self.completed_broker_candle,
        }
        return sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def resolve_symbol_context(
    state: Mapping[str, Any],
    route: str,
    requested_lunch_symbol: Any = None,
) -> SymbolContext:
    """Resolve a read-only legacy view from GlobalSymbolContext.

    ``requested_lunch_symbol`` is accepted only for compatibility and is never
    promoted into a second authority.  A differing request is ignored until the
    global selector service persists it atomically.
    """
    try:
        from core.global_symbol_context import get_global_symbol_context
        global_context = get_global_symbol_context(state, restore=True)
    except Exception:
        global_context = None
    configured = tuple(getattr(global_context, "configured_symbols", ()) or ())
    loaded = tuple(getattr(global_context, "loaded_symbols", ()) or ())
    completed = tuple(getattr(global_context, "completed_symbols", ()) or ())
    active = _normalize_raw(getattr(global_context, "active_display_symbol", ""))
    eligible = completed or loaded
    if active not in eligible:
        active = eligible[0] if eligible else ""
    main = _normalize_raw(state.get(MAIN_SYMBOL_KEY) or state.get("settings_main_symbol"))
    if main not in configured:
        main = ""
    connector = _normalize_raw(state.get(CONNECTOR_SYMBOL_KEY) or state.get("connector_symbol") or state.get("ws_symbol"))
    calculation = _normalize_raw(state.get(CALCULATION_SYMBOL_KEY) or state.get("calculation_symbol")) or None
    child_meta = _mapping(state.get(CHILD_RUN_KEY))
    canonical = _canonical(state)
    return SymbolContext(
        settings_main_symbol=main,
        connector_symbol=connector,
        calculation_symbol=calculation,
        lunch_display_symbol=active,
        active_snapshot_symbol=active,
        selected_symbols=configured,
        timeframe=str(getattr(global_context, "timeframe", "") or state.get("timeframe") or ""),
        parent_run_id=str(getattr(global_context, "parent_run_id", "") or state.get(PARENT_RUN_KEY) or "") or None,
        child_run_id=str(child_meta.get("child_run_id") or "") or None,
        canonical_run_id=str(canonical.get("run_id") or canonical.get("canonical_calculation_id") or "") or None,
        source_id=str(canonical.get("source_id") or canonical.get("data_source_id") or "") or None,
        snapshot_hash=str(getattr(global_context, "snapshot_hash", "") or canonical.get("snapshot_hash") or canonical.get("source_snapshot_hash") or "") or None,
        completed_broker_candle=_iso(getattr(global_context, "latest_completed_candle", "") or canonical.get("completed_broker_candle") or canonical.get("broker_candle_time")),
        generation_status=str(getattr(global_context, "publication_status", "EMPTY") or "EMPTY"),
        valid_until=_iso(canonical.get("valid_until") or canonical.get("expires_at")),
    )


def publish_context_state(state: MutableMapping[str, Any], context: SymbolContext) -> None:
    """Publish only authoritative context keys; connector ownership is preserved."""
    from core.global_symbol_compat import set_legacy_calculation_symbol
    if context.settings_main_symbol:
        set_legacy_calculation_symbol(state, context.settings_main_symbol, connector=True)
    state[SELECTED_SYMBOLS_KEY] = list(context.selected_symbols)
    state[LUNCH_DISPLAY_SYMBOL_KEY] = context.lunch_display_symbol
    state[ACTIVE_SNAPSHOT_SYMBOL_KEY] = context.active_snapshot_symbol
    state.setdefault(CONNECTOR_SYMBOL_KEY, context.connector_symbol)
    if context.calculation_symbol:
        state[CALCULATION_SYMBOL_KEY] = context.calculation_symbol
    else:
        state.pop(CALCULATION_SYMBOL_KEY, None)
    state["resolved_symbol_context_20260702"] = context.to_dict()


def identity_invariants(state: Mapping[str, Any], route: str = "Lunch") -> dict[str, Any]:
    context = resolve_symbol_context(state, route)
    canonical = _canonical(state)
    canonical_symbol = normalize_symbol(canonical.get("symbol") or context.active_snapshot_symbol)
    checks = {
        "top_market_symbol": normalize_symbol(state.get("top_market_symbol_20260702") or context.lunch_display_symbol),
        "canonical_symbol": canonical_symbol,
        "field1_symbol": normalize_symbol(state.get("field1_active_symbol_20260702") or canonical_symbol),
        "field2_symbol": normalize_symbol(state.get("field2_active_symbol_20260702") or canonical_symbol),
        "field3_symbol": normalize_symbol(state.get("field3_active_symbol_20260702") or canonical_symbol),
        "field10_symbol": normalize_symbol(state.get("field10_active_symbol_20260702") or context.lunch_display_symbol),
        "copy_symbol": normalize_symbol(state.get("copy_active_symbol_20260702") or context.lunch_display_symbol),
    }
    target = context.lunch_display_symbol
    failures = {name: value for name, value in checks.items() if value != target}
    return {"ok": not failures, "target": target, "checks": checks, "failures": failures, "context": context.to_dict()}


__all__ = [
    "SymbolContext", "resolve_symbol_context", "publish_context_state", "identity_invariants",
    "normalize_symbol", "normalize_selected", "SUPPORTED_SYMBOLS", "MAIN_SYMBOL_KEY",
    "SELECTED_SYMBOLS_KEY", "LUNCH_DISPLAY_SYMBOL_KEY", "ACTIVE_SNAPSHOT_SYMBOL_KEY",
    "CONNECTOR_SYMBOL_KEY", "CALCULATION_SYMBOL_KEY", "GENERATION_REGISTRY_STATE_KEY",
]

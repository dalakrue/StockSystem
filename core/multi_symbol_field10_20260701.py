"""Multi-symbol orchestration and Lunch Field 10 persistence.

This module is additive.  It reuses the existing single-symbol Settings-owned
calculation transaction, stores each completed symbol generation separately,
and exposes read-only cross-symbol quality/regime evidence to Lunch Field 10.
No protected calculation, decision, priority, BFP/SFP, or Field 1-9 formula is
replaced here.
"""
# Legacy compatibility marker; never execute from render: migrate_and_verify_field10(DB_PATH)
from __future__ import annotations
from core.global_symbol_compat import set_legacy_calculation_symbol, clear_legacy_calculation_symbol

from collections.abc import Callable, Mapping, MutableMapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
import gzip
import json
import os
import sqlite3
import time
import uuid

import numpy as np
import pandas as pd

from core.sqlite_readonly_20260704 import connect_readonly

from core.serialization_compat_20260702 import loads as serializer_loads

VERSION = "multi-symbol-field10-20260703-v3"
TOP_10_CURRENCY_PAIRS: tuple[str, ...] = (
    "EURUSD", "USDJPY", "AUDUSD", "GBPUSD", "USDCAD", "USDCHF", "EURJPY", "GBPJPY", "EURGBP", "NZDUSD",
)

SUPPORTED_SYMBOLS: tuple[str, ...] = (
    # Top FX pairs
    "EURUSD", "USDJPY", "AUDUSD", "GBPUSD", "USDCAD", "USDCHF", "EURJPY", "GBPJPY", "EURGBP", "NZDUSD",
    "EURCHF", "EURAUD", "EURCAD", "EURNZD", "GBPCHF", "GBPAUD", "GBPCAD", "AUDJPY",
    # High-volume equities
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "GOOGL", "AVGO", "JPM", "AMD",
    # Indices
    "NAS100", "US500", "US30", "DAX40", "UK100", "JPN225", "HK50", "FRA40", "AUS200", "EU50",
    # Metals
    "XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD", "COPPER",
    # Crypto
    "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BNBUSD", "ADAUSD", "DOGEUSD", "AVAXUSD", "DOTUSD", "LINKUSD",
)

# Canonical names remain provider-neutral.  Provider aliases are resolved only
# at the connector boundary, so one provider's naming convention is never
# imposed on the rest of the application.
PROVIDER_ALIASES: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "canonical": {
        "BTCUSD": ("BTCUSD", "BTC/USD", "XBTUSD"),
        "XAUUSD": ("XAUUSD", "XAU/USD", "GOLD"),
        "NAS100": ("NAS100", "USTEC", "NDX", "US100", "NASDAQ100"),
        "US500": ("US500", "SPX500", "SPX", "SP500", "^GSPC", "GSPC"),
        "US30": ("US30", "DJI", "DOW", "^DJI"),
        "DAX40": ("DAX40", "GER40", "DAX"),
        "UK100": ("UK100", "FTSE", "FTSE100"),
        "JPN225": ("JPN225", "NIKKEI", "JP225"),
        "XAGUSD": ("XAGUSD", "XAG/USD", "SILVER"),
        "ETHUSD": ("ETHUSD", "ETH/USD", "ETHUSDT"),
    },
    "twelve": {
        "BTCUSD": ("BTC/USD", "BTCUSD"),
        "XAUUSD": ("XAU/USD", "XAUUSD"),
        "NAS100": ("NDX", "NASDAQ100", "NAS100"),
        "US500": ("SPX", "GSPC", "US500"),
        "US30": ("DJI", "DOW", "US30"),
        "DAX40": ("DAX", "DAX40", "GER40"),
        "UK100": ("FTSE", "UK100"),
        "XAGUSD": ("XAG/USD", "XAGUSD"),
        "ETHUSD": ("ETH/USD", "ETHUSD"),
    },
    "finnhub": {
        "BTCUSD": ("BINANCE:BTCUSDT", "COINBASE:BTC-USD", "BTCUSD"),
        "XAUUSD": ("OANDA:XAU_USD", "XAUUSD"),
        "NAS100": ("^NDX", "NDX", "NAS100"),
        "US500": ("^GSPC", "SPX", "US500"),
        "US30": ("^DJI", "DJI", "US30"),
        "DAX40": ("^GDAXI", "DAX", "DAX40"),
        "UK100": ("^FTSE", "UK100"),
        "XAGUSD": ("OANDA:XAG_USD", "XAGUSD"),
        "ETHUSD": ("BINANCE:ETHUSDT", "COINBASE:ETH-USD", "ETHUSD"),
    },
    "mt5": {
        "BTCUSD": ("BTCUSD", "BTCUSD.", "BTCUSDm", "BTCUSD.c"),
        "XAUUSD": ("XAUUSD", "GOLD", "XAUUSD.", "XAUUSDm"),
        "NAS100": ("NAS100", "USTEC", "US100", "NDX"),
        "US500": ("US500", "SPX500", "SP500", "SPX"),
        "US30": ("US30", "DJ30", "DJI"),
        "DAX40": ("DAX40", "GER40", "DE40"),
        "UK100": ("UK100", "FTSE100"),
        "XAGUSD": ("XAGUSD", "SILVER"),
        "ETHUSD": ("ETHUSD", "ETHUSD."),
    },
}

SELECTED_KEY = "multi_symbol_selected_20260701"
ACTIVE_KEY = "multi_symbol_active_20260701"
MAIN_SYMBOL_KEY = "multi_symbol_main_symbol_20260702"
DISPLAY_SYMBOL_KEY = "lunch_display_symbol_20260702"
LUNCH_SYMBOL_WIDGET_KEY = "lunch_symbol_selector_widget_20260702"
MANIFEST_KEY = "multi_symbol_manifest_20260701"
PROGRESS_KEY = "multi_symbol_progress_20260701"
CHILD_RUN_KEY = "multi_symbol_child_run_active_20260701"
PARENT_RUN_KEY = "multi_symbol_parent_run_id_20260701"
LAST_RESOURCE_KEY = "multi_symbol_resource_report_20260701"
RUNNING_KEY = "multi_symbol_run_in_progress_20260701"
FIELD10_SUMMARY_KEY = "field10_multi_symbol_summary_20260701"
FIELD10_DAILY_KEY = "field10_daily_higher_regime_20260701"
FIELD10_HOURLY_KEY = "field10_hourly_quality_20260701"

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "multi_symbol_runtime_20260701"
DB_PATH = ROOT / "data" / "multi_symbol_field10_20260701.sqlite3"

_UI_PRESERVE_KEYS = {
    "active_page", "tab_choice", "active_subpage", "phone_mode",
    "lunch_active_field_selector_20260624", "settings_calculation_scope_20260625",
    SELECTED_KEY, ACTIVE_KEY, MAIN_SYMBOL_KEY, DISPLAY_SYMBOL_KEY, LUNCH_SYMBOL_WIDGET_KEY,
    "connector_symbol_20260702", "requested_symbol_20260629", "selected_symbol",
    "active_snapshot_symbol_20260702", "ws_symbol",
    MANIFEST_KEY, PROGRESS_KEY, CHILD_RUN_KEY,
    PARENT_RUN_KEY, LAST_RESOURCE_KEY, RUNNING_KEY, FIELD10_SUMMARY_KEY, FIELD10_DAILY_KEY,
    FIELD10_HOURLY_KEY,
}


def normalize_symbol(value: Any, default: str = "EURUSD") -> str:
    raw = str(value or default).strip().upper().replace("/", "").replace(" ", "")
    aliases = {
        "XBTUSD": "BTCUSD", "BTCUSDT": "BTCUSD", "GOLD": "XAUUSD",
        "USTEC": "NAS100", "US100": "NAS100", "NDX": "NAS100",
        "NASDAQ100": "NAS100", "SPX500": "US500", "SP500": "US500",
        "SPX": "US500", "GSPC": "US500", "^GSPC": "US500",
    }
    return aliases.get(raw, raw) or default


def normalize_selected(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Sequence):
        values = []
    seen: list[str] = []
    for value in values:
        symbol = normalize_symbol(value)
        if symbol in SUPPORTED_SYMBOLS and symbol not in seen:
            seen.append(symbol)
    return seen


def selected_symbols(state: Mapping[str, Any]) -> list[str]:
    """Return the Settings-configured universe from GlobalSymbolContext."""
    try:
        from core.global_symbol_context import get_global_symbol_context
        context = get_global_symbol_context(state)
        if context.configured_symbols:
            return list(context.configured_symbols)
    except Exception:
        pass
    return normalize_selected(state.get(SELECTED_KEY))


def main_symbol(state: Mapping[str, Any]) -> str:
    """Legacy name for the active global display symbol; never inject a default."""
    try:
        from core.global_symbol_context import get_global_symbol_context
        return get_global_symbol_context(state).active_display_symbol
    except Exception:
        return ""


def ensure_main_symbol_active(state: MutableMapping[str, Any]) -> dict[str, Any]:
    """Compatibility facade: restore the global context without changing display identity."""
    try:
        from core.global_symbol_context import restore_latest_context
        context = restore_latest_context(state)
        return {"ok": bool(context.universe_id), "status": "GLOBAL_CONTEXT_RESTORED", "symbol": context.active_display_symbol,
                "provider_calls": 0, "calculation_calls": 0}
    except Exception as exc:
        return {"ok": False, "status": "GLOBAL_CONTEXT_RESTORE_FAILED", "symbol": "", "error": f"{type(exc).__name__}: {exc}",
                "provider_calls": 0, "calculation_calls": 0}

def resolve_provider_symbol(symbol: Any, provider: Any, available_symbols: Sequence[str] | None = None) -> str:
    """Resolve a canonical instrument to the first provider-supported alias."""
    canonical = normalize_symbol(symbol)
    provider_name = str(provider or "canonical").strip().lower()
    aliases = list(PROVIDER_ALIASES.get(provider_name, {}).get(canonical, ()))
    aliases += list(PROVIDER_ALIASES["canonical"].get(canonical, (canonical,)))
    if canonical not in aliases:
        aliases.insert(0, canonical)
    if available_symbols:
        lookup = {str(item).strip().upper(): str(item) for item in available_symbols}
        for alias in aliases:
            match = lookup.get(str(alias).strip().upper())
            if match:
                return match
    return aliases[0]


def _runtime_cache_dirs() -> list[Path]:
    """Return every configured runtime-snapshot directory in priority order."""
    directories = [CACHE_DIR]
    with suppress(Exception):
        from core.generation_registry_20260702 import snapshot_root
        configured = snapshot_root()
        if configured not in directories:
            directories.insert(0, configured)
    return directories


def _cache_path(symbol: str) -> Path:
    return _runtime_cache_dirs()[0] / f"{normalize_symbol(symbol)}.pkl.gz"


def _registry_records(*, parent_run_id: str | None = None, symbol: str | None = None) -> list[Mapping[str, Any]]:
    with suppress(Exception):
        from core.generation_registry_20260702 import list_completed_generations
        rows = list_completed_generations(parent_run_id=parent_run_id or None)
        if symbol:
            target = normalize_symbol(symbol)
            rows = [row for row in rows if normalize_symbol(row.get("symbol")) == target]
        return rows
    return []


def _candidate_cache_paths(symbol: Any) -> list[Path]:
    canonical = normalize_symbol(symbol)
    paths: list[Path] = []
    for directory in _runtime_cache_dirs():
        candidate = directory / f"{canonical}.pkl.gz"
        if candidate not in paths:
            paths.append(candidate)
    for row in _registry_records(symbol=canonical):
        raw = str(row.get("runtime_snapshot_path") or "").strip()
        if raw:
            candidate = Path(raw).expanduser()
            if candidate not in paths:
                paths.append(candidate)
            # Deployment paths change between local Windows, Streamlit Cloud and
            # extracted delivery packages. Re-map the saved basename into each
            # current runtime directory before declaring the snapshot missing.
            for directory in _runtime_cache_dirs():
                remapped = directory / candidate.name
                if remapped not in paths:
                    paths.append(remapped)
    return paths


def _resolved_cache_path(symbol: Any) -> Path:
    for candidate in _candidate_cache_paths(symbol):
        if candidate.is_file():
            try:
                payload = _read_cache_payload(candidate)
                if isinstance(payload.get("state"), Mapping):
                    return candidate
            except Exception:
                continue
    return _cache_path(normalize_symbol(symbol))


def _read_cache_payload(path: Path) -> Mapping[str, Any]:
    from core.runtime_state_cache_20260628 import CACHE_VERSION

    payload = serializer_loads(gzip.decompress(path.read_bytes()))
    if not isinstance(payload, Mapping) or not isinstance(payload.get("state"), Mapping):
        raise ValueError("Unreadable symbol runtime cache")
    # Older secret-free caches remain readable after a deployment upgrade. The
    # restored state is still validated by canonical identity before rendering.
    if payload.get("cache_version") != CACHE_VERSION:
        payload = dict(payload)
        payload["compatibility_restore"] = True
        payload["loaded_by_cache_version"] = CACHE_VERSION
    return payload




def saved_symbol_available(symbol: Any) -> bool:
    """Return True only when the symbol has a readable runtime snapshot."""
    for path in _candidate_cache_paths(symbol):
        if not path.is_file():
            continue
        try:
            payload = _read_cache_payload(path)
            if isinstance(payload.get("state"), Mapping):
                return True
        except Exception:
            continue
    return False


def available_saved_symbols(symbols: Sequence[Any] | None = None) -> list[str]:
    """List cache-ready symbols in requested order, then registry/disk caches."""
    requested = normalize_selected(symbols or [])
    discovered: list[str] = []
    for directory in _runtime_cache_dirs():
        if directory.is_dir():
            discovered.extend(normalize_symbol(path.name.split(".pkl", 1)[0]) for path in directory.glob("*.pkl.gz"))
    for row in _registry_records():
        discovered.append(normalize_symbol(row.get("symbol")))
        discovered.extend(normalize_selected(row.get("selected_symbols") or []))
    ordered = normalize_selected([*requested, *sorted(set(discovered))])
    return [symbol for symbol in ordered if saved_symbol_available(symbol)]



def available_published_symbols(symbols: Sequence[Any] | Mapping[str, Any] | None = None, *, requested: Sequence[Any] | None = None) -> list[str]:
    """List published symbols; accepts both legacy and repaired call signatures."""
    if isinstance(symbols, Mapping):
        state_requested = normalize_selected([
            *(symbols.get("multi_symbol_completed_union_20260706") or []),
            *(symbols.get(SELECTED_KEY) or symbols.get("selected_symbols_for_run_20260705") or []),
        ])
    else:
        state_requested = symbols or []
    requested = normalize_selected(requested or state_requested)
    discovered = list(available_saved_symbols(requested))
    with suppress(Exception):
        with connect_readonly(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT symbol FROM field10_daily_snapshot_symbol ORDER BY broker_day DESC, daily_rank ASC"
            ).fetchall()
        discovered.extend(normalize_symbol(row[0]) for row in rows)
    return normalize_selected([*requested, *discovered])


def _published_symbol_row(symbol: Any) -> dict[str, Any]:
    canonical = normalize_symbol(symbol)
    with suppress(Exception):
        with connect_readonly(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT s.*, d.parent_run_id, d.latest_completed_h1, d.publication_status
                   FROM field10_daily_snapshot_symbol s
                   JOIN field10_daily_snapshot d ON d.daily_snapshot_id=s.daily_snapshot_id
                   WHERE s.symbol=? ORDER BY s.broker_day DESC LIMIT 1""",
                (canonical,),
            ).fetchone()
        if row is not None:
            return dict(row)
    return {}


def _synchronize_display_authorities(state: MutableMapping[str, Any], symbol: str) -> None:
    """Compatibility facade delegating display selection to GlobalSymbolContext."""
    from core.global_symbol_context import select_active_display_symbol
    select_active_display_symbol(symbol, state=state, db_path=DB_PATH)


def activate_symbol_view(state: MutableMapping[str, Any], symbol: Any) -> dict[str, Any]:
    """Select saved display evidence only; never restore another runtime or contact a provider."""
    canonical = normalize_symbol(symbol)
    try:
        from core.global_symbol_context import select_active_display_symbol
        from core.field3_three_regime_engine import load_saved_field3_v2
        context = select_active_display_symbol(canonical, state=state, db_path=DB_PATH)
        reload_report = load_saved_field3_v2(state, context=context, db_path=DB_PATH)
        return {"ok": True, "status": "GLOBAL_DISPLAY_SELECTED", "symbol": canonical,
                "universe_id": context.universe_id, "generation": context.generation,
                "saved_evidence_reload": reload_report, "provider_calls": 0, "calculation_calls": 0}
    except Exception as exc:
        return {"ok": False, "status": "GLOBAL_DISPLAY_SELECTION_FAILED", "symbol": canonical,
                "error": f"{type(exc).__name__}: {exc}", "provider_calls": 0, "calculation_calls": 0}

def _canonical_symbol_from_state(state: Mapping[str, Any]) -> str | None:
    with suppress(Exception):
        from core.canonical_lookup_20260626 import resolve_canonical
        canonical = resolve_canonical(state)
        if isinstance(canonical, Mapping):
            symbol = normalize_symbol(canonical.get("symbol"), default="")
            if symbol in SUPPORTED_SYMBOLS:
                return symbol
    for key in ("canonical_decision_result_20260617", "canonical_result_20260617", "last_valid_canonical_decision_result_20260617"):
        canonical = state.get(key)
        if isinstance(canonical, Mapping):
            symbol = normalize_symbol(canonical.get("symbol"), default="")
            if symbol in SUPPORTED_SYMBOLS:
                return symbol
    symbol = normalize_symbol(state.get("active_snapshot_symbol_20260702") or state.get("symbol"), default="")
    return symbol if symbol in SUPPORTED_SYMBOLS else None


def recover_symbol_universe(state: MutableMapping[str, Any] | Mapping[str, Any]) -> dict[str, Any]:
    """Recover only completed or load-validated exact-symbol publications.

    A selector choice or a readable partial cache is not proof that a symbol has
    enough genuine history.  This prevents failed 97% children from appearing
    in Field 10 as permanent ``INSUFFICIENT LOCAL HISTORY`` cards.
    """
    manifest = state.get(MANIFEST_KEY) if isinstance(state.get(MANIFEST_KEY), Mapping) else {}
    parent_run_id = str(manifest.get("parent_run_id") or state.get(PARENT_RUN_KEY) or "")
    registry_rows = _registry_records(parent_run_id=parent_run_id or None)
    if not registry_rows and not parent_run_id:
        registry_rows = _registry_records()
        if registry_rows:
            parent_run_id = str(registry_rows[0].get("parent_run_id") or "")
            registry_rows = [row for row in registry_rows if str(row.get("parent_run_id") or "") == parent_run_id]

    registry_selected: list[str] = []
    registry_main = ""
    for row in registry_rows:
        if not registry_main:
            registry_main = normalize_symbol(row.get("settings_main_symbol"), default="")
        registry_selected.extend(normalize_selected(row.get("selected_symbols") or []))
        registry_selected.append(normalize_symbol(row.get("symbol"), default=""))
    registry_selected = normalize_selected(registry_selected)

    symbol_status = manifest.get("symbol_status") if isinstance(manifest.get("symbol_status"), Mapping) else {}
    completed_manifest: list[str] = []
    for symbol in normalize_selected(manifest.get("selected_symbols") or []):
        item = symbol_status.get(symbol) if isinstance(symbol_status.get(symbol), Mapping) else {}
        effective = str(item.get("state") or item.get("publication_status") or item.get("status") or "").upper()
        if effective == "COMPLETED":
            completed_manifest.append(symbol)

    cumulative_selected = normalize_selected(
        state.get("multi_symbol_completed_union_20260706")
        or state.get("field10_cumulative_symbols_20260706")
        or []
    )
    loaded_selected: list[str] = []
    try:
        from core.multi_symbol_load_manager_20260707 import LOAD_RECORDS_KEY
        load_records = state.get(LOAD_RECORDS_KEY)
        if isinstance(load_records, Mapping):
            for record in load_records.values():
                if isinstance(record, Mapping):
                    loaded_selected.extend(normalize_selected(record.get("loaded_symbols") or []))
    except Exception:
        loaded_selected = []
    loaded_selected = normalize_selected(loaded_selected)

    # Field 10 is a publication surface, not a loading preview. Only completed
    # registry/cumulative children are admitted; load-validated but not-yet-
    # calculated symbols remain in Settings until they publish successfully.
    selected = normalize_selected([
        *cumulative_selected,
        *completed_manifest,
        *registry_selected,
    ])
    canonical_symbol = _canonical_symbol_from_state(state)
    completed_or_loaded = set(selected)
    if canonical_symbol and canonical_symbol in completed_or_loaded and canonical_symbol not in selected:
        selected.insert(0, canonical_symbol)

    # Only when no completed/validated evidence exists do we expose one current
    # fallback identity. This keeps first-use navigation usable without creating
    # a false all-symbol publication universe.
    fallback_identity_mode = False
    if not selected:
        fallback_identity_mode = True
        raw_selected = normalize_selected(state.get(SELECTED_KEY) or [])
        fallback = normalize_symbol(
            canonical_symbol or state.get(MAIN_SYMBOL_KEY) or state.get("symbol") or (raw_selected[0] if raw_selected else "EURUSD")
        )
        fallback = fallback if fallback in SUPPORTED_SYMBOLS else "EURUSD"
        # Preserve the user's selector universe while promoting the current
        # canonical child to the front. This repairs stale widget identity
        # without silently deleting a previously selected instrument.
        selected = normalize_selected([fallback, *raw_selected])

    manifest_main = normalize_symbol(manifest.get("main_symbol"), default="")
    state_main = normalize_symbol(state.get(MAIN_SYMBOL_KEY), default="")
    main_candidates = (canonical_symbol, manifest_main, registry_main, state_main) if fallback_identity_mode else (manifest_main, registry_main, state_main, canonical_symbol)
    main = next(
        (item for item in main_candidates if item in selected),
        selected[0],
    )
    selected = [main, *[symbol for symbol in selected if symbol != main]]

    requested_active = normalize_symbol(
        state.get(DISPLAY_SYMBOL_KEY) or state.get(ACTIVE_KEY) or manifest.get("display_symbol")
        or manifest.get("active_symbol") or canonical_symbol or main
    )
    if fallback_identity_mode and canonical_symbol in selected:
        active = canonical_symbol
    else:
        active = requested_active if requested_active in selected else (canonical_symbol if canonical_symbol in selected else main)

    if isinstance(state, MutableMapping):
        state[SELECTED_KEY] = list(selected)
        state[MAIN_SYMBOL_KEY] = main
        state[ACTIVE_KEY] = active
        state[DISPLAY_SYMBOL_KEY] = active
        state["active_snapshot_symbol_20260702"] = active
        if parent_run_id:
            state[PARENT_RUN_KEY] = parent_run_id
    return {
        "selected_symbols": selected,
        "main_symbol": main,
        "active_symbol": active,
        "canonical_symbol": canonical_symbol,
        "cache_ready_symbols": [],
        "registry_symbols": registry_selected,
        "loaded_symbols": loaded_selected,
        "completed_manifest_symbols": completed_manifest,
        "parent_run_id": parent_run_id,
        "manifest_consistent": set(completed_manifest).issubset(set(selected)),
    }


def _managed_runtime_key(name: str) -> bool:
    from core.runtime_state_cache_20260628 import _EXACT_KEYS, _PREFIXES

    return name in _EXACT_KEYS or name.startswith(_PREFIXES)


def clear_active_symbol_results(state: MutableMapping[str, Any]) -> int:
    """Clear only reconstructable symbol-generation state before a fresh symbol."""
    removed = 0
    for key in list(state.keys()):
        name = str(key)
        if name in _UI_PRESERVE_KEYS or name.startswith("multi_symbol_"):
            continue
        if _managed_runtime_key(name):
            state.pop(key, None)
            removed += 1
    return removed


def activate_symbol_result(state: MutableMapping[str, Any], symbol: Any) -> dict[str, Any]:
    """Load one saved symbol generation without running calculations."""
    canonical = normalize_symbol(symbol)
    path = _resolved_cache_path(canonical)
    if not path.is_file():
        current = _canonical_symbol_from_state(state)
        if current == canonical:
            state[ACTIVE_KEY] = canonical
            state[DISPLAY_SYMBOL_KEY] = canonical
            state["active_snapshot_symbol_20260702"] = canonical
            set_legacy_calculation_symbol(state, canonical, connector=False)
            return {"ok": True, "status": "ALREADY_ACTIVE_CURRENT_GENERATION", "symbol": canonical, "path": "SESSION_STATE"}
        return {"ok": False, "status": "NO_SAVED_RESULT", "symbol": canonical, "path": str(path)}
    started = time.perf_counter()
    try:
        payload = _read_cache_payload(path)
        cached_state = payload.get("state")
        if not isinstance(cached_state, Mapping):
            raise ValueError("Symbol cache contains no state mapping")
        # Preserve navigation/selection controls, but never carry a previous
        # symbol's child-run identity across an atomic child restore.  The child
        # IDs from the selected cache are part of canonical publication identity.
        preserved = {
            key: state.get(key) for key in _UI_PRESERVE_KEYS
            if key in state and key not in {CHILD_RUN_KEY, FIELD10_SUMMARY_KEY, FIELD10_DAILY_KEY, FIELD10_HOURLY_KEY}
        }
        clear_active_symbol_results(state)
        restored = 0
        for key, value in cached_state.items():
            name = str(key)
            if any(part in name.lower() for part in ("api_key", "secret", "password", "token", "credential")):
                continue
            state[name] = value
            restored += 1
        state.update(preserved)
        # Legacy ``symbol`` remains a compatibility mirror for calculations
        # that have not yet migrated. It is not the Settings or connector owner.
        set_legacy_calculation_symbol(state, canonical, connector=False)
        state["active_snapshot_symbol_20260702"] = canonical
        state[ACTIVE_KEY] = canonical
        state["selected_symbol_pending_run_20260629"] = False
        return {
            "ok": True, "status": "RESTORED", "symbol": canonical,
            "restored_keys": restored, "path": str(path),
            "seconds": round(time.perf_counter() - started, 4),
        }
    except Exception as exc:
        return {
            "ok": False, "status": "ERROR", "symbol": canonical, "path": str(path),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _canonical(state: Mapping[str, Any]) -> Mapping[str, Any]:
    with suppress(Exception):
        from core.canonical_runtime_20260617 import get_canonical
        value = get_canonical(state)
        if isinstance(value, Mapping):
            return value
    for key in ("canonical_decision_result_20260617", "canonical_result_20260617", "last_valid_canonical_decision_result_20260617"):
        value = state.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _source_frame(state: Mapping[str, Any]) -> pd.DataFrame:
    for key in ("canonical_completed_ohlc_df_20260617", "calculation_staging_ohlc_df_20260617", "last_df", "dv_pp_df"):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value
    return pd.DataFrame()


def _time_series(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype="datetime64[ns, UTC]")
    normalized = {str(c).strip().lower().replace("_", " "): c for c in frame.columns}
    column = next((normalized.get(name) for name in ("broker candle time", "time", "datetime", "timestamp", "date") if normalized.get(name) is not None), None)
    if column is None:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
    return pd.to_datetime(frame[column], errors="coerce", utc=True)


def grade_from_score(score: Any) -> str:
    try:
        value = float(score)
    except Exception:
        value = 0.0
    if value >= 90:
        return "A"
    if value >= 75:
        return "B"
    if value >= 60:
        return "C"
    return "D"


def assess_data_quality(state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Transparent A-D quality score for the exact selected timeframe.

    The previous implementation treated every frame as H1 and required 600
    rows.  That incorrectly downgraded a complete 25-day H4 publication, which
    needs 150 completed candles.  This version changes only the window/spacing
    contract; existing OHLC, identity and Field 3 safety checks are preserved.
    """
    from core.timeframe_window_contract_20260706 import (
        TIMEFRAME_SECONDS, required_candles, selected_timeframe,
        validate_timeframe_spacing,
    )

    canonical = dict(canonical or _canonical(state))
    timeframe = selected_timeframe(state, canonical)
    expected_seconds = int(TIMEFRAME_SECONDS[timeframe])
    required_history = int(required_candles(timeframe, "higher"))
    frame = _source_frame(state)
    score = 100.0
    reasons: list[str] = []
    if frame.empty:
        return {
            "score": 0.0, "grade": "D", "status": "FAILED",
            "reasons": ["completed OHLC unavailable"], "rows": 0,
            "timeframe": timeframe, "required_rows": required_history,
        }
    times = _time_series(frame)
    valid_times = times.dropna().sort_values()
    invalid_time_count = int(times.isna().sum())
    duplicate_count = int(valid_times.duplicated().sum())
    missing_periods = 0
    unique_times = valid_times.drop_duplicates()
    if len(unique_times) > 1:
        previous = unique_times.shift(1)
        for earlier, later in zip(previous.iloc[1:], unique_times.iloc[1:]):
            delta_seconds = float((later - earlier).total_seconds())
            if delta_seconds <= expected_seconds * 1.05:
                continue
            # FX weekend closure is not missing provider data.  Preserve
            # weekday/holiday evidence instead of manufacturing weekend bars.
            if earlier.weekday() >= 4 and later.weekday() == 0:
                continue
            intervals = int(round(delta_seconds / expected_seconds))
            missing_periods += max(0, intervals - 1)
    spacing = validate_timeframe_spacing(frame, timeframe=timeframe)
    if invalid_time_count:
        score -= min(25.0, invalid_time_count * 2.0); reasons.append(f"invalid timestamps: {invalid_time_count}")
    if duplicate_count:
        score -= min(15.0, duplicate_count * 1.5); reasons.append(f"duplicate candles: {duplicate_count}")
    if missing_periods:
        score -= min(20.0, missing_periods * 0.35); reasons.append(f"missing {timeframe} periods: {missing_periods}")
    if not spacing.get("ok"):
        score -= min(20.0, float(spacing.get("bad_spacing_count") or 1) * 2.0)
        reasons.append(f"invalid {timeframe} candle spacing: {spacing.get('bad_spacing_count') or 1}")
    if len(frame) < required_history:
        shortage = required_history - len(frame)
        score -= min(25.0, 25.0 * shortage / max(1, required_history))
        reasons.append(f"higher-standard {timeframe} history incomplete: {len(frame)}/{required_history}")

    normalized = {str(c).strip().lower(): c for c in frame.columns}
    required = [normalized.get(name) for name in ("open", "high", "low", "close")]
    invalid_ohlc = 0
    if all(column is not None for column in required):
        o, h, l, c = (pd.to_numeric(frame[column], errors="coerce") for column in required)
        invalid_ohlc = int((h.lt(pd.concat([o, c], axis=1).max(axis=1)) | l.gt(pd.concat([o, c], axis=1).min(axis=1)) | o.le(0) | h.le(0) | l.le(0) | c.le(0)).sum())
        if invalid_ohlc:
            score -= min(35.0, invalid_ohlc * 4.0); reasons.append(f"invalid OHLC rows: {invalid_ohlc}")
    else:
        score -= 20.0; reasons.append("required OHLC columns missing")

    identity_missing = [name for name in ("run_id", "symbol", "timeframe") if not canonical.get(name)]
    source_id = canonical.get("source_id") or canonical.get("data_source_id") or canonical.get("source_snapshot_hash") or canonical.get("snapshot_hash")
    if not source_id:
        score -= 8.0; reasons.append("source ID missing")
    if identity_missing:
        score -= 8.0; reasons.append("identity missing: " + ", ".join(identity_missing))
    field3 = state.get("field3_regime_lifecycle_monitor_20260701")
    if isinstance(field3, Mapping):
        reported = (field3.get("data_quality") or {}).get("score") if isinstance(field3.get("data_quality"), Mapping) else None
        if reported is not None:
            try:
                score = min(score, float(reported))
                reasons.append("capped by Field 3 data-quality gate")
            except Exception:
                pass
    score = round(max(0.0, min(100.0, score)), 2)
    return {
        "score": score, "grade": grade_from_score(score),
        "status": "PASS" if score >= 75 else ("WARN" if score >= 60 else "FAIL"),
        "reasons": reasons or ["all checked quality controls passed"],
        "rows": int(len(frame)), "required_rows": required_history,
        "timeframe": timeframe, "timeframe_seconds": expected_seconds,
        "invalid_timestamps": invalid_time_count,
        "duplicates": duplicate_count, "missing_periods": missing_periods,
        "invalid_ohlc": invalid_ohlc, "spacing": spacing,
        "first_candle": valid_times.min().isoformat() if not valid_times.empty else None,
        "last_candle": valid_times.max().isoformat() if not valid_times.empty else None,
        "source_id": str(source_id or ""),
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_number(*values: Any) -> float | None:
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(number):
            return number
    return None


def _broker_wall_timestamp_value(value: Any) -> pd.Timestamp:
    """Parse a broker timestamp while preserving its displayed wall-clock hour."""
    try:
        stamp = pd.Timestamp(value)
    except Exception:
        return pd.NaT
    if pd.isna(stamp):
        return pd.NaT
    # tz_localize(None) removes the offset without converting the clock.  This is
    # intentional: Field 10 displays MetaTrader/broker candle time, not UTC.
    if stamp.tzinfo is not None:
        stamp = stamp.tz_localize(None)
    return stamp


def _broker_wall_series(values: Any) -> pd.Series:
    series = values if isinstance(values, pd.Series) else pd.Series(values)
    return series.map(_broker_wall_timestamp_value)


def _session_execution_context(state: Mapping[str, Any], canonical: Mapping[str, Any], broker_time: pd.Timestamp | None = None) -> dict[str, Any]:
    """Read published session/execution evidence without creating a new prediction."""
    contract = state.get("shared_fx_session_contract_20260625")
    contract = contract if isinstance(contract, Mapping) else {}
    if not contract:
        with suppress(Exception):
            from core.session_context_20260625 import normalize_session_selection, resolve_session_contract
            selection = normalize_session_selection(state.get("shared_fx_session_selection_20260625"))
            contract = resolve_session_contract(dict(state), dict(canonical), selection).to_dict()
    session = str(contract.get("selected_session") or contract.get("detected_session") or "UNAVAILABLE")
    priority_map = {
        "LONDON_NEW_YORK_OVERLAP": 100.0, "TOKYO_LONDON_OVERLAP": 90.0,
        "LONDON": 85.0, "NEW_YORK": 80.0, "TOKYO_SYDNEY_OVERLAP": 75.0,
        "TOKYO": 65.0, "SYDNEY": 55.0, "GLOBAL_FALLBACK": 40.0,
        "UNAVAILABLE": 0.0,
    }
    session_priority = _first_number(contract.get("session_priority"), contract.get("priority_score"))
    if session_priority is None:
        session_priority = priority_map.get(session.upper(), 50.0 if session != "UNAVAILABLE" else 0.0)

    execution = _mapping(canonical.get("execution"))
    market = _mapping(canonical.get("market"))
    spread = _first_number(
        execution.get("spread_pips"), execution.get("spread_points"),
        market.get("spread_pips"), market.get("spread"),
        canonical.get("spread_pips"), state.get("spread_pips"), state.get("estimated_spread_pips"),
    )
    published_quality = str(
        execution.get("spread_quality") or market.get("spread_quality")
        or canonical.get("spread_quality") or state.get("spread_quality") or ""
    ).upper().strip()
    if published_quality:
        spread_quality = published_quality
    elif spread is None:
        spread_quality = "UNAVAILABLE"
    elif spread <= 0.6:
        spread_quality = "LOW"
    elif spread <= 1.2:
        spread_quality = "AVERAGE"
    elif spread <= 2.0:
        spread_quality = "HIGH"
    else:
        spread_quality = "VERY HIGH"
    spread_score_map = {"LOW": 100.0, "GOOD": 90.0, "AVERAGE": 70.0, "MEDIUM": 65.0, "HIGH": 35.0, "VERY HIGH": 10.0, "UNAVAILABLE": 40.0}
    spread_score = spread_score_map.get(spread_quality, 50.0)

    final = _mapping(canonical.get("final_decision"))
    reliability = _mapping(canonical.get("reliability"))
    uncertainty = _first_number(
        final.get("uncertainty_pct"), canonical.get("uncertainty_pct"),
        reliability.get("uncertainty_pct"), reliability.get("uncertainty"),
    )
    error = _first_number(
        final.get("error_percentage"), canonical.get("error_percentage"),
        canonical.get("forecast_error_pct"), reliability.get("error_percentage"),
    )
    trade_permission = str(
        final.get("trade_permission") or canonical.get("trade_permission")
        or ("BLOCKED" if str(final.get("less_risky_decision") or "").upper() in {"WAIT", "NO TRADE"} else "CHECK")
    ).upper()
    final_action = str(
        final.get("final_decision") or final.get("less_risky_decision")
        or canonical.get("decision") or "WAIT"
    ).upper()
    return {
        "current_session": session, "session_priority": float(session_priority),
        "average_spread": spread, "spread_quality": spread_quality, "spread_score": spread_score,
        "uncertainty": uncertainty, "error_percentage": error,
        "trade_permission": trade_permission, "final_action": final_action,
    }


def _daily_higher_snapshot(state: MutableMapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    locked: Mapping[str, Any] = {}
    with suppress(Exception):
        from core.daily_locked_regime_20260625 import ensure_daily_locked_regime
        locked = ensure_daily_locked_regime(state, canonical)
    higher = _mapping(locked.get("higher"))
    final = _mapping(canonical.get("final_decision"))
    regime = _mapping(canonical.get("regime"))
    adaptive: Mapping[str, Any] = {}
    with suppress(Exception):
        from core.field10_adaptive_regime_metrics_20260702 import compute_adaptive_regime_metrics
        adaptive = compute_adaptive_regime_metrics(_source_frame(state), timeframe=state.get("timeframe") or _mapping(state.get("canonical_shared_result")).get("timeframe"))
    higher_bias = str(higher.get("bias") or regime.get("higher_bias") or regime.get("bias") or "WAIT")
    less_risky_bias = str(final.get("less_risky_decision") or canonical.get("less_risky_decision") or higher_bias or "WAIT")
    return {
        "higher_regime": str(higher.get("regime") or regime.get("higher_regime") or regime.get("major_regime") or canonical.get("regime") or "UNKNOWN"),
        "higher_standard_bias": higher_bias,
        "less_risky_bias": less_risky_bias,
        "higher_reliability": float(higher.get("reliability") or regime.get("reliability") or 0.0),
        "higher_transition_risk": float(
            _first_number(higher.get("transition_risk"), adaptive.get("transition_risk_6h")) or 0.0
        ),
        "transition_risk_24h": _first_number(
            higher.get("transition_risk_24h"), regime.get("transition_risk_24h"),
            adaptive.get("transition_risk_24h"),
        ),
        "expected_return_12h": _first_number(
            higher.get("expected_return_12h"), canonical.get("expected_return_12h"),
            adaptive.get("expected_return_12h"),
        ),
        "expected_return_24h": _first_number(
            higher.get("expected_return_24h"), canonical.get("expected_return_24h"),
            adaptive.get("expected_return_24h"),
        ),
        "expected_return_36h": _first_number(
            higher.get("expected_return_36h"), canonical.get("expected_return_36h"),
            adaptive.get("expected_return_36h"),
        ),
        "transition_risk_6h": _first_number(adaptive.get("transition_risk_6h")),
        "expected_value_6h": _first_number(adaptive.get("expected_value_6h")),
        "risk_adjusted_expected_value_6h": _first_number(adaptive.get("risk_adjusted_expected_value_6h")),
        "probability_profit_1h": _first_number(adaptive.get("probability_profit_1h")),
        "probability_profit_6h": _first_number(adaptive.get("probability_profit_6h")),
        "probability_profit_12h": _first_number(adaptive.get("probability_profit_12h")),
        "probability_reach_ev_1h": _first_number(adaptive.get("probability_reach_ev_1h")),
        "probability_reach_ev_6h": _first_number(adaptive.get("probability_reach_ev_6h")),
        "probability_reach_ev_12h": _first_number(adaptive.get("probability_reach_ev_12h")),
        "ev_target_1h": _first_number(adaptive.get("ev_target_1h")),
        "ev_target_6h": _first_number(adaptive.get("ev_target_6h")),
        "ev_target_12h": _first_number(adaptive.get("ev_target_12h")),
        "tick_volume_12h": _first_number(adaptive.get("tick_volume_12h")),
        "volume_12h_z": _first_number(adaptive.get("volume_12h_z")),
        "volume_source": str(adaptive.get("volume_source") or "UNAVAILABLE"),
        "ev_model_version": str(adaptive.get("ev_model_version") or "UNAVAILABLE"),
        "probability_calibration_status": str(adaptive.get("probability_calibration_status") or "UNAVAILABLE"),
        "unexpected_situation_status": str(adaptive.get("unexpected_situation_status") or "CAUTION"),
        "unexpected_situation_severity": _first_number(adaptive.get("unexpected_situation_severity")),
        "validation_permission": str(adaptive.get("validation_permission") or "VALIDATE"),
        "evidence_sample_size": int(adaptive.get("evidence_sample_size") or 0),
        "metric_provenance_json": str(adaptive.get("metric_provenance_json") or "{}"),
        "higher_alpha": float(higher.get("alpha") or 0.0),
        "higher_delta": float(higher.get("delta") or 0.0),
        "sample_count": int(higher.get("sample_count") or 0),
        "next_review_broker_time": locked.get("next_review_broker_time"),
        "locked_status": locked.get("status") or "UNAVAILABLE",
    }


def _hourly_history(state: Mapping[str, Any], canonical: Mapping[str, Any], quality: Mapping[str, Any]) -> pd.DataFrame:
    symbol = normalize_symbol(canonical.get("symbol") or state.get("symbol") or "EURUSD")
    run_id = str(canonical.get("run_id") or canonical.get("canonical_calculation_id") or "")
    source_id = str(canonical.get("source_id") or canonical.get("data_source_id") or canonical.get("source_snapshot_hash") or canonical.get("snapshot_hash") or "")
    monitor = state.get("field3_regime_lifecycle_monitor_20260701")
    if isinstance(monitor, Mapping):
        raw_history = monitor.get("history_25d")
        history = raw_history.copy(deep=False) if isinstance(raw_history, pd.DataFrame) else pd.DataFrame(raw_history or [])
    else:
        history = pd.DataFrame()
    if history.empty:
        details = state.get("regime_standard_detail_tables_published_20260618") or state.get("regime_standard_detail_tables_20260617")
        details = details if isinstance(details, Mapping) else {}
        higher = next((details.get(k) for k in ("higher", "high") if isinstance(details.get(k), pd.DataFrame)), None)
        history = higher.copy(deep=False) if isinstance(higher, pd.DataFrame) else pd.DataFrame()
    if history.empty:
        frame = _source_frame(state)
        history = pd.DataFrame({"event_time_utc": _time_series(frame)}) if not frame.empty else pd.DataFrame()
    if history.empty:
        return pd.DataFrame()

    def col(*tokens: str) -> str | None:
        for column in history.columns:
            lower = str(column).lower()
            if all(token in lower for token in tokens):
                return str(column)
        return None

    time_col = col("broker", "time") or col("event_time") or col("time") or col("date")
    times = _broker_wall_series(history[time_col]) if time_col else pd.Series(pd.NaT, index=history.index, dtype="datetime64[ns]")
    higher_col = col("existing higher regime") or col("higher", "regime") or col("regime")
    higher_bias_col = col("higher", "bias") or col("regime bias") or col("bias")
    less_risky_col = col("less-risky") or col("less risky") or col("final", "bias") or higher_bias_col or col("decision")
    dq_col = col("data quality score") or col("data quality")
    trust_col = col("calibrated trust score") or col("trust score") or col("trust")
    reliability_col = col("bias reliability score") or col("reliability")
    session_col = col("session")
    session_priority_col = col("session", "priority")
    spread_col = col("average", "spread") or col("spread", "pips") or col("spread")
    spread_quality_col = col("spread", "quality")
    uncertainty_col = col("uncertainty")
    error_col = col("error", "percentage") or col("error", "pct")
    permission_col = col("trade", "permission")
    action_col = col("final", "action")
    transition_24h_col = col("transition", "risk", "24")
    expected_return_12h_col = col("expected", "return", "12")
    expected_return_24h_col = col("expected", "return", "24")
    expected_return_36h_col = col("expected", "return", "36")
    result = pd.DataFrame({
        "Broker Timestamp": times,
        "Symbol": symbol,
        "Timeframe": str(state.get("timeframe") or canonical.get("timeframe") or "H4").upper(),
        "Higher Standard Regime": history[higher_col].astype(str).values if higher_col else "UNKNOWN",
        "Higher-Standard Bias": history[higher_bias_col].astype(str).values if higher_bias_col else "WAIT",
        "Less-Risky Bias": history[less_risky_col].astype(str).values if less_risky_col else "WAIT",
        "Data Quality Score": pd.to_numeric(history[dq_col], errors="coerce").values if dq_col else float(quality.get("score") or 0.0),
        "Trust Score": pd.to_numeric(history[trust_col], errors="coerce").values if trust_col else np.nan,
        "Reliability": pd.to_numeric(history[reliability_col], errors="coerce").values if reliability_col else np.nan,
        "Current Session": history[session_col].astype(str).values if session_col else "UNAVAILABLE",
        "Session Priority": pd.to_numeric(history[session_priority_col], errors="coerce").values if session_priority_col else np.nan,
        "Average Spread": pd.to_numeric(history[spread_col], errors="coerce").values if spread_col else np.nan,
        "Spread Quality": history[spread_quality_col].astype(str).values if spread_quality_col else "UNAVAILABLE",
        "Uncertainty": pd.to_numeric(history[uncertainty_col], errors="coerce").values if uncertainty_col else np.nan,
        "Error Percentage": pd.to_numeric(history[error_col], errors="coerce").values if error_col else np.nan,
        "Trade Permission": history[permission_col].astype(str).values if permission_col else "CHECK",
        "Final Action": history[action_col].astype(str).values if action_col else (history[less_risky_col].astype(str).values if less_risky_col else "WAIT"),
        "Transition Risk 24H": pd.to_numeric(history[transition_24h_col], errors="coerce").values if transition_24h_col else np.nan,
        "Expected Return 12H (%)": pd.to_numeric(history[expected_return_12h_col], errors="coerce").values if expected_return_12h_col else np.nan,
        "Expected Return 24H (%)": pd.to_numeric(history[expected_return_24h_col], errors="coerce").values if expected_return_24h_col else np.nan,
        "Expected Return 36H (%)": pd.to_numeric(history[expected_return_36h_col], errors="coerce").values if expected_return_36h_col else np.nan,
        "Transition Risk 6H (%)": np.nan,
        "Expected Value 6H (%)": np.nan,
        "Risk-Adjusted EV 6H (%)": np.nan,
        "Probability of Profit 1H (%)": np.nan,
        "Probability of Profit 6H (%)": np.nan,
        "Probability of Profit 12H (%)": np.nan,
        "Probability Reach EV 1H (%)": np.nan,
        "Probability Reach EV 6H (%)": np.nan,
        "Probability Reach EV 12H (%)": np.nan,
        "EV Target 1H (%)": np.nan,
        "EV Target 6H (%)": np.nan,
        "EV Target 12H (%)": np.nan,
        "Observed Tick Volume 12H": np.nan,
        "Volume 12H Z-Score": np.nan,
        "Volume Data Source": "UNAVAILABLE",
        "EV Model Version": "UNAVAILABLE",
        "Probability Calibration Status": "UNAVAILABLE",
        "Unexpected Situation Status": "CAUTION",
        "Unexpected Situation Severity": np.nan,
        "Validation Permission": "VALIDATE",
        "Evidence Sample Size": np.nan,
        "Metric Provenance JSON": "{}",
        "Run ID": run_id,
        "Source ID": source_id,
    })
    result = result.dropna(subset=["Broker Timestamp"]).sort_values("Broker Timestamp").drop_duplicates("Broker Timestamp", keep="last").tail(600)
    broker_wall = _broker_wall_series(result["Broker Timestamp"])
    result["Broker Timestamp"] = broker_wall
    result["Broker Date"] = broker_wall.dt.strftime("%Y-%m-%d")
    result["Broker Hour"] = broker_wall.dt.strftime("%H:%M")
    result["Data Quality Score"] = result["Data Quality Score"].fillna(float(quality.get("score") or 0.0)).clip(0, 100)
    result["Data Quality"] = result["Data Quality Score"].map(grade_from_score)
    result["Validation Status"] = str(quality.get("status") or "CHECK")
    result["Quality Reason"] = "; ".join(str(x) for x in list(quality.get("reasons") or [])[:4])
    # Only the newest row may use current exact-generation execution/session evidence.
    # Older rows stay UNAVAILABLE unless the historical source explicitly published it.
    if not result.empty:
        latest_index = result["Broker Timestamp"].idxmax()
        context = _session_execution_context(state, canonical, pd.Timestamp(result.loc[latest_index, "Broker Timestamp"]))
        adaptive: Mapping[str, Any] = {}
        with suppress(Exception):
            from core.field10_adaptive_regime_metrics_20260702 import compute_adaptive_regime_metrics
            adaptive = compute_adaptive_regime_metrics(_source_frame(state), timeframe=state.get("timeframe") or _mapping(state.get("canonical_shared_result")).get("timeframe"))
        if str(result.loc[latest_index, "Current Session"]).upper() in {"", "NAN", "UNAVAILABLE"}:
            result.loc[latest_index, "Current Session"] = context["current_session"]
        if pd.isna(result.loc[latest_index, "Session Priority"]):
            result.loc[latest_index, "Session Priority"] = context["session_priority"]
        if pd.isna(result.loc[latest_index, "Average Spread"]):
            result.loc[latest_index, "Average Spread"] = context["average_spread"]
        if str(result.loc[latest_index, "Spread Quality"]).upper() in {"", "NAN", "UNAVAILABLE"}:
            result.loc[latest_index, "Spread Quality"] = context["spread_quality"]
        if pd.isna(result.loc[latest_index, "Uncertainty"]):
            result.loc[latest_index, "Uncertainty"] = context["uncertainty"]
        if pd.isna(result.loc[latest_index, "Error Percentage"]):
            result.loc[latest_index, "Error Percentage"] = context["error_percentage"]
        if str(result.loc[latest_index, "Trade Permission"]).upper() in {"", "NAN", "CHECK"}:
            result.loc[latest_index, "Trade Permission"] = context["trade_permission"]
        if str(result.loc[latest_index, "Final Action"]).upper() in {"", "NAN"}:
            result.loc[latest_index, "Final Action"] = context["final_action"]
        if pd.isna(result.loc[latest_index, "Transition Risk 24H"]):
            result.loc[latest_index, "Transition Risk 24H"] = adaptive.get("transition_risk_24h")
        if pd.isna(result.loc[latest_index, "Expected Return 12H (%)"]):
            result.loc[latest_index, "Expected Return 12H (%)"] = adaptive.get("expected_return_12h")
        if pd.isna(result.loc[latest_index, "Expected Return 24H (%)"]):
            result.loc[latest_index, "Expected Return 24H (%)"] = adaptive.get("expected_return_24h")
        if pd.isna(result.loc[latest_index, "Expected Return 36H (%)"]):
            result.loc[latest_index, "Expected Return 36H (%)"] = adaptive.get("expected_return_36h")
        current_map = {
            "Transition Risk 6H (%)": "transition_risk_6h",
            "Expected Value 6H (%)": "expected_value_6h",
            "Risk-Adjusted EV 6H (%)": "risk_adjusted_expected_value_6h",
            "Probability of Profit 1H (%)": "probability_profit_1h",
            "Probability of Profit 6H (%)": "probability_profit_6h",
            "Probability of Profit 12H (%)": "probability_profit_12h",
            "Probability Reach EV 1H (%)": "probability_reach_ev_1h",
            "Probability Reach EV 6H (%)": "probability_reach_ev_6h",
            "Probability Reach EV 12H (%)": "probability_reach_ev_12h",
            "EV Target 1H (%)": "ev_target_1h", "EV Target 6H (%)": "ev_target_6h",
            "EV Target 12H (%)": "ev_target_12h", "Observed Tick Volume 12H": "tick_volume_12h",
            "Volume 12H Z-Score": "volume_12h_z", "Unexpected Situation Severity": "unexpected_situation_severity",
            "Evidence Sample Size": "evidence_sample_size",
        }
        for display, key in current_map.items():
            result.loc[latest_index, display] = adaptive.get(key)
        text_map = {
            "Volume Data Source": "volume_source", "EV Model Version": "ev_model_version",
            "Probability Calibration Status": "probability_calibration_status",
            "Unexpected Situation Status": "unexpected_situation_status",
            "Validation Permission": "validation_permission", "Metric Provenance JSON": "metric_provenance_json",
        }
        for display, key in text_map.items():
            result.loc[latest_index, display] = str(adaptive.get(key) or result.loc[latest_index, display])
    return result.reset_index(drop=True)


def migrate_database(path: Path | str = DB_PATH) -> dict[str, Any]:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path), timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS multi_symbol_runs (
                parent_run_id TEXT NOT NULL,
                child_run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                scope TEXT NOT NULL,
                status TEXT NOT NULL,
                elapsed_seconds REAL NOT NULL DEFAULT 0,
                rss_delta_mb REAL NOT NULL DEFAULT 0,
                cpu_seconds REAL NOT NULL DEFAULT 0,
                canonical_run_id TEXT,
                source_id TEXT,
                completed_candle TEXT,
                current_session TEXT,
                session_priority REAL,
                average_spread REAL,
                spread_quality TEXT,
                uncertainty REAL,
                error_percentage REAL,
                trade_permission TEXT,
                final_action TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id, symbol)
            );
            CREATE TABLE IF NOT EXISTS field10_hourly_quality (
                parent_run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                broker_timestamp TEXT NOT NULL,
                rank INTEGER,
                data_quality_grade TEXT NOT NULL,
                data_quality_score REAL NOT NULL,
                higher_standard_regime TEXT,
                higher_standard_bias TEXT,
                less_risky_bias TEXT,
                trust_score REAL,
                reliability REAL,
                validation_status TEXT,
                quality_reason TEXT,
                broker_date TEXT,
                broker_hour TEXT,
                current_session TEXT,
                session_priority REAL,
                average_spread REAL,
                spread_quality TEXT,
                uncertainty REAL,
                error_percentage REAL,
                trade_permission TEXT,
                final_action TEXT,
                transition_risk_24h REAL,
                expected_return_12h REAL,
                expected_return_24h REAL,
                expected_return_36h REAL,
                rank_score REAL,
                rank_reason TEXT,
                run_id TEXT,
                source_id TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id, symbol, broker_timestamp)
            );
            CREATE INDEX IF NOT EXISTS idx_field10_hourly_latest
                ON field10_hourly_quality(symbol, broker_timestamp DESC);
            CREATE TABLE IF NOT EXISTS field10_daily_higher_lock (
                broker_day TEXT NOT NULL,
                symbol TEXT NOT NULL,
                rank INTEGER,
                higher_standard_regime TEXT NOT NULL,
                higher_standard_bias TEXT,
                less_risky_bias TEXT NOT NULL,
                data_quality_grade TEXT NOT NULL,
                data_quality_score REAL NOT NULL,
                higher_reliability REAL,
                higher_transition_risk REAL,
                transition_risk_24h REAL,
                expected_return_12h REAL,
                expected_return_24h REAL,
                expected_return_36h REAL,
                higher_alpha REAL,
                higher_delta REAL,
                sample_count INTEGER,
                current_session TEXT,
                session_priority REAL,
                average_spread REAL,
                spread_quality TEXT,
                uncertainty REAL,
                error_percentage REAL,
                trade_permission TEXT,
                final_action TEXT,
                rank_score REAL,
                rank_reason TEXT,
                lock_status TEXT NOT NULL,
                locked_at_broker_time TEXT NOT NULL,
                last_reviewed_broker_time TEXT NOT NULL,
                next_review_broker_time TEXT,
                parent_run_id TEXT NOT NULL,
                run_id TEXT,
                source_id TEXT,
                PRIMARY KEY(broker_day, symbol)
            );
            CREATE INDEX IF NOT EXISTS idx_field10_daily_latest
                ON field10_daily_higher_lock(broker_day DESC, rank ASC);
            """
        )
        # Additive migrations for databases created by earlier Field 10 builds.
        additive_columns = {
            "multi_symbol_runs": {
                "current_session": "TEXT", "session_priority": "REAL", "average_spread": "REAL",
                "spread_quality": "TEXT", "uncertainty": "REAL", "error_percentage": "REAL",
                "trade_permission": "TEXT", "final_action": "TEXT",
            },
            "field10_hourly_quality": {
                "broker_date": "TEXT", "broker_hour": "TEXT", "current_session": "TEXT",
                "session_priority": "REAL", "average_spread": "REAL", "spread_quality": "TEXT",
                "uncertainty": "REAL", "error_percentage": "REAL", "trade_permission": "TEXT",
                "final_action": "TEXT", "rank_score": "REAL", "rank_reason": "TEXT",
                "higher_standard_bias": "TEXT", "transition_risk_24h": "REAL",
                "expected_return_12h": "REAL", "expected_return_24h": "REAL",
                "expected_return_36h": "REAL",
                "transition_risk_6h": "REAL", "expected_value_6h": "REAL",
                "risk_adjusted_expected_value_6h": "REAL", "probability_profit_1h": "REAL",
                "probability_profit_6h": "REAL", "probability_profit_12h": "REAL",
                "probability_reach_ev_1h": "REAL", "probability_reach_ev_6h": "REAL",
                "probability_reach_ev_12h": "REAL", "ev_target_1h": "REAL",
                "ev_target_6h": "REAL", "ev_target_12h": "REAL",
                "tick_volume_12h": "REAL", "volume_12h_z": "REAL", "volume_source": "TEXT",
                "ev_model_version": "TEXT", "probability_calibration_status": "TEXT",
                "unexpected_situation_status": "TEXT", "unexpected_situation_severity": "REAL",
                "validation_permission": "TEXT", "evidence_sample_size": "INTEGER",
                "metric_provenance_json": "TEXT", "migration_version": "TEXT",
            },
            "field10_daily_higher_lock": {
                "current_session": "TEXT", "session_priority": "REAL", "average_spread": "REAL",
                "spread_quality": "TEXT", "uncertainty": "REAL", "error_percentage": "REAL",
                "trade_permission": "TEXT", "final_action": "TEXT", "rank_score": "REAL",
                "rank_reason": "TEXT", "higher_standard_bias": "TEXT",
                "transition_risk_24h": "REAL", "expected_return_12h": "REAL",
                "expected_return_24h": "REAL", "expected_return_36h": "REAL",
                "transition_risk_6h": "REAL", "expected_value_6h": "REAL",
                "risk_adjusted_expected_value_6h": "REAL", "probability_profit_1h": "REAL",
                "probability_profit_6h": "REAL", "probability_profit_12h": "REAL",
                "probability_reach_ev_1h": "REAL", "probability_reach_ev_6h": "REAL",
                "probability_reach_ev_12h": "REAL", "ev_target_1h": "REAL",
                "ev_target_6h": "REAL", "ev_target_12h": "REAL",
                "tick_volume_12h": "REAL", "volume_12h_z": "REAL", "volume_source": "TEXT",
                "ev_model_version": "TEXT", "probability_calibration_status": "TEXT",
                "unexpected_situation_status": "TEXT", "unexpected_situation_severity": "REAL",
                "validation_permission": "TEXT", "evidence_sample_size": "INTEGER",
                "metric_provenance_json": "TEXT", "migration_version": "TEXT",
                "timeframe": "TEXT", "completed_candle": "TEXT",
                "canonical_run_id": "TEXT", "generation_id": "TEXT",
                "snapshot_hash": "TEXT", "child_run_id": "TEXT",
            },
        }
        for table, definitions in additive_columns.items():
            existing = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for column, sql_type in definitions.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
        # Backfill only identity aliases that are already evidenced by legacy
        # columns.  H1 is the historical default; newer writes set the selected
        # timeframe explicitly and therefore remain isolated from H4/D1 rows.
        daily_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(field10_daily_higher_lock)").fetchall()}
        if {"timeframe", "completed_candle"}.issubset(daily_columns):
            conn.execute("UPDATE field10_daily_higher_lock SET timeframe='H1' WHERE timeframe IS NULL OR TRIM(timeframe)='' ")
            conn.execute(
                "UPDATE field10_daily_higher_lock SET completed_candle=COALESCE(NULLIF(last_reviewed_broker_time,''),NULLIF(locked_at_broker_time,'')) "
                "WHERE completed_candle IS NULL OR TRIM(completed_candle)=''"
            )
        # Older daily rows stored only a shorter-horizon transition risk.  When
        # available, compound that probability over four six-hour blocks to
        # backfill the new 24-hour column.  No expected-return zero is invented.
        rows = conn.execute(
            "SELECT broker_day,symbol,higher_transition_risk,transition_risk_24h "
            "FROM field10_daily_higher_lock"
        ).fetchall()
        for broker_day, symbol, risk6, risk24 in rows:
            if risk24 is not None or risk6 is None:
                continue
            try:
                probability = float(risk6)
                if 0.0 <= probability <= 1.0:
                    probability *= 100.0
                probability = float(np.clip(probability, 0.0, 100.0)) / 100.0
                compounded = (1.0 - (1.0 - probability) ** 4) * 100.0
            except Exception:
                continue
            conn.execute(
                "UPDATE field10_daily_higher_lock SET transition_risk_24h=? "
                "WHERE broker_day=? AND symbol=?",
                (compounded, broker_day, symbol),
            )
        conn.commit()
    return {"ok": True, "path": str(path), "version": VERSION}


def _broker_timestamp(canonical: Mapping[str, Any], state: Mapping[str, Any]) -> pd.Timestamp:
    """Return the canonical broker-wall timestamp without silently converting it to UTC."""
    value: Any = None
    with suppress(Exception):
        from core.shared_broker_time_20260622 import shared_broker_time_provider
        contract = shared_broker_time_provider(state, canonical=dict(canonical))
        if bool(contract.get("broker_clock_available")):
            value = contract.get("broker_time") or contract.get("shared_broker_time")
    if value in (None, ""):
        value = canonical.get("broker_candle_time")
    if value in (None, ""):
        raise ValueError("Canonical broker candle timestamp is unavailable; Field 10 evidence was not fabricated")
    try:
        parsed = pd.Timestamp(value)
    except Exception as exc:
        raise ValueError(f"Canonical broker candle timestamp is invalid: {value!r}") from exc
    if pd.isna(parsed):
        raise ValueError("Canonical broker candle timestamp is invalid; Field 10 evidence was not fabricated")
    return parsed


def validate_fields_1_9(state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Read-only post-run integrity checks for Fields 1–9.

    The observer inspects already-published objects only.  It never imports a
    renderer, refreshes a connector, settles an outcome, or reruns a model.
    Status values are intentionally limited to PASS, WARNING, and FAIL.
    """
    canonical = dict(canonical or _canonical(state))
    expected_symbol = normalize_symbol(canonical.get("symbol") or state.get("symbol") or "EURUSD")
    expected_timeframe = str(state.get("timeframe") or canonical.get("timeframe") or "H4").upper()
    run_id = str(canonical.get("run_id") or canonical.get("canonical_calculation_id") or "")
    source_id = str(canonical.get("source_id") or canonical.get("data_source_id") or canonical.get("snapshot_hash") or "")
    canonical_candle_raw = canonical.get("broker_candle_time") or canonical.get("latest_completed_candle_time")
    canonical_candle = _broker_wall_timestamp_value(canonical_candle_raw)
    candidates: Mapping[int, tuple[str, ...]] = {
        1: ("lunch_metric_result_published_20260618", "full_metric_result_cache_20260618", "full_metric_history_df_20260618"),
        2: ("field2_quant_upgrade_20260629", "powerbi_projection_result_20260619", "powerbi_calibrated_bundle_20260617"),
        3: ("field3_regime_lifecycle_monitor_20260701", "regime_standard_detail_tables_published_20260618", "regime_standard_table_20260617"),
        4: ("field4to9_collection_history_full_20260628", "field4to9_collection_history_display_20260628"),
        5: ("canonical_ai_fact_pack_20260619", "compact_canonical_summary_20260619"),
        6: ("field6_quant_history_result_20260622", "field6_quant_history_20260622", "session_ai_field6_9_20260625"),
        7: ("field7_research_result_20260626", "field7_shadow_v13"),
        8: ("field8_integrated_history_result_20260624", "field8_integrated_history_20260624"),
        9: ("field9_research_result_20260626", "field9_decision_impact_result_20260624", "field9_eurusd_h1_decision_impact"),
    }

    def shape(value: Any) -> tuple[int, int, bool, str]:
        if isinstance(value, pd.DataFrame):
            return int(len(value)), int(len(value.columns)), not value.empty, "DataFrame"
        if isinstance(value, Mapping):
            ok_flag = value.get("ok")
            meaningful = any(v not in (None, "", [], {}) for k, v in value.items() if str(k).lower() not in {"ok", "status"})
            valid = bool(meaningful and ok_flag is not False)
            return int(value.get("rows") or len(value)), int(value.get("columns") or len(value)), valid, "Mapping"
        if isinstance(value, (list, tuple)):
            return len(value), 0, len(value) > 0, type(value).__name__
        return 0, 0, value not in (None, ""), type(value).__name__

    def first_value(mapping: Mapping[str, Any], names: tuple[str, ...]) -> Any:
        for name in names:
            if mapping.get(name) not in (None, ""):
                return mapping.get(name)
        return None

    rows: list[dict[str, Any]] = []
    for field, keys in candidates.items():
        selected_key = ""; selected_value: Any = None
        for key in keys:
            value = state.get(key)
            _, _, valid, _ = shape(value)
            if valid:
                selected_key, selected_value = key, value
                break
            if selected_value is None and value is not None:
                selected_key, selected_value = key, value
        row_count, column_count, valid, kind = shape(selected_value)
        failures: list[str] = []
        warnings: list[str] = []
        if not run_id:
            failures.append("canonical run_id missing")
        if not source_id:
            failures.append("canonical source/snapshot ID missing")
        if pd.isna(canonical_candle):
            failures.append("canonical completed broker candle missing or invalid")
        if not valid:
            if field in {1, 2, 3} or not run_id:
                failures.append("required saved result is empty or unavailable")
            else:
                warnings.append("optional field result is not published for this run/scope; renderer stays read-only instead of crashing")

        published_symbol = expected_symbol
        published_timeframe = expected_timeframe
        if isinstance(selected_value, Mapping):
            published_symbol = normalize_symbol(first_value(selected_value, ("symbol", "identity.symbol")) or expected_symbol)
            published_timeframe = str(first_value(selected_value, ("timeframe", "identity.timeframe")) or expected_timeframe).upper()
            published_run = str(first_value(selected_value, ("run_id", "canonical_run_id", "identity.run_id")) or "")
            published_source = str(first_value(selected_value, ("source_id", "snapshot_hash", "source_snapshot_hash")) or "")
            published_candle_raw = first_value(selected_value, (
                "broker_candle_time", "latest_completed_candle_time", "completed_candle_time", "identity.latest_completed_candle",
            ))
            published_status = str(first_value(selected_value, ("calculation_status", "status")) or "").upper()
            if published_run and run_id and published_run != run_id:
                failures.append(f"run_id mismatch: {published_run}")
            if published_source and source_id and published_source != source_id:
                failures.append("source/snapshot mismatch")
            if published_candle_raw not in (None, "") and pd.notna(canonical_candle):
                published_candle = _broker_wall_timestamp_value(published_candle_raw)
                if pd.isna(published_candle):
                    warnings.append("published completed candle is invalid")
                elif published_candle != canonical_candle:
                    failures.append(f"completed-candle mismatch: {pd.Timestamp(published_candle).isoformat()}")
            if published_status in {"FAIL", "FAILED", "ERROR"}:
                failures.append(f"published calculation status={published_status}")
            elif published_status in {"PARTIAL", "WARNING", "STALE", "INSUFFICIENT_DATA"}:
                warnings.append(f"published calculation status={published_status}")

        if published_symbol != expected_symbol:
            failures.append(f"symbol mismatch: {published_symbol}")
        if published_timeframe != expected_timeframe:
            failures.append(f"timeframe mismatch: {published_timeframe}")

        if isinstance(selected_value, pd.DataFrame) and not selected_value.empty:
            time_column = next((column for column in selected_value.columns if any(token in str(column).lower() for token in ("broker time", "timestamp", "candle time"))), None)
            if time_column is not None:
                parsed = _broker_wall_series(selected_value[time_column])
                invalid_count = int(parsed.isna().sum())
                duplicate_count = int(parsed.dropna().duplicated().sum())
                if invalid_count:
                    warnings.append(f"{invalid_count} invalid timestamp row(s)")
                if duplicate_count:
                    warnings.append(f"{duplicate_count} duplicate timestamp row(s)")
            all_null = [str(column) for column in selected_value.columns if selected_value[column].isna().all()]
            if all_null:
                warnings.append(f"all-null columns: {', '.join(all_null[:4])}")

        status = "FAIL" if failures else ("WARNING" if warnings else "PASS")
        messages = failures + warnings
        rows.append({
            "Field": field, "Status": status, "Result Key": selected_key or "-",
            "Object Type": kind, "Row Count": row_count, "Column Count": column_count,
            "Symbol": expected_symbol, "Timeframe": expected_timeframe, "Run ID": run_id,
            "Source ID": source_id, "Completed Broker Candle": pd.Timestamp(canonical_candle).isoformat() if pd.notna(canonical_candle) else "",
            "Validation Message": "; ".join(messages) or "saved result is non-empty, identity-compatible, and linked to the canonical completed candle",
        })
    return rows


def _persist_symbol_evidence(
    state: MutableMapping[str, Any], *, parent_run_id: str, child_run_id: str,
    scope: str, status: Mapping[str, Any], elapsed: float, rss_delta_mb: float,
    cpu_seconds: float, path: Path | str = DB_PATH,
) -> dict[str, Any]:
    migrate_database(path)
    canonical = dict(_canonical(state))
    symbol = normalize_symbol(canonical.get("symbol") or state.get("symbol") or "EURUSD")
    quality = assess_data_quality(state, canonical)
    daily = _daily_higher_snapshot(state, canonical)
    hourly = _hourly_history(state, canonical, quality)
    broker_time = _broker_timestamp(canonical, state)
    broker_day = broker_time.strftime("%Y-%m-%d")
    current_hour = int(broker_time.hour)
    execution_context = _session_execution_context(state, canonical, broker_time)
    source_id = str(quality.get("source_id") or "")
    run_id = str(canonical.get("run_id") or canonical.get("canonical_calculation_id") or "")
    child_status = "COMPLETED" if bool((status.get("canonical") or {}).get("ok") or status.get("ok") or canonical) else "PARTIAL"
    created = pd.Timestamp.now(tz="UTC").isoformat()

    with sqlite3.connect(str(path), timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """INSERT OR REPLACE INTO multi_symbol_runs(
                    parent_run_id,child_run_id,symbol,timeframe,scope,status,elapsed_seconds,
                    rss_delta_mb,cpu_seconds,canonical_run_id,source_id,completed_candle,
                    current_session,session_priority,average_spread,spread_quality,uncertainty,error_percentage,
                    trade_permission,final_action,error,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (parent_run_id, child_run_id, symbol, str(state.get("timeframe") or canonical.get("timeframe") or "H4").upper(), scope,
                 child_status, float(elapsed), float(rss_delta_mb), float(cpu_seconds), run_id,
                 source_id, str(canonical.get("latest_completed_candle_time") or canonical.get("broker_candle_time") or ""),
                 str(execution_context.get("current_session") or "UNAVAILABLE"),
                 float(execution_context.get("session_priority") or 0.0),
                 execution_context.get("average_spread"), str(execution_context.get("spread_quality") or "UNAVAILABLE"),
                 execution_context.get("uncertainty"), execution_context.get("error_percentage"),
                 str(execution_context.get("trade_permission") or "CHECK"),
                 str(execution_context.get("final_action") or "WAIT"),
                 str(status.get("error") or ""), created),
            )
            for row in hourly.to_dict("records"):
                ts = _broker_wall_timestamp_value(row.get("Broker Timestamp"))
                if pd.isna(ts):
                    continue
                conn.execute(
                    """INSERT OR REPLACE INTO field10_hourly_quality(
                        parent_run_id,symbol,timeframe,broker_timestamp,rank,data_quality_grade,
                        data_quality_score,higher_standard_regime,higher_standard_bias,less_risky_bias,trust_score,
                        reliability,validation_status,quality_reason,broker_date,broker_hour,current_session,
                        session_priority,average_spread,spread_quality,uncertainty,error_percentage,
                        trade_permission,final_action,transition_risk_24h,expected_return_12h,
                        expected_return_24h,expected_return_36h,rank_score,rank_reason,run_id,source_id,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (parent_run_id, symbol, str(row.get("Timeframe") or "H4"), pd.Timestamp(ts).isoformat(), None,
                     str(row.get("Data Quality") or "D"), float(row.get("Data Quality Score") or 0),
                     str(row.get("Higher Standard Regime") or "UNKNOWN"), str(row.get("Higher-Standard Bias") or "WAIT"),
                     str(row.get("Less-Risky Bias") or "WAIT"),
                     None if pd.isna(row.get("Trust Score")) else float(row.get("Trust Score")),
                     None if pd.isna(row.get("Reliability")) else float(row.get("Reliability")),
                     str(row.get("Validation Status") or "CHECK"), str(row.get("Quality Reason") or ""),
                     str(row.get("Broker Date") or pd.Timestamp(ts).strftime("%Y-%m-%d")),
                     str(row.get("Broker Hour") or pd.Timestamp(ts).strftime("%H:%M")),
                     str(row.get("Current Session") or "UNAVAILABLE"),
                     None if pd.isna(row.get("Session Priority")) else float(row.get("Session Priority")),
                     None if pd.isna(row.get("Average Spread")) else float(row.get("Average Spread")),
                     str(row.get("Spread Quality") or "UNAVAILABLE"),
                     None if pd.isna(row.get("Uncertainty")) else float(row.get("Uncertainty")),
                     None if pd.isna(row.get("Error Percentage")) else float(row.get("Error Percentage")),
                     str(row.get("Trade Permission") or "CHECK"), str(row.get("Final Action") or "WAIT"),
                     None if pd.isna(row.get("Transition Risk 24H")) else float(row.get("Transition Risk 24H")),
                     None if pd.isna(row.get("Expected Return 12H (%)")) else float(row.get("Expected Return 12H (%)")),
                     None if pd.isna(row.get("Expected Return 24H (%)")) else float(row.get("Expected Return 24H (%)")),
                     None if pd.isna(row.get("Expected Return 36H (%)")) else float(row.get("Expected Return 36H (%)")),
                     None, "pending deterministic rank",
                     str(row.get("Run ID") or run_id), str(row.get("Source ID") or source_id), created),
                )

            # Persist the current causal quant extension on the newest exact-candle row.
            if not hourly.empty:
                newest = hourly.sort_values("Broker Timestamp").iloc[-1]
                conn.execute(
                    """UPDATE field10_hourly_quality SET transition_risk_6h=?,expected_value_6h=?,
                    risk_adjusted_expected_value_6h=?,probability_profit_1h=?,probability_profit_6h=?,
                    probability_profit_12h=?,probability_reach_ev_1h=?,probability_reach_ev_6h=?,
                    probability_reach_ev_12h=?,ev_target_1h=?,ev_target_6h=?,ev_target_12h=?,
                    tick_volume_12h=?,volume_12h_z=?,volume_source=?,ev_model_version=?,
                    probability_calibration_status=?,unexpected_situation_status=?,
                    unexpected_situation_severity=?,validation_permission=?,evidence_sample_size=?,
                    metric_provenance_json=?,migration_version=?
                    WHERE parent_run_id=? AND symbol=? AND broker_timestamp=?""",
                    (newest.get("Transition Risk 6H (%)"), newest.get("Expected Value 6H (%)"),
                     newest.get("Risk-Adjusted EV 6H (%)"), newest.get("Probability of Profit 1H (%)"),
                     newest.get("Probability of Profit 6H (%)"), newest.get("Probability of Profit 12H (%)"),
                     newest.get("Probability Reach EV 1H (%)"), newest.get("Probability Reach EV 6H (%)"),
                     newest.get("Probability Reach EV 12H (%)"), newest.get("EV Target 1H (%)"),
                     newest.get("EV Target 6H (%)"), newest.get("EV Target 12H (%)"),
                     newest.get("Observed Tick Volume 12H"), newest.get("Volume 12H Z-Score"),
                     str(newest.get("Volume Data Source") or "UNAVAILABLE"), str(newest.get("EV Model Version") or "UNAVAILABLE"),
                     str(newest.get("Probability Calibration Status") or "UNAVAILABLE"),
                     str(newest.get("Unexpected Situation Status") or "CAUTION"),
                     newest.get("Unexpected Situation Severity"), str(newest.get("Validation Permission") or "VALIDATE"),
                     newest.get("Evidence Sample Size"), str(newest.get("Metric Provenance JSON") or "{}"),
                     "field10-rank-ev6-probability-volume12-20260704-v1", parent_run_id, symbol,
                     pd.Timestamp(newest.get("Broker Timestamp")).isoformat()),
                )

            existing = conn.execute(
                "SELECT locked_at_broker_time FROM field10_daily_higher_lock WHERE broker_day=? AND symbol=?",
                (broker_day, symbol),
            ).fetchone()
            # Before broker 23:00, today's first published value remains immutable.
            # At/after 23:00 the day-end review may update it from the final completed H1 evidence.
            may_write = existing is None or current_hour >= 23
            if may_write:
                lock_status = "DAY_END_REVIEW_23H" if current_hour >= 23 else "TODAY_LOCKED_UNTIL_23H"
                locked_at = existing[0] if existing else broker_time.isoformat()
                conn.execute(
                    """INSERT OR REPLACE INTO field10_daily_higher_lock(
                        broker_day,symbol,rank,higher_standard_regime,higher_standard_bias,less_risky_bias,
                        data_quality_grade,data_quality_score,higher_reliability,
                        higher_transition_risk,transition_risk_24h,expected_return_12h,
                        expected_return_24h,expected_return_36h,higher_alpha,higher_delta,sample_count,
                        current_session,session_priority,average_spread,spread_quality,uncertainty,error_percentage,
                        trade_permission,final_action,rank_score,rank_reason,
                        lock_status,locked_at_broker_time,last_reviewed_broker_time,
                        next_review_broker_time,parent_run_id,run_id,source_id
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (broker_day, symbol, None, str(daily.get("higher_regime") or "UNKNOWN"),
                     str(daily.get("higher_standard_bias") or "WAIT"), str(daily.get("less_risky_bias") or "WAIT"),
                     str(quality.get("grade") or "D"),
                     float(quality.get("score") or 0), float(daily.get("higher_reliability") or 0),
                     float(daily.get("higher_transition_risk") or 0),
                     None if daily.get("transition_risk_24h") is None else float(daily.get("transition_risk_24h")),
                     None if daily.get("expected_return_12h") is None else float(daily.get("expected_return_12h")),
                     None if daily.get("expected_return_24h") is None else float(daily.get("expected_return_24h")),
                     None if daily.get("expected_return_36h") is None else float(daily.get("expected_return_36h")),
                     float(daily.get("higher_alpha") or 0),
                     float(daily.get("higher_delta") or 0), int(daily.get("sample_count") or 0),
                     str(execution_context.get("current_session") or "UNAVAILABLE"),
                     float(execution_context.get("session_priority") or 0.0),
                     execution_context.get("average_spread"), str(execution_context.get("spread_quality") or "UNAVAILABLE"),
                     execution_context.get("uncertainty"), execution_context.get("error_percentage"),
                     str(execution_context.get("trade_permission") or "CHECK"),
                     str(execution_context.get("final_action") or daily.get("less_risky_bias") or "WAIT"),
                     None, "pending deterministic rank",
                     lock_status, locked_at, broker_time.isoformat(), str(daily.get("next_review_broker_time") or ""),
                     parent_run_id, run_id, source_id),
                )
                conn.execute(
                    """UPDATE field10_daily_higher_lock SET timeframe=?,completed_candle=?,canonical_run_id=?,generation_id=?,snapshot_hash=?,child_run_id=?
                       WHERE broker_day=? AND symbol=?""",
                    (str(state.get("timeframe") or canonical.get("timeframe") or "H4").upper(), broker_time.isoformat(),
                     run_id, str(canonical.get("generation_id") or canonical.get("calculation_generation") or ""),
                     str(canonical.get("snapshot_hash") or canonical.get("source_snapshot_hash") or ""),
                     str(state.get("multi_symbol_current_child_id_20260701") or ""), broker_day, symbol),
                )
                conn.execute(
                    """UPDATE field10_daily_higher_lock SET transition_risk_6h=?,expected_value_6h=?,
                    risk_adjusted_expected_value_6h=?,probability_profit_1h=?,probability_profit_6h=?,
                    probability_profit_12h=?,probability_reach_ev_1h=?,probability_reach_ev_6h=?,
                    probability_reach_ev_12h=?,ev_target_1h=?,ev_target_6h=?,ev_target_12h=?,
                    tick_volume_12h=?,volume_12h_z=?,volume_source=?,ev_model_version=?,
                    probability_calibration_status=?,unexpected_situation_status=?,
                    unexpected_situation_severity=?,validation_permission=?,evidence_sample_size=?,
                    metric_provenance_json=?,migration_version=? WHERE broker_day=? AND symbol=?""",
                    (daily.get("transition_risk_6h"), daily.get("expected_value_6h"),
                     daily.get("risk_adjusted_expected_value_6h"), daily.get("probability_profit_1h"),
                     daily.get("probability_profit_6h"), daily.get("probability_profit_12h"),
                     daily.get("probability_reach_ev_1h"), daily.get("probability_reach_ev_6h"),
                     daily.get("probability_reach_ev_12h"), daily.get("ev_target_1h"), daily.get("ev_target_6h"),
                     daily.get("ev_target_12h"), daily.get("tick_volume_12h"), daily.get("volume_12h_z"),
                     daily.get("volume_source"), daily.get("ev_model_version"), daily.get("probability_calibration_status"),
                     daily.get("unexpected_situation_status"), daily.get("unexpected_situation_severity"),
                     daily.get("validation_permission"), daily.get("evidence_sample_size"), daily.get("metric_provenance_json"),
                     "field10-rank-ev6-probability-volume12-20260704-v1", broker_day, symbol),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {
        "symbol": symbol, "status": child_status, "quality": quality, "daily": daily,
        "hourly_rows": int(len(hourly)), "broker_day": broker_day,
        "broker_time": broker_time.isoformat(), "run_id": run_id, "source_id": source_id,
        "field_validation": validate_fields_1_9(state, canonical),
    }


def _rank_persisted_rows(parent_run_id: str, broker_day: str, path: Path | str = DB_PATH) -> None:
    """Apply deterministic eligibility-first ranking to persisted Field 10 rows."""
    with sqlite3.connect(str(path), timeout=30) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            rows = conn.execute(
                """SELECT symbol,broker_timestamp,data_quality_score,COALESCE(trust_score,0),
                          COALESCE(reliability,0),COALESCE(session_priority,0),
                          COALESCE(spread_quality,'UNAVAILABLE'),COALESCE(uncertainty,0),
                          COALESCE(error_percentage,0),COALESCE(trade_permission,'CHECK')
                   FROM field10_hourly_quality WHERE parent_run_id=?""",
                (parent_run_id,),
            ).fetchall()
            if rows:
                frame = pd.DataFrame(rows, columns=[
                    "symbol", "broker_timestamp", "quality", "trust", "reliability",
                    "session_priority", "spread_quality", "uncertainty", "error", "permission",
                ])
                for column in ("quality", "trust", "reliability", "session_priority", "uncertainty", "error"):
                    frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
                for column in ("trust", "reliability", "session_priority", "uncertainty", "error"):
                    mask = frame[column].abs().le(1.0) & frame[column].ne(0)
                    frame.loc[mask, column] = frame.loc[mask, column] * 100.0
                spread_scores = {"LOW": 100.0, "GOOD": 90.0, "AVERAGE": 70.0, "MEDIUM": 65.0, "HIGH": 35.0, "VERY HIGH": 10.0, "UNAVAILABLE": 40.0}
                frame["spread_score"] = frame["spread_quality"].astype(str).str.upper().map(spread_scores).fillna(50.0)
                permission_scores = {"ALLOWED": 2.0, "TRADE ALLOWED": 2.0, "CAUTION": 1.0, "CHECK": 1.0, "BLOCKED": 0.0, "NO TRADE": 0.0}
                frame["eligibility"] = frame["permission"].astype(str).str.upper().map(permission_scores).fillna(1.0)
                frame["rank_score"] = (
                    frame["quality"] * 0.35 + frame["trust"] * 0.15 + frame["reliability"] * 0.20
                    + frame["session_priority"] * 0.15 + frame["spread_score"] * 0.15
                    - frame["uncertainty"].clip(lower=0) * 0.05 - frame["error"].clip(lower=0) * 0.05
                ).clip(0.0, 100.0)
                frame = frame.sort_values(
                    ["broker_timestamp", "eligibility", "rank_score", "quality", "reliability", "uncertainty", "symbol"],
                    ascending=[True, False, False, False, False, True, True], kind="mergesort",
                )
                frame["rank"] = np.nan
                eligible_mask = frame["eligibility"].gt(0.0)
                frame.loc[eligible_mask, "rank"] = (
                    frame.loc[eligible_mask].groupby("broker_timestamp", sort=False).cumcount() + 1
                )
                for row in frame.itertuples(index=False):
                    is_ranked = pd.notna(row.rank)
                    reason = (
                        f"eligibility={row.permission}; quality={row.quality:.1f}; reliability={row.reliability:.1f}; "
                        f"session={row.session_priority:.1f}; spread={row.spread_quality}; "
                        f"uncertainty={row.uncertainty:.1f}; error={row.error:.1f}"
                    )
                    if not is_ranked:
                        reason = "UNRANKED — failed or blocked symbols are excluded from the eligible rank pool; " + reason
                    conn.execute(
                        "UPDATE field10_hourly_quality SET rank=?,rank_score=?,rank_reason=? WHERE parent_run_id=? AND symbol=? AND broker_timestamp=?",
                        (int(row.rank) if is_ranked else None, float(row.rank_score), reason, parent_run_id, str(row.symbol), str(row.broker_timestamp)),
                    )
            daily = conn.execute(
                """SELECT symbol,data_quality_score,COALESCE(higher_reliability,0),
                          COALESCE(session_priority,0),COALESCE(spread_quality,'UNAVAILABLE'),
                          COALESCE(uncertainty,0),COALESCE(error_percentage,0),COALESCE(trade_permission,'CHECK')
                   FROM field10_daily_higher_lock WHERE broker_day=?""",
                (broker_day,),
            ).fetchall()
            if daily:
                d = pd.DataFrame(daily, columns=[
                    "symbol", "quality", "reliability", "session_priority", "spread_quality",
                    "uncertainty", "error", "permission",
                ])
                for column in ("quality", "reliability", "session_priority", "uncertainty", "error"):
                    d[column] = pd.to_numeric(d[column], errors="coerce").fillna(0.0)
                for column in ("reliability", "session_priority", "uncertainty", "error"):
                    mask = d[column].abs().le(1.0) & d[column].ne(0)
                    d.loc[mask, column] = d.loc[mask, column] * 100.0
                spread_scores = {"LOW": 100.0, "GOOD": 90.0, "AVERAGE": 70.0, "MEDIUM": 65.0, "HIGH": 35.0, "VERY HIGH": 10.0, "UNAVAILABLE": 40.0}
                permission_scores = {"ALLOWED": 2.0, "TRADE ALLOWED": 2.0, "CAUTION": 1.0, "CHECK": 1.0, "BLOCKED": 0.0, "NO TRADE": 0.0}
                d["spread_score"] = d["spread_quality"].astype(str).str.upper().map(spread_scores).fillna(50.0)
                d["eligibility"] = d["permission"].astype(str).str.upper().map(permission_scores).fillna(1.0)
                d["rank_score"] = (
                    d["quality"] * 0.40 + d["reliability"] * 0.25
                    + d["session_priority"] * 0.15 + d["spread_score"] * 0.20
                    - d["uncertainty"] * 0.05 - d["error"] * 0.05
                ).clip(0.0, 100.0)
                d = d.sort_values(
                    ["eligibility", "rank_score", "quality", "reliability", "uncertainty", "symbol"],
                    ascending=[False, False, False, False, True, True], kind="mergesort",
                ).reset_index(drop=True)
                d["rank"] = np.nan
                eligible_mask = d["eligibility"].gt(0.0)
                d.loc[eligible_mask, "rank"] = np.arange(1, int(eligible_mask.sum()) + 1)
                for row in d.itertuples(index=False):
                    is_ranked = pd.notna(row.rank)
                    reason = (
                        f"eligibility={row.permission}; quality={row.quality:.1f}; reliability={row.reliability:.1f}; "
                        f"session={row.session_priority:.1f}; spread={row.spread_quality}"
                    )
                    if not is_ranked:
                        reason = "UNRANKED — failed or blocked symbols are excluded from the eligible rank pool; " + reason
                    conn.execute(
                        "UPDATE field10_daily_higher_lock SET rank=?,rank_score=?,rank_reason=? WHERE broker_day=? AND symbol=?",
                        (int(row.rank) if is_ranked else None, float(row.rank_score), reason, broker_day, str(row.symbol)),
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def load_field10_tables(
    state: MutableMapping[str, Any] | None = None, *, parent_run_id: str | None = None,
    symbol: str | None = None, path: Path | str = DB_PATH,
) -> dict[str, pd.DataFrame]:
    state = state if state is not None else {}
    manifest = state.get(MANIFEST_KEY) if isinstance(state.get(MANIFEST_KEY), Mapping) else {}
    parent_run_id = str(parent_run_id or manifest.get("parent_run_id") or state.get(PARENT_RUN_KEY) or "")
    symbol = normalize_symbol(symbol or state.get(ACTIVE_KEY) or state.get("symbol") or "EURUSD")
    with connect_readonly(path, timeout=30) as conn:
        if parent_run_id:
            summary = pd.read_sql_query(
                """SELECT symbol AS Symbol,timeframe AS Timeframe,status AS Status,status AS [Calculation Status],elapsed_seconds AS [Elapsed Seconds],
                rss_delta_mb AS [RSS Delta MB],cpu_seconds AS [CPU Seconds],canonical_run_id AS [Run ID],canonical_run_id AS [Canonical Run ID],
                source_id AS [Source ID],completed_candle AS [Completed Candle],
                current_session AS [Current Session],session_priority AS [Session Priority],
                average_spread AS [Average Spread],spread_quality AS [Spread Quality],
                uncertainty AS Uncertainty,error_percentage AS [Error Percentage],
                trade_permission AS [Trade Permission],final_action AS [Final Action],error AS Error
                FROM multi_symbol_runs WHERE parent_run_id=? ORDER BY status DESC,symbol""",
                conn, params=(parent_run_id,),
            )
            hourly = pd.read_sql_query(
                """SELECT broker_date AS [Broker Date],broker_hour AS [Broker Hour],
                broker_timestamp AS [Broker Timestamp],broker_timestamp AS [Completed Broker Candle],timeframe AS Timeframe,rank AS Rank,rank_score AS [Rank Score],symbol AS Symbol,
                data_quality_grade AS [Data Quality],data_quality_score AS [Data Quality Score],
                higher_standard_regime AS [Higher Standard Regime],higher_standard_bias AS [Higher-Standard Bias],less_risky_bias AS [Less-Risky Bias],
                current_session AS [Current Session],session_priority AS [Session Priority],
                average_spread AS [Average Spread],spread_quality AS [Spread Quality],
                uncertainty AS Uncertainty,error_percentage AS [Error Percentage],
                trade_permission AS [Trade Permission],final_action AS [Final Action],
                transition_risk_24h AS [Transition Risk 24H],transition_risk_6h AS [Transition Risk 6H (%)],
                expected_return_12h AS [Expected Return 12H (%)],expected_return_24h AS [Expected Return 24H (%)],
                expected_return_36h AS [Expected Return 36H (%)],expected_value_6h AS [Expected Value 6H (%)],
                risk_adjusted_expected_value_6h AS [Risk-Adjusted EV 6H (%)],
                probability_profit_1h AS [Probability of Profit 1H (%)],
                probability_profit_6h AS [Probability of Profit 6H (%)],
                probability_profit_12h AS [Probability of Profit 12H (%)],
                probability_reach_ev_1h AS [Probability Reach EV 1H (%)],
                probability_reach_ev_6h AS [Probability Reach EV 6H (%)],
                probability_reach_ev_12h AS [Probability Reach EV 12H (%)],
                ev_target_1h AS [EV Target 1H (%)],ev_target_6h AS [EV Target 6H (%)],ev_target_12h AS [EV Target 12H (%)],
                tick_volume_12h AS [Observed Tick Volume 12H],volume_12h_z AS [Volume 12H Z-Score],
                volume_source AS [Volume Data Source],ev_model_version AS [EV Model Version],
                probability_calibration_status AS [Probability Calibration Status],
                unexpected_situation_status AS [Unexpected Situation Status],
                unexpected_situation_severity AS [Unexpected Situation Severity],
                validation_permission AS [Validation Permission],evidence_sample_size AS [Evidence Sample Size],
                metric_provenance_json AS [Metric Provenance JSON],migration_version AS [Migration Version],
                trust_score AS [Trust Score],reliability AS Reliability,validation_status AS [Validation Status],
                quality_reason AS [Quality Reason],rank_reason AS [Rank Reason],run_id AS [Run ID],source_id AS [Source ID]
                FROM field10_hourly_quality WHERE parent_run_id=? AND symbol=?
                ORDER BY broker_timestamp DESC LIMIT 600""",
                conn, params=(parent_run_id, symbol),
            )
        else:
            summary = pd.DataFrame(); hourly = pd.DataFrame()
        # Cumulative three-selector view: keep the latest persisted daily row for
        # every completed symbol, not only the newest run's broker day. This lets
        # Super Quick, Quick and Full results rank together without recalculation.
        cumulative_symbols = normalize_selected(
            state.get("multi_symbol_completed_union_20260706")
            or state.get("field10_cumulative_symbols_20260706")
            or state.get(SELECTED_KEY)
            or []
        )
        requested_timeframe = str(state.get("timeframe") or "H4").upper()
        daily = pd.read_sql_query(
            """WITH latest AS (
                   SELECT symbol, MAX(broker_day) AS broker_day
                   FROM field10_daily_higher_lock
                   WHERE UPPER(COALESCE(NULLIF(TRIM(timeframe), ''), ?))=?
                   GROUP BY symbol
               ), current_rows AS (
                   SELECT f.*
                   FROM field10_daily_higher_lock f
                   JOIN latest l ON l.symbol=f.symbol AND l.broker_day=f.broker_day
                   WHERE UPPER(COALESCE(NULLIF(TRIM(f.timeframe), ''), ?))=?
               )
               SELECT broker_day AS [Broker Day],completed_candle AS [Completed Broker Candle],timeframe AS Timeframe,rank AS Rank,rank_score AS [Rank Score],symbol AS Symbol,
               higher_standard_regime AS [Higher Standard Regime],higher_standard_bias AS [Higher-Standard Bias],less_risky_bias AS [Less-Risky Bias],
               data_quality_grade AS [Data Quality],data_quality_score AS [Data Quality Score],
               higher_reliability AS [Higher Reliability],higher_transition_risk AS [Transition Risk],
               transition_risk_24h AS [Transition Risk 24H],transition_risk_6h AS [Transition Risk 6H (%)],
               expected_return_12h AS [Expected Return 12H (%)],expected_return_24h AS [Expected Return 24H (%)],
               expected_return_36h AS [Expected Return 36H (%)],expected_value_6h AS [Expected Value 6H (%)],
               risk_adjusted_expected_value_6h AS [Risk-Adjusted EV 6H (%)],
               probability_profit_1h AS [Probability of Profit 1H (%)],
               probability_profit_6h AS [Probability of Profit 6H (%)],
               probability_profit_12h AS [Probability of Profit 12H (%)],
               probability_reach_ev_1h AS [Probability Reach EV 1H (%)],
               probability_reach_ev_6h AS [Probability Reach EV 6H (%)],
               probability_reach_ev_12h AS [Probability Reach EV 12H (%)],
               ev_target_1h AS [EV Target 1H (%)],ev_target_6h AS [EV Target 6H (%)],ev_target_12h AS [EV Target 12H (%)],
               tick_volume_12h AS [Observed Tick Volume 12H],volume_12h_z AS [Volume 12H Z-Score],
               volume_source AS [Volume Data Source],ev_model_version AS [EV Model Version],
               probability_calibration_status AS [Probability Calibration Status],
               unexpected_situation_status AS [Unexpected Situation Status],
               unexpected_situation_severity AS [Unexpected Situation Severity],
               validation_permission AS [Validation Permission],evidence_sample_size AS [Evidence Sample Size],
               metric_provenance_json AS [Metric Provenance JSON],migration_version AS [Migration Version],
               higher_alpha AS Alpha,higher_delta AS Delta,sample_count AS [Sample Count],
               current_session AS [Current Session],session_priority AS [Session Priority],
               average_spread AS [Average Spread],spread_quality AS [Spread Quality],
               uncertainty AS Uncertainty,error_percentage AS [Error Percentage],
               trade_permission AS [Trade Permission],final_action AS [Final Action],rank_reason AS [Rank Reason],
               lock_status AS [Lock Status],locked_at_broker_time AS [Locked At],
               last_reviewed_broker_time AS [Last Reviewed],next_review_broker_time AS [Next Review],
               run_id AS [Run ID],source_id AS [Source ID]
               FROM current_rows""",
            conn, params=(requested_timeframe, requested_timeframe, requested_timeframe, requested_timeframe),
        )
        if not daily.empty and cumulative_symbols and "Symbol" in daily.columns:
            daily = daily.loc[daily["Symbol"].astype(str).str.upper().isin(cumulative_symbols)].copy()
        if not daily.empty:
            # Preserve the locked daily rank for audit, then create one display
            # rank across the cumulative symbols using the existing Rank Score.
            if "Rank" in daily.columns:
                daily["Stored Daily Rank"] = daily["Rank"]
            scores = pd.to_numeric(daily.get("Rank Score"), errors="coerce")
            permissions = daily.get("Trade Permission", pd.Series("CHECK", index=daily.index)).astype(str).str.upper()
            eligible = ~permissions.isin(["BLOCKED", "NO TRADE", "UNRANKED"])
            daily["_cumulative_score"] = scores
            daily["_eligible"] = eligible & scores.notna()
            daily = daily.sort_values(["_eligible", "_cumulative_score", "Symbol"], ascending=[False, False, True], kind="stable").reset_index(drop=True)
            cumulative_rank = pd.Series(pd.NA, index=daily.index, dtype="Int64")
            eligible_positions = daily.index[daily["_eligible"]].tolist()
            for rank_value, position in enumerate(eligible_positions, start=1):
                cumulative_rank.iloc[position] = rank_value
            daily["Rank"] = cumulative_rank
            daily["Rank Scope"] = "Cumulative completed symbols from First + Second + Third selectors"
            daily = daily.drop(columns=["_cumulative_score", "_eligible"], errors="ignore")
    if not summary.empty and not daily.empty:
        merge_columns = [
            "Symbol", "Rank", "Rank Score", "Data Quality", "Data Quality Score",
            "Higher Standard Regime", "Higher-Standard Bias", "Less-Risky Bias", "Higher Reliability",
            "Transition Risk 24H", "Transition Risk 6H (%)", "Expected Return 12H (%)", "Expected Return 24H (%)", "Expected Return 36H (%)",
            "Expected Value 6H (%)", "Risk-Adjusted EV 6H (%)",
            "Probability of Profit 1H (%)", "Probability of Profit 6H (%)", "Probability of Profit 12H (%)",
            "Probability Reach EV 1H (%)", "Probability Reach EV 6H (%)", "Probability Reach EV 12H (%)",
            "EV Target 1H (%)", "EV Target 6H (%)", "EV Target 12H (%)",
            "Observed Tick Volume 12H", "Volume 12H Z-Score", "Volume Data Source",
            "EV Model Version", "Probability Calibration Status", "Unexpected Situation Status",
            "Unexpected Situation Severity", "Validation Permission", "Evidence Sample Size",
            "Current Session", "Session Priority", "Average Spread", "Spread Quality",
            "Uncertainty", "Error Percentage", "Trade Permission", "Final Action", "Rank Reason",
        ]
        # Prefer the daily locked table for rank/regime; keep run-level execution columns when duplicate.
        summary = summary.drop(columns=[c for c in merge_columns if c != "Symbol" and c in summary.columns], errors="ignore")
        summary = summary.merge(daily[[c for c in merge_columns if c in daily.columns]], on="Symbol", how="left")
        first = [
            "Expected Return 24H (%)", "Expected Return 36H (%)", "Expected Value 6H (%)",
            "Probability Reach EV 1H (%)", "Probability Reach EV 6H (%)", "Probability Reach EV 12H (%)",
            "Transition Risk 6H (%)", "Observed Tick Volume 12H", "Volume 12H Z-Score",
            "Rank", "Rank Score", "Symbol", "Status",
            "Data Quality", "Data Quality Score", "Higher Standard Regime", "Higher-Standard Bias",
            "Less-Risky Bias", "Final Action", "Trade Permission", "Transition Risk 24H",
            "Expected Return 12H (%)", "Current Session", "Session Priority", "Average Spread",
            "Spread Quality", "Higher Reliability", "Uncertainty", "Error Percentage",
        ]
        summary = summary[[c for c in first if c in summary] + [c for c in summary.columns if c not in first]]
    def _finalize_rank_frame(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        pinned = [
            column for column in (
                "Expected Return 24H (%)", "Expected Return 36H (%)", "Expected Value 6H (%)",
                "Probability Reach EV 1H (%)", "Probability Reach EV 6H (%)",
                "Probability Reach EV 12H (%)", "Transition Risk 6H (%)",
                "Observed Tick Volume 12H", "Volume 12H Z-Score",
            )
            if column in frame.columns
        ]
        if pinned:
            frame = frame.loc[:, pinned + [column for column in frame.columns if column not in pinned]].copy()
        if "Rank Score" in frame.columns:
            score = pd.to_numeric(frame["Rank Score"], errors="coerce")
            permission = (
                frame["Trade Permission"].astype(str).str.upper()
                if "Trade Permission" in frame.columns
                else pd.Series("CHECK", index=frame.index)
            )
            frame["Rank Grade"] = np.select(
                [permission.isin(["BLOCKED", "NO TRADE"]), score.ge(90), score.ge(75), score.ge(60)],
                ["UNRANKED", "A", "B", "C"], default="D",
            )
        return frame

    summary = _finalize_rank_frame(summary)
    daily = _finalize_rank_frame(daily)
    hourly = _finalize_rank_frame(hourly)

    def _add_time_identity(frame: pd.DataFrame, *, fallback_timeframe: str) -> pd.DataFrame:
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            return frame
        out = frame.copy()
        if "Timeframe" not in out.columns:
            out["Timeframe"] = fallback_timeframe
        else:
            out["Timeframe"] = out["Timeframe"].fillna(fallback_timeframe).replace("", fallback_timeframe)
        if "Time" not in out.columns:
            source = next((c for c in ("Completed Broker Candle", "Completed Candle", "Broker Timestamp", "Locked At") if c in out.columns), None)
            if source is not None:
                out["Time"] = out[source]
            else:
                out["Time"] = pd.NA
        preferred = [c for c in ("Time", "Timeframe", "Rank", "Symbol") if c in out.columns]
        return out.loc[:, preferred + [c for c in out.columns if c not in preferred]]

    fallback_tf = str(state.get("timeframe") or "H4").upper() if state is not None else "H4"
    summary = _add_time_identity(summary, fallback_timeframe=fallback_tf)
    daily = _add_time_identity(daily, fallback_timeframe=fallback_tf)
    hourly = _add_time_identity(hourly, fallback_timeframe=fallback_tf)
    if not summary.empty and "Completed Candle" in summary.columns:
        completed = _broker_wall_series(summary["Completed Candle"])
        summary.insert(min(2, len(summary.columns)), "Date", completed.dt.strftime("%Y-%m-%d"))
        summary.insert(min(3, len(summary.columns)), "Broker Candle Time", completed.dt.strftime("%H:%M"))
    if state is not None:
        canonical_run_id = str(state.get("canonical_run_id_20260617") or state.get("quota_safe_run_id_20260705") or "")
        canonical_timeframe = str(state.get("canonical_selected_timeframe_20260705") or state.get("timeframe") or "H4").upper()
        canonical_symbols = state.get("canonical_selected_symbols_20260705") or state.get(SELECTED_KEY) or []
        canonical_scope = ",".join(str(item) for item in canonical_symbols)
        if canonical_run_id:
            tagged_frames = []
            for frame in (summary, daily, hourly):
                tagged = frame.copy()
                if not tagged.empty:
                    tagged["Canonical Run ID"] = canonical_run_id
                    tagged["Canonical Timeframe"] = canonical_timeframe
                    tagged["Canonical Symbol Scope"] = canonical_scope
                tagged_frames.append(tagged)
            summary, daily, hourly = tagged_frames
        state[FIELD10_SUMMARY_KEY] = summary
        state[FIELD10_DAILY_KEY] = daily
        state[FIELD10_HOURLY_KEY] = hourly
    return {"summary": summary, "daily": daily, "hourly": hourly}


def _persist_state_machine(
    parent_run_id: str, symbol: str, timeframe: str, item: Mapping[str, Any],
) -> None:
    """Durably record a symbol stage so reruns can resume incomplete children."""
    try:
        from core.timeframe_identity_migration_20260706 import migrate_timeframe_identity
        migrate_timeframe_identity(DB_PATH, create_backup=False)
        now = pd.Timestamp.now(tz="UTC").isoformat()
        with sqlite3.connect(str(DB_PATH), timeout=15) as conn:
            conn.execute("PRAGMA busy_timeout=15000")
            conn.execute(
                """INSERT OR REPLACE INTO multi_symbol_state_machine_20260706(
                    parent_run_id,symbol,timeframe,state,progress_percent,provider,available_candles,
                    required_candles,latest_timestamp,rejection_reason,details_json,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (parent_run_id, normalize_symbol(symbol), str(timeframe).upper(),
                 str(item.get("state") or item.get("publication_status") or item.get("status") or "WAITING"),
                 float(item.get("percent") or 0.0), str(item.get("provider") or item.get("provider_status") or ""),
                 item.get("available_candles"), item.get("required_candles"),
                 str(item.get("latest_timestamp") or ""), str(item.get("rejection_reason") or item.get("error") or ""),
                 json.dumps(dict(item), sort_keys=True, default=str), now),
            )
            conn.commit()
    except Exception:
        pass


def _progress_snapshot(parent_run_id: str, selected: Sequence[str], statuses: Mapping[str, Mapping[str, Any]], current: str = "", stage: str = "") -> dict[str, Any]:
    terminal = {"COMPLETED", "HARD_SOURCE_UNAVAILABLE", "FAILED_VALIDATION", "FAILED"}
    effective = lambda item: str(item.get("state") or item.get("publication_status") or item.get("status") or "WAITING")
    completed = sum(1 for item in statuses.values() if effective(item) == "COMPLETED")
    failed = sum(1 for item in statuses.values() if effective(item) in terminal - {"COMPLETED"})
    total = max(1, len(selected))
    processing_percent = round(sum(float(item.get("percent") or 0.0) for item in statuses.values()) / total, 1)
    # Processing completion and publication success are separate signals.  A
    # terminal failed child may legitimately reach 100% processing, while the
    # publication_status remains PARTIAL/FAILED and can never be shown as a
    # successful all-symbol calculation.
    publication_status = "COMPLETED" if completed == len(selected) else ("FAILED" if failed == len(selected) else "PARTIAL")
    return {
        "parent_run_id": parent_run_id, "selected_symbols": list(selected),
        "overall_percent": processing_percent,
        "progress_percent": processing_percent,
        "publication_status": publication_status,
        "current_symbol": current, "current_stage": stage,
        "completed_symbols": completed, "failed_symbols": failed,
        "remaining_symbols": max(0, total - completed - failed),
        "symbols": {key: dict(value) for key, value in statuses.items()},
        "updated_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }


def _run_selected_symbols_impl(
    state: MutableMapping[str, Any], single_symbol_runner: Callable[[], Mapping[str, Any]], *,
    scope: str = "FULL", progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Implementation for the guarded public multi-symbol transaction."""
    from core.timeframe_identity_migration_20260706 import migrate_timeframe_identity
    migrate_timeframe_identity(DB_PATH, create_backup=True)
    # Calculation authority is the exact loaded subset of GlobalSymbolContext.
    # Configured symbols remain separate and failed members are never admitted.
    try:
        from core.global_symbol_context import get_global_symbol_context
        global_context = get_global_symbol_context(state, db_path=DB_PATH, restore=True)
        selected = list(global_context.loaded_symbols)
    except Exception:
        selected = []
    if not selected:
        return {"ok": False, "status": "NO_LOADED_GLOBAL_SYMBOLS", "error": "Load the configured global universe before calculation."}
    scope = str(scope or "FULL").upper()
    try:
        from core.field10_fast_lane_20260709 import is_field10_fast_lane, defer_to_quick, field10_fast_lane_summary
        field10_fast_lane_20260709 = is_field10_fast_lane(state, scope)
    except Exception:
        field10_fast_lane_20260709 = False
        def defer_to_quick(state, name, **kwargs):
            return {"ok": False, "status": "DEFERRED_TO_QUICK_RUN", "deferred": True, **kwargs}
        def field10_fast_lane_summary(state):
            return {"enabled": False}
    main = selected[0]
    from core.global_symbol_compat import set_legacy_calculation_symbol
    set_legacy_calculation_symbol(state, main, connector=False)
    state["selected_symbols_for_run_20260705"] = list(selected)
    requested_initial_display = normalize_symbol(
        getattr(global_context, "active_display_symbol", "") or main
    )
    if main not in selected:
        selected.insert(0, main)
    # The main symbol always runs first. Secondary instruments are restricted to
    # the existing Lunch-core path (Fields 1–3) plus Fields 10–11 persistence.
    selected = [main, *[symbol for symbol in selected if symbol != main]]
    fingerprint = sha256((scope + "|MAIN=" + main + "|" + "|".join(selected)).encode()).hexdigest()[:16]
    previous_manifest = state.get(MANIFEST_KEY)

    parent_run_id = f"MS-{pd.Timestamp.now(tz='UTC').strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    state[PARENT_RUN_KEY] = parent_run_id
    started = time.perf_counter()
    budget_enabled = bool(state.get("super_quick_time_budget_enabled_20260706") and scope == "LUNCH_CORE")
    overall_started = float(state.get("super_quick_run_started_monotonic_20260706") or time.monotonic())
    target_min_seconds = max(0.0, float(state.get("super_quick_target_min_seconds_20260706") or 120.0))
    target_max_seconds = max(target_min_seconds, float(state.get("super_quick_target_max_seconds_20260706") or 240.0))
    process = None
    with suppress(Exception):
        import psutil
        process = psutil.Process(os.getpid())
    original_rss = float(process.memory_info().rss) if process else 0.0
    original_cpu = float(sum(process.cpu_times()[:2])) if process else 0.0
    statuses: dict[str, dict[str, Any]] = {symbol: {"status": "WAITING", "percent": 0, "stage": "Queued", "publication_status": "PENDING"} for symbol in selected}
    resource_rows: list[dict[str, Any]] = []
    summaries: dict[str, Any] = {}
    last_status: dict[str, Any] = {}
    latest_broker_day = ""
    _last_emitted_percent: dict[str, float] = {}

    def publish(current: str = "", stage: str = "") -> None:
        snapshot = _progress_snapshot(parent_run_id, selected, statuses, current, stage)
        elapsed_now = time.perf_counter() - started
        processed = int(snapshot.get("completed_symbols") or 0) + int(snapshot.get("failed_symbols") or 0)
        remaining = int(snapshot.get("remaining_symbols") or 0)
        eta = (elapsed_now / processed * remaining) if processed > 0 else None
        snapshot["elapsed_seconds"] = round(elapsed_now, 2)
        snapshot["estimated_remaining_seconds"] = round(eta, 2) if eta is not None else None
        state[PROGRESS_KEY] = snapshot
        tf = str(state.get("timeframe") or "H4").upper()
        current_percent = float(statuses.get(current, {}).get("percent") or 0.0) if current else 0.0
        current_state = str(statuses.get(current, {}).get("state") or statuses.get(current, {}).get("status") or "").upper() if current else ""
        terminal = current_state in {"COMPLETED", "HARD_SOURCE_UNAVAILABLE", "FAILED_VALIDATION", "FAILED"} or current_percent >= 99.9
        last_emitted = float(_last_emitted_percent.get(current, -100.0)) if current else -100.0
        # Super Quick used to write SQLite and redraw a full progress table for
        # every small sub-stage. Emit only meaningful 20-point changes plus all
        # terminal states; calculations and internal state still update normally.
        should_emit = (not field10_fast_lane_20260709) or not current or terminal or (current_percent - last_emitted >= 20.0)
        if current and current in statuses and should_emit:
            _persist_state_machine(parent_run_id, current, tf, statuses[current])
            _last_emitted_percent[current] = current_percent
        if progress_callback and should_emit:
            progress_callback(snapshot)

    publish(stage="Validating selected instruments")
    original_scope = str(state.get("settings_calculation_scope_20260625") or scope).upper()
    for index, symbol in enumerate(selected, start=1):
        # Quota-safe batches continue through the full selected universe.
        # Provider backoff/cache policy is handled by the prepared-data orchestrator.
        child_started = time.perf_counter()
        child_rss = float(process.memory_info().rss) if process else 0.0
        child_cpu = float(sum(process.cpu_times()[:2])) if process else 0.0
        child_id = f"{parent_run_id}:{symbol}"
        statuses[symbol] = {"status": "LOADING_CACHE", "percent": 5, "stage": "Loading symbol context", "child_run_id": child_id, "publication_status": "PENDING"}
        publish(symbol, "Loading symbol context")
        try:
            cached = activate_symbol_result(state, symbol)
            if not cached.get("ok"):
                clear_active_symbol_results(state)
                set_legacy_calculation_symbol(state, symbol, connector=False)  # approved calculation boundary
                state[CHILD_RUN_KEY] = {"symbol": symbol, "child_run_id": child_id, "parent_run_id": parent_run_id}
            state["multi_symbol_current_child_id_20260701"] = child_id
            state["multi_symbol_current_index_20260701"] = index
            state["multi_symbol_current_total_20260701"] = len(selected)
            child_scope = scope if symbol == main else "LUNCH_CORE"
            state["settings_calculation_scope_20260625"] = child_scope
            state["multi_symbol_child_scope_20260702"] = child_scope
            stage_text = (
                "Refreshing main symbol Field 10 production fast lane"
                if field10_fast_lane_20260709 else
                (
                    "Refreshing main symbol and running requested production scope"
                    if symbol == main else
                    "Refreshing secondary symbol and running Fields 1-3 plus Fields 10-11"
                )
            )
            statuses[symbol].update({
                "percent": 20,
                "stage": stage_text,
                "calculation_scope": child_scope,
                "field_scope": (
                    "FIELDS_1_TO_9_PLUS_AI" if symbol == main and child_scope in {"QUICK", "FULL"}
                    else "FIELD_10_FAST_LANE_PLUS_MINIMUM_FIELDS_1_TO_3_GATES" if field10_fast_lane_20260709
                    else "FIELDS_1_TO_3_PLUS_FIELDS_10_11"
                ),
                "main_symbol": symbol == main,
            })
            publish(symbol, stage_text)
            # The Settings-owned run orchestrator collected market data once
            # before any child calculation. Activate that normalized frame here;
            # opening fields and recursive child runs must never call a provider.
            try:
                from core.calculation.run_orchestrator import activate_prepared_symbol
                api_report = activate_prepared_symbol(state, symbol)
            except Exception as api_exc:
                from core.complete_repair_20260705 import log_internal_error
                api_report = {
                    "ok": False, "status": "PREPARED_DATA_ACTIVATION_FAILED", "requests": 0,
                    "cache_hits": 0,
                    "incident_id": log_internal_error("multi_symbol.prepared_market_data", api_exc, symbol=symbol),
                }
            statuses[symbol]["provider_retry_count"] = 0
            statuses[symbol]["provider_status"] = api_report.get("status")
            statuses[symbol]["provider"] = api_report.get("source") or api_report.get("provider")
            statuses[symbol]["status"] = "FETCHING_FALLBACK" if "FALLBACK" in str(api_report.get("status") or "").upper() else "VALIDATING"
            statuses[symbol]["percent"] = 30
            publish(symbol, "Validating exact-symbol selected-timeframe candles")
            statuses[symbol]["fallback_count"] = int(str(api_report.get("status") or "").startswith(("LIVE_PLAN_", "CACHED", "STALE")))
            # Build the common immutable OHLC/return/volatility/ADX/session
            # bundle once per exact source fingerprint. It is a protected-output
            # neutral cache substrate; existing calculators remain authoritative.
            try:
                from core.multi_symbol_api_runtime_20260702 import completed_h1_identity
                from core.quick_run_feature_cache_20260702 import get_or_build_shared_feature_bundle
                shared_bundle = get_or_build_shared_feature_bundle(
                    state, state.get("last_df"),
                    provider=api_report.get("source") or state.get("source"),
                    symbol=symbol, timeframe=state.get("timeframe") or "H4",
                    completed_broker_candle=completed_h1_identity(state),
                    calculation_version=state.get("calculation_version") or "protected-current",
                )
                api_report["shared_feature_bundle"] = {
                    "fingerprint": shared_bundle.fingerprint.key(),
                    "rows": len(shared_bundle.frame),
                    "cache_hit": shared_bundle.cache_hit,
                }
            except Exception as feature_exc:
                api_report["shared_feature_bundle"] = {
                    "status": "UNAVAILABLE",
                    "error": f"{type(feature_exc).__name__}: {feature_exc}",
                }
            statuses[symbol].update({"status": "CALCULATING_FIELD_1", "percent": 40, "stage": "Calculating and publishing Field 1"})
            publish(symbol, statuses[symbol]["stage"])
            runner_attempts = 0
            runner_error: Exception | None = None
            result: Mapping[str, Any] | None = None
            for runner_attempts in range(1, 3):
                try:
                    candidate = single_symbol_runner()
                    result = candidate if isinstance(candidate, Mapping) else {"ok": False, "status": "EMPTY_RUNNER_STATUS"}
                    runner_error = None
                    break
                except Exception as exc:
                    runner_error = exc
                    if runner_attempts < 2:
                        time.sleep(0.05 * (2 ** (runner_attempts - 1)))
            statuses[symbol]["calculation_retry_count"] = max(0, runner_attempts - 1)
            if runner_error is not None:
                from core.complete_repair_20260705 import log_internal_error
                incident = log_internal_error("multi_symbol.single_symbol_runner", runner_error, symbol=symbol, attempt=runner_attempts)
                raise RuntimeError(f"symbol calculation failed safely; incident={incident}") from runner_error
            result = dict(result) if isinstance(result, Mapping) else {"ok": False, "status": "EMPTY_RUNNER_STATUS"}
            result["multi_symbol_api_router_20260702"] = api_report

            # Materialize the genuine exact-symbol Field 1 Table 4 before the
            # runtime cache is written. Previously this adapter was first called
            # during Field 10 bundle construction *after* the cache save, so a
            # reload could falsely report field1_complete=False for secondary
            # children even though the live publication had succeeded.
            try:
                from core.canonical_runtime_20260617 import get_canonical as _get_field1_canonical
                from ui.lunch_next_hour_bias_history_20260626 import build_field1_table4_publication
                field1_table4, field1_source_status = build_field1_table4_publication(
                    state=state, canonical=dict(_get_field1_canonical(state) or {}),
                )
                result["field1_table4_publication_20260707"] = {
                    "ok": isinstance(field1_table4, pd.DataFrame) and not field1_table4.empty,
                    "rows": int(len(field1_table4)) if isinstance(field1_table4, pd.DataFrame) else 0,
                    "source_status": field1_source_status,
                    "symbol": symbol,
                    "timeframe": str(state.get("timeframe") or "H4").upper(),
                }
            except Exception as field1_sidecar_exc:
                result["field1_table4_publication_20260707"] = {
                    "ok": False, "status": "EXACT_SYMBOL_FIELD1_UNAVAILABLE",
                    "error": f"{type(field1_sidecar_exc).__name__}: {field1_sidecar_exc}",
                }

            statuses[symbol].update({"status": "CALCULATING_FIELD_2", "percent": 55, "stage": "Publishing selected-symbol Power BI bundle"})
            publish(symbol, statuses[symbol]["stage"])
            # Ensure every selected symbol has genuine saved Field 3 standard
            # evidence. Secondary LUNCH_CORE runs do not always publish the UI
            # aliases required by the immutable Field 10 child bundle. Reuse the
            # existing exact-symbol local builder with provider fetching disabled;
            # it reads only the already activated selected-timeframe frame.
            try:
                from core.field3_multi_symbol_fallback_20260703 import build_field3_local_snapshot
                local_field3 = build_field3_local_snapshot(state, symbol, allow_provider_fetch=False)
                result["field3_local_symbol_snapshot_20260703"] = {
                    "ok": bool(local_field3.get("ok")),
                    "status": local_field3.get("status"),
                    "symbol": local_field3.get("symbol"),
                    "timeframe": local_field3.get("timeframe"),
                    "rows": local_field3.get("rows"),
                    "source": local_field3.get("source"),
                }
            except Exception as local_field3_exc:
                result["field3_local_symbol_snapshot_20260703"] = {
                    "ok": False, "status": "EXACT_SYMBOL_FIELD3_UNAVAILABLE",
                    "error": f"{type(local_field3_exc).__name__}: {local_field3_exc}",
                }

            # The lifecycle monitor is additive shadow evidence, not a production
            # gate. Defer it in Super Quick so the top-30 publication is not slowed
            # by one extra historical lifecycle build per symbol.
            if field10_fast_lane_20260709:
                result["field3_regime_lifecycle_monitor_20260701"] = defer_to_quick(
                    state,
                    f"field3_regime_lifecycle_monitor_20260701:{symbol}",
                    reason="Lifecycle shadow evidence is deferred to Quick/Full; exact Field 3 production evidence is already published.",
                )
            else:
                try:
                    from core.canonical_runtime_20260617 import get_canonical
                    from core.field3_regime_lifecycle_monitor_20260701 import build_field3_regime_lifecycle_monitor
                    field3_snapshot = get_canonical(state)
                    if field3_snapshot:
                        required_identity = {
                            "run_id": field3_snapshot.get("run_id") or field3_snapshot.get("canonical_calculation_id"),
                            "source_id": field3_snapshot.get("source_id") or field3_snapshot.get("data_source_id"),
                            "snapshot_hash": field3_snapshot.get("snapshot_hash") or field3_snapshot.get("source_snapshot_hash"),
                            "completed_candle": (
                                field3_snapshot.get("completed_broker_candle")
                                or field3_snapshot.get("broker_candle_time")
                                or field3_snapshot.get("latest_completed_candle_time")
                            ),
                        }
                        if all(required_identity.values()):
                            field3_payload = build_field3_regime_lifecycle_monitor(field3_snapshot, state, force=False)
                            result["field3_regime_lifecycle_monitor_20260701"] = {
                                "ok": str(field3_payload.get("status") or "").upper() in {"AVAILABLE", "INVALID_DATA_QUALITY"},
                                "status": field3_payload.get("status"),
                                "symbol": field3_payload.get("symbol"),
                                "rows": len(field3_payload.get("history_25d") or []),
                                "shadow_only": True,
                            }
                        else:
                            result["field3_regime_lifecycle_monitor_20260701"] = {
                                "ok": False,
                                "status": "IDENTITY_INCOMPLETE",
                                "missing_identity": [name for name, value in required_identity.items() if not value],
                                "shadow_only": True,
                            }
                except Exception as field3_exc:
                    result["field3_regime_lifecycle_monitor_20260701"] = {
                        "ok": False, "shadow_only": True,
                        "error": f"{type(field3_exc).__name__}: {field3_exc}",
                    }
            result["multi_symbol_child_scope_20260702"] = child_scope
            result["multi_symbol_main_symbol_20260702"] = main
            try:
                from core.v9_architecture_guard_20260702 import finalize_after_settings_run
                finalize_after_settings_run(state, result)
            except Exception as v9_guard_exc:
                result.setdefault("diagnostics", {})["v9_architecture_guard_error"] = f"{type(v9_guard_exc).__name__}: {v9_guard_exc}"
            from core.powerbi_child_bundle_20260706 import build_and_store_powerbi_bundle
            powerbi_publication = build_and_store_powerbi_bundle(state, allow_causal_fallback=True)
            result["powerbi_child_publication_20260706"] = powerbi_publication
            field1_receipt = result.get("field1_table4_publication_20260707") if isinstance(result.get("field1_table4_publication_20260707"), Mapping) else {}
            field3_receipt = result.get("field3_local_symbol_snapshot_20260703") if isinstance(result.get("field3_local_symbol_snapshot_20260703"), Mapping) else {}
            state["child_component_completion_receipt_20260722"] = {
                "version": "exact-child-components-20260722-v1",
                "symbol": symbol,
                "timeframe": str(state.get("timeframe") or "H4").upper(),
                "parent_run_id": parent_run_id,
                "child_run_id": child_id,
                "field1_complete": bool(field1_receipt.get("ok")),
                "field2_complete": bool(isinstance(powerbi_publication, Mapping) and powerbi_publication.get("ok")),
                "field3_complete": bool(field3_receipt.get("ok")),
                "field1_detail": dict(field1_receipt),
                "field2_status": str(powerbi_publication.get("status") or powerbi_publication.get("calibration_status") or "") if isinstance(powerbi_publication, Mapping) else "",
                "field3_detail": dict(field3_receipt),
                "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
            }
            statuses[symbol].update({"status": "CALCULATING_FIELD_3", "percent": 68, "stage": "Validating and publishing Field 3"})
            publish(symbol, statuses[symbol]["stage"])
            last_status = result
            statuses[symbol].update({"status": "CALCULATING_FIELD_10", "percent": 82, "stage": "Validating and publishing Field 10"})
            publish(symbol, "Validating and publishing Field 10")
            elapsed = time.perf_counter() - child_started
            rss_delta = ((float(process.memory_info().rss) if process else child_rss) - child_rss) / (1024 * 1024)
            cpu_delta = (float(sum(process.cpu_times()[:2])) if process else child_cpu) - child_cpu
            evidence = _persist_symbol_evidence(
                state, parent_run_id=parent_run_id, child_run_id=child_id, scope=child_scope,
                status=result, elapsed=elapsed, rss_delta_mb=rss_delta, cpu_seconds=cpu_delta,
            )
            if symbol != main:
                evidence["field_validation"] = [
                    row for row in (evidence.get("field_validation") or [])
                    if int(row.get("Field") or 0) in {1, 2, 3}
                ]
            latest_broker_day = str(evidence.get("broker_day") or latest_broker_day)
            summaries[symbol] = evidence
            from core.runtime_state_cache_20260628 import save_runtime_state
            snapshot_path = _cache_path(symbol)
            cache_report = save_runtime_state(state, status=result, scope=child_scope, path=snapshot_path)
            statuses[symbol].update({"status": "PUBLISHING", "percent": 92, "stage": "Persisting canonical child snapshot"})
            publish(symbol, statuses[symbol]["stage"])
            table4_publication = {"ok": False, "status": "NOT_ATTEMPTED", "symbol": symbol}
            registry_report = {"ok": False, "status": "NOT_ATTEMPTED"}
            try:
                from core.canonical_runtime_20260617 import get_canonical
                from core.child_generation_contract_20260702 import (
                    build_child_generation_bundle, publish_child_generation_to_field10,
                )
                from core.generation_registry_20260702 import calculate_valid_until, register_completed_generation
                from core.symbol_context_20260702 import SymbolContext
                frozen_canonical = dict(get_canonical(state) or {})
                candle_value = (frozen_canonical.get("completed_broker_candle") or frozen_canonical.get("broker_candle_time")
                                or frozen_canonical.get("latest_completed_candle_time") or frozen_canonical.get("completed_candle"))
                candle_stamp = pd.to_datetime(candle_value, errors="coerce", utc=True)
                if pd.isna(candle_stamp):
                    candle_iso = ""
                else:
                    tf_for_identity = str(state.get("timeframe") or frozen_canonical.get("timeframe") or "H4").upper()
                    floor_rule = {"M1":"min", "M5":"5min", "M15":"15min", "M30":"30min", "H1":"h", "H4":"4h", "D1":"D"}.get(tf_for_identity, "h")
                    candle_iso = pd.Timestamp(candle_stamp).floor(floor_rule).isoformat()
                canonical_run_id = str(frozen_canonical.get("run_id") or frozen_canonical.get("canonical_calculation_id") or "")
                source_id = str(frozen_canonical.get("source_id") or frozen_canonical.get("data_source_id")
                                or frozen_canonical.get("source_snapshot_hash") or "")
                snapshot_hash = str(frozen_canonical.get("snapshot_hash") or frozen_canonical.get("source_snapshot_hash") or "")
                child_context = SymbolContext(
                    settings_main_symbol=main,
                    connector_symbol=normalize_symbol(state.get("connector_symbol_20260702") or main),
                    calculation_symbol=symbol, lunch_display_symbol=symbol, active_snapshot_symbol=symbol,
                    selected_symbols=tuple(selected), timeframe=str(state.get("timeframe") or frozen_canonical.get("timeframe") or "H4").upper(),
                    parent_run_id=parent_run_id, child_run_id=child_id, canonical_run_id=canonical_run_id or None,
                    source_id=source_id or None, snapshot_hash=snapshot_hash or None,
                    completed_broker_candle=candle_iso or None, generation_status=str(evidence.get("status") or "PARTIAL"),
                    valid_until=(calculate_valid_until(candle_iso, state.get("timeframe") or frozen_canonical.get("timeframe") or "H4") if candle_iso else None),
                )
                bundle = build_child_generation_bundle(
                    state=state, canonical=frozen_canonical, context=child_context,
                    runtime_snapshot_path=snapshot_path, calculation_status=str(evidence.get("status") or "PARTIAL"),
                    calculation_timing={"elapsed_seconds": elapsed},
                    resource_metrics={"rss_delta_mb": rss_delta, "cpu_seconds": cpu_delta,
                                      "api_requests": api_report.get("requests", 0), "cache_hits": api_report.get("cache_hits", 0)},
                )
                table4_publication = publish_child_generation_to_field10(bundle, path=DB_PATH)
                state["field10_table4_publication_status_20260702"] = {
                    **dict(table4_publication),
                    "symbol": symbol,
                    "timeframe": str(state.get("timeframe") or frozen_canonical.get("timeframe") or "H4").upper(),
                    "parent_run_id": parent_run_id,
                    "child_run_id": child_id,
                }
                if table4_publication.get("ok") and table4_publication.get("completion_status") == "COMPLETED":
                    context_map = bundle.context.to_dict()
                    context_map["symbol"] = symbol
                    registry_report = register_completed_generation(
                        context=context_map, runtime_snapshot_path=snapshot_path,
                        publication_status="COMPLETED",
                        last_active_route="Lunch", last_open_lunch_field="Field 10",
                    )
            except Exception as publication_exc:
                table4_publication = {
                    "ok": False, "status": "PARTIAL", "symbol": symbol,
                    "error": f"{type(publication_exc).__name__}: {publication_exc}",
                }
            evidence["field1_table4_to_field10"] = table4_publication
            evidence["generation_registry"] = registry_report
            statuses[symbol].update({"status": "RELOAD_VALIDATION", "percent": 97, "stage": "Reload-validating persisted child snapshot"})
            publish(symbol, statuses[symbol]["stage"])
            from core.child_snapshot_publication_20260706 import publish_complete_child, validate_child_state, mark_reload_validation
            child_publication = publish_complete_child(state, runtime_snapshot_path=snapshot_path, db_path=DB_PATH)
            reload_detail: dict[str, Any] = {"ok": False, "status": "CACHE_RELOAD_FAILED"}
            if snapshot_path.is_file():
                try:
                    reloaded_payload = _read_cache_payload(snapshot_path)
                    reloaded_state = reloaded_payload.get("state") if isinstance(reloaded_payload, Mapping) else {}
                    reload_detail = validate_child_state(
                        reloaded_state if isinstance(reloaded_state, Mapping) else {},
                        runtime_snapshot_path=snapshot_path, db_path=DB_PATH,
                    )
                except Exception as reload_exc:
                    reload_detail = {"ok": False, "status": "CACHE_RELOAD_FAILED", "error": f"{type(reload_exc).__name__}: {reload_exc}"}
            publication_row = child_publication.get("validation", {}).get("identity", {})
            if publication_row:
                mark_reload_validation(publication=publication_row, db_path=DB_PATH, passed=bool(reload_detail.get("ok")), detail=reload_detail)
            evidence["complete_child_publication_20260706"] = child_publication
            evidence["reload_validation_20260706"] = reload_detail
            # Research-paper upgrades are deliberately isolated from production.
            # They consume only the frozen exact-symbol completed frame, persist
            # NOT_PROMOTED evidence, and never feed a decision or ranking input.
            if field10_fast_lane_20260709:
                evidence["field10_shadow_research_candidates_20260706"] = defer_to_quick(
                    state,
                    f"field10_shadow_research_candidates_20260706:{symbol}",
                    reason="Shadow research evidence is deferred so Super Quick can publish Field 10 production rank first.",
                )
            else:
                try:
                    from core.field10_shadow_research_candidates_20260706 import evaluate_and_persist_shadow_candidates
                    from core.powerbi_child_bundle_20260706 import _source_frame as _published_source_frame
                    _research_identity = child_publication.get("validation", {}).get("identity", {})
                    evidence["field10_shadow_research_candidates_20260706"] = evaluate_and_persist_shadow_candidates(
                        frame=_published_source_frame(state),
                        symbol=symbol,
                        timeframe=str(state.get("timeframe") or _research_identity.get("timeframe") or "H4"),
                        completed_candle=_research_identity.get("completed_candle"),
                        db_path=DB_PATH,
                        research_run_id=f"{child_id}:SHADOW",
                    )
                except Exception as shadow_exc:
                    evidence["field10_shadow_research_candidates_20260706"] = {
                        "ok": False, "status": "SHADOW_ONLY_UNAVAILABLE",
                        "promotion_status": "NOT_PROMOTED",
                        "production_decision_changed": False,
                        "error": f"{type(shadow_exc).__name__}: {shadow_exc}",
                    }
            validation = child_publication.get("validation") if isinstance(child_publication.get("validation"), Mapping) else {}
            completed = bool(child_publication.get("ok") and reload_detail.get("ok"))
            hard_source = (
                int(validation.get("available_candles") or 0) < int(validation.get("required_candles") or 0)
                and not bool(api_report.get("ok"))
            )
            terminal_status = "COMPLETED" if completed else ("HARD_SOURCE_UNAVAILABLE" if hard_source else "FAILED_VALIDATION")
            terminal_percent = 100 if completed else (98 if hard_source else 97)
            statuses[symbol].update({
                "status": "COMPLETED" if completed else "PARTIAL", "state": terminal_status, "publication_status": terminal_status,
                "percent": terminal_percent, "stage": "Completed" if completed else ("Real source history unavailable" if hard_source else "Failed publication validation"),
                "elapsed_seconds": round(elapsed, 3), "data_quality": evidence.get("quality", {}).get("grade"),
                "cache_bytes": cache_report.get("bytes", 0),
                "available_candles": validation.get("available_candles"),
                "required_candles": validation.get("required_candles"),
                "latest_timestamp": validation.get("identity", {}).get("completed_candle"),
                "rejection_reason": (
                    "; ".join(validation.get("missing_identity") or [])
                    or ("failed components: " + ", ".join(validation.get("failed_components") or []) if validation.get("failed_components") else "")
                    or validation.get("spacing", {}).get("status")
                ),
                "publication_component_gates": validation.get("component_gates") or {},
            })
            resource_rows.append({
                "Symbol": symbol, "Elapsed Seconds": round(elapsed, 3),
                "RSS Delta MB": round(rss_delta, 3), "CPU Seconds": round(cpu_delta, 3),
                "Cache MB": round(float(cache_report.get("bytes") or 0) / (1024 * 1024), 3),
                "Status": statuses[symbol]["status"],
                "Calculation Scope": child_scope,
                "Fields Calculated": (
                    "1-9 + AI" if symbol == main and child_scope in {"QUICK", "FULL"}
                    else "Field 10 + minimum Fields 1-3 gates" if field10_fast_lane_20260709
                    else "1-3 + Fields 10-11"
                ),
                "API Request Count": int(state.get("multi_symbol_api_requests_current_symbol_20260702") or 0),
                "Cache Hit Count": int(state.get("multi_symbol_api_cache_hits_current_symbol_20260702") or 0),
                "Database Write Count": 1 if table4_publication.get("ok") else 0,
            })
        except Exception as exc:
            elapsed = time.perf_counter() - child_started
            statuses[symbol].update({
                "status": "PARTIAL", "state": "FAILED_VALIDATION", "publication_status": "FAILED_VALIDATION", "percent": 97, "stage": "Failed validation",
                "elapsed_seconds": round(elapsed, 3), "error": f"{type(exc).__name__}: {exc}",
            })
            resource_rows.append({"Symbol": symbol, "Elapsed Seconds": round(elapsed, 3), "RSS Delta MB": 0.0, "CPU Seconds": 0.0, "Cache MB": 0.0, "Status": "FAILED_VALIDATION"})
        finally:
            state.pop(CHILD_RUN_KEY, None)
            clear_legacy_calculation_symbol(state)
            state["settings_calculation_scope_20260625"] = original_scope
            publish(symbol, statuses[symbol].get("stage", "Complete"))

    # A live 5+5 Twelve Data run is intentionally kept inside the requested
    # two-to-four-minute window. Cache-only reruns are never slowed down.
    try:
        market_report = state.get("market_data_run_results_20260705") or {}
        live_requests = int(market_report.get("live_requests_started") or 0) if isinstance(market_report, Mapping) else 0
    except Exception:
        live_requests = 0
    if False and budget_enabled and live_requests >= 6:
        overall_elapsed = max(0.0, time.monotonic() - overall_started)
        remaining_minimum = min(
            max(0.0, target_min_seconds - overall_elapsed),
            max(0.0, target_max_seconds - overall_elapsed),
        )
        if remaining_minimum > 0:
            publish(stage="Final consistency window before opening Lunch")
            time.sleep(remaining_minimum)
            state["super_quick_minimum_pacing_seconds_20260706"] = round(remaining_minimum, 3)
    state["super_quick_total_elapsed_seconds_20260706"] = round(max(0.0, time.monotonic() - overall_started), 3)

    if latest_broker_day:
        with suppress(Exception):
            _rank_persisted_rows(parent_run_id, latest_broker_day)
    with suppress(Exception):
        from core.field10_integrated_evidence_20260702 import sync_integrated_ranks
        sync_integrated_ranks(parent_run_id)
    # Restore the main-symbol generation after the batch. Lunch may later switch
    # Fields 1–3 to another saved symbol without changing Fields 4–9.
    active = main
    if (
        requested_initial_display in selected
        and statuses.get(requested_initial_display, {}).get("status") in {"COMPLETED"}
    ):
        active = requested_initial_display
    elif statuses.get(active, {}).get("status") != "COMPLETED":
        active = next((symbol for symbol in selected if statuses.get(symbol, {}).get("status") in {"COMPLETED"}), selected[0])
    activation = activate_symbol_result(state, active)
    state[ACTIVE_KEY] = active
    state[DISPLAY_SYMBOL_KEY] = active
    if LUNCH_SYMBOL_WIDGET_KEY not in state:
        state[LUNCH_SYMBOL_WIDGET_KEY] = active
    else:
        state["lunch_symbol_selector_pending_widget_reset_20260702"] = active
    state["settings_calculation_scope_20260625"] = original_scope
    tables = load_field10_tables(state, parent_run_id=parent_run_id, symbol=active)
    elapsed_total = time.perf_counter() - started
    final_rss = float(process.memory_info().rss) if process else original_rss
    final_cpu = float(sum(process.cpu_times()[:2])) if process else original_cpu
    resource_report = {
        "rows": resource_rows,
        "total_elapsed_seconds": round(elapsed_total, 3),
        "rss_delta_mb": round((final_rss - original_rss) / (1024 * 1024), 3),
        "cpu_seconds": round(final_cpu - original_cpu, 3),
        "symbols": len(selected),
        "heat_proxy": "HIGH" if (final_cpu - original_cpu) > 180 else ("MODERATE" if (final_cpu - original_cpu) > 45 else "LOW"),
        "heat_proxy_note": "CPU-time proxy only; the application cannot read device temperature sensors on Streamlit Cloud.",
    }
    state[LAST_RESOURCE_KEY] = resource_report
    _effective_status = lambda item: str(item.get("state") or item.get("publication_status") or item.get("status") or "WAITING")
    completed = sum(1 for item in statuses.values() if _effective_status(item) == "COMPLETED")
    partial = sum(1 for item in statuses.values() if _effective_status(item) not in {"COMPLETED", "HARD_SOURCE_UNAVAILABLE", "FAILED_VALIDATION", "FAILED"})
    usable = completed
    failed = sum(1 for item in statuses.values() if _effective_status(item) in {"HARD_SOURCE_UNAVAILABLE", "FAILED_VALIDATION", "FAILED"})
    manifest = {
        **last_status,
        "ok": completed == len(selected),
        "status": "COMPLETED" if completed == len(selected) else ("FAILED" if failed == len(selected) else "PARTIAL"),
        "parent_run_id": parent_run_id,
        "selection_fingerprint": fingerprint,
        "selected_symbols": selected,
        "main_symbol": main,
        "fields_4_to_9_symbol": main,
        "secondary_symbol_scope": (
            "FIELD_10_FAST_LANE_PLUS_MINIMUM_FIELDS_1_TO_3_GATES"
            if field10_fast_lane_20260709 else
            "FIELDS_1_TO_3_PLUS_FIELDS_10_11"
        ),
        "active_symbol": active,
        "display_symbol": active,
        "symbol_status": statuses,
        "symbol_summaries": summaries,
        "completed_symbols": completed,
        "failed_symbols": failed,
        "calculation_scope": scope,
        "run_profile": "FIELD10_FAST_LANE" if field10_fast_lane_20260709 else scope,
        "field10_fast_lane_20260709": field10_fast_lane_summary(state) if field10_fast_lane_20260709 else {"enabled": False},
        "scope_matrix": {
            symbol: (
                "FIELDS_1_TO_9_PLUS_AI" if symbol == main and scope in {"QUICK", "FULL"}
                else "FIELD_10_FAST_LANE_PLUS_MINIMUM_FIELDS_1_TO_3_GATES" if field10_fast_lane_20260709
                else "FIELDS_1_TO_3_PLUS_FIELDS_10_11"
            )
            for symbol in selected
        },
        "elapsed_seconds": round(elapsed_total, 3),
        "activation": activation,
        "field10_rows": {name: int(len(frame)) for name, frame in tables.items()},
        "resource_report": resource_report,
        "version": VERSION,
    }
    state[MANIFEST_KEY] = manifest
    research_report: dict[str, Any] = {"ok": False, "status": "NOT_ATTEMPTED"}
    integrated_sync: dict[str, Any] = {"ok": False, "status": "NOT_ATTEMPTED"}
    try:
        from core.field10_ten_paper_research_20260701 import ensure_field10_research_validation
        research_report = ensure_field10_research_validation(state)
        from core.field10_integrated_evidence_20260702 import sync_integrated_research, load_integrated_current
        integrated_sync = sync_integrated_research(parent_run_id)
        manifest["field10_integrated_current_rows"] = int(len(load_integrated_current(parent_run_id)))
    except Exception as research_exc:
        research_report = {"ok": False, "status": "FAILED", "error": f"{type(research_exc).__name__}: {research_exc}"}
    manifest["ten_paper_research"] = research_report
    manifest["integrated_research_sync"] = integrated_sync

    # Authoritative append-only morning publication. This runs only inside the
    # existing Settings calculation transaction; Field 10 rendering remains a
    # read-only SQLite view. Existing protected ranks/actions remain evidence.
    daily_snapshot_report: dict[str, Any] = {"ok": False, "status": "NOT_ATTEMPTED"}
    finnhub_sentiment_report: dict[str, Any] = {"ok": False, "status": "NOT_ATTEMPTED"}
    crowd_final_report: dict[str, Any] = {"ok": False, "status": "NOT_ATTEMPTED"}
    safety_report: dict[str, Any] = {"ok": False, "status": "NOT_ATTEMPTED"}
    settlement_report: dict[str, Any] = {"ok": False, "status": "NOT_ATTEMPTED"}
    institutional_shadow_report: dict[str, Any] = {"ok": False, "status": "NOT_ATTEMPTED"}
    institutional_settlement_report: dict[str, Any] = {"ok": False, "status": "NOT_ATTEMPTED"}
    horizon_connected_tail_report: dict[str, Any] = {"ok": False, "status": "NOT_ATTEMPTED"}
    try:
        if failed:
            daily_snapshot_report = {
                "ok": False, "status": "SKIPPED_PARTIAL_RUN",
                "reason": "A partial run cannot replace the latest complete canonical publication.",
                "failed_symbols": failed,
            }
        else:
            from core.field10_daily_snapshot_contract_20260702 import publish_daily_snapshot
            daily_snapshot_report = publish_daily_snapshot(
                state, parent_run_id=parent_run_id, selected_symbols=selected, main_symbol=main, path=DB_PATH,
            )
        if daily_snapshot_report.get("ok"):
            from core.field10_live_safety_veto_20260702 import update_live_safety_veto
            safety_report = update_live_safety_veto(state, symbols=selected, path=DB_PATH)
            from core.field10_daily_outcome_settlement_20260702 import settle_current_day
            settlement_report = settle_current_day(
                state, parent_run_id=parent_run_id, symbols=selected, path=DB_PATH,
            )
    except Exception as daily_contract_exc:
        daily_snapshot_report = {
            "ok": False, "status": "FAILED",
            "error": f"{type(daily_contract_exc).__name__}: {daily_contract_exc}",
        }
    if daily_snapshot_report.get("ok"):
        try:
            from core.field10_finnhub_sentiment_20260704 import refresh_and_persist_finnhub_sentiment
            finnhub_sentiment_report = refresh_and_persist_finnhub_sentiment(
                state,
                daily_snapshot_id=str(daily_snapshot_report.get("daily_snapshot_id") or ""),
                selected_symbols=selected,
                path=DB_PATH,
            )
        except Exception as finnhub_sentiment_exc:
            finnhub_sentiment_report = {
                "ok": False,
                "status": "FAILED",
                "provider": "FINNHUB",
                "error": f"{type(finnhub_sentiment_exc).__name__}: {finnhub_sentiment_exc}",
                "secret_persisted": False,
            }
    if daily_snapshot_report.get("ok"):
        try:
            from core.field10_crowd_final_20260704 import publish_crowd_and_final_tables
            crowd_final_report = publish_crowd_and_final_tables(
                state,
                daily_snapshot_id=str(daily_snapshot_report.get("daily_snapshot_id") or ""),
                selected_symbols=selected,
                path=DB_PATH,
            )
        except Exception as crowd_final_exc:
            crowd_final_report = {
                "ok": False,
                "status": "FAILED",
                "error": f"{type(crowd_final_exc).__name__}: {crowd_final_exc}",
                "models": [
                    "field10_crowd_psychology_candidate_v1",
                    "field10_final_multi_symbol_candidate_v1",
                ],
                "validation_status": "SHADOW_ONLY_NOT_PROMOTED",
            }

    if daily_snapshot_report.get("ok"):
        try:
            from core.field10_institutional_shadow_20260704 import (
                publish_institutional_shadow, settle_matured_forecasts,
            )
            # Settlement uses only exact-symbol completed due candles and appends
            # to the immutable outcome ledger. Current publication remains shadow.
            institutional_settlement_report = settle_matured_forecasts(state, path=DB_PATH)
            institutional_shadow_report = publish_institutional_shadow(
                state,
                daily_snapshot_id=str(daily_snapshot_report.get("daily_snapshot_id") or ""),
                selected_symbols=selected,
                path=DB_PATH,
            )
        except Exception as institutional_exc:
            institutional_shadow_report = {
                "ok": False, "status": "FAILED",
                "error": f"{type(institutional_exc).__name__}: {institutional_exc}",
                "production_parent_unchanged": True,
            }

    # Additive 20260705 institutional research candidate. It runs only inside
    # this existing heavy Settings transaction and can never republish or
    # reorder the immutable parent daily snapshot.
    if daily_snapshot_report.get("ok"):
        try:
            from core.field10_research_orchestrator_20260705 import publish_horizon_connected_tail_candidate
            horizon_connected_tail_report = publish_horizon_connected_tail_candidate(
                state,
                daily_snapshot_id=str(daily_snapshot_report.get("daily_snapshot_id") or ""),
                selected_symbols=selected,
                path=DB_PATH,
            )
        except Exception as horizon_tail_exc:
            horizon_connected_tail_report = {
                "ok": False, "status": "FAILED",
                "error": f"{type(horizon_tail_exc).__name__}: {horizon_tail_exc}",
                "production_rank_modified": False,
                "locked_bias_modified": False,
            }

    manifest["field10_daily_snapshot_contract"] = {key: value for key, value in daily_snapshot_report.items() if key != "rows"}
    manifest["field10_finnhub_sentiment_rank_20260704"] = finnhub_sentiment_report
    manifest["field10_crowd_final_rank_20260704"] = crowd_final_report
    manifest["field10_live_safety_veto"] = safety_report
    manifest["field10_day_end_settlement"] = settlement_report
    manifest["field10_institutional_shadow_20260704"] = institutional_shadow_report
    manifest["field10_institutional_outcome_settlement_20260704"] = institutional_settlement_report
    manifest["field10_horizon_connected_tail_candidate_v1"] = horizon_connected_tail_report

    # Runtime code never migrates SQLite. Deployment owns the dedicated CLI
    # migration; Settings records only a read-only readiness check.
    try:
        from core.field10_institutional_shadow_20260704 import schema_ready
        schema_ok, schema_missing = schema_ready(DB_PATH)
        migration_report = {
            "ok": schema_ok,
            "status": "DEPLOYMENT_MIGRATION_READY" if schema_ok else "MIGRATION_REQUIRED",
            "missing_tables": schema_missing,
            "runtime_migration_executed": False,
        }
    except Exception as migration_exc:
        migration_report = {
            "ok": False, "status": "READINESS_CHECK_FAILED",
            "error": f"{type(migration_exc).__name__}: {migration_exc}",
            "runtime_migration_executed": False,
        }
    manifest["field10_database_migration_20260704"] = migration_report
    state["field10_deployment_migration_readiness_20260704"] = migration_report
    try:
        from core.field10_research_common_20260705 import schema_ready as horizon_tail_schema_ready
        horizon_schema_ok, horizon_schema_missing = horizon_tail_schema_ready(DB_PATH)
        horizon_migration_report = {
            "ok": horizon_schema_ok,
            "status": "DEPLOYMENT_MIGRATION_READY" if horizon_schema_ok else "MIGRATION_REQUIRED",
            "missing_tables": horizon_schema_missing,
            "runtime_migration_executed": False,
        }
    except Exception as horizon_migration_exc:
        horizon_migration_report = {
            "ok": False, "status": "READINESS_CHECK_FAILED",
            "error": f"{type(horizon_migration_exc).__name__}: {horizon_migration_exc}",
            "runtime_migration_executed": False,
        }
    manifest["field10_database_migration_20260705"] = horizon_migration_report
    state["field10_deployment_migration_readiness_20260705"] = horizon_migration_report

    # Field 11 preparation is additive and runs only inside this existing heavy
    # transaction. The Lunch renderer reads these persisted artifacts and never
    # rebuilds Fields 1-10 or calls a market connector.
    field11_index_report: dict[str, Any] = {"ok": False, "status": "NOT_ATTEMPTED"}
    field11_settlement_report: dict[str, Any] = {"ok": False, "status": "NOT_ATTEMPTED"}
    if field10_fast_lane_20260709:
        field11_index_report = defer_to_quick(
            state,
            "field11_historical_index",
            reason="Field 11 similar-path index is deferred so Super Quick can open Lunch after Field 10 production rank is published.",
        )
        field11_settlement_report = defer_to_quick(
            state,
            "field11_outcome_settlement",
            reason="Field 11 settlement is deferred to Quick/Full; it does not change Field 10 production rank.",
        )
    else:
        try:
            if failed:
                field11_index_report = {"ok": False, "status": "SKIPPED_PARTIAL_RUN", "failed_symbols": failed}
                cache_ready_symbols = []
            else:
                from core.field11_similar_path_simulator_20260702 import DB_PATH as FIELD11_DB_PATH, prepare_field11_index, settle_matured_simulations
                cache_ready_symbols = available_saved_symbols(selected)
            if cache_ready_symbols:
                field11_index_report = prepare_field11_index(
                    state, parent_run_id=parent_run_id, symbols=cache_ready_symbols, path=FIELD11_DB_PATH, field10_path=DB_PATH,
                )
                field11_settlement_report = settle_matured_simulations(path=FIELD11_DB_PATH)
            else:
                field11_index_report = {"ok": False, "status": "NO_READABLE_SYMBOL_CACHE"}
        except Exception as field11_exc:
            field11_index_report = {
                "ok": False, "status": "FAILED",
                "error": f"{type(field11_exc).__name__}: {field11_exc}",
            }
    manifest["field11_historical_index"] = field11_index_report
    manifest["field11_outcome_settlement"] = field11_settlement_report
    state[MANIFEST_KEY] = manifest
    validation_report: dict[str, Any] = {"ok": False, "status": "NOT_ATTEMPTED"}
    try:
        from core.system_continuous_validation_20260702 import validate_and_repair_state
        validation_report = validate_and_repair_state(state)
    except Exception as validation_exc:
        validation_report = {
            "ok": False, "status": "FAILED",
            "error": f"{type(validation_exc).__name__}: {validation_exc}",
        }
    manifest["continuous_validation"] = validation_report

    # A Settings run may display 100% only when every selected symbol has a
    # reload-validated child publication and a usable Field 10 result row.
    # The contract is additive: it validates and persists existing outputs but
    # never changes the protected calculation/ranking formulas.
    try:
        from core.multi_symbol_completion_contract_20260706 import apply_completion_contract
        manifest = apply_completion_contract(state, manifest)
    except Exception as completion_exc:
        manifest = {
            **manifest,
            "ok": False,
            "status": "PARTIAL",
            "completion_contract": {
                "ok": False,
                "status": "VALIDATION_ERROR",
                "error": f"{type(completion_exc).__name__}: {completion_exc}",
                "open_lunch_allowed": False,
                "success_message_allowed": False,
                "progress_percent": 99.0,
            },
        }

    contract = manifest.get("completion_contract") if isinstance(manifest.get("completion_contract"), Mapping) else {}
    strict_complete = manifest.get("status") == "COMPLETED" and bool(contract.get("ok"))
    if strict_complete:
        state[MANIFEST_KEY] = manifest
        state["multi_symbol_latest_complete_manifest_20260705"] = manifest
    else:
        state["multi_symbol_partial_manifest_20260705"] = manifest
        previous_complete = state.get("multi_symbol_latest_complete_manifest_20260705")
        if not isinstance(previous_complete, Mapping) and isinstance(previous_manifest, Mapping) and previous_manifest.get("status") == "COMPLETED":
            previous_complete = previous_manifest
        # Preserve the last known complete snapshot for read-only browsing while
        # Settings keeps the current partial manifest and exact failure reasons.
        state[MANIFEST_KEY] = previous_complete if isinstance(previous_complete, Mapping) else manifest

    final_stage = (
        "Completed — all selected symbols validated"
        if strict_complete else
        "Partial — selected-symbol publication contract incomplete"
    )
    final_progress = _progress_snapshot(parent_run_id, selected, statuses, active, final_stage)
    if not strict_complete:
        final_progress["overall_percent"] = min(99.0, float(final_progress.get("overall_percent") or 99.0))
        final_progress["progress_percent"] = final_progress["overall_percent"]
        incomplete = set(contract.get("missing_or_invalid_field10_symbols") or [])
        incomplete.update((contract.get("child_failures") or {}).keys())
        for failed_symbol in incomplete:
            item = final_progress.get("symbols", {}).get(failed_symbol)
            if not isinstance(item, MutableMapping):
                continue
            item["state"] = "FIELD10_RESULT_INCOMPLETE"
            item["publication_status"] = "FIELD10_RESULT_INCOMPLETE"
            item["status"] = "PARTIAL"
            item["percent"] = min(99.0, float(item.get("percent") or 99.0))
            item["stage"] = "Publication validation incomplete"
            reasons = (contract.get("field10_failure_reasons") or {}).get(failed_symbol) or []
            child_reason = (contract.get("child_failures") or {}).get(failed_symbol)
            all_reasons = [*map(str, reasons), *( [str(child_reason)] if child_reason else [] )]
            item["rejection_reason"] = "; ".join(dict.fromkeys(all_reasons))
    state[PROGRESS_KEY] = {
        **final_progress,
        "elapsed_seconds": round(elapsed_total, 2),
        "final_run_status": manifest.get("status"),
        "completion_contract": contract,
    }
    return manifest


def run_selected_symbols(
    state: MutableMapping[str, Any], single_symbol_runner: Callable[[], Mapping[str, Any]], *,
    scope: str = "FULL", progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run one quota-safe, synchronized selected-symbol transaction."""
    previous_manifest = state.get(MANIFEST_KEY)
    if bool(state.get(RUNNING_KEY)):
        if isinstance(previous_manifest, Mapping):
            return {**dict(previous_manifest), "duplicate_click_ignored": True}
        return {"ok": False, "status": "ALREADY_RUNNING", "duplicate_click_ignored": True}
    state[RUNNING_KEY] = True
    try:
        from core.calculation.run_orchestrator import execute_existing_multi_symbol_run
        return execute_existing_multi_symbol_run(
            state, single_symbol_runner, scope=scope,
            progress_callback=progress_callback,
            existing_runner=_run_selected_symbols_impl,
        )
    finally:
        state.pop(RUNNING_KEY, None)


__all__ = [
    "VERSION", "TOP_10_CURRENCY_PAIRS", "SUPPORTED_SYMBOLS", "PROVIDER_ALIASES", "SELECTED_KEY", "ACTIVE_KEY",
    "MAIN_SYMBOL_KEY", "DISPLAY_SYMBOL_KEY", "LUNCH_SYMBOL_WIDGET_KEY",
    "MANIFEST_KEY", "PROGRESS_KEY", "CHILD_RUN_KEY", "PARENT_RUN_KEY",
    "LAST_RESOURCE_KEY", "RUNNING_KEY", "FIELD10_SUMMARY_KEY", "FIELD10_DAILY_KEY", "FIELD10_HOURLY_KEY",
    "DB_PATH", "normalize_symbol", "normalize_selected", "selected_symbols", "main_symbol",
    "resolve_provider_symbol", "grade_from_score", "assess_data_quality", "validate_fields_1_9",
    "activate_symbol_result", "activate_symbol_view", "available_published_symbols", "saved_symbol_available", "available_saved_symbols", "recover_symbol_universe",
    "ensure_main_symbol_active", "clear_active_symbol_results", "migrate_database",
    "load_field10_tables", "run_selected_symbols",
]

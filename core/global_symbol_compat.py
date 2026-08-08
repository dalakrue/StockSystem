"""Only approved compatibility writer for legacy symbol state keys.

Ordinary modules must use GlobalSymbolContext.  These mirrors exist only for
imports that cannot yet be removed; display changes never alter connector or
calculation identity.
"""
from __future__ import annotations
from collections.abc import MutableMapping
from typing import Any

DISPLAY_MIRROR_KEYS = (
    "canonical_display_symbol_20260709", "selected_symbol_for_display_20260709",
    "lunch_active_symbol_20260704", "canonical_display_symbol_20260705",
    "lunch_display_symbol_20260702", "active_snapshot_symbol_20260702", "active_symbol",
    "field1_selected_symbol_20260709", "field2_selected_symbol_20260709", "field3_selected_symbol_20260709",
    "field10_selected_symbol_20260709", "field11_selected_symbol_20260709", "field12_selected_symbol_20260709",
    "research_selected_symbol_20260709", "finder_selected_symbol_20260709",
    "dinner_selected_symbol_20260709", "morning_selected_symbol_20260709", "ai_selected_symbol_20260709",
)


def mirror_context_to_legacy_state(state: MutableMapping[str, Any], context: Any) -> None:
    configured = list(getattr(context, "configured_symbols", ()) or ())
    active = str(getattr(context, "active_display_symbol", "") or "")
    timeframe = str(getattr(context, "timeframe", "") or "")
    state["multi_symbol_selected_20260701"] = configured
    state["canonical_selected_symbols"] = configured
    state["canonical_loaded_symbols"] = list(getattr(context, "loaded_symbols", ()) or ())
    state["calculation_loaded_symbols_20260708"] = list(getattr(context, "loaded_symbols", ()) or ())
    state["canonical_completed_symbols_v2"] = list(getattr(context, "completed_symbols", ()) or ())
    if timeframe:
        state["timeframe"] = timeframe
        state["selected_timeframe"] = timeframe
    if active:
        for key in DISPLAY_MIRROR_KEYS:
            state[key] = active


def set_legacy_configured_symbols(state: MutableMapping[str, Any], symbols: Any) -> list[str]:
    values = symbols if isinstance(symbols, (list, tuple)) else [symbols]
    configured: list[str] = []
    for value in values:
        sym = str(value or "").strip().upper().replace("/", "").replace(" ", "")
        if sym and sym not in configured:
            configured.append(sym)
    state["multi_symbol_selected_20260701"] = configured
    state["canonical_selected_symbols"] = configured
    state["selected_symbols_for_run_20260705"] = configured
    return configured


def clear_legacy_calculation_symbol(state: MutableMapping[str, Any]) -> None:
    """Clear transient calculation identity without touching display identity."""
    for key in ("symbol", "selected_symbol", "calculation_symbol", "calculation_symbol_20260702"):
        state.pop(key, None)


def set_legacy_calculation_symbol(state: MutableMapping[str, Any], symbol: Any, *, connector: bool = False) -> str:
    """Approved calculation-transaction boundary for generic legacy keys."""
    sym = str(symbol or "").strip().upper().replace("/", "").replace(" ", "")
    state["symbol"] = sym
    state["selected_symbol"] = sym
    state["calculation_symbol_20260702"] = sym
    state["calculation_symbol"] = sym
    if connector:
        state["connector_symbol_20260702"] = sym
        state["connector_symbol"] = sym
        state["multi_symbol_main_symbol_20260702"] = sym
        state["settings_main_symbol"] = sym
        state["settings_main_symbol_20260702"] = sym
    return sym


__all__ = ["mirror_context_to_legacy_state", "set_legacy_configured_symbols", "set_legacy_calculation_symbol", "clear_legacy_calculation_symbol", "DISPLAY_MIRROR_KEYS"]

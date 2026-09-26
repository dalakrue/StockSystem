"""Shared instrument universe and symbol-state authority.

The project historically had several independent symbol widgets.  This module
makes the user selection authoritative while preserving the last completed
canonical generation as audit evidence until a new run is published.
"""
from __future__ import annotations
from core.global_symbol_compat import set_legacy_calculation_symbol, set_legacy_configured_symbols

from typing import Any, Mapping, MutableMapping

FX_SYMBOLS: tuple[str, ...] = (
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD", "GBPJPY",
    "GBPCHF", "GBPAUD", "GBPCAD", "AUDJPY", "CADJPY", "CHFJPY",
)

EQUITY_SYMBOLS: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK.B",
    "AVGO", "JPM", "LLY", "V", "MA", "XOM", "UNH", "COST", "HD", "PG",
    "JNJ", "AMD",
)

INDEX_SYMBOLS: tuple[str, ...] = ("SPX", "NAS100", "US500")

# Existing frequently used instruments remain available in addition to the
# requested 20 FX + 20 equities + S&P 500 library.
OTHER_SYMBOLS: tuple[str, ...] = ("XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD")

SYMBOL_GROUPS: Mapping[str, tuple[str, ...]] = {
    "Major & Cross FX (20)": FX_SYMBOLS,
    "High-volume Equities (20)": EQUITY_SYMBOLS,
    "Index": INDEX_SYMBOLS,
    "Metals & Crypto": OTHER_SYMBOLS,
}

_ALIAS_MAP = {
    "S&P500": "SPX", "S&P 500": "SPX", "SP500": "SPX", "^GSPC": "SPX",
    "GSPC": "SPX", "USTEC": "NAS100", "US100": "NAS100", "NDX": "NAS100",
    "SPX500": "US500",
}


def normalize_instrument(value: Any, default: str = "EURUSD") -> str:
    raw = str(value or default).strip().upper()
    raw = _ALIAS_MAP.get(raw, raw)
    # Slash is presentation-only for FX.  Dot and dash are preserved for equity
    # symbols such as BRK.B and exchange-qualified symbols.
    cleaned = raw.replace("/", "").replace(" ", "")
    return cleaned or default


def category_for_symbol(symbol: Any) -> str:
    normalized = normalize_instrument(symbol)
    for category, symbols in SYMBOL_GROUPS.items():
        if normalized in symbols:
            return category
    return "Type another symbol"


def all_library_symbols() -> tuple[str, ...]:
    ordered: list[str] = []
    for values in SYMBOL_GROUPS.values():
        for symbol in values:
            if symbol not in ordered:
                ordered.append(symbol)
    return tuple(ordered)


def apply_symbol_selection(
    state: MutableMapping[str, Any],
    symbol: Any,
    *,
    reason: str = "user_selection",
) -> dict[str, Any]:
    """Publish one global symbol selection without deleting the prior snapshot."""
    selected = normalize_instrument(symbol, str(state.get("symbol") or "EURUSD"))
    previous = normalize_instrument(state.get("symbol") or "EURUSD")
    changed = selected != previous

    set_legacy_calculation_symbol(state, selected, connector=True)
    state["ws_symbol"] = selected
    # One authoritative Settings symbol.  The historical global connector
    # selector and the newer multi-symbol selector previously wrote different
    # keys, allowing a stale USDCHF value to overwrite the user's choice when
    # Connect was pressed.  Keep every non-widget alias synchronized here.
    selected_symbols = state.get("multi_symbol_selected_20260701")
    if isinstance(selected_symbols, (list, tuple, set)):
        normalized_selected = []
        for value in selected_symbols:
            item = normalize_instrument(value)
            if item and item not in normalized_selected:
                normalized_selected.append(item)
        set_legacy_configured_symbols(state, [selected, *[item for item in normalized_selected if item != selected]])
    else:
        set_legacy_configured_symbols(state, [selected])
    state["requested_symbol_20260629"] = selected
    state["symbol_selection_reason_20260629"] = str(reason)
    state["symbol_selection_version_20260629"] = int(state.get("symbol_selection_version_20260629", 0) or 0) + (1 if changed else 0)

    if changed:
        # The old canonical result remains intact for audit, but every renderer is
        # told that it belongs to the previous instrument until a new run finishes.
        state["dependent_calculations_stale_20260621"] = True
        state["canonical_display_stale_20260621"] = True
        state["selected_symbol_pending_run_20260629"] = True
        state["selected_symbol_previous_20260629"] = previous
        state["last_connection_message"] = f"Symbol changed from {previous} to {selected}. Refreshing the selected feed is required."
        # Clear only reconstructable presentation caches that can otherwise show
        # a chart from the previous instrument under the new symbol label.
        for key in list(state.keys()):
            text = str(key)
            if text.startswith((
                "field2_quant_upgrade_20260629", "symbol_specific_view_20260629",
                "lunch_bi_visual_cache", "cached_powerbi_projection_20260619",
                "powerbi_projection_cache_20260619",
            )):
                state.pop(key, None)

    return {"symbol": selected, "previous_symbol": previous, "changed": changed, "reason": reason}


def symbol_identity_matches(state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None) -> bool:
    active = normalize_instrument(state.get("symbol") or "EURUSD")
    canonical = canonical or {}
    published = normalize_instrument(canonical.get("symbol") or active)
    return active == published


__all__ = [
    "FX_SYMBOLS", "EQUITY_SYMBOLS", "INDEX_SYMBOLS", "OTHER_SYMBOLS",
    "SYMBOL_GROUPS", "normalize_instrument", "category_for_symbol",
    "all_library_symbols", "apply_symbol_selection", "symbol_identity_matches",
]

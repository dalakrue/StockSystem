"""Shared read-only multi-symbol selector for Lunch Fields 1, 2 and 11.

Selecting a symbol is inert until the user presses Load Selected Symbol.  The
button restores a saved child snapshot and never calls a market provider or
starts a calculation.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any
import time

import pandas as pd
import streamlit as st

ACTIVE_KEY = "lunch_active_symbol_20260704"
STATUS_KEY = "lunch_active_symbol_status_20260704"
WIDGET_KEYS = {
    1: "field1_multi_symbol_selector_20260704",
    2: "field2_multi_symbol_selector_20260704",
    11: "field11_multi_symbol_selector_20260705",
}
VERSION = "lunch-shared-symbol-selector-20260706-v3"


def _available(state: Mapping[str, Any]) -> list[str]:
    try:
        from core.canonical_symbol_selection_20260709 import available_symbols
        symbols = available_symbols(state)
        if symbols:
            return symbols
    except Exception:
        pass
    from core.multi_symbol_field10_20260701 import available_published_symbols, normalize_selected, recover_symbol_universe

    universe = recover_symbol_universe(state)
    requested = normalize_selected(
        universe.get("completed_symbols")
        or universe.get("selected_symbols")
        or state.get("multi_symbol_selected_20260701")
        or []
    )
    published = available_published_symbols(state, requested=requested)
    ordered = [symbol for symbol in requested if symbol in published]
    ordered.extend(symbol for symbol in published if symbol not in ordered)
    return ordered


def _rank_row(state: MutableMapping[str, Any], symbol: str) -> dict[str, Any]:
    try:
        from core.multi_symbol_field10_20260701 import load_field10_tables
        tables = load_field10_tables(state, symbol=symbol)
        summary = tables.get("summary")
        if isinstance(summary, pd.DataFrame) and not summary.empty and "Symbol" in summary.columns:
            match = summary.loc[summary["Symbol"].astype(str).str.upper().eq(symbol)]
            if not match.empty:
                return dict(match.iloc[0])
    except Exception:
        pass
    return {}


def _metric_cards(values: tuple[tuple[str, Any], ...], *, phone: bool) -> None:
    per_row = 2 if phone else 3
    for start in range(0, len(values), per_row):
        cols = st.columns(per_row)
        for card, item in zip(cols, values[start : start + per_row]):
            label, value = item
            card.metric(label, value)


def _load(state: MutableMapping[str, Any], symbol: str, *, field_number: int | None = None) -> dict[str, Any]:
    try:
        from core.canonical_symbol_selection_20260709 import activate_symbol
        surface = f"field{field_number}" if field_number in {1, 2, 11} else "lunch"
        report = activate_symbol(state, symbol, surface=surface, try_legacy=True)
    except Exception as exc:
        try:
            from core.complete_repair_20260705 import log_internal_error
            incident = log_internal_error("lunch.shared_selector", exc, symbol=symbol)
        except Exception:
            incident = ""
        report = {"ok": False, "status": "CANONICAL_SYMBOL_LOAD_FAILED", "symbol": symbol, "incident_id": incident}
    if report.get("ok"):
        state[ACTIVE_KEY] = symbol
    state[STATUS_KEY] = {**report, "processed_at": time.time(), "heavy_calculation_triggered": False}
    return report


def render(field_number: int, state: MutableMapping[str, Any]) -> str | None:
    """Render the same loaded-only authority used by every other tab."""
    if field_number not in WIDGET_KEYS:
        raise ValueError("field_number must be 1, 2, or 11")
    from core.canonical_symbol_selection_20260709 import render_selector
    selected, _, report = render_selector(
        st, state, surface=f"field{field_number}",
        title=f"Field {field_number} Loaded-Symbol Selector — Global Sync",
        expanded=True,
    )
    state[STATUS_KEY] = dict(report or {})
    state[ACTIVE_KEY] = selected
    return selected or None


__all__ = ["ACTIVE_KEY", "STATUS_KEY", "WIDGET_KEYS", "render"]

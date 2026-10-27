"""Compatibility facade over the database-backed GlobalSymbolContext.

This module intentionally renders no selectable symbol widget.  Legacy imports
continue to work, but every read and write delegates to the single global
service.  The only interactive symbol selector lives in the floating app bar.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any
import time

import pandas as pd

from core.global_symbol_context import (
    get_global_symbol_context, loaded_selector_options, normalize_symbol,
    restore_latest_context, select_active_display_symbol,
)

GLOBAL_SYMBOL_KEY = "canonical_display_symbol_20260709"
STATUS_KEY = "canonical_symbol_load_status_20260709"
FIELD_WIDGET_KEY = "global_symbol_widget_v2"  # one shared widget key, owned by the floating bar
HORIZON_KEY = "canonical_horizon_20260709"
SURFACE_SYMBOL_KEYS: dict[str, str] = {}
DISPLAY_COMPAT_KEYS: tuple[str, ...] = ()


def available_symbols(state: Mapping[str, Any] | None, *, limit: int = 24) -> list[str]:
    context = get_global_symbol_context(state)
    return loaded_selector_options(context)[:limit]


def active_symbol(state: Mapping[str, Any] | None, *, surface: str = "lunch") -> str:
    del surface
    return get_global_symbol_context(state).active_display_symbol


def filter_frame_for_symbol(frame: Any, symbol: str, *, symbol_col: str = "Symbol") -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    if symbol_col not in frame.columns:
        return frame.copy()
    sym = normalize_symbol(symbol)
    return frame.loc[frame[symbol_col].astype(str).map(normalize_symbol).eq(sym)].copy()


def activate_symbol(state: MutableMapping[str, Any], symbol: Any, *, surface: str = "lunch", try_legacy: bool = True) -> dict[str, Any]:
    """Atomic display-only compatibility call; no provider/calculation side effects."""
    del try_legacy
    try:
        context = select_active_display_symbol(symbol, state=state)
        report = {
            "ok": True, "status": "GLOBAL_DISPLAY_SYMBOL_APPLIED", "symbol": context.active_display_symbol,
            "surface": surface, "universe_id": context.universe_id, "generation": context.generation,
            "timeframe": context.timeframe, "snapshot_hash": context.snapshot_hash,
            "completed_candle": context.latest_completed_candle, "processed_at": time.time(),
            "provider_calls": 0, "calculation_calls": 0, "heavy_calculation_triggered": False,
        }
    except Exception as exc:
        report = {
            "ok": False, "status": "GLOBAL_DISPLAY_SYMBOL_REJECTED", "symbol": normalize_symbol(symbol),
            "surface": surface, "error": f"{type(exc).__name__}: {exc}", "processed_at": time.time(),
            "provider_calls": 0, "calculation_calls": 0, "heavy_calculation_triggered": False,
        }
    state[STATUS_KEY] = report
    state[f"{surface}_symbol_load_status_20260709"] = report
    return report


def render_identity_strip(st: Any, state: MutableMapping[str, Any], *, surface: str) -> str:
    context = get_global_symbol_context(state)
    active = context.active_display_symbol
    st.caption(
        f"Global Symbol: {active or 'NOT PUBLISHED'} · Global Timeframe: {context.timeframe or '—'} · "
        f"Run ID: {context.parent_run_id or '—'} · Generation: {context.generation} · "
        f"Snapshot Hash: {context.snapshot_hash or '—'} · Completed Candle: {context.latest_completed_candle or '—'}"
    )
    state[f"{surface}_global_identity_seen_v2"] = context.selection_hash
    return active


def render_selector(
    st: Any,
    state: MutableMapping[str, Any],
    *,
    surface: str,
    title: str = "Global Symbol Identity",
    show_horizon: bool = False,
    expanded: bool = True,
) -> tuple[str, str | None, dict[str, Any]]:
    """Legacy UI facade: read-only identity strip, never another selector."""
    del expanded
    context = get_global_symbol_context(state)
    if not context.universe_id:
        context = restore_latest_context(state)
    st.markdown(f"#### {title.replace('Selector', 'Identity')}")
    active = render_identity_strip(st, state, surface=surface)
    horizon: str | None = None
    if show_horizon:
        horizons = ["1H", "3H", "6H", "12H", "24H"]
        key = f"{HORIZON_KEY}_{surface}"
        current = state.get(key) if state.get(key) in horizons else "1H"
        horizon = st.selectbox("Evidence horizon", horizons, index=horizons.index(current), key=key)
    report = {
        "ok": bool(active), "status": "READ_ONLY_GLOBAL_IDENTITY",
        "symbol": active, "universe_id": context.universe_id, "generation": context.generation,
        "timeframe": context.timeframe, "snapshot_hash": context.snapshot_hash,
        "completed_candle": context.latest_completed_candle, "provider_calls": 0, "calculation_calls": 0,
    }
    return active, horizon, report


__all__ = [
    "GLOBAL_SYMBOL_KEY", "STATUS_KEY", "FIELD_WIDGET_KEY", "available_symbols", "active_symbol", "activate_symbol",
    "filter_frame_for_symbol", "render_selector", "render_identity_strip", "normalize_symbol",
]

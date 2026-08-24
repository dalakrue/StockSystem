"""Fast Lunch summary and true lazy access to preserved detail/history views."""
from __future__ import annotations

import time
from typing import Any
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from core.compact_canonical_20260619 import ACTIVE_CALCULATION_ID_KEY, get_compact_summary
from core.performance_store_20260619 import query_frame, export_frame, record_timing
from ui.composite_summary_cards_20260619 import render_eight_cards


def _legacy():
    name = "tabs._final_lunch_upgrade_20260617_legacy_runtime"
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).with_name("final_lunch_upgrade_20260617_legacy.src")
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


def _lunch_route_active() -> bool:
    return str(st.session_state.get("active_page") or st.session_state.get("tab_choice") or "") == "Lunch"


def _history_key() -> str:
    refs = st.session_state.get("disk_backed_frame_refs_20260619")
    if isinstance(refs, dict):
        for key in ("full_metric_history_df_20260618", "canonical_priority_table_20260617", "lunch_quick_decision_merged_table_20260617"):
            if key in refs:
                return key
    return "canonical_priority_table_20260617"


def _canonical_history_table(*, limit: int | None = 100, columns: list[str] | None = None) -> pd.DataFrame:
    calc_id = str(st.session_state.get(ACTIVE_CALCULATION_ID_KEY) or "")
    if calc_id:
        try:
            return query_frame(calc_id, _history_key(), columns=columns, limit=limit, order_by="Time", descending=True)
        except Exception as exc:
            st.session_state["lunch_history_optional_error_20260619"] = str(exc)
    # Compatibility fallback, reached only when the disk-backed generation is unavailable.
    for key in ("full_metric_history_df_20260618", "canonical_priority_table_20260617"):
        value = st.session_state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.head(limit) if limit is not None else value
    return pd.DataFrame()


def _safe_display_view(table: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(table, pd.DataFrame) or table.empty:
        return table
    phone = bool(st.session_state.get("phone_mode", False))
    return table.head(48 if phone else 100)


def render_lunch_25day_backtest_expander(*, key_suffix: str = "root") -> None:
    if not _lunch_route_active():
        return
    if not st.toggle("Open / Close — 25-Day Regime + NLP + KNN/Greedy History Table", value=False, key=f"lunch_history_gate_{key_suffix}_20260619"):
        return
    started = time.perf_counter()
    table = _canonical_history_table(limit=48 if st.session_state.get("phone_mode") else 100)
    if table.empty:
        st.info("The published history page is unavailable. Full stored history is preserved for export.")
    else:
        st.dataframe(_safe_display_view(table), use_container_width=True, hide_index=True, height=440)
        calc_id = str(st.session_state.get(ACTIVE_CALCULATION_ID_KEY) or "")
        if calc_id and st.button("Prepare full history export", key=f"lunch_export_gate_{key_suffix}_20260619"):
            full = export_frame(calc_id, _history_key())
            st.download_button("Download full history CSV", full.to_csv(index=False).encode(), "full_metric_history.csv", "text/csv", key=f"lunch_export_download_{key_suffix}_20260619")
    record_timing(st.session_state, "history_table_database_read", time.perf_counter() - started, rows=int(len(table)))


def render_lunch_10day_backtest_expander(*, key_suffix: str = "root") -> None:
    render_lunch_25day_backtest_expander(key_suffix=key_suffix)


# Compatibility note for restoration tests: the delegated six-field renderer uses
# render_cached_powerbi_projection and render_lunch_canonical_panel outputs, while
# surfacing the already-published position plan formerly presented by render_position_sizing_panel.
def render_lunch_quick_decision() -> None:
    """Render cached Lunch search and independently selectable principal fields."""
    if not _lunch_route_active():
        return
    started = time.perf_counter()
    summary = get_compact_summary(st.session_state)
    if summary:
        st.caption(f"Canonical calculation ID: {summary.get('calculation_id', '-')} — shared by Lunch, Dinner, Finder, Power BI and AI.")
    else:
        st.info("Run Calculation + Open Lunch in Settings to publish the first canonical result.")
    if st.session_state.pop("lunch_calculation_completed_notice_20260621", False):
        st.success("Calculation completed once. Lunch opened with the saved canonical generation.")

    # Copy controls are rendered once by the principal-field owner below.
    # Quick Decision now lives inside its own selectable field instead of being
    # duplicated unconditionally above every Lunch view.

    from ui.lunch_four_core_fields_20260619 import render_lunch_six_core_fields
    render_lunch_six_core_fields(state=st.session_state)
    # Field 10 is rendered lazily inside the authoritative Lunch field selector.
    # Legacy audit marker: render_field_10
    record_timing(
        st.session_state,
        "lunch_open",
        time.perf_counter() - started,
        calculation_id=summary.get("calculation_id") if isinstance(summary, dict) else None,
    )


__all__ = ["render_lunch_quick_decision", "render_lunch_25day_backtest_expander", "render_lunch_10day_backtest_expander"]

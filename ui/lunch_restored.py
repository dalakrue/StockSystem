"""Automatic cached Lunch restoration after the Settings Run Calculation button.

The user no longer has to press a second intermediate load or calculation button. This module reads and displays the caches produced by
``core.settings_run_orchestrator_20260617`` while preserving the project's
existing metric, regime, priority, PowerBI and export logic.
"""
from __future__ import annotations

from typing import Any, Dict

import pandas as pd
import streamlit as st

from ui.table_ordering_20260618 import newest_first


def _lunch_active() -> bool:
    return str(st.session_state.get("active_page") or st.session_state.get("tab_choice") or "") == "Lunch"


def _safe_call(label: str, fn, *args, **kwargs) -> Any:
    if not callable(fn):
        return None
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        st.warning(f"{label} skipped safely; the rest of Lunch remains available.")
        with st.expander(f"Open / Close — {label} status", expanded=False):
            st.caption(f"{type(exc).__name__}: {exc}")
        return None


def _shared_status() -> Dict[str, Any]:
    try:
        from core.canonical_runtime_20260617 import shared_from_runtime
        return shared_from_runtime(st.session_state) or {}
    except Exception:
        return {}


def _cached_metric_result(ns: Dict[str, Any]) -> Dict[str, Any]:
    cached = st.session_state.get("lunch_metric_result_cache")
    if isinstance(cached, dict) and cached.get("ok"):
        return cached
    try:
        from core.system_wide_completion_20260618 import published_metric_result
        published = published_metric_result(st.session_state)
        if isinstance(published, dict) and published.get("ok"):
            return published
    except Exception:
        pass
    getter = ns.get("_get_cached_lunch_metric_result")
    result = _safe_call("Cached Lunch metric result", getter, False) if callable(getter) else {}
    return result if isinstance(result, dict) else {}


def _render_metric_summary(ns: Dict[str, Any], result: Dict[str, Any]) -> None:
    quality = ns.get("_render_lunch_metric_quality_table")
    if callable(quality):
        _safe_call("Original Lunch metric quality table", quality, result)

    scores = result.get("scores", {}) if isinstance(result.get("scores"), dict) else {}
    if scores:
        cols = st.columns(5)
        cols[0].metric("Master", f"{float(scores.get('Master /10', 0) or 0):.2f}/10", scores.get("Decision", "WAIT"))
        cols[1].metric("Entry", f"{float(scores.get('Entry /10', 0) or 0):.2f}/10")
        cols[2].metric("Direction", str(scores.get("Direction", "WAIT")))
        cols[3].metric("Hold", f"{float(scores.get('Hold /10', 0) or 0):.2f}/10")
        cols[4].metric("TP", f"{float(scores.get('TP /10', 0) or 0):.2f}/10")

    reverse = result.get("reverse10")
    st.markdown("#### 010 Reverse Decision Table")
    if isinstance(reverse, pd.DataFrame) and not reverse.empty:
        st.dataframe(reverse, use_container_width=True, hide_index=True, height=340)
    else:
        st.dataframe(pd.DataFrame([{"Status": "The current cached metric result has no reverse-decision rows."}]), use_container_width=True, hide_index=True)


def _render_full_details(ns: Dict[str, Any], result: Dict[str, Any]) -> None:
    """Render every existing metric table; one table error cannot stop the rest."""
    del ns
    with st.expander("Open / Close — Full Metric Details — Complete All Tables", expanded=False):
        st.caption("All existing metric tables are restored in order. Historical tables use the latest completed H1 row first.")
        ordered = (
            ("Session Decision", "session"),
            ("010 Reverse Decision", "reverse10"),
            ("10 Entry Decision", "entry"),
            ("10 Direction Decision", "direction"),
            ("10 Hold Decision", "hold"),
            ("10 Exit Decision", "exit"),
            ("10 TP Decision", "tp"),
            ("Metric Table", "metric_table"),
            ("Full Metric Table", "full_metric_table"),
        )
        aliases = {
            "session": ("session", "session_table"),
            "reverse10": ("reverse10",),
            "entry": ("entry", "entry_table"),
            "direction": ("direction", "direction_table"),
            "hold": ("hold", "hold_table"),
            "exit": ("exit", "exit_table"),
            "tp": ("tp", "tp_table"),
            "metric_table": ("metric_table",),
            "full_metric_table": ("full_metric_table",),
        }
        seen: set[int] = set()
        rendered_keys: set[str] = set()
        limit = 600
        for title, logical_key in ordered:
            value = None
            source_key = logical_key
            for candidate in aliases.get(logical_key, (logical_key,)):
                candidate_value = result.get(candidate)
                if isinstance(candidate_value, pd.DataFrame) and not candidate_value.empty:
                    value = candidate_value
                    source_key = candidate
                    break
            if not isinstance(value, pd.DataFrame) or value.empty or id(value) in seen:
                continue
            seen.add(id(value)); rendered_keys.add(source_key)
            st.markdown(f"##### {title}")
            try:
                show = newest_first(value, limit)
                st.dataframe(show, use_container_width=True, hide_index=True, height=min(560, max(220, 42 + len(show) * 27)))
            except Exception as exc:
                st.warning(f"{title} could not render, but later metric tables are still shown: {exc}")

        # Preserve any additional dataframe produced by the real project without
        # letting an unknown table suppress Direction, Exit, TP, or History.
        for key, value in result.items():
            if key in {"history", "history_by_factor"} or key in rendered_keys:
                continue
            if not isinstance(value, pd.DataFrame) or value.empty or id(value) in seen:
                continue
            seen.add(id(value))
            st.markdown(f"##### {str(key).replace('_', ' ').title()}")
            try:
                show = newest_first(value, limit)
                st.dataframe(show, use_container_width=True, hide_index=True, height=min(560, max(220, 42 + len(show) * 27)))
            except Exception as exc:
                st.warning(f"{key} could not render, but the remaining tables are still available: {exc}")

        if not seen:
            st.info("The current calculation result has no additional metric-detail tables yet.")


def _render_full_history(ns: Dict[str, Any], result: Dict[str, Any]) -> None:
    with st.expander("Open / Close — Full Metric History — Current H1 First", expanded=False):
        st.caption("Current/latest completed day and hour are always displayed first. Older backtest rows remain below for comparison.")
        history = result.get("history")
        if isinstance(history, pd.DataFrame) and not history.empty:
            newest = ns.get("_lunch_newest_first_table_v20260609")
            try:
                prepared = newest(history, 600) if callable(newest) else history
                show = newest_first(prepared, 600)
                st.dataframe(show, use_container_width=True, hide_index=True, height=460)
            except Exception as exc:
                st.warning(f"Full metric history could not render safely: {exc}")
        else:
            st.info("The current calculation result has no metric-history rows yet.")

        # Restore the existing Regime inner section in the same Full Metric
        # History workspace. It is deliberately direct-visible: no second Run
        # button, nested expander or hidden tab can suppress its existing tables.
        try:
            from ui.full_metric_regime_inner_renderer_20260618 import render_existing_regime_inner_section
            render_existing_regime_inner_section(result)
        except Exception as exc:
            st.warning(f"Existing Regime inner tables skipped safely: {exc}")

        factor_history = result.get("history_by_factor", {})
        valid_factors = {str(name): frame for name, frame in (factor_history.items() if isinstance(factor_history, dict) else []) if isinstance(frame, pd.DataFrame) and not frame.empty}
        if valid_factors:
            st.markdown("##### Separate History for All 10 Metric Decisions")
            selected = st.selectbox(
                "Choose reverse-decision factor",
                list(valid_factors),
                key="restored_lunch_selected_factor_20260619",
            )
            try:
                st.dataframe(newest_first(valid_factors[selected], 600), use_container_width=True, hide_index=True, height=400)
            except Exception as exc:
                st.warning(f"{selected} history skipped safely: {exc}")


def _render_powerbi_auto() -> None:
    # Reuse the same cached-only renderer as Lunch → PowerBI Projection.  The
    # optional restored Lunch tools therefore cannot trigger a second model or
    # calibration pass.
    try:
        from ui.powerbi_cached_renderer_20260619 import render_cached_powerbi_projection
        render_cached_powerbi_projection()
    except Exception as exc:
        st.warning(f"PowerBI cached projection skipped safely: {exc}")


def _render_copy_export(ns: Dict[str, Any]) -> None:
    with st.expander("Open / Close — Original Lunch Copy and Export Controls", expanded=False):
        short_builder = ns.get("_build_short_necessary_copy_text")
        full_builder = ns.get("_build_lunch_all_copy_text")
        short_text = _safe_call("Original Lunch short-copy payload", short_builder) if callable(short_builder) else ""
        full_text = _safe_call("Original Lunch full-copy payload", full_builder) if callable(full_builder) else ""
        short_text = str(short_text or "No completed Lunch calculation is available yet.")
        full_text = str(full_text or short_text)
        # Legacy duplicate clipboard controls were intentionally removed.
        # The only mobile-safe Copy Short / Copy Full pair is rendered once at
        # the top of the active Lunch page from the current canonical identity.
        st.caption("Current-generation copy controls are available at the top of Lunch.")
        st.download_button(
            "Export Original Lunch Analysis",
            data=full_text.encode("utf-8", errors="replace"),
            file_name="original_lunch_analysis.txt",
            mime="text/plain",
            key="restored_lunch_export_20260617",
            use_container_width=True,
        )


def render_restored_lunch_bottom(ns: Dict[str, Any]) -> None:
    if not _lunch_active():
        return
    shared = _shared_status()
    result = _cached_metric_result(ns)

    st.divider()
    st.markdown("## Original Lunch Analysis — Auto Loaded")
    built_at = st.session_state.get("lunch_metric_result_built_at") or shared.get("built_at", "-")
    cols = st.columns(4)
    cols[0].metric("Calculation", "READY" if result.get("ok") else "CHECK DATA")
    cols[1].metric("Lunch Cache", "AUTO LOADED" if result.get("ok") else "NOT READY")
    cols[2].metric("PowerBI Cache", "READY" if st.session_state.get("lunch_bi_visual_ready") else "NOT READY")
    cols[3].metric("Built At", str(built_at))

    if not result.get("ok"):
        try:
            from core.system_wide_completion_20260618 import readiness_message
            st.warning(result.get("message") or readiness_message(st.session_state, "Full Metric"))
        except Exception:
            st.warning(result.get("message") or "The published Full Metric result is unavailable. Open Settings → Errors / Fix Fast.")
    else:
        # One live renderer now owns the complete Full Metric workspace in both
        # Lunch Main and Lunch → Full Metric Details + History. This removes the
        # old divergence where one route could stop after Entry while another
        # continued to Direction, Exit, TP and complete history.
        with st.expander(
            "Open / Close — Full Metric Details + History — Complete Current-H1-First View",
            expanded=True,
        ):
            try:
                from ui.full_metric_shared_renderer_20260618 import render_full_metric_shared
                render_full_metric_shared(ns, result=result)
            except Exception as exc:
                st.warning(f"Complete Full Metric workspace skipped safely: {exc}")
                # The preserved legacy display remains a final fallback and keeps
                # the existing Regime inner section directly visible.
                _render_metric_summary(ns, result)
                _render_full_details(ns, result)
                _render_full_history(ns, result)

    _render_powerbi_auto()
    _render_copy_export(ns)

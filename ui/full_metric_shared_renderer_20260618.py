"""Single active renderer for the protected Full Metric result.

This module never imports or duplicates Full Metric formulas.  It renders the
already-computed result produced by ``tabs.eurusd_h1_matrix`` and keeps all
operational histories current-first.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

import pandas as pd
import streamlit as st

from ui.table_ordering_20260618 import chronological_view


_SKIP_TABLES = {"reverse10", "history", "history_by_factor", "metrics", "scores"}
_PREFERRED_TABLES = (
    "session", "session_table",
    "entry", "entry_table",
    "direction", "direction_table",
    "hold", "hold_table",
    "exit", "exit_table",
    "tp", "tp_table",
    "metric_table", "full_metric_table",
    "detail", "details",
)
_TABLE_LABELS = {
    "session": "Session Decision Table",
    "session_table": "Session Decision Table",
    "entry": "10 Entry Decision Table",
    "entry_table": "10 Entry Decision Table",
    "direction": "10 Direction Decision Table",
    "direction_table": "10 Direction Decision Table",
    "hold": "10 Hold Decision Table",
    "hold_table": "10 Hold Decision Table",
    "exit": "10 Exit Decision Table",
    "exit_table": "10 Exit Decision Table",
    "tp": "10 TP Decision Table",
    "tp_table": "10 TP Decision Table",
    "metric_table": "Metric Table",
    "full_metric_table": "Full Metric Table",
}


def _height(frame: pd.DataFrame, maximum: int = 560) -> int:
    return min(maximum, max(220, 44 + min(len(frame), 18) * 28))





def _last_25day_view(frame: pd.DataFrame) -> pd.DataFrame:
    """Display-only 25-day current-first view; does not alter protected source."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    time_col = next((c for c in ("Time", "time", "Datetime", "DateTime", "Date", "Timestamp", "Hour") if c in out.columns), None)
    if time_col is not None:
        parsed = pd.to_datetime(out[time_col], errors="coerce", utc=True)
        if parsed.notna().any():
            latest = parsed.max()
            start = latest - pd.Timedelta(days=25)
            out = out.loc[parsed >= start].copy()
    try:
        return chronological_view(out, row_limit=None)
    except Exception:
        return out.reset_index(drop=True)

def _render_dataframe_safely(
    title: str,
    frame: pd.DataFrame,
    *,
    row_limit: int | None = 600,
    height: int | None = None,
    current_first: bool = True,
) -> bool:
    """Render one existing table without allowing it to hide later tables.

    This is intentionally display-only. It does not edit values, formulas, or
    the protected Full Metric source. Tables with a timestamp are sorted latest
    completed H1 first; snapshot tables keep their original factor order.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return False
    st.markdown(f"#### {title}")
    try:
        show = chronological_view(frame, row_limit=row_limit) if current_first else frame.head(row_limit) if row_limit is not None else frame
        st.dataframe(
            show,
            use_container_width=True,
            hide_index=True,
            height=height or _height(show),
        )
        return True
    except Exception as exc:
        st.warning(f"{title} could not render, but every table below it is still available.")
        with st.expander(f"Open / Close — {title} render status", expanded=False):
            st.caption(f"{type(exc).__name__}: {exc}")
        return False


def _jsonable(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return value.to_dict("records")
    if isinstance(value, pd.Series):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items() if str(k) != "metrics"}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _current_identity() -> dict[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        canonical = get_canonical(st.session_state)
    except Exception:
        canonical = {}
    return {
        "Symbol": canonical.get("symbol", "EURUSD") if isinstance(canonical, dict) else "EURUSD",
        "Timeframe": canonical.get("timeframe", "H1") if isinstance(canonical, dict) else "H1",
        "Latest Completed H1": canonical.get("latest_completed_candle_time", "Not ready") if isinstance(canonical, dict) else "Not ready",
        "Run ID": canonical.get("run_id", "Not ready") if isinstance(canonical, dict) else "Not ready",
        "Generation": canonical.get("calculation_generation", "-") if isinstance(canonical, dict) else "-",
        "Data Signature": canonical.get("data_signature", "Not ready") if isinstance(canonical, dict) else "Not ready",
    }


def _decision_summary(result: Mapping[str, Any]) -> pd.DataFrame:
    scores = dict(result.get("scores") or {})
    rows = [
        {"Decision Field": "Current Decision", "Value": scores.get("Decision", "NO TRADE"), "Score /10": scores.get("Master /10")},
        {"Decision Field": "Direction Decision", "Value": scores.get("Direction", "WAIT"), "Score /10": scores.get("Direction Score")},
        {"Decision Field": "Entry Decision", "Value": (result.get("entry").iloc[0].get("Decision") if isinstance(result.get("entry"), pd.DataFrame) and not result.get("entry").empty else "Not recorded"), "Score /10": scores.get("Entry /10")},
        {"Decision Field": "Hold Decision", "Value": "Protected Hold score", "Score /10": scores.get("Hold /10")},
        {"Decision Field": "Exit Decision", "Value": (result.get("exit").iloc[0].get("Decision") if isinstance(result.get("exit"), pd.DataFrame) and not result.get("exit").empty else "Not recorded"), "Score /10": scores.get("Exit Risk /10")},
        {"Decision Field": "TP Decision", "Value": (result.get("tp").iloc[0].get("Decision") if isinstance(result.get("tp"), pd.DataFrame) and not result.get("tp").empty else "Not recorded"), "Score /10": scores.get("TP /10")},
        {"Decision Field": "Master Decision", "Value": scores.get("Decision", "NO TRADE"), "Score /10": scores.get("Master /10")},
        {"Decision Field": "Trend Capacity Remaining", "Value": "Protected metric", "Score /10": None},
    ]
    return pd.DataFrame(rows)


_fragment = getattr(st, "fragment", lambda fn: fn)


@_fragment
def _render_one_factor_history(valid_factors: Mapping[str, pd.DataFrame]) -> None:
    """Render one cached reverse-factor history without rerunning the system."""
    names = list(valid_factors)
    selected = st.selectbox(
        "Choose reverse-decision factor",
        names,
        key="full_metric_selected_factor",
    )
    frame = valid_factors.get(selected)
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        st.info("The selected factor history is unavailable in this generation.")
        return
    show = chronological_view(frame, row_limit=None)
    st.dataframe(show, use_container_width=True, hide_index=True, height=420)
    if st.toggle("Prepare selected factor CSV", value=False, key="full_metric_selected_factor_export_toggle"):
        st.download_button(
            f"Export {selected} History CSV",
            data=frame.to_csv(index=False).encode("utf-8"),
            file_name=f"eurusd_h1_{str(selected).lower().replace(' ', '_')}_history.csv",
            mime="text/csv",
            key="full_metric_selected_factor_export_20260619",
            use_container_width=True,
        )


def render_full_metric_shared(ns: dict[str, Any], *, result: Any = None) -> None:
    """Render the complete cached Full Metric output without recalculation."""
    identity = _current_identity()
    st.caption(
        "Canonical source of truth: protected Full Metric Detail + History. "
        "Run Calculation is available only in Settings; this route reuses the published generation."
    )
    id_cols = st.columns(3)
    id_cols[0].metric("EURUSD H1", f"{identity['Symbol']} {identity['Timeframe']}", f"Generation {identity['Generation']}")
    id_cols[1].metric("Latest Completed H1", str(identity["Latest Completed H1"])[:25])
    id_cols[2].metric("Run", str(identity["Run ID"])[:18], str(identity["Data Signature"])[:18])

    if result is None:
        getter = ns.get("_get_cached_lunch_metric_result")
        if callable(getter):
            try:
                result = getter(force=False)
            except Exception as exc:
                st.warning(f"Cached Full Metric result could not load safely: {exc}")
                result = None
    if not isinstance(result, Mapping) or not result.get("ok"):
        try:
            from core.system_wide_completion_20260618 import published_metric_result
            result = published_metric_result(st.session_state)
        except Exception:
            result = {}
    if not isinstance(result, Mapping) or not result.get("ok"):
        try:
            from core.system_wide_completion_20260618 import readiness_message
            st.warning(readiness_message(st.session_state, "Full Metric"))
        except Exception:
            st.warning("Full Metric output is missing from the published generation. Open Settings → Errors / Fix Fast.")
        return

    quality = ns.get("_render_lunch_metric_quality_table")
    if callable(quality):
        try:
            quality(result)
        except TypeError:
            quality()
        except Exception as exc:
            st.caption(f"Metric quality display skipped safely: {exc}")

    # User request 2026-06-18: hide the current-hour/snapshot decision tables in
    # this Full Metric History section. Keep st.metric cards above unchanged, but
    # show the operational 25-day history table as the main table.
    history = result.get("history")
    st.markdown("#### Complete Full Metric History — Latest Completed H1 First")
    if isinstance(history, pd.DataFrame) and not history.empty:
        history_view = chronological_view(history, row_limit=None)
        history_25day = _last_25day_view(history)
        # Render only the prepared current-first 25-day slice.  The complete
        # protected history stays in ``history`` and remains available through
        # the lazy export control below.
        st.dataframe(
            history_25day,
            use_container_width=True,
            hide_index=True,
            height=500,
        )
    else:
        st.info("Full Metric 25-day history is unavailable for this generation.")

    # Regime section must also show historical 25-day tables, not only current snapshot.
    try:
        from ui.full_metric_regime_inner_renderer_20260618 import render_existing_regime_inner_section
        render_existing_regime_inner_section(result)
    except Exception as exc:
        st.warning(f"Existing Regime inner tables could not render safely: {exc}")

    factor_history = result.get("history_by_factor") or {}
    valid_factors = {
        str(name): frame for name, frame in (factor_history.items() if isinstance(factor_history, Mapping) else [])
        if isinstance(frame, pd.DataFrame) and not frame.empty
    }
    if valid_factors:
        st.markdown("#### Individual Histories for All Ten Reverse-Decision Factors")
        st.caption("Only the selected factor is serialized to the browser; all ten cached histories remain available.")
        _render_one_factor_history(valid_factors)

    st.markdown("#### Existing Copy and Full Export Controls")
    try:
        from tabs.eurusd_h1_matrix import _render_short_necessary_metric_copy
        _render_short_necessary_metric_copy(result, key="metric_short_copy_shared_20260618")
    except Exception as exc:
        st.caption(f"Existing short-copy control unavailable: {exc}")

    # CSV/JSON conversion can be large.  Build bytes only after the user opens
    # this explicit control, never during normal Full Metric rendering.
    if st.toggle("Prepare complete Full Metric exports", value=False, key="full_metric_prepare_exports_20260619"):
        if isinstance(history, pd.DataFrame) and not history.empty:
            st.download_button(
                "Export 25-Day Full Metric History CSV",
                data=history_25day.to_csv(index=False).encode("utf-8"),
                file_name="eurusd_h1_full_metric_25day_history_current_first.csv",
                mime="text/csv",
                key="full_metric_history_25day_export_20260618",
                use_container_width=True,
            )
            st.download_button(
                "Export Complete Full Metric History CSV",
                data=history.to_csv(index=False).encode("utf-8"),
                file_name="eurusd_h1_full_metric_complete_history.csv",
                mime="text/csv",
                key="full_metric_complete_history_csv_20260618",
                use_container_width=True,
            )
        export_payload = json.dumps(_jsonable(result), ensure_ascii=False, indent=2, default=str).encode("utf-8")
        st.download_button(
            "Export Complete Full Metric Result JSON",
            data=export_payload,
            file_name="eurusd_h1_full_metric_complete.json",
            mime="application/json",
            key="full_metric_complete_export_20260618",
            use_container_width=True,
        )


__all__ = ["render_full_metric_shared"]

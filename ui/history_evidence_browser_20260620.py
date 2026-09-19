"""Bounded, column-projecting browser for disk-backed history evidence."""
from __future__ import annotations

from typing import Any, MutableMapping

import streamlit as st


_DISPLAY_COLUMNS = (
    "latest_completed_h1", "record_time", "target_time", "horizon", "condition",
    "metric_name", "value_numeric", "value_text", "rank_value", "lower_value",
    "median_value", "upper_value", "actual_value", "residual_value",
    "coverage_flag", "settled_status", "sample_count", "calculation_generation",
    "calculation_id", "logic_version",
)


def render_history_evidence_browser(field: str, *, state: MutableMapping[str, Any] | None = None, key_suffix: str = "") -> None:
    """Query only a selected table and a bounded page; full export is explicit."""
    from core.history_evidence_store_20260620 import catalog_frame, export_history, query_history
    from core.tinylfu_runtime_cache_20260620 import get_or_prepare

    state = state if state is not None else st.session_state
    catalog = catalog_frame(field=field)
    if catalog.empty:
        return
    st.markdown("#### Disk-Backed Evidence History")
    st.caption("Only the selected columns and one bounded page are sent to the browser. Full rows stay on disk until export is explicitly prepared.")
    labels = {
        row["name"]: f"{row['name']} — {row['description']}"
        for _, row in catalog.iterrows()
    }
    table = st.selectbox(
        "History table", list(labels), format_func=lambda name: labels[name],
        key=f"history_evidence_table_{field}_{key_suffix}",
    )
    phone = bool(state.get("phone_mode", False))
    page_size = 48 if phone else 120
    page = int(st.number_input(
        "Page", min_value=1, value=1, step=1,
        key=f"history_evidence_page_{field}_{key_suffix}",
    ))
    generation_key = str(
        state.get("canonical_calculation_id_20260617")
        or state.get("canonical_run_id_20260617")
        or state.get("calculation_generation")
        or "no-generation"
    )
    cache_key = f"history-browser|{table}|{generation_key}|{page_size}|{page}"
    frame, cache_status = get_or_prepare(
        cache_key,
        lambda: query_history(
            table, columns=_DISPLAY_COLUMNS, limit=page_size, offset=(page - 1) * page_size,
        ),
        size_bytes=lambda value: int(value.memory_usage(index=True, deep=True).sum()),
    )
    if frame.empty:
        st.info("No rows have been committed for this history yet. The next successful completed-H1 Settings transaction will populate available evidence.")
    else:
        st.dataframe(frame, use_container_width=True, hide_index=True, height=430)
        st.caption(f"Browser page: {len(frame):,} rows · maximum {page_size:,} rows · newest completed H1 first · display cache {cache_status}.")

    if st.button(
        "Prepare Complete CSV Export", key=f"history_evidence_export_{field}_{key_suffix}",
        use_container_width=True,
    ):
        full = export_history(table)
        csv_bytes = full.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download Complete History CSV", data=csv_bytes,
            file_name=f"{table}.csv", mime="text/csv",
            key=f"history_evidence_download_{field}_{key_suffix}",
            use_container_width=True,
        )
        st.caption(f"Complete export prepared only after your click: {len(full):,} rows.")


__all__ = ["render_history_evidence_browser"]

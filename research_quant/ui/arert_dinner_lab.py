"""Cached, read-only ARERT Dinner thesis laboratory renderer.

Opening a field only renders the last completed envelope. It never trains,
fetches APIs, mutates Lunch production values, or runs a research module.
"""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping

import pandas as pd
import streamlit as st

from research_quant.arert_lab import MODULE_CATALOG, STATE_KEY

FIELD_LAYOUT = {
    1: ("Research Snapshot and Data Integrity", ()),
    2: ("Multi-Scale Regime Laboratory", (1, 2, 3, 4)),
    3: ("Forecast and Uncertainty Laboratory", (5, 6)),
    4: ("Decision Reliability Laboratory", (7, 8, 9, 10)),
    5: ("Historical Analogue Laboratory", (11, 12)),
    6: ("Behavioral Finance and NLP Laboratory", (13, 14, 15)),
    7: ("Model Ecology and Drift Laboratory", (16,)),
    8: ("Event-Response Laboratory", (17,)),
    9: ("Evidence Information Laboratory", (18,)),
    10: ("Thesis Validation and ARERT", (19, 20)),
}


def _frame(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy(deep=False)
    if isinstance(value, list):
        try:
            return pd.DataFrame(value)
        except Exception:
            return pd.DataFrame()
    if isinstance(value, Mapping):
        try:
            return pd.DataFrame([dict(value)])
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def _drop_blank_display_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    keep = []
    for column in frame.columns:
        series = frame[column]
        text = series.astype(str).str.strip().str.upper()
        meaningful = series.notna() & ~text.isin({"", "NONE", "NAN", "N/A", "NA", "UNAVAILABLE"})
        if meaningful.any():
            keep.append(column)
    return frame.loc[:, keep]


def _search(frame: pd.DataFrame, query: str) -> pd.DataFrame:
    if frame.empty or not query.strip():
        return frame
    needle = query.strip().casefold()
    mask = frame.astype(str).apply(lambda col: col.str.casefold().str.contains(needle, regex=False, na=False)).any(axis=1)
    return frame.loc[mask]


def _render_table(frame: pd.DataFrame, *, key: str, label: str, query: str) -> None:
    display = _drop_blank_display_columns(_search(frame, query))
    if display.empty:
        st.caption(f"{label}: no populated rows match the current filter.")
        return
    st.markdown(f"**{label}**")
    st.dataframe(display, use_container_width=True, hide_index=True, height=min(500, 88 + 35 * min(len(display), 12)))
    st.download_button(
        f"Export {label} CSV",
        display.to_csv(index=False).encode("utf-8"),
        file_name=f"{key}.csv",
        mime="text/csv",
        key=f"arert_export_{key}",
        use_container_width=True,
    )


def _render_integrity(envelope: Mapping[str, Any]) -> None:
    metadata = envelope.get("metadata") if isinstance(envelope.get("metadata"), Mapping) else {}
    cols = st.columns(4)
    cols[0].metric("run_id", str(metadata.get("run_id") or "Unavailable"))
    cols[1].metric("generation_id", str(metadata.get("generation_id") or "Unavailable"))
    cols[2].metric("Symbol / Timeframe", f"{metadata.get('symbol') or '—'} / {metadata.get('timeframe') or '—'}")
    cols[3].metric("Completed Broker Candle", str(metadata.get("completed_broker_candle") or "Unavailable"))
    cols2 = st.columns(4)
    cols2[0].metric("Sample Size", str(metadata.get("sample_size", 0)))
    cols2[1].metric("Missingness", f"{100*float(metadata.get('missingness_ratio') or 0):.2f}%")
    cols2[2].metric("Duplicate Rows", str(metadata.get("duplicate_rows", 0)))
    cols2[3].metric("Data Quality", str(metadata.get("data_quality_status") or "CHECK"))

    identity = pd.DataFrame([
        {"Required Research Identity": key, "Value": metadata.get(key)}
        for key in (
            "run_id", "generation_id", "symbol", "timeframe", "completed_broker_candle",
            "research_model_version", "input_data_version", "calculation_timestamp",
            "sample_period", "sample_size", "data_quality_status", "leakage_cutoff",
        )
    ])
    st.dataframe(identity, use_container_width=True, hide_index=True)
    db = envelope.get("database") if isinstance(envelope.get("database"), Mapping) else {}
    st.caption(
        "Database: " + ("isolated ARERT store ready" if db.get("ok") else f"not persisted — {db.get('error') or 'unknown'}")
        + ". Production values modified: " + str(bool(envelope.get("production_values_modified"))).upper()
    )
    benchmark = _frame(envelope.get("benchmarks"))
    if not benchmark.empty:
        st.markdown("**Module run/cache evidence**")
        st.dataframe(benchmark, use_container_width=True, hide_index=True)


def _render_module(module: Mapping[str, Any], number: int, query: str) -> None:
    title = MODULE_CATALOG[number][0]
    status = str(module.get("status") or "NOT RUN")
    st.markdown(f"#### Module {number} — {title}")
    st.caption(f"Status: {status} · Production influence enabled: {bool(module.get('production_influence_enabled'))}")

    summary = module.get("summary") if isinstance(module.get("summary"), Mapping) else {}
    if summary:
        summary_rows = []
        for key, value in summary.items():
            if isinstance(value, (Mapping, list, tuple)):
                continue
            summary_rows.append({"Metric": key, "Value": value})
        if summary_rows:
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
    tables = module.get("tables") if isinstance(module.get("tables"), Mapping) else {}
    for table_name, value in tables.items():
        _render_table(_frame(value), key=f"module_{number}_{table_name}", label=str(table_name).replace("_", " ").title(), query=query)
    limitations = module.get("limitations") if isinstance(module.get("limitations"), list) else []
    if limitations:
        st.warning("Known limitation: " + " | ".join(str(item) for item in limitations))
    methodology = str(module.get("methodology") or "")
    if methodology:
        st.caption("Methodology: " + methodology)


def render_arert_dinner_lab(state: MutableMapping[str, Any], canonical: Mapping[str, Any] | None = None) -> None:
    st.markdown("## 🎓 Adaptive Regime–Evidence Reliability Theory — ARERT")
    st.caption(
        "Separate Master’s/PhD research layer. It reads one frozen completed production snapshot. "
        "Opening fields only displays cached results and never changes Lunch calculations."
    )
    envelope = state.get(STATE_KEY)
    if not isinstance(envelope, Mapping):
        st.info("No completed ARERT research run is cached. Use Settings → Run Full Dinner Thesis Research + Open Dinner.")
        return

    query = st.text_input(
        "Search/filter all ARERT research tables",
        value="",
        key="arert_dinner_table_search_20260628",
        placeholder="Type a decision, regime, timestamp, module value, or status",
    )
    modules = envelope.get("modules") if isinstance(envelope.get("modules"), Mapping) else {}

    for field_number, (field_title, module_numbers) in FIELD_LAYOUT.items():
        with st.expander(
            f"Open / Close — Field {field_number}: {field_title}",
            expanded=(field_number == 1),
        ):
            if field_number == 1:
                _render_integrity(envelope)
                continue
            for module_number in module_numbers:
                module = modules.get(str(module_number))
                if not isinstance(module, Mapping):
                    st.info(f"Module {module_number} — {MODULE_CATALOG[module_number][0]} was not selected or has not run.")
                    continue
                _render_module(module, module_number, query)


__all__ = ["FIELD_LAYOUT", "render_arert_dinner_lab"]

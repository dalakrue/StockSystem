"""Read-only IMAP-RV Dinner renderer. Heavy research runs only in Settings."""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping

import pandas as pd
import streamlit as st

from research_quant.imap_rv_20260628 import STATE_KEY

SECTIONS = {
    "1. Research Snapshot Identity": None,
    "2. Information Efficiency and Residual Information Value": "information_value_history",
    "3. Path-Dependent Volatility Memory": "path_memory_history",
    "4. Internal Model Crowding and Consensus Fragility": "model_crowding",
    "5. Signal IC and Multiple-Testing Validation": "signal_validity",
    "6. Effective Breadth and Beta Fragility": "beta_fragility",
    "7. Cleaned Evidence Covariance": "cleaned_evidence_correlation",
    "8. Diversity-Weighted Evidence Consensus": "diversity_weighted_consensus",
    "9. NLP Attention and Hype": "attention_hype",
    "10. IMAP-RV Reliability Decomposition": "imap_rv_reliability_decomposition",
}


def _frame(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value
    if isinstance(value, list):
        try:
            return pd.DataFrame(value)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def _render_identity(envelope: Mapping[str, Any]) -> None:
    metadata = envelope.get("metadata") if isinstance(envelope.get("metadata"), Mapping) else {}
    rows = [
        {"Metric": "Framework", "Value": metadata.get("framework", "IMAP-RV")},
        {"Metric": "Implementation status", "Value": metadata.get("implementation_status")},
        {"Metric": "Run ID", "Value": metadata.get("run_id")},
        {"Metric": "Generation ID", "Value": metadata.get("generation_id")},
        {"Metric": "Symbol / Timeframe", "Value": f"{metadata.get('symbol')} / {metadata.get('timeframe')}"},
        {"Metric": "Completed broker candle", "Value": metadata.get("completed_broker_candle")},
        {"Metric": "Sample period", "Value": metadata.get("sample_period")},
        {"Metric": "Sample size", "Value": metadata.get("sample_size")},
        {"Metric": "Data quality", "Value": metadata.get("data_quality_status")},
        {"Metric": "Production values modified", "Value": envelope.get("production_values_modified")},
        {"Metric": "Cache status", "Value": envelope.get("cache_status")},
        {"Metric": "Research database", "Value": (envelope.get("database") or {}).get("path") if isinstance(envelope.get("database"), Mapping) else "—"},
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=430)


def render_imap_rv_dinner(state: MutableMapping[str, Any]) -> None:
    st.markdown("### IMAP-RV — Information Mining, Attention, Path-Memory and Research Validity")
    st.caption(
        "Separate thesis-research layer. It never overwrites the protected Lunch direction. "
        "Only the selected field is rendered; opening this section never trains or recalculates a model."
    )
    envelope = state.get(STATE_KEY)
    if not isinstance(envelope, Mapping):
        st.info("Run IMAP-RV explicitly from Settings after a completed canonical generation is published.")
        return
    top = st.columns(4)
    top[0].metric("IMAP-RV Score", "N/A" if envelope.get("imap_rv_score") is None else f"{float(envelope.get('imap_rv_score')):.1f}/100")
    top[1].metric("Protective Action", str(envelope.get("protective_action") or "NO TRADE"))
    top[2].metric("Production Direction", str(envelope.get("protected_production_direction") or "UNAVAILABLE"))
    top[3].metric("Status", str(envelope.get("status") or "CHECK"))
    st.caption(str(envelope.get("protective_reason") or "No research protective reason was published."))

    selected = st.selectbox(
        "Open one IMAP-RV research field",
        list(SECTIONS),
        key="imap_rv_dinner_section_20260628",
        help="One selected field only; unselected research tables are not sent to the browser.",
    )
    if SECTIONS[selected] is None:
        _render_identity(envelope)
    else:
        tables = envelope.get("tables") if isinstance(envelope.get("tables"), Mapping) else {}
        frame = _frame(tables.get(SECTIONS[selected]))
        if frame.empty:
            st.info("This research field has insufficient valid evidence. No value was fabricated.")
        else:
            mobile = bool(state.get("extreme_mobile_lite_mode_20260628") or state.get("phone_mode"))
            rows = 10 if mobile else 50
            st.dataframe(frame.head(rows), use_container_width=True, hide_index=True, height=min(520, 90 + rows * 32))
            st.caption(f"Rendered {min(rows, len(frame)):,} of {len(frame):,} cached rows. Full data remains in the research envelope/database.")
            st.download_button(
                "Download Selected IMAP-RV Table CSV",
                frame.to_csv(index=False).encode("utf-8"),
                file_name=f"imap_rv_{SECTIONS[selected]}.csv",
                mime="text/csv",
                key=f"imap_rv_export_{SECTIONS[selected]}_20260628",
                use_container_width=True,
            )
    limitations = envelope.get("limitations") if isinstance(envelope.get("limitations"), list) else []
    with st.expander("Open / Close — IMAP-RV limitations", expanded=False):
        for item in limitations:
            st.write(f"- {item}")


__all__ = ["render_imap_rv_dinner", "SECTIONS"]

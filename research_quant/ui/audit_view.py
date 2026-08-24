from __future__ import annotations
from typing import Any, Mapping
import pandas as pd


def render_audit_view(state: Mapping[str, Any]) -> None:
    import streamlit as st
    result = state.get("crcef_sv_research_20260627")
    audit = result.get("audit") if isinstance(result, Mapping) else None
    if isinstance(audit, Mapping):
        frame = pd.DataFrame([dict(audit)])
        st.dataframe(frame, use_container_width=True, hide_index=True)
        st.download_button("Export CRCEF-SV Audit CSV", frame.to_csv(index=False).encode(), "crcef_sv_audit.csv", "text/csv")
    else:
        st.info("No CRCEF-SV audit row is available.")

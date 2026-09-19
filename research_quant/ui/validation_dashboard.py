from __future__ import annotations
from typing import Any, Mapping
import pandas as pd


def render_validation_dashboard(state: Mapping[str, Any]) -> None:
    import streamlit as st
    st.markdown("### CRCEF-SV Validation Dashboard")
    result = state.get("crcef_sv_research_20260627")
    payload = result.get("payload") if isinstance(result, Mapping) and isinstance(result.get("payload"), Mapping) else {}
    modules = payload.get("research_modules") if isinstance(payload, Mapping) else {}
    if isinstance(modules, Mapping) and modules:
        st.dataframe(pd.DataFrame([{"Module": key, "Status": value} for key, value in modules.items()]), use_container_width=True, hide_index=True)
    else:
        st.info("Validation modules have not published for this generation.")

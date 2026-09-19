from __future__ import annotations
from typing import Any, Mapping


def render_dinner_research(state: Mapping[str, Any]) -> None:
    import streamlit as st
    result = state.get("crcef_sv_research_20260627")
    if not isinstance(result, Mapping) or not result:
        st.info("No CRCEF-SV publication is available for this exact generation.")
        return
    payload = result.get("payload") if isinstance(result.get("payload"), Mapping) else result
    st.json({
        "Production Decision": payload.get("production_decision"),
        "Research Shadow Decision": payload.get("research_shadow_decision"),
        "BUY Evidence": payload.get("buy_evidence"),
        "SELL Evidence": payload.get("sell_evidence"),
        "Conflict": payload.get("conflict"),
        "Coverage": payload.get("coverage"),
        "Actionability": payload.get("actionability_probability"),
        "Expected Utility": payload.get("expected_utility"),
        "Uncertainty": payload.get("uncertainty_pct"),
        "Promotion": payload.get("promotion_status"),
    }, expanded=False)

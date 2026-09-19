from __future__ import annotations
from typing import Any, Mapping
import pandas as pd


def _payload(result: Mapping[str, Any]) -> Mapping[str, Any]:
    value = result.get("payload")
    return value if isinstance(value, Mapping) else result


def render_lunch_research(state: Mapping[str, Any]) -> None:
    import streamlit as st
    result = state.get("crcef_sv_research_20260627")
    with st.expander("CRCEF-SV — Research-Only Selective Evidence Fusion", expanded=False):
        if not isinstance(result, Mapping) or not result:
            st.info("No CRCEF-SV result was published for the current exact run. Use the Settings full-run button.")
            return
        payload = _payload(result)
        cols = st.columns(5)
        cols[0].metric("Production", str(payload.get("production_decision") or "—"))
        cols[1].metric("Research Shadow", str(payload.get("research_shadow_decision") or "—"))
        cols[2].metric("Fusion", f"{float(payload.get('direction_fusion_score') or 0):.3f}")
        cols[3].metric("Uncertainty", f"{float(payload.get('uncertainty_pct') or 0):.1f}%")
        cols[4].metric("Reliability", f"{100*float(payload.get('research_reliability') or 0):.1f}%")
        st.caption("Research output is shadow-only and never overwrites the protected production decision.")
        rows = [
            {"Evidence": name, "Weight": weight}
            for name, weight in (payload.get("evidence_weights") or {}).items()
        ]
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.json({
            "status": result.get("status"), "reason": result.get("reason"),
            "quality_flags": result.get("quality_flags", []),
            "promotion_status": payload.get("promotion_status"),
        }, expanded=False)


def render_regime_research(state: Mapping[str, Any]) -> None:
    import streamlit as st
    result = state.get("crcef_sv_research_20260627")
    if not isinstance(result, Mapping):
        return
    payload = _payload(result)
    regime = payload.get("regime_lifecycle")
    with st.expander("Research Markov Regime Lifecycle", expanded=False):
        if not isinstance(regime, Mapping) or not regime:
            st.info("Research regime lifecycle is unavailable for this generation.")
            return
        st.json(dict(regime), expanded=False)

"""Read-only renderer for the V13 completed-H1 regime evidence matrix."""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping

import pandas as pd

DISPLAY_COLUMNS = (
    "event_time_utc", "Broker Time", "Close",
    "Lower 1-Day Regime", "Lower 1-Day Z-Score",
    "Middle 5-Day Regime", "Middle 5-Day Z-Score",
    "Higher 25-Day Regime", "Higher 25-Day Z-Score",
    "Trend Agreement", "Actionability", "Regime Decision Level /10",
    "Data Quality", "Data Quality Score /100", "Evidence Class",
    "Settled Status", "Source Provenance",
)


def build_field3_matrix(
    state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None, *, limit: int = 600
) -> pd.DataFrame:
    """Build the display matrix from cached completed H1 inputs only."""
    from core.lunch_h1_data_quality_v13 import build_regime_decision_matrix

    frame = build_regime_decision_matrix(state, canonical, limit=limit)
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    columns = [column for column in DISPLAY_COLUMNS if column in frame.columns]
    return frame.loc[:, columns].head(max(1, int(limit))).reset_index(drop=True)


def render_field3_matrix(
    state: MutableMapping[str, Any], canonical: Mapping[str, Any] | None = None
) -> None:
    import streamlit as st

    st.markdown("#### Completed-H1 Regime Evidence Matrix — Last 25 Days")
    st.caption(
        "Read-only shadow decision support derived from cached canonical completed-H1 OHLC. "
        "It does not replace the protected Lower, Middle or Higher production regime and is not a settled outcome."
    )
    matrix = build_field3_matrix(state, canonical, limit=600)
    if matrix.empty:
        st.info("Cached completed-H1 evidence is unavailable; no regime matrix rows were invented.")
        return
    try:
        from core.shared_broker_time_20260622 import frame_to_shared_broker_clock

        display = frame_to_shared_broker_clock(matrix, state, canonical=canonical)
    except Exception:
        display = matrix
    st.dataframe(display, use_container_width=True, hide_index=True, height=520)
    st.caption(
        f"{len(matrix):,} completed H1 rows · newest first · "
        "Evidence class COMPLETED_H1_SHADOW_DECISION_SUPPORT · settlement NOT_A_SETTLED_OUTCOME."
    )


__all__ = ["DISPLAY_COLUMNS", "build_field3_matrix", "render_field3_matrix", "build_regime_intelligence_view", "render_regime_intelligence"]


def build_regime_intelligence_view(state: Mapping[str, Any]) -> dict[str, Any]:
    """Return the saved Settings-owned payload; never fit during rendering."""
    value = state.get("regime_intelligence_20260624")
    return dict(value) if isinstance(value, Mapping) else {}


def render_regime_intelligence(state: MutableMapping[str, Any]) -> None:
    """Compact read-only Field 3 research-grade evidence view."""
    import streamlit as st
    payload = build_regime_intelligence_view(state)
    if not payload:
        st.info("Regime Intelligence is unavailable. Run Settings → Run Calculation + Open Lunch.")
        return
    current = payload.get("current") or {}; lower=payload.get("lower_standard") or {}; middle=payload.get("middle_standard") or {}; higher=payload.get("higher_standard") or {}
    hsmm=payload.get("hsmm") or {}; fil=payload.get("filardo") or {}; boc=payload.get("bocpd") or {}; ood=payload.get("ood") or {}; dq=payload.get("data_quality") or {}
    st.markdown("#### Regime Intelligence Stack — Saved Canonical Evidence")
    cards = [
        ("Major Regime", current.get("major_regime","N/A")), ("Lower",lower.get("major_regime","N/A")),
        ("Middle",middle.get("major_regime","N/A")), ("Higher",higher.get("major_regime","N/A")),
        ("Reliable", "TRUE" if current.get("regime_reliability") else "FALSE"),
        ("Posterior", f"{100*float(current.get('posterior_probability') or 0):.1f}%"),
        ("Runner-up", f"{100*float(current.get('runner_up_probability') or 0):.1f}%"),
        ("Margin", f"{100*float(current.get('probability_margin') or 0):.1f}%"),
        ("Entropy", f"{float(current.get('normalized_entropy') or 0):.3f}"),
        ("Age", hsmm.get("current_age","N/A")), ("Remaining", hsmm.get("expected_remaining_duration","N/A")),
        ("Transition 1h", f"{100*float(fil.get('transition_probability_1h') or 0):.1f}%"),
        ("Transition 3h", f"{100*float(fil.get('transition_probability_3h') or 0):.1f}%"),
        ("Transition 6h", f"{100*float(fil.get('transition_probability_6h') or 0):.1f}%"),
        ("Changepoint", f"{100*float(boc.get('changepoint_probability') or 0):.1f}%"),
        ("OOD/New Era", ood.get("unknown_status","N/A")), ("Agreement", f"{100*float(current.get('model_agreement') or 0):.1f}%"),
        ("Data Quality", dq.get("status","N/A")),
    ]
    cols=st.columns(3)
    for i,(label,value) in enumerate(cards): cols[i%3].metric(label,value)
    sections=[("Complete regime posterior",(payload.get("ensemble") or {}).get("posterior")),("Transition matrix",fil.get("matrix")),("Transition-driver contributions",fil.get("driver_contributions")),("Duration and survival estimates",hsmm),("BOCPD run-length distribution",boc),("CUSUM warnings",payload.get("shift_detection")),("Structural-break evidence",payload.get("structural_breaks")),("OOD feature contributions",ood),("Model weights and disagreements",payload.get("ensemble")),("Validation and calibration evidence",payload.get("validation"))]
    for title,value in sections:
        with st.expander(title, expanded=False): st.json(value or {})
    history=payload.get("history_25d") or {}
    for label,key in (("Lower standard history","lower"),("Middle standard history","middle"),("Higher standard history","higher")):
        with st.expander(label, expanded=False):
            frame=pd.DataFrame(history.get(key) or [])
            if frame.empty:
                st.info("N/A — no point-in-time stored history is available.")
            else:
                from core.time_safe_frame_20260628 import safe_sort_by_time
                frame = safe_sort_by_time(frame, column="Broker Time", ascending=False)
                st.dataframe(frame,use_container_width=True,hide_index=True)

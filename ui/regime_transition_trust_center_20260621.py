"""Cached-only Dinner/Regime renderer for transition, drift and system trust."""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping

import pandas as pd
import streamlit as st

from core.generation_identity_20260707 import numeric_generation

FIELD_LABEL = "6. Regime Transition, Drift & System Trust Center"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _canonical(state: MutableMapping[str, Any]) -> Mapping[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        value = get_canonical(state)
        return value if isinstance(value, Mapping) else {}
    except Exception:
        value = state.get("canonical_decision_result") or state.get("canonical_decision_result_20260617") or {}
        return value if isinstance(value, Mapping) else {}


def _metric_grid(items: list[tuple[str, Any, str | None]], *, phone: bool) -> None:
    width = 2 if phone else 4
    for start in range(0, len(items), width):
        cols = st.columns(width)
        for col, item in zip(cols, items[start : start + width]):
            label, value, delta = item
            col.metric(label, "-" if value in (None, "") else str(value), delta=delta)


def _safe_frame(records: Any) -> pd.DataFrame:
    if isinstance(records, pd.DataFrame):
        return records.copy(deep=False)
    if isinstance(records, list):
        return pd.DataFrame([dict(row) for row in records if isinstance(row, Mapping)])
    return pd.DataFrame()


@st.cache_data(show_spinner=False, max_entries=64)
def _cached_transition_matches(previous_regime: str, current_regime: str, run_id: str, generation: int) -> pd.DataFrame:
    # run_id/generation are bounded immutable cache keys. The query itself uses
    # only projected transition/outcome columns and never invokes a calculator.
    del run_id, generation
    from core.regime_trust_store_20260621 import default_store
    return default_store().transition_matches(previous_regime, current_regime, limit=50)


def _history_matches(summary: Mapping[str, Any]) -> pd.DataFrame:
    transition = _mapping(summary.get("transition_summary"))
    audit = _mapping(summary.get("system_trust_audit"))
    previous_regime = str(transition.get("previous_regime") or "")
    current_regime = str(transition.get("current_regime") or "")
    try:
        frame = _cached_transition_matches(
            previous_regime, current_regime,
            str(audit.get("canonical_run_id") or ""),
            numeric_generation(audit.get("calculation_generation") or audit.get("generation_id"), default=1),
        )
        if not frame.empty:
            for horizon in (1, 2, 3, 6):
                close_col = f"actual_close_{horizon}h"
                if close_col in frame.columns and "entry_reference_price" in frame.columns:
                    frame[f"movement_{horizon}h_pct"] = (
                        (pd.to_numeric(frame[close_col], errors="coerce") - pd.to_numeric(frame["entry_reference_price"], errors="coerce"))
                        / pd.to_numeric(frame["entry_reference_price"], errors="coerce").replace(0, pd.NA) * 100.0
                    )
            return frame.head(5)
    except Exception as exc:
        st.session_state["regime_trust_history_query_error_20260621"] = repr(exc)
    return _safe_frame(_mapping(summary.get("historical_transition_matches")).get("top_five"))


def render_regime_transition_trust_center(*, state: MutableMapping[str, Any] | None = None) -> None:
    """Render the already-published trust evidence; never run a detector here."""
    state = state if state is not None else st.session_state
    canonical = _canonical(state)
    payload = _mapping(canonical.get("regime_transition_trust_center"))
    if not payload:
        payload = _mapping(state.get("regime_transition_trust_center_20260621"))
    if not payload:
        st.info("Regime transition and system-trust evidence is not published yet. Run Calculation once from Settings.")
        return

    phone = bool(state.get("phone_mode", False))
    transition = _mapping(payload.get("transition_summary"))
    evidence = _mapping(payload.get("change_evidence"))
    matches = _mapping(payload.get("historical_transition_matches"))
    calibration = _mapping(payload.get("prediction_calibration"))
    audit = _mapping(payload.get("system_trust_audit"))

    st.caption("Evidence-only layer. The existing canonical regime and protected trading decisions remain authoritative and unchanged.")

    st.markdown("#### A. Transition Summary")
    _metric_grid([
        ("Previous Regime", transition.get("previous_regime"), None),
        ("Current Regime", transition.get("current_regime"), None),
        ("Candidate Next", transition.get("candidate_next_regime"), None),
        ("Change Probability", f"{float(transition.get('regime_change_probability') or 0):.1f}%", None),
        ("Transition Status", transition.get("transition_status"), None),
        ("Drift Type", transition.get("drift_type"), None),
        ("Hours Since Transition", transition.get("hours_since_last_confirmed_transition"), None),
        ("Days Since Transition", transition.get("days_since_last_confirmed_transition"), None),
        ("Calibrated Regime Trust", f"{float(transition.get('calibrated_regime_trust') or 0):.1f}/100", None),
        ("Safer Decision", transition.get("safer_decision"), None),
    ], phone=phone)
    st.info(str(transition.get("reason") or "No plain-language reason was published."))

    st.markdown("#### B. Change Evidence")
    _metric_grid([
        ("BOCPD Probability", f"{float(evidence.get('bayesian_online_changepoint_probability') or 0):.1f}%", None),
        ("Most Likely Run Length", evidence.get("most_likely_run_length"), None),
        ("Run-Length Uncertainty", f"{float(evidence.get('run_length_uncertainty') or 0):.1f}%", None),
        ("ADWIN Status", evidence.get("adwin_change_status"), None),
        ("Adaptive Window", evidence.get("effective_adaptive_window_size"), None),
        ("Volatility Shift", f"{float(evidence.get('volatility_shift') or 0):.1f}%", None),
        ("Forecast Disagreement", f"{float(evidence.get('forecast_disagreement') or 0):.1f}/100", None),
        ("Prediction-Error Drift", f"{float(evidence.get('prediction_error_drift') or 0):.1f}/100", None),
        ("Calibration Deterioration", f"{float(evidence.get('calibration_deterioration') or 0):.1f}/100", None),
        ("Regime vs Prediction", evidence.get("regime_prediction_conflict"), None),
    ], phone=phone)

    st.markdown("#### C. Historical Transition Matches")
    sample_size = int(matches.get("sample_size") or 0)
    st.caption(f"Matching historical transition sample: {sample_size}.")
    if matches.get("warning"):
        st.warning(str(matches.get("warning")))
    table = _history_matches(payload)
    if table.empty:
        st.info("No settled historical transition match is available for this regime pair yet.")
    else:
        preferred = [
            "transition_time", "previous_regime", "new_regime", "similarity_score",
            "movement_1h_pct", "movement_2h_pct", "movement_3h_pct", "movement_6h_pct",
            "maximum_favorable_excursion", "maximum_adverse_excursion", "regime_still_active_6h",
        ]
        show = table[[column for column in preferred if column in table.columns]].copy()
        st.dataframe(show, use_container_width=True, hide_index=True, height=min(360, 80 + len(show) * 38))

    st.markdown("#### D. Prediction Calibration")
    _metric_grid([
        ("Raw Confidence", f"{float(calibration.get('raw_confidence') or 0):.1f}%", None),
        ("Calibrated Confidence", f"{float(calibration.get('calibrated_confidence') or 0):.1f}%", None),
        ("Expected Calibration Error", calibration.get("expected_calibration_error", "Unavailable"), None),
        ("Brier Score", calibration.get("brier_score", "Unavailable"), None),
        ("Rolling Coverage", calibration.get("rolling_interval_coverage", "Unavailable"), None),
        ("Target Coverage", calibration.get("target_coverage", "Unavailable"), None),
        ("Coverage Error", calibration.get("coverage_error", "Unavailable"), None),
        ("Adaptive Lower Band", calibration.get("adaptive_lower_prediction_band", "Unavailable"), None),
        ("Adaptive Upper Band", calibration.get("adaptive_upper_prediction_band", "Unavailable"), None),
        ("PID P", calibration.get("pid_proportional_error", "Unavailable"), None),
        ("PID I", calibration.get("pid_integral_error", "Unavailable"), None),
        ("PID D", calibration.get("pid_derivative_error", "Unavailable"), None),
        ("Next Width Adjustment", f"{float(calibration.get('next_interval_width_adjustment') or 0):+.1f}%", None),
    ], phone=phone)

    st.markdown("#### E. System Trust Audit")
    audit_frame = pd.DataFrame([
        {"Audit Field": "Canonical Run ID", "Value": audit.get("canonical_run_id")},
        {"Audit Field": "Calculation Generation", "Value": audit.get("calculation_generation")},
        {"Audit Field": "Source-Data Timestamp", "Value": audit.get("source_data_timestamp")},
        {"Audit Field": "Data Freshness", "Value": audit.get("data_freshness")},
        {"Audit Field": "Data Fingerprint", "Value": audit.get("data_fingerprint")},
        {"Audit Field": "Result-Schema Version", "Value": audit.get("result_schema_version")},
        {"Audit Field": "Missing Source Warnings", "Value": ", ".join(audit.get("missing_source_warnings") or []) or "None"},
        {"Audit Field": "Fallback Use", "Value": audit.get("fallback_use")},
        {"Audit Field": "Last Successful Calculation", "Value": audit.get("last_successful_calculation")},
        {"Audit Field": "All Visible Components Same Canonical Result", "Value": audit.get("all_visible_components_same_canonical_result")},
    ])
    st.dataframe(audit_frame, use_container_width=True, hide_index=True, height=390)


__all__ = ["FIELD_LABEL", "render_regime_transition_trust_center"]

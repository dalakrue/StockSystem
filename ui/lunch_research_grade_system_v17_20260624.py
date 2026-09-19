"""Read-only compact renderer for the saved unified research sidecar."""
from __future__ import annotations

from typing import Any, Mapping
import pandas as pd
import streamlit as st


def _payload(state: Mapping[str, Any]) -> Mapping[str, Any]:
    value = state.get("research_grade_system_v17_20260624")
    return value if isinstance(value, Mapping) else {}


def _identity(payload: Mapping[str, Any]) -> None:
    contract = payload.get("contract") or {}
    st.caption(
        f"Run {contract.get('run_id', '—')} · Broker candle {contract.get('broker_candle_time', '—')} · "
        f"Cutoff {contract.get('data_cutoff_time', '—')} · {payload.get('status', 'MISSING')} · SHADOW ONLY"
    )


def _field2(payload: Mapping[str, Any]) -> None:
    rows = []
    for horizon, item in (payload.get("field2") or {}).items():
        metrics = item.get("metrics") or {}
        rows.append({
            "horizon": f"H{horizon}", "point": item.get("point_forecast"), "median": item.get("median_forecast"),
            "origin lower": item.get("origin_lower"), "origin upper": item.get("origin_upper"),
            "raw direction p": item.get("raw_direction_probability"), "calibrated direction p": item.get("calibrated_direction_probability"),
            "MAE": metrics.get("mae"), "RMSE": metrics.get("rmse"), "CRPS": metrics.get("crps"), "CRPS method": metrics.get("crps_method"),
            "coverage": metrics.get("interval_coverage"), "coverage debt": (item.get("conformal") or {}).get("coverage_debt"),
            "after-cost value": metrics.get("after_cost_directional_value"), "models": ", ".join(item.get("selected_shadow_models") or []),
            "status": item.get("evidence_status"),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No saved unified Field 2 research evidence for this canonical run.")


def _field3(payload: Mapping[str, Any]) -> None:
    item = payload.get("field3") or {}
    cols = st.columns(5)
    values = [
        ("Production regime", item.get("production_regime")), ("Shadow regime", item.get("shadow_filtered_regime")),
        ("Persistence", item.get("persistence_probability")), ("Changepoint p", item.get("changepoint_probability")),
        ("Warning", item.get("transition_warning_state")),
    ]
    for col, (label, value) in zip(cols, values):
        col.metric(label, "—" if value is None else value)
    posterior = item.get("posterior_probabilities") or {}
    if posterior:
        st.dataframe(pd.DataFrame([{"regime": k, "posterior_probability": v} for k, v in posterior.items()]), use_container_width=True, hide_index=True)
    st.json({
        "transition_probabilities": item.get("transition_probabilities"),
        "expected_regime_duration": item.get("expected_regime_duration"),
        "estimated_remaining_duration": item.get("estimated_remaining_duration"),
        "production_shadow_agreement": item.get("production_shadow_agreement"),
        "evidence_sufficient": item.get("regime_evidence_sufficiency"),
        "confusion_matrix": item.get("regime_confusion_matrix"),
    }, expanded=False)


def _field8(payload: Mapping[str, Any]) -> None:
    rows = []
    for horizon, item in (payload.get("field8") or {}).items():
        rows.append({
            "horizon": f"H{horizon}", "calibration method": ((item.get("current_calibration_quality") or {}).get("calibration_method")),
            "conformal fallback": ((item.get("conformal_coverage_status") or {}).get("fallback_level")),
            "MCS members": ", ".join((item.get("model_confidence_set_membership") or {}).get("members") or []),
            "SPA": (item.get("spa_status") or {}).get("status"), "data sufficient": item.get("data_sufficiency"),
            "shadow eligible": item.get("shadow_eligibility"), "leakage": item.get("leakage_status"), "drift": item.get("drift_status"),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    limitations = [item.get("explicit_limitation_text") for item in (payload.get("field8") or {}).values() if item.get("explicit_limitation_text")]
    if limitations:
        st.caption(limitations[0])


def _field9(payload: Mapping[str, Any]) -> None:
    item = payload.get("field9") or {}
    rows = item.get("action_results") or []
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.json({
        "production_action_unchanged": item.get("production_action"), "best_counterfactual_action": item.get("best_counterfactual_action"),
        "counterfactual_regret": item.get("counterfactual_regret"), "minimum_input_change_required": item.get("minimum_input_change_required"),
        "stability_across_models": item.get("stability_across_models"), "stability_across_regimes": item.get("stability_across_regimes"),
        "stability_across_sessions": item.get("stability_across_sessions"), "stability_across_chronological_blocks": item.get("stability_across_chronological_blocks"),
        "evidence_sufficiency": item.get("evidence_sufficiency"),
    }, expanded=False)


def render_for_field(state: Mapping[str, Any], field_number: int) -> None:
    payload = _payload(state)
    if not payload:
        st.info("Run Settings → Run Calculation + Open Lunch once to publish the unified shadow evidence.")
        return
    _identity(payload)
    if field_number == 2:
        _field2(payload)
    elif field_number == 3:
        _field3(payload)
    elif field_number == 8:
        _field8(payload)
    elif field_number == 9:
        _field9(payload)
    else:
        st.json({
            "field2_status": {h: row.get("evidence_status") for h, row in (payload.get("field2") or {}).items()},
            "field3": {k: (payload.get("field3") or {}).get(k) for k in ("shadow_filtered_regime", "changepoint_probability", "transition_warning_state")},
            "validation": {"errors": payload.get("validation_errors"), "warnings": payload.get("validation_warnings")},
            "field9": {k: (payload.get("field9") or {}).get(k) for k in ("net_expected_action_value", "counterfactual_regret", "evidence_sufficiency")},
        }, expanded=False)

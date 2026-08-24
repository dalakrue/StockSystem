"""Read-only Lunch views for the saved research-grade shadow snapshot."""
from __future__ import annotations

from typing import Any, Mapping
import math

import pandas as pd
import streamlit as st


def _payload(state: Mapping[str, Any] | None) -> dict[str, Any]:
    value = state.get("research_grade_shadow_20260624") if isinstance(state, Mapping) else None
    return dict(value) if isinstance(value, Mapping) else {}


def _display(value: Any, digits: int = 6) -> Any:
    if value is None:
        return "INSUFFICIENT EVIDENCE"
    if isinstance(value, float):
        return round(value, digits) if math.isfinite(value) else "INSUFFICIENT EVIDENCE"
    return value


def _score_rows(payload: Mapping[str, Any], model_id: str) -> list[dict[str, Any]]:
    rows = []
    for horizon, score in (payload.get("scorecards") or {}).get(model_id, {}).items():
        if not isinstance(score, Mapping):
            continue
        rows.append({
            "Horizon": f"H{horizon}", "Matured OOS": score.get("sample_count"),
            "CRPS": score.get("crps"), "CRPS method": score.get("crps_method"),
            "MAE": score.get("mae"), "RMSE": score.get("rmse"),
            "Directional accuracy": score.get("directional_accuracy"),
            "Log score": score.get("log_score"), "Interval score": score.get("interval_score"),
            "Coverage": score.get("interval_coverage"), "Interval width": score.get("interval_width"),
            "Coverage debt": score.get("coverage_debt"), "Walk-forward folds": score.get("fold_count"),
        })
    return rows


def render_for_field(state: Mapping[str, Any], field: int) -> None:
    payload = _payload(state)
    if not payload:
        st.info("Research-grade shadow evidence is not stored for this canonical run. No evidence is fabricated.")
        return
    if payload.get("status") == "FAILED_SAFELY":
        st.warning(f"The research-grade layer failed safely: {payload.get('error')}")
        return
    st.caption(
        f"Saved research snapshot {str(payload.get('snapshot_hash') or '')[:20]} · "
        f"run {payload.get('run_id') or '—'} · completed H1 only · shadow-only"
    )

    if field == 2:
        catalog = payload.get("current_forecasts") or {}
        selectable = [m for m in ("nhits", "timemixer", "patchtst", "deepar_student_t", "regime_conditioned_ensemble", "chronos_optional") if m in catalog]
        selected = st.selectbox(
            "Shadow challenger path",
            selectable or ["nhits"],
            format_func=lambda x: x.replace("_", " ").title(),
            key="research_grade_field2_model_20260624",
        )
        forecasts = catalog.get(selected) or {}
        rows = []
        for horizon in ("1", "3", "6"):
            item = forecasts.get(horizon) or {}
            calibration = item.get("calibration") if isinstance(item.get("calibration"), Mapping) else {}
            score = (payload.get("scorecards") or {}).get(selected, {}).get(horizon, {})
            agreement = (payload.get("model_agreement") or {}).get(horizon, {})
            quantiles = item.get("quantile_prices") if isinstance(item.get("quantile_prices"), Mapping) else {}
            rows.append({
                "Horizon": f"H{horizon}", "Status": item.get("status"),
                "Mean price": item.get("mean_price"), "Median price": item.get("median_price"),
                "Q05": quantiles.get("0.05"), "Q10": quantiles.get("0.10"),
                "Q90": quantiles.get("0.90"), "Q95": quantiles.get("0.95"),
                "Calibrated lower": item.get("calibrated_lower_price", item.get("lower_price")),
                "Calibrated upper": item.get("calibrated_upper_price", item.get("upper_price")),
                "Direction probability": item.get("direction_probability"),
                "Model agreement": agreement.get("direction_agreement"),
                "CRPS": score.get("crps"), "CRPS method": score.get("crps_method"),
                "MAE": score.get("mae"), "Coverage": score.get("interval_coverage"),
                "Uncertainty": item.get("uncertainty"), "Calibration": calibration.get("status"),
                "Calibration pool": calibration.get("method"), "Data sufficiency": item.get("sample_count"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("The existing production path above remains unchanged. This selector reads saved shadow paths only and never trains a model.")

    elif field == 3:
        duration = payload.get("duration_regime") or {}
        transitions = duration.get("transition_probabilities") or {}
        cols = st.columns(5)
        cards = (
            ("Production regime", "UNCHANGED"),
            ("Shadow duration regime", duration.get("shadow_duration_adjusted_regime")),
            ("Regime age", duration.get("regime_age")),
            ("Expected duration", duration.get("expected_duration")),
            ("Remaining duration", duration.get("estimated_remaining_duration")),
        )
        for col, (label, value) in zip(cols, cards):
            col.metric(label, _display(value, 2))
        st.dataframe(pd.DataFrame([{
            "H1 transition probability": transitions.get("1"),
            "H3 transition probability": transitions.get("3"),
            "H6 transition probability": transitions.get("6"),
            "Changepoint warning": duration.get("changepoint_warning"),
            "Persistent transition declared": duration.get("shadow_transition_declared"),
            "Duration surprise": duration.get("duration_surprise"),
            "Regime reliability": duration.get("duration_adjusted_reliability"),
        }]), use_container_width=True, hide_index=True)
        confusion = payload.get("regime_confusion") or {}
        st.caption(f"Matured regime accuracy: {_display(confusion.get('accuracy'), 4)} from {confusion.get('sample_count', 0)} matured observations")
        matrix = confusion.get("matrix") or {}
        if matrix:
            st.dataframe(pd.DataFrame(matrix).T, use_container_width=True)
        else:
            st.info("A matured confusion matrix is unavailable; no current or future label was substituted.")

    elif field == 4:
        agreement = payload.get("model_agreement") or {}
        duration = payload.get("duration_regime") or {}
        explanations = payload.get("tft_explanations") or {}
        rows = []
        for h in ("1", "3", "6"):
            a = agreement.get(h) or {}
            top = (explanations.get(h) or {}).get("top_features") or []
            rows.append({
                "Horizon": f"H{h}", "Multiscale agreement": a.get("direction_agreement"),
                "Forecast-vs-regime conflict": a.get("micro_macro_conflict"),
                "Model disagreement": a.get("model_disagreement_std"),
                "Top stable causal-time features": ", ".join(str(x.get("feature")) for x in top[:5]) or "INSUFFICIENT EVIDENCE",
                "Transition risk": duration.get("transition_probabilities", {}).get(h),
                "Changepoint warning": duration.get("changepoint_warning"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("Decision evidence is concise and shadow-only; it cannot reverse or overwrite the protected production decision.")

    elif field == 5:
        duration = payload.get("duration_regime") or {}
        leaderboard = payload.get("leaderboard_25d") or []
        best = next((row for row in leaderboard if row.get("rank") == 1), None)
        evidence = {
            "run_id": payload.get("run_id"),
            "origin_candle_time": payload.get("origin_candle_time"),
            "forecast_explanation": "Saved H1/H3/H6 challenger distributions and calibrated bands; no live recalculation.",
            "regime_explanation": {
                "shadow_duration_regime": duration.get("shadow_duration_adjusted_regime"),
                "age": duration.get("regime_age"), "expected_duration": duration.get("expected_duration"),
                "transition_warning": duration.get("changepoint_warning"),
            },
            "confidence_reliability_explanation": {
                "best_validated_model": best.get("model_id") if best else "INSUFFICIENT EVIDENCE",
                "promotion_eligible_models": (payload.get("promotion_eligibility") or {}).get("eligible_models") or [],
                "automatic_promotion": False,
            },
            "limitations": payload.get("limitations") or [],
        }
        st.json(evidence, expanded=False)
        st.caption("The assistant may explain these saved values. It must say ‘insufficient evidence’ when a value is absent and must not invent calculations.")

    elif field == 6:
        history = payload.get("history") or {}
        options = {
            "Model performance by regime": "by_regime",
            "Model performance by session": "by_session",
            "Calibration history": "calibration_history",
            "Coverage history": "coverage_history",
            "Feature stability history": None,
            "Model agreement history": None,
            "Changepoint and duration history": None,
            "Drift and data-quality evidence": None,
        }
        selected = st.selectbox("Research evidence history", list(options), key="research_grade_field6_history_20260624")
        key = options[selected]
        if key:
            st.dataframe(pd.DataFrame(history.get(key) or []), use_container_width=True, hide_index=True)
        elif selected.startswith("Feature"):
            rows = []
            for h, block in (payload.get("tft_explanations") or {}).items():
                for feature in block.get("top_features") or []:
                    rows.append({"Horizon": f"H{h}", **feature, "Fold count": block.get("fold_count"), "Method": block.get("method")})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        elif selected.startswith("Model agreement"):
            st.dataframe(pd.DataFrame([{"Horizon": f"H{h}", **values} for h, values in (payload.get("model_agreement") or {}).items()]), use_container_width=True, hide_index=True)
        elif selected.startswith("Changepoint"):
            st.json(payload.get("duration_regime") or {}, expanded=False)
        else:
            st.json({"warnings": payload.get("warnings"), "data_quality": payload.get("data_quality")}, expanded=False)

    elif field == 7:
        warnings = payload.get("warnings") or {}
        performance = payload.get("performance") or {}
        cols = st.columns(4)
        cols[0].metric("Coverage debt rows", len(warnings.get("coverage_debt") or []))
        cols[1].metric("Residual drift", str((warnings.get("residual_drift") or {}).get("status") or "INSUFFICIENT EVIDENCE"))
        cols[2].metric("Compute seconds", _display(performance.get("wall_seconds"), 3))
        cols[3].metric("Peak memory MB", _display((performance.get("peak_traced_memory_bytes") or 0) / 1024 / 1024, 2))
        st.dataframe(pd.DataFrame(warnings.get("coverage_debt") or []), use_container_width=True, hide_index=True)
        st.json({
            "calibration_drift": warnings.get("calibration_drift"),
            "regime_instability": warnings.get("regime_instability"),
            "model_retirement_warning": warnings.get("model_retirement"),
            "data_quality_warning": warnings.get("data_quality"),
            "compute_and_memory_cost": warnings.get("compute_cost"),
        }, expanded=False)

    elif field == 8:
        leaderboard = payload.get("leaderboard_25d") or []
        st.markdown("#### 25-Day Integrated Research Leaderboard")
        st.dataframe(pd.DataFrame(leaderboard), use_container_width=True, hide_index=True, height=520)
        st.markdown("#### Promotion-Eligibility Report — no automatic promotion")
        st.dataframe(pd.DataFrame((payload.get("promotion_eligibility") or {}).get("models") or []), use_container_width=True, hide_index=True)
        st.caption("Ranking includes CRPS, MAE, RMSE, direction, coverage, interval width, computational cost and minimum-sample penalty. No live-profit claim is made.")


__all__ = ["render_for_field"]

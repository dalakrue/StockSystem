"""Compact renderers for the canonical reliability result.

All functions are designed for insertion into existing pages/expanders only.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
import streamlit as st

KEY = "canonical_decision_result_20260617"


def _result() -> Dict[str, Any]:
    value = st.session_state.get(KEY)
    if isinstance(value, dict) and value:
        return value
    value = st.session_state.get("last_valid_canonical_decision_result_20260617")
    return value if isinstance(value, dict) else {}


def _pct(value: Any, digits: int = 1) -> str:
    try:
        number = float(value)
        if 0 <= number <= 1:
            number *= 100
        return f"{number:.{digits}f}%"
    except Exception:
        return "N/A"


def _num(value: Any, digits: int = 5) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "N/A"


def _current_attempt_warning() -> None:
    attempt = st.session_state.get("canonical_decision_attempt_20260617")
    result = _result()
    if isinstance(attempt, dict) and attempt.get("calculation_status") == "FAILED":
        st.warning(
            "The newest calculation failed and was not published. The last valid result remains visible. "
            + str(attempt.get("failure_reason") or "Check Settings diagnostics.")
        )
    elif result:
        metadata = result.get("metadata") or {}
        signature = str(result.get("data_signature") or "-")
        st.caption(
            f"Run ID {result.get('run_id','-')} • Gen {result.get('calculation_generation','-')} • "
            f"{result.get('symbol','-')} {result.get('timeframe','-')} • Latest completed candle "
            f"{(result.get('market') or {}).get('latest_completed_candle_time','-')} • "
            f"Signature {signature[:12]} • Cache {result.get('cache_status') or metadata.get('support_cache_status','-')} • "
            f"Created {result.get('created_at','-')}"
        )


def render_lunch_canonical_panel() -> None:
    """Zero-calculation summary renderer retained under the existing API."""
    from core.compact_canonical_20260619 import get_compact_summary
    from ui.composite_summary_cards_20260619 import render_eight_cards
    summary = get_compact_summary(st.session_state)
    if not summary:
        try:
            from core.canonical_runtime_20260617 import get_canonical, shared_from_runtime
            from core.compact_canonical_20260619 import publish_compact_runtime
            canonical = get_canonical(st.session_state)
            if canonical:
                summary, _ = publish_compact_runtime(st.session_state, canonical, shared_from_runtime(st.session_state))
        except Exception:
            summary = {}
    render_eight_cards(summary, location="lunch-canonical")


def render_lunch_canonical_panel_details() -> None:
    result = _result()
    if not result:
        try:
            from core.system_wide_completion_20260618 import readiness_message
            st.info(readiness_message(st.session_state, "Full Metric"))
        except Exception:
            st.info("The synchronized decision result is unavailable. Open Settings → Errors / Fix Fast.")
        return
    _current_attempt_warning()
    final = dict(result.get("final_decision") or {})
    regime = dict(result.get("regime") or {})
    drift = dict(result.get("drift") or {})
    quality = dict(result.get("data_quality") or {})
    risk = dict(result.get("risk") or {})
    forecasts = dict(result.get("forecasts") or {})

    c = st.columns(5)
    c[0].metric("Final Decision", final.get("final_decision", "WAIT"), final.get("directional_market_view", "WAIT"))
    c[1].metric("Tradeability", final.get("tradeability_decision", "WAIT"), f"{final.get('selected_horizon',3)}h selected")
    c[2].metric("Calibrated Confidence", _pct(final.get("calibrated_confidence")), "OOS when available")
    c[3].metric("Actionability", _pct(final.get("actionability_probability")), "approve or force WAIT")
    c[4].metric("Expected Value", _num(final.get("expected_value")), "after estimated costs")
    c2 = st.columns(5)
    c2[0].metric("Current Regime", regime.get("major_regime", "UNKNOWN"), regime.get("transition_warning", "NONE"))
    c2[1].metric("3h Transition", _pct(regime.get("transition_probability_3h")), "regime lifecycle")
    c2[2].metric("Drift", drift.get("status", "STABLE"), _num(drift.get("score"), 1))
    c2[3].metric("Uncertainty", _pct(final.get("uncertainty_pct")), risk.get("risk_level", "HIGH"))
    c2[4].metric("Error Estimate", _pct(final.get("error_estimate_pct")), quality.get("status", "UNKNOWN"))

    pattern = dict(result.get("pattern_memory") or {})
    transition = dict(result.get("transition_risk") or {})
    actionability = dict(result.get("actionability") or {})
    support_row = st.columns(5)
    support_row[0].metric("Alpha", _num(result.get("alpha", regime.get("alpha")), 3))
    support_row[1].metric("Delta", _num(result.get("delta", regime.get("delta")), 3))
    support_row[2].metric("Pattern", pattern.get("pattern_confirmation", final.get("pattern_confirmation", "NEUTRAL")), _pct(pattern.get("pattern_confidence", pattern.get("confidence", 0))))
    support_row[3].metric("Transition Risk", transition.get("status", "WATCH"), _num(transition.get("value"), 2))
    support_row[4].metric("Actionability Label", actionability.get("current_label", final.get("actionability_status", "WATCH")), str(actionability.get("status", "")))

    candidates = result.get("top_two_daily_candidates") or result.get("opportunity_candidates") or []
    if isinstance(candidates, list) and candidates:
        candidate_frame = pd.DataFrame(candidates).head(2)
        candidate_columns = [column for column in (
            "Candidate Timestamp", "Direction", "Current Status", "Master Score", "Entry Score",
            "Hold Score", "TP Score", "Exit Risk", "Regime", "Alpha", "Delta",
            "Pattern Confirmation", "Transition Risk", "Actionability Label", "Expected Value",
            "Reliability", "Reason Accepted or Blocked", "Validity Horizon", "Final Candidate Decision",
        ) if column in candidate_frame.columns]
        st.dataframe(candidate_frame[candidate_columns] if candidate_columns else candidate_frame, use_container_width=True, hide_index=True, height=150)

    with st.expander("Open / Close — Why the final policy returned this result", expanded=False):
        st.write(f"**Main reason:** {final.get('main_reason','No reason available')}")
        support = final.get("supporting_reasons") or []
        block = final.get("blocking_reasons") or []
        rows: List[Dict[str, str]] = []
        rows.extend({"Type": "Supporting", "Reason": str(x)} for x in support)
        rows.extend({"Type": "Blocking", "Reason": str(x)} for x in block)
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No extra reasons were recorded.")
        st.caption(str((result.get("metadata") or {}).get("expected_value_note", "Expected value is an estimate, not guaranteed profit.")))

    with st.expander("Open / Close — 1h / 2h / 3h / 6h reconciliation", expanded=True):
        rows = []
        for key, item in (forecasts.get("horizons") or {}).items():
            item = dict(item or {})
            direction = item.get("direction", "WAIT")
            directional_p = item.get(f"{str(direction).lower()}_probability_calibrated")
            rows.append({
                "Horizon": key,
                "Direction": direction,
                "Trade Decision": item.get("decision", "WAIT"),
                "Calibrated Probability": _pct(directional_p),
                "Threshold": _pct(item.get("threshold")),
                "Point Forecast": _num(item.get("point_forecast")),
                "Lower": _num(item.get("lower_bound")),
                "Upper": _num(item.get("upper_bound")),
                "Expected Value": _num(item.get("expected_value")),
                "Actionability": _pct(item.get("actionability_probability")),
                "Priority": _num(item.get("priority_score"), 1),
                "Probability Source": item.get("probability_source", "UNAVAILABLE"),
            })
        st.caption(f"{forecasts.get('reconciliation_label','NO DATA')}: {forecasts.get('reconciliation_reason','')}")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=260)


def render_powerbi_canonical_details() -> None:
    result = _result()
    if not result:
        try:
            from core.system_wide_completion_20260618 import readiness_message
            st.info(readiness_message(st.session_state, "PowerBI"))
        except Exception:
            st.info("The published multi-horizon bounds are unavailable. Open Settings → Errors / Fix Fast.")
        return
    forecasts = dict(result.get("forecasts") or {})
    regime = dict(result.get("regime") or {})
    with st.expander("Open / Close — Validated Multi-Horizon Projection Details", expanded=True):
        rows = []
        for key, item in (forecasts.get("horizons") or {}).items():
            item = dict(item or {})
            rows.append({
                "Horizon": key,
                "Decision": item.get("decision", "WAIT"),
                "Direction": item.get("direction", "WAIT"),
                "Point": item.get("point_forecast"),
                "Lower Bound": item.get("lower_bound"),
                "Upper Bound": item.get("upper_bound"),
                "Target Coverage": item.get("target_coverage"),
                "Actual Coverage": item.get("actual_coverage"),
                "Coverage Error": item.get("coverage_error"),
                "Residual Samples": item.get("residual_sample_count", 0),
                "Expected Value": item.get("expected_value"),
                "Threshold": item.get("threshold"),
                "Actionability": item.get("actionability_probability"),
            })
        projection_table = pd.DataFrame(rows)
        st.dataframe(projection_table, use_container_width=True, hide_index=True, height=260)
        # A compact bounds chart is rendered inside the existing Power BI field.
        # It uses one row per horizon, so point/lower/upper arrays can never drift
        # out of alignment or produce a length-mismatch chart error.
        if not projection_table.empty:
            chart = projection_table[["Horizon", "Point", "Lower Bound", "Upper Bound"]].copy()
            for column in ("Point", "Lower Bound", "Upper Bound"):
                chart[column] = pd.to_numeric(chart[column], errors="coerce")
            chart = chart.dropna(subset=["Point", "Lower Bound", "Upper Bound"]).set_index("Horizon")
            if not chart.empty:
                st.line_chart(chart, use_container_width=True)
        m = st.columns(3)
        m[0].metric("Alpha", _num(regime.get("alpha"), 3))
        m[1].metric("Delta", _num(regime.get("delta"), 3))
        m[2].metric("Delta Acceleration", _num(regime.get("delta_acceleration"), 3))
        st.caption("Bands are horizon-specific. They widen when rolling out-of-sample coverage is below target or drift increases.")


def render_regime_lifecycle_panel() -> None:
    result = _result()
    if not result:
        try:
            from core.system_wide_completion_20260618 import readiness_message
            st.info(readiness_message(st.session_state, "Regime History"))
        except Exception:
            st.info("The published regime lifecycle is unavailable. Open Settings → Errors / Fix Fast.")
        return
    r = dict(result.get("regime") or {})
    with st.expander("Open / Close — Regime Lifecycle + Transition Logic", expanded=True):
        c = st.columns(4)
        c[0].metric("Regime Age", f"{float(r.get('age_hours',0) or 0):.1f} h", f"{float(r.get('age_hours',0) or 0)/24:.2f} days")
        c[1].metric("Expected Duration", f"{float(r.get('expected_duration_hours',0) or 0):.1f} h" if r.get("expected_duration_hours") is not None else "N/A")
        c[2].metric("Remaining", f"{float(r.get('remaining_duration_hours',0) or 0):.1f} h" if r.get("remaining_duration_hours") is not None else "N/A")
        c[3].metric("Persistence", _pct(r.get("persistence_score")), r.get("transition_warning", "NONE"))
        rows = [
            {"Window": "1 day lower", "Regime": r.get("lower_standard_regime"), "Score /10": round(float(r.get("regime_score",0) or 0)/10,2)},
            {"Window": "5 day middle", "Regime": r.get("middle_standard_regime"), "Score /10": round(float(r.get("regime_score",0) or 0)/10,2)},
            {"Window": "25 day higher", "Regime": r.get("higher_standard_regime"), "Score /10": round(float(r.get("regime_score",0) or 0)/10,2)},
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        t = st.columns(3)
        t[0].metric("Transition 1h", _pct(r.get("transition_probability_1h")))
        t[1].metric("Transition 3h", _pct(r.get("transition_probability_3h")))
        t[2].metric("Transition 6h", _pct(r.get("transition_probability_6h")))
        ad = st.columns(3)
        ad[0].metric("Alpha", _num(r.get("alpha"), 3))
        ad[1].metric("Delta", _num(r.get("delta"), 3))
        ad[2].metric("Delta Acceleration", _num(r.get("delta_acceleration"), 3))
        possible = r.get("possible_next_regimes") or {}
        if possible:
            st.dataframe(pd.DataFrame([{"Possible Next Regime": k, "Weight": v} for k,v in possible.items()]), use_container_width=True, hide_index=True)
        if r.get("conflict_warning") and r.get("conflict_warning") != "NONE":
            st.warning(str(r.get("conflict_warning")))


def render_validation_calibration_panel() -> None:
    result = _result()
    if not result:
        st.info("No canonical validation result exists yet.")
        return
    rel = dict(result.get("reliability") or {})
    meta = dict(result.get("metadata") or {})
    with st.expander("Open / Close — Walk-Forward, Calibration, Threshold and Cost Results", expanded=True):
        c = st.columns(4)
        c[0].metric("Validation", rel.get("status", "INSUFFICIENT SAMPLE"), f"{rel.get('sample_count',0)} samples")
        c[1].metric("Direction Accuracy", _pct(rel.get("direction_accuracy")))
        c[2].metric("Balanced Accuracy", _pct(rel.get("balanced_accuracy")))
        c[3].metric("Interval Coverage", _pct(rel.get("interval_coverage")))
        validation = rel.get("validation_by_horizon") or {}
        rows = []
        for h, item in validation.items():
            item = dict(item or {})
            rows.append({"Horizon": h, **{k:v for k,v in item.items() if k != "class_metrics"}})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=280)
        cal = rel.get("calibration_by_horizon") or {}
        cal_rows = [{"Horizon": h, **dict(v or {})} for h,v in cal.items()]
        st.dataframe(pd.DataFrame(cal_rows), use_container_width=True, hide_index=True, height=220)
        st.caption(f"Threshold version: {meta.get('threshold_version','fallback-v1')}. Insufficient samples remain explicitly marked; no accuracy is fabricated.")


def render_settings_product_status() -> None:
    result = _result()
    attempt = st.session_state.get("canonical_decision_attempt_20260617") or {}
    status = st.session_state.get("settings_run_status_20260617") or {}
    with st.expander("Open / Close — Decision Product Diagnostics", expanded=True):
        if result:
            q = result.get("data_quality") or {}
            d = result.get("drift") or {}
            rel = result.get("reliability") or {}
            c = st.columns(5)
            c[0].metric("Data Quality", q.get("status", "UNKNOWN"), _num(q.get("score"),1))
            c[1].metric("Calculation", result.get("calculation_status", "UNKNOWN"))
            c[2].metric("Ledger", ((result.get("metadata") or {}).get("ledger_status") or {}).get("status", "UNKNOWN"))
            c[3].metric("Calibration", rel.get("status", "INSUFFICIENT SAMPLE"), f"{rel.get('sample_count',0)} samples")
            c[4].metric("Drift", d.get("status", "STABLE"), _num(d.get("score"),1))
            st.caption(f"Latest completed candle: {(result.get('market') or {}).get('latest_completed_candle_time','-')} • Run ID {result.get('run_id','-')}")
        else:
            st.info("No completed canonical calculation is available.")
        if attempt.get("calculation_status") == "FAILED":
            st.error("Latest attempt failed: " + str(attempt.get("failure_reason") or "Unknown failure"))
        errors = status.get("errors") if isinstance(status, dict) else []
        if errors:
            st.dataframe(pd.DataFrame({"Calculation Message": list(errors)}), use_container_width=True, hide_index=True)

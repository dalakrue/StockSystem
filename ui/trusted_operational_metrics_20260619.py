"""Trusted operational Lunch metrics from the published canonical generation.

This module is display-only. It never recalculates, changes, or reverses the
protected Full Metric direction.
"""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Optional

import streamlit as st

from core.canonical_runtime_20260617 import get_canonical
from core.compact_canonical_20260619 import get_compact_summary
from core.trust_config_20260619 import TRUST_CONFIG


def _map(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _num(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        out = float(value)
        return out if out == out else default
    except Exception:
        return default


def _pct(value: Any) -> Optional[float]:
    out = _num(value)
    if out is None:
        return None
    if 0.0 <= out <= 1.0:
        out *= 100.0
    return max(0.0, min(100.0, out))


def _fmt_pct(value: Any, digits: int = 1) -> str:
    out = _pct(value)
    return "—" if out is None else f"{out:.{digits}f}%"


def _fmt_pips(value: Any, *, already_pips: bool = False) -> str:
    out = _num(value)
    if out is None:
        return "—"
    pips = out if already_pips else out / float(TRUST_CONFIG["pip_size"])
    return f"{pips:+.1f} pips"


def _direction_probability(forecast: Mapping[str, Any], direction: str, calibrated: bool) -> Optional[float]:
    key = f"{direction.lower()}_probability_{'calibrated' if calibrated else 'raw'}"
    return _num(forecast.get(key))


def _selected_forecast(canonical: Mapping[str, Any]) -> tuple[int, Mapping[str, Any]]:
    final = _map(canonical.get("final_decision"))
    forecasts = _map(canonical.get("forecasts"))
    horizon = int(_num(final.get("selected_horizon"), _num(forecasts.get("selected_horizon"), 3)) or 3)
    return horizon, _map(_map(forecasts.get("horizons")).get(f"{horizon}h"))


def _regime_age(canonical: Mapping[str, Any]) -> str:
    regime = _map(canonical.get("regime"))
    for key in ("regime_age_hours", "age_hours", "current_regime_age_hours", "regime_age"):
        value = _num(regime.get(key))
        if value is not None:
            return f"{value:.1f}h"
    return "not available"


def _transition(canonical: Mapping[str, Any], summary: Mapping[str, Any]) -> tuple[float, str]:
    regime = _map(canonical.get("regime"))
    research = _map(canonical.get("research_calibration"))
    cp = _map(research.get("bayesian_changepoint"))
    transition = _map(canonical.get("transition_risk"))
    value = _pct(
        cp.get("transition_risk_0_100")
        or regime.get("transition_probability")
        or transition.get("value")
        or _map(summary.get("regime")).get("transition_risk")
    ) or 0.0
    label = "STABLE" if value < 30 else "MODERATE" if value < 55 else "HIGH" if value < 80 else "CRITICAL"
    return value, label


def _identity_caption(canonical: Mapping[str, Any], trust: Mapping[str, Any]) -> str:
    calc_id = str(canonical.get("calculation_id") or canonical.get("canonical_calculation_id") or canonical.get("run_id") or "—")
    as_of = str(canonical.get("data_timestamp") or canonical.get("latest_completed_candle_time") or "—")
    settled = int(_num(trust.get("settled_sample_count"), 0) or 0)
    status = str(trust.get("trust_classification") or "INSUFFICIENT")
    quality = str(canonical.get("data_quality_status") or _map(canonical.get("data_quality")).get("status") or "UNKNOWN")
    return f"As of {as_of} · ID {calc_id[:26]} · n={settled} settled · {status} · data {quality}"


def _safe_metric(column: Any, label: str, value: str, delta: Optional[str], caption: str) -> None:
    column.metric(label, value, delta=delta)
    column.caption(caption)


def render_trusted_operational_metrics(*, state: MutableMapping[str, Any] | None = None) -> None:
    state = state if state is not None else st.session_state
    canonical = get_canonical(state)
    summary = get_compact_summary(state)
    if not canonical:
        st.info("Run Calculation + Open Lunch to publish one synchronized canonical result.")
        return

    final = _map(canonical.get("final_decision"))
    trust = _map(canonical.get("trust_validation")) or _map(state.get("settled_trust_summary_20260619"))
    horizon, forecast = _selected_forecast(canonical)
    full_metric = str(canonical.get("full_metric_direction") or _map(canonical.get("metadata")).get("full_metric_direction") or final.get("directional_market_view") or "WAIT").upper()
    decision = str(final.get("final_decision") or "WAIT").upper()
    tradeability = str(final.get("tradeability_decision") or "WAIT").upper()
    raw = _direction_probability(forecast, full_metric, calibrated=False)
    calibrated = _direction_probability(forecast, full_metric, calibrated=True)
    if calibrated is None:
        calibrated = _num(final.get("calibrated_confidence"))
    calibrated_available = calibrated is not None and int(_num(trust.get("settled_sample_count"), 0) or 0) >= int(TRUST_CONFIG["minimum_calibration_samples"])
    display_conf = calibrated if calibrated_available else raw
    confidence_value = _fmt_pct(display_conf)
    confidence_delta = None
    if raw is not None and calibrated_available:
        confidence_delta = f"Raw {_fmt_pct(raw)} → calibrated {_fmt_pct(calibrated)}"
    elif not calibrated_available:
        confidence_delta = "Calibration developing — insufficient settled samples"

    ev = _num(final.get("expected_value"), _num(forecast.get("expected_value")))
    expected_gain = _num(forecast.get("expected_gain"))
    expected_loss = _num(forecast.get("expected_loss"))
    mfe = _num(trust.get("expected_mfe_pips"))
    mae = _num(trust.get("expected_mae_pips"))
    if mfe is None and expected_gain is not None:
        mfe = expected_gain / float(TRUST_CONFIG["pip_size"])
    if mae is None and expected_loss is not None:
        mae = abs(expected_loss) / float(TRUST_CONFIG["pip_size"])
    reward_adverse = (mfe / mae) if mfe is not None and mae not in (None, 0) else None
    transition_pct, transition_label = _transition(canonical, summary)
    interval = _map(trust.get("interval"))
    coverage = _pct(interval.get("coverage"))
    width = _num(interval.get("mean_width_pips"))
    interval_n = int(_num(interval.get("settled_residual_sample_count"), 0) or 0)
    expiry = str(final.get("decision_expiry_time") or canonical.get("expires_at") or "—")
    caption = _identity_caption(canonical, trust)

    st.markdown("### Lunch — synchronized operational decision")
    st.caption("Full Metric History is the protected direction authority; all other modules only confirm, rank, calibrate, delay, or block it.")
    st.markdown(
        """<style>
        [data-testid="stMetric"]{min-height:118px;padding:.72rem;border:1px solid rgba(128,128,128,.20);border-radius:14px;}
        [data-testid="stMetricLabel"]{font-size:.82rem;}
        [data-testid="stMetricValue"]{font-size:1.42rem;}
        @media (max-width: 430px){[data-testid="column"]{min-width:100%!important;flex:1 1 100%!important;}[data-testid="stMetric"]{min-height:105px;}}
        </style>""",
        unsafe_allow_html=True,
    )

    row1 = st.columns(3)
    _safe_metric(row1[0], "Decision", decision, f"Full Metric {full_metric} · tradeability {tradeability}", caption)
    _safe_metric(row1[1], "Calibrated confidence", confidence_value, confidence_delta, caption)
    _safe_metric(row1[2], "Expected value after costs", _fmt_pips(ev), f"H+{horizon} · expiry {expiry}", caption)

    row2 = st.columns(3)
    interval_value = "—" if coverage is None else f"{coverage:.1f}% coverage"
    interval_delta = f"{width:.1f} pips width · H+{horizon} · n={interval_n}" if width is not None else f"H+{horizon} · n={interval_n}"
    _safe_metric(row2[0], "Prediction interval quality", interval_value, interval_delta, caption)
    _safe_metric(row2[1], "Regime transition risk", transition_label, f"{transition_pct:.1f}% · regime age {_regime_age(canonical)}", caption)
    movement_value = f"+{mfe:.1f} / -{mae:.1f} pips" if mfe is not None and mae is not None else "—"
    movement_delta = f"Reward/adverse {reward_adverse:.2f}×" if reward_adverse is not None else "Insufficient settled excursion history"
    _safe_metric(row2[2], "Expected MFE versus MAE", movement_value, movement_delta, caption)

    research_risk = _map(canonical.get("research_risk_stack"))
    research_summary = _map(research_risk.get("current_summary"))
    selective = _map(research_risk.get("selective_prediction"))
    evt = _map(research_risk.get("evt_tail"))
    risk_multiplier = _map(research_risk.get("risk_multiplier"))
    required_threshold = _num(final.get("required_confidence_threshold"), _num(research_summary.get("required_confidence_threshold"), 90.0)) or 90.0
    selective_pass = bool(final.get("selective_prediction_pass", research_summary.get("selective_prediction_pass", False)))
    tp_first = _num(final.get("tp_first_probability"), _num(research_summary.get("tp_first_probability")))
    sl_first = _num(final.get("sl_first_probability"), _num(research_summary.get("sl_first_probability")))
    robust_ev = _num(final.get("robust_expected_value"), _num(research_summary.get("robust_expected_value")))
    extreme_block = bool(final.get("extreme_risk_warning", research_summary.get("extreme_risk_block", False)))
    multiplier = _num(final.get("display_risk_multiplier"), _num(research_summary.get("display_risk_multiplier"), 0.0)) or 0.0
    less_risky = str(final.get("less_risky_decision") or final.get("final_decision") or "WAIT").upper()
    research_reason = str(final.get("research_risk_reason") or selective.get("abstention_reason") or "Research risk stack is developing")

    st.markdown("#### Research-calibrated risk note")
    research_row1 = st.columns(4)
    _safe_metric(research_row1[0], "Less-risky decision", less_risky, f"Canonical direction remains {full_metric}", caption)
    _safe_metric(research_row1[1], "Required confidence", f"{required_threshold:.1f}%", "Selective risk–coverage threshold", caption)
    _safe_metric(research_row1[2], "Selective prediction", "PASS" if selective_pass else "FAIL / WAIT", str(selective.get("selected_threshold_group") or "global fallback"), caption)
    _safe_metric(research_row1[3], f"H+{horizon} TP-first / SL-first", f"{_fmt_pct(tp_first)} / {_fmt_pct(sl_first)}", "Censored rows are not counted as losses", caption)
    research_row2 = st.columns(4)
    _safe_metric(research_row2[0], "Robust expected value", _fmt_pips(robust_ev, already_pips=True), "After ambiguity, cost, and safety buffer", caption)
    _safe_metric(research_row2[1], "Extreme-risk warning", "BLOCK" if extreme_block else "CLEAR", f"EVT n={int(_num(evt.get('evt_exceedance_count'), 0) or 0)}", caption)
    _safe_metric(research_row2[2], "Risk multiplier", f"{multiplier:.2f}×", str(risk_multiplier.get("position_risk_warning") or "Informational only · no leverage"), caption)
    _safe_metric(research_row2[3], "Event cluster", str(_map(research_risk.get("event_intensity")).get("event_cluster_level") or "LOW"), research_reason[:120], caption)

    blockers = list(final.get("blocking_reasons") or [])
    soft = list(_map(canonical.get("metadata")).get("soft_penalties") or [])
    main_reason = str(final.get("main_reason") or "No current reason available")
    strongest = str(blockers[0]) if blockers else "No hard blocker"
    regime = _map(canonical.get("regime"))
    current_regime = str(regime.get("major_regime") or regime.get("h1_regime") or canonical.get("current_major_regime") or "UNKNOWN")
    nlp = _map(summary.get("nlp"))
    quick_tp = forecast.get("selected_tp") or canonical.get("selected_tp") or "dynamic from current risk plan"
    quick_sl = forecast.get("selected_sl") or canonical.get("selected_sl") or "dynamic from current risk plan"
    details = st.columns(2)
    details[0].markdown(
        f"**Main reason:** {main_reason}  \n"
        f"**Strongest blocker:** {strongest}  \n"
        f"**Current H1 regime:** {current_regime}  \n"
        f"**Decision expiry:** {expiry}  \n"
        f"**Latest completed H1:** {canonical.get('latest_completed_candle_time', '—')}"
    )
    details[1].markdown(
        f"**Latest NLP rank-1 event:** {nlp.get('highest_ranked_news', 'No relevant news')}  \n"
        f"**Event time / impact:** {nlp.get('news_time', '—')} / {nlp.get('event_impact', 'N/A')}  \n"
        f"**Less-risky decision:** {final.get('less_risky_decision', 'WAIT')}  \n"
        f"**Quick TP / SL:** {quick_tp} / {quick_sl}  \n"
        f"**Soft evidence:** {', '.join(map(str, soft[:4])) if soft else 'none'}"
    )


__all__ = ["render_trusted_operational_metrics"]

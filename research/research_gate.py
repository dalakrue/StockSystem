"""Field 7 shadow research orchestrator.

It validates the protected canonical decision and never writes back to it.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from core.canonical.snapshot import CanonicalRunSnapshot
from core.contracts.research_contract import ResearchEvaluation
from research import adaptive_conformal, bias_correction, changepoint, decision_stability
from research import event_embargo, forecastability, horizon_gate, model_confidence_set
from research import overfitting_control, regime_age, robust_expected_value
from research import action_expected_value, entry_delay, mfe_mae, session_performance
from research._utils import clamp, deep_find, number, prediction_for_horizon

HORIZONS = (1, 2, 3, 6)


def _history_records(snapshot: CanonicalRunSnapshot) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for value in snapshot.histories.values():
        if isinstance(value, list):
            records.extend(dict(row) for row in value if isinstance(row, Mapping))
    return records


def evaluate(snapshot: CanonicalRunSnapshot, *, settled_outcomes: Iterable[Mapping[str, Any]] = (), prior_research: Iterable[Mapping[str, Any]] = ()) -> ResearchEvaluation:
    outcomes = list(settled_outcomes)
    history = _history_records(snapshot)
    prior = list(prior_research)
    sample_size = max(len(outcomes), len(history), len(prior))
    metrics = dict(snapshot.metrics)
    intervals = metrics.get("prediction_intervals") if isinstance(metrics.get("prediction_intervals"), Mapping) else {}
    model_agreement = clamp(deep_find({"p": snapshot.predictions, "m": metrics}, ("forecast_agreement", "path_agreement", "model_agreement", "agreement")), default=snapshot.reliability)
    data_quality = clamp(metrics.get("data_quality_score"), default=max(0.0, 100.0 - snapshot.uncertainty))
    cp = changepoint.evaluate(metrics, regime_age=snapshot.regime_age, uncertainty=snapshot.uncertainty)
    stability = decision_stability.evaluate(history or prior, snapshot.decision)
    embargo = event_embargo.evaluate(metrics.get("sentiment") if isinstance(metrics.get("sentiment"), Mapping) else {})
    models = model_confidence_set.evaluate(metrics, sample_size=sample_size)
    eligible = [row["model_name"] for row in models if row["eligibility"] == "ELIGIBLE"]
    overfit = overfitting_control.evaluate(
        sample_size=sample_size,
        models_tested=int(number(deep_find(metrics, ("models_tested",)), 7) or 7),
        thresholds_tested=int(number(deep_find(metrics, ("thresholds_tested",)), 4) or 4),
        feature_combinations=int(number(deep_find(metrics, ("feature_combinations",)), 1) or 1),
        horizons_tested=4,
        tp_sl_alternatives=int(number(deep_find(metrics, ("tp_sl_alternatives",)), 0) or 0),
        in_sample_score=number(deep_find(metrics, ("in_sample_score", "training_score")), None),
        out_of_sample_score=number(deep_find(metrics, ("out_of_sample_score", "validation_score")), None),
    )
    regime = regime_age.evaluate(snapshot.regime_age, reliability=snapshot.regime_reliability, changepoint_probability=cp["change_probability"])

    horizon_rows: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        horizon_outcomes = [row for row in outcomes if int(number(row.get("horizon_hours"), horizon) or horizon) == horizon]
        raw = prediction_for_horizon(snapshot.predictions, horizon)
        bias = bias_correction.evaluate(raw, horizon_outcomes)
        conformal = adaptive_conformal.evaluate(intervals, horizon, sample_size=len(horizon_outcomes))
        forecast = forecastability.evaluate(
            reliability=snapshot.reliability,
            uncertainty=snapshot.uncertainty,
            model_agreement=model_agreement,
            sample_size=len(horizon_outcomes),
            horizon=horizon,
        )
        tail_penalty = max(0.0, cp["change_probability"] - 50.0) * 0.08
        ev = robust_expected_value.evaluate(
            current_price=snapshot.current_price,
            target_price=bias["corrected_prediction"],
            decision=snapshot.decision,
            uncertainty=snapshot.uncertainty,
            reliability=snapshot.reliability,
            tail_risk_penalty_pips=tail_penalty,
        )
        gate = horizon_gate.evaluate(
            forecastability=float(forecast["score"]),
            coverage_status=str(conformal["status"]),
            similar_history_count=sample_size,
            regime_stability=max(0.0, 100.0 - cp["change_probability"]),
            error_risk=min(100.0, snapshot.error_rate + cp["change_probability"] * 0.4),
            robust_ev=ev["robust_ev"],
            model_agreement=model_agreement,
            data_quality=data_quality,
            event_multiplier=float(embargo["trust_multiplier"]),
            safe_horizon_hours=int(cp["safe_horizon_hours"]),
            horizon=horizon,
        )
        horizon_rows.append({
            "horizon_hours": horizon,
            "gate_status": gate["status"],
            "gate_reason": gate["reason"],
            "forecastability": forecast["score"],
            "coverage": conformal.get("actual_coverage"),
            "coverage_status": conformal["status"],
            "raw_prediction": raw,
            "corrected_prediction": bias["corrected_prediction"],
            "forecast_bias": bias["adaptive_bias"],
            "nominal_ev": ev["nominal_ev"],
            "robust_ev": ev["robust_ev"],
            "tail_risk": "HIGH" if cp["change_probability"] >= 70 else "WATCH" if cp["change_probability"] >= 45 else "ACCEPTABLE",
            "model_agreement": model_agreement,
            "sample_size": len(horizon_outcomes),
            "conformal": conformal,
            "expected_value": ev,
            "forecastability_status": forecast["status"],
        })

    approved = [f"{row['horizon_hours']}H" for row in horizon_rows if row["gate_status"] in {"ACCEPT", "ACCEPT WITH REDUCED RISK"}]
    abstained = [f"{row['horizon_hours']}H" for row in horizon_rows if row["gate_status"] == "ABSTAIN"]
    waits = [row for row in horizon_rows if row["gate_status"] == "WAIT"]
    robust_values = [float(row["robust_ev"]) for row in horizon_rows if row["robust_ev"] is not None]
    nominal_values = [float(row["nominal_ev"]) for row in horizon_rows if row["nominal_ev"] is not None]
    trust = 0.24 * snapshot.reliability + 0.18 * snapshot.regime_reliability + 0.16 * model_agreement + 0.16 * float(stability["score"]) + 0.14 * (100.0 - cp["change_probability"]) + 0.12 * data_quality
    trust *= float(embargo["trust_multiplier"])
    if sample_size < 25:
        trust = min(trust, 49.0)
    trust = clamp(trust)
    removed_models = [row for row in models if row["eligibility"] == "REMOVED FROM CURRENT SET"]
    accepted_normally = any(row["gate_status"] == "ACCEPT" for row in horizon_rows)
    approved_hours = [int(label.rstrip("H")) for label in approved]
    best = max(horizon_rows, key=lambda row: (row["robust_ev"] if row["robust_ev"] is not None else -1e9))
    if sample_size < 10:
        status = "INSUFFICIENT EVIDENCE"
    elif cp["status"] in {"TRANSITION", "HIGH RISK"}:
        status = "REGIME TRANSITION"
    elif not eligible and removed_models and sample_size >= 25:
        status = "MODEL SHIFT"
    elif not robust_values:
        status = "INSUFFICIENT EVIDENCE"
    elif max(robust_values) <= 0:
        status = "COST-DOMINATED"
    elif best["tail_risk"] == "HIGH" and not accepted_normally:
        status = "TAIL-RISK DOMINATED"
    elif approved and abstained and approved_hours and max(approved_hours) <= 3:
        status = "ABSTAIN FOR LONG HORIZONS"
    elif approved and accepted_normally:
        status = "TRADEABLE — NORMAL RISK" if trust >= 70 and embargo["state"] == "NORMAL" else "TRADEABLE — REDUCED RISK"
    elif approved:
        status = "TRADEABLE — REDUCED RISK"
    elif waits:
        status = "WAIT FOR CONFIRMATION"
    else:
        status = "NO TRADE"
    risk_multiplier = 0.0 if status in {"NO TRADE", "COST-DOMINATED", "INSUFFICIENT EVIDENCE", "TAIL-RISK DOMINATED", "MODEL SHIFT"} else round(max(0.25, min(1.0, trust / 100.0 * float(embargo["trust_multiplier"]))), 3)
    approved_action = snapshot.decision if approved else "WAIT" if waits else "SKIP"
    summary = {
        "run_id": snapshot.run_id,
        "broker_candle_time": snapshot.broker_candle_time.isoformat(),
        "symbol": snapshot.symbol,
        "timeframe": snapshot.timeframe,
        "session": str(deep_find(metrics, ("session", "market_session")) or "UNAVAILABLE"),
        "canonical_decision": snapshot.decision,
        "research_approved_action": approved_action,
        "approved_horizons": approved,
        "abstained_horizons": abstained,
        "change_probability": cp["change_probability"],
        "regime_age": snapshot.regime_age,
        "forecastability_1h": next(row["forecastability"] for row in horizon_rows if row["horizon_hours"] == 1),
        "forecastability_3h": next(row["forecastability"] for row in horizon_rows if row["horizon_hours"] == 3),
        "forecastability_6h": next(row["forecastability"] for row in horizon_rows if row["horizon_hours"] == 6),
        "eligible_model_set": eligible,
        "model_confidence_set": "ELIGIBLE" if eligible else "INSUFFICIENT EVIDENCE" if sample_size < 25 else "SUPPORT ONLY",
        "forecast_bias_1h": next(row["forecast_bias"] for row in horizon_rows if row["horizon_hours"] == 1),
        "forecast_bias_3h": next(row["forecast_bias"] for row in horizon_rows if row["horizon_hours"] == 3),
        "coverage_1h": next(row["coverage"] for row in horizon_rows if row["horizon_hours"] == 1),
        "coverage_3h": next(row["coverage"] for row in horizon_rows if row["horizon_hours"] == 3),
        "raw_target": best["raw_prediction"],
        "bias_corrected_target": best["corrected_prediction"],
        "conformal_coverage": best["coverage"],
        "nominal_ev": max(nominal_values) if nominal_values else None,
        "robust_ev": max(robust_values) if robust_values else None,
        "tail_risk": best["tail_risk"],
        "decision_stability": stability["status"],
        "decision_stability_score": stability["score"],
        "regime_remaining_edge": regime["remaining_edge"],
        "event_state": embargo["state"],
        "overfitting_risk": overfit["overfitting_risk"],
        "research_trust_score": round(trust, 3),
        "risk_multiplier": risk_multiplier,
        "research_status": status,
        "structural_stability": cp["status"],
        "settled_outcome": None,
        "realized_pips": None,
        "sample_size": sample_size,
        "shadow_only": True,
        "snapshot_hash": snapshot.source_snapshot_hash,
    }
    best_target = best["corrected_prediction"]
    action_matrix = action_expected_value.evaluate(
        current_price=snapshot.current_price, target_price=best_target,
        uncertainty=snapshot.uncertainty, reliability=snapshot.reliability,
        tail_risk_penalty_pips=max(0.0, cp["change_probability"] - 50.0) * 0.08,
    )
    diagnostics = {
        "changepoint": cp, "decision_stability": stability, "event_embargo": embargo,
        "regime_age": regime, "overfitting": overfit, "action_expected_value": action_matrix,
        "session_performance": session_performance.evaluate(outcomes),
        "mfe_mae": [mfe_mae.evaluate(outcomes, horizon) for horizon in HORIZONS],
        "entry_delay": entry_delay.evaluate(outcomes),
    }
    return ResearchEvaluation(summary=summary, horizons=tuple(horizon_rows), models=tuple(models), diagnostics=diagnostics)

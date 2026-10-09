"""Logic Safety Guard + Hidden Danger Engine.

This package is an additive safety wrapper around existing outputs. It does not
replace any prediction, regime, KNN, greedy, PowerBI, NLP, or priority engine.
"""
from __future__ import annotations
from typing import Any, Dict
from ._shared import flatten_metrics, first_dataframe, current_values
from . import data_quality_guard, prediction_drift_monitor, signal_stability_memory, conflict_matrix, regime_change_warning, confidence_calibration, logic_health_score, hidden_danger_detector, no_trade_guard, lookahead_bias_guard, decision_reason_chain, shadow_backtest, long_term_logic_audit


def run_full_safety_check(session_state: Any) -> Dict[str, Any]:
    metrics_flat = flatten_metrics(session_state)
    values = current_values(metrics_flat)
    df, df_source = first_dataframe(session_state)
    data_quality = data_quality_guard.check(df)
    drift = prediction_drift_monitor.monitor(df, metrics_flat)
    signal = signal_stability_memory.calculate(df, metrics_flat)
    regime = regime_change_warning.analyze(metrics_flat)
    conflicts = conflict_matrix.build(metrics_flat, drift=drift, signal=signal)
    health = logic_health_score.calculate(metrics_flat, drift=drift, data_quality=data_quality, signal=signal, conflicts=conflicts)
    danger = hidden_danger_detector.detect(metrics_flat, drift=drift, data_quality=data_quality, signal=signal, conflicts=conflicts, regime=regime)
    guard = no_trade_guard.evaluate(metrics_flat, health=health, danger=danger, drift=drift, data_quality=data_quality, signal=signal, conflicts=conflicts)
    calibration = confidence_calibration.calibrate(metrics_flat, df=df)
    lookahead = lookahead_bias_guard.check(df=df, metrics=metrics_flat)
    reason_chain = decision_reason_chain.build(health, danger, guard, drift, regime, calibration)
    shadow = shadow_backtest.compare(guard, health, danger)
    # include derived current values in metrics for audit only
    audit_metrics = dict(values)
    audit_metrics["conflict_count"] = conflicts.get("conflict_count", 0)
    audit, audit_summary = long_term_logic_audit.build(df, audit_metrics, health, danger, drift, guard, data_quality)
    scoreboard = {
        "Logic Health Score": health.get("score"),
        "Hidden Danger Level": danger.get("danger_level"),
        "No-Trade Guard Status": guard.get("guard_status"),
        "Prediction Drift": drift.get("drift_level"),
        "Regime Change Risk": regime.get("risk_label"),
        "Data Quality Status": data_quality.get("status"),
        "Confidence Calibration": calibration.get("label"),
        "Signal Stability": signal.get("label"),
    }
    return {
        "ok": True,
        "dataframe_source": df_source,
        "current_values": values,
        "scoreboard": scoreboard,
        "logic_health": health,
        "hidden_danger": danger,
        "no_trade_guard": guard,
        "prediction_drift": drift,
        "regime_warning": regime,
        "conflict_matrix": conflicts,
        "confidence_calibration": calibration,
        "data_quality": data_quality,
        "lookahead_bias": lookahead,
        "signal_stability": signal,
        "decision_reason_chain": reason_chain,
        "shadow_backtest": shadow,
        "audit_table": audit,
        "audit_summary": audit_summary,
    }

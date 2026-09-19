"""Compact Morning Quant Intelligence console.

Reads only the immutable canonical/session data already produced by Settings.
It does not trigger heavy calculation and it does not alter production decisions.
"""
from __future__ import annotations
from typing import Any, Mapping
import pandas as pd

VERSION = "morning-quant-intelligence-20260624-v1"


def _m(x: Any) -> Mapping[str, Any]: return x if isinstance(x, Mapping) else {}

def _fmt(x: Any) -> str:
    if x is None or x == "": return "INSUFFICIENT"
    try: return f"{float(x):.5g}"
    except Exception: return str(x)


def extract_morning_snapshot(state: Mapping[str, Any]) -> dict[str, Any]:
    can = _m(state.get("canonical_decision_result_20260617") or state.get("canonical_decision_result") or {})
    final = _m(can.get("final_decision")); regime = _m(can.get("regime")); market = _m(can.get("market")); reliability = _m(can.get("reliability"))
    q24 = _m(can.get("quant_20260624") or state.get("quant_20260624") or {})
    return {"version": VERSION, "run_id": can.get("run_id") or can.get("canonical_calculation_id") or state.get("canonical_calculation_id_20260617"), "broker_candle_time": can.get("broker_time") or market.get("broker_time") or state.get("shared_broker_time_display_20260622"), "current_decision": final.get("decision") or final.get("current_decision") or can.get("decision"), "less_risky_decision": _m(can.get("research_risk") or {}).get("less_risky_decision") or final.get("less_risky_decision"), "current_major_regime": regime.get("major_regime") or regime.get("regime"), "regime_probability": regime.get("probability") or regime.get("regime_probability"), "regime_age": _m(q24.get("duration") or {}).get("current_regime_age"), "expected_remaining_duration": _m(q24.get("duration") or {}).get("expected_remaining_duration"), "changepoint_probability": _m(q24.get("changepoint") or {}).get("posterior_changepoint_probability"), "data_freshness": market.get("freshness") or can.get("data_freshness") or "SAVED SNAPSHOT", "reliability": reliability}


def render_morning_quant_intelligence(state: Mapping[str, Any]) -> None:
    try:
        import streamlit as st
        import pandas as pd
    except Exception:
        return
    snap = extract_morning_snapshot(state)
    st.markdown("### 🌅 Morning Quant Intelligence — 20260624 Shadow")
    st.caption("Read-only professional pre-trade evidence console. Shadow-only: it does not change BUY/SELL/WAIT production decisions.")
    cols = st.columns(4)
    cols[0].metric("Current Decision", _fmt(snap.get("current_decision")))
    cols[1].metric("Less-Risky Decision", _fmt(snap.get("less_risky_decision")))
    cols[2].metric("Major Regime", _fmt(snap.get("current_major_regime")), _fmt(snap.get("regime_probability")))
    cols[3].metric("Canonical Run ID", _fmt(snap.get("run_id")))
    cols = st.columns(4)
    cols[0].metric("Regime Age", _fmt(snap.get("regime_age")))
    cols[1].metric("Expected Remaining", _fmt(snap.get("expected_remaining_duration")))
    cols[2].metric("Changepoint Prob.", _fmt(snap.get("changepoint_probability")))
    cols[3].metric("Broker Candle Time", _fmt(snap.get("broker_candle_time")))
    q24 = _m(state.get("quant_20260624") or _m(state.get("canonical_decision_result_20260617")).get("quant_20260624") or {})
    metrics = q24.get("prediction_quality") if isinstance(q24.get("prediction_quality"), list) else []
    if metrics:
        with st.expander("Open / Close — H1/H3/H6 Prediction Quality", expanded=True):
            st.dataframe(pd.DataFrame(metrics), use_container_width=True, hide_index=True)
    risk_rows = q24.get("risk_rows") if isinstance(q24.get("risk_rows"), list) else []
    with st.expander("Open / Close — Risk / Execution Evidence", expanded=False):
        if risk_rows: st.dataframe(pd.DataFrame(risk_rows), use_container_width=True, hide_index=True)
        else: st.info("Risk evidence unavailable in saved snapshot; Morning stays read-only and will not calculate.")
    readiness = q24.get("trade_readiness") or "INSUFFICIENT EVIDENCE"
    if readiness == "READY": st.success("Trade Readiness: READY (advisory only)")
    elif readiness == "CAUTION": st.warning("Trade Readiness: CAUTION (advisory only)")
    elif readiness == "NOT READY": st.error("Trade Readiness: NOT READY (advisory only)")
    else: st.info("Trade Readiness: INSUFFICIENT EVIDENCE")

__all__ = ["VERSION", "extract_morning_snapshot", "render_morning_quant_intelligence"]

def publish_quant_20260624_snapshot(state: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
    """Publish a compact read-only shadow snapshot after Settings calculation.

    It uses only already-published state/ledger information.  Missing evidence is
    explicit rather than fabricated.
    """
    snap = extract_morning_snapshot(state)
    horizons = ["H1", "H3", "H6"]
    rows: list[dict[str, Any]] = []
    try:
        from core.forecast_origin_ledger_20260624 import ForecastOriginLedger
        from core.probabilistic_evaluation_20260624 import evaluate_horizon
        ledger = ForecastOriginLedger()
        df = ledger.read("settlement_status='FULLY_SETTLED'")
        for h in horizons:
            rows.append(evaluate_horizon(df[df.get("horizon", pd.Series(dtype=str)).astype(str).str.upper() == h], horizon=h))
    except Exception:
        rows = [{"horizon": h, "sample_count": 0, "mae": None, "rmse": None, "crps": None, "crps_method": "unavailable", "coverage": None, "mean_interval_width": None, "direction_accuracy": None, "calibration_error": None} for h in horizons]
    ready_counts = [int(r.get("sample_count") or 0) for r in rows]
    if min(ready_counts or [0]) >= 30:
        readiness = "READY"
    elif max(ready_counts or [0]) >= 8:
        readiness = "CAUTION"
    else:
        readiness = "INSUFFICIENT EVIDENCE"
    q24 = {"version": VERSION, "top": snap, "prediction_quality": rows, "risk_rows": [], "trade_readiness": readiness, "shadow_only": True, "production_influence_enabled": False}
    if isinstance(state, dict):
        state["quant_20260624"] = q24
        can = state.get("canonical_decision_result_20260617")
        if isinstance(can, dict):
            can["quant_20260624"] = q24
    return q24

__all__ = ["VERSION", "extract_morning_snapshot", "render_morning_quant_intelligence", "publish_quant_20260624_snapshot"]

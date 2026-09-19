"""Existing Research Lab route: stored Field 7/V12/V13 shadow diagnostics only."""
from __future__ import annotations

from typing import Any, Mapping
import json

import pandas as pd
import streamlit as st


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _summary() -> dict[str, Any]:
    value = st.session_state.get("field_07_research_summary_v11")
    if isinstance(value, Mapping):
        return dict(value)
    try:
        from core.repositories.research_repository import ResearchRepository
        return ResearchRepository().latest_summary()
    except Exception:
        return {}


def _catalog_frame(v13: Mapping[str, Any]) -> pd.DataFrame:
    catalog = v13.get("catalog") if isinstance(v13.get("catalog"), list) else []
    if not catalog:
        try:
            from research.v13_catalog import catalog_rows
            catalog = catalog_rows()
        except Exception:
            catalog = []
    return pd.DataFrame(catalog)


def _result_rows(v13: Mapping[str, Any]) -> pd.DataFrame:
    results = _mapping(v13.get("full_results"))
    rows: list[dict[str, Any]] = []
    for slug, raw in results.items():
        result = _mapping(raw)
        outputs = _mapping(result.get("outputs"))
        rows.append({
            "Layer": str(slug).replace("_", " ").title(),
            "Research Title": result.get("research_title"),
            "Status": result.get("status"),
            "Sample Size": result.get("sample_size"),
            "Key Outputs": json.dumps(outputs, default=str, sort_keys=True)[:2500],
            "Shadow Only": result.get("shadow_only", True),
            "Production Changed": result.get("production_changed", False),
        })
    return pd.DataFrame(rows)


def show(runtime_context=None) -> None:
    del runtime_context
    st.title("🔬 Research Lab")
    st.caption(
        "Read-only stored diagnostics from the Settings calculation. Opening this page never runs a model, "
        "settles an outcome, or changes production BUY/SELL/WAIT logic."
    )
    summary = _summary()
    if not summary:
        st.warning("No stored research generation is available. Run Settings → Run Calculation + Open Lunch once.")
        return

    identity = st.columns(4)
    identity[0].metric("Run ID", str(summary.get("run_id") or "-")[:24])
    identity[1].metric("Broker Candle", str(summary.get("broker_candle_time") or "-")[:25])
    identity[2].metric("Research Status", str(summary.get("research_status") or "UNAVAILABLE"))
    identity[3].metric("Production Changed", "NO")

    v12 = _mapping(summary.get("v12_research"))
    v13 = _mapping(summary.get("v13_research"))
    overview, layers, documentation, history, v14tab, field9tab = st.tabs(
        ["V13 Overview", "V13 Full Results", "Method Contracts", "Stored Research History", "V14 Shadow Diagnostics", "Field 9 EURUSD H1"]
    )
    with overview:
        compact = _mapping(v13.get("compact_results"))
        if compact:
            st.dataframe(
                pd.DataFrame([{"Check": key.replace("_", " ").title(), "Value": value} for key, value in compact.items()]),
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("This stored generation predates V13 or V13 failed safely.")
        st.markdown("#### Integrity contract")
        st.json({
            "snapshot_hash": v13.get("snapshot_hash"),
            "schema_version": v13.get("schema_version"),
            "settled_outcome_cutoff": v13.get("settled_outcome_cutoff"),
            "source_hashes": v13.get("source_hashes"),
            "configuration": v13.get("configuration"),
            "warnings": v13.get("warnings"),
            "shadow_only": True,
            "production_changed": False,
        })
        if v12:
            st.caption(f"V12 snapshot retained: {str(v12.get('snapshot_hash') or 'UNAVAILABLE')[:24]}")

    with layers:
        frame = _result_rows(v13)
        if frame.empty:
            st.info("No V13 layer results are stored for this generation.")
        else:
            st.dataframe(frame, use_container_width=True, hide_index=True, height=620)
        st.warning(
            "AVAILABLE_SHADOW means the bounded calculation ran; it does not mean the method has a proven edge, "
            "passed a promotion gate, or can guarantee future accuracy or profit."
        )

    with documentation:
        catalog = _catalog_frame(v13)
        if catalog.empty:
            st.info("V13 method documentation is unavailable.")
        else:
            display = [
                "id", "title", "mathematical_principle", "input_schema",
                "prediction_time_availability", "outputs", "failure_states",
                "computational_budget", "validation_metrics", "promotion_gate",
                "eurusd_h1_benefit",
            ]
            st.dataframe(catalog[[column for column in display if column in catalog]], use_container_width=True, hide_index=True, height=720)

    with history:
        try:
            from core.repositories.research_repository import ResearchRepository
            frame = ResearchRepository().history(25)
        except Exception:
            frame = pd.DataFrame()
        if frame.empty:
            st.info("Stored research history is empty; no rows were fabricated.")
        else:
            keep = [column for column in (
                "run_id", "broker_candle_time", "symbol", "timeframe", "canonical_decision",
                "research_approved_action", "research_status", "research_trust_score", "risk_multiplier",
            ) if column in frame.columns]
            st.dataframe(frame[keep] if keep else frame, use_container_width=True, hide_index=True, height=560)


    with v14tab:
        v14 = _mapping(summary.get("quant_research_v14"))
        if not v14:
            st.info("No saved V14 generation is available.")
        else:
            st.error("SHADOW ONLY — no production influence or automatic promotion")
            st.json({"identity":v14.get("identity"),"readiness":v14.get("readiness"),"performance":v14.get("performance"),"limitations":v14.get("limitations"),"production_decision_changed":False,"protected_weights_changed":False})
            rows=[]
            for key in ("student_t_state","mixture_of_experts","venn_abers_calibration","caviar_tail_risk","conformal_risk_control","wasserstein_robust_decision","asymmetric_copula","knockoff_selection","proper_scoring","causal_news_impact"):
                value=_mapping(v14.get(key)); rows.append({"Method":key.replace("_"," ").title(),"Status":value.get("status","UNAVAILABLE"),"Sample Count":value.get("sample_count",value.get("calibration_count",value.get("score_sample_count",0))),"Full Saved Evidence":json.dumps(value,default=str,sort_keys=True)[:5000]})
            st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True,height=720)

    with field9tab:
        field9 = _mapping(st.session_state.get("field9_eurusd_h1_decision_impact"))
        if not field9:
            st.info("No saved Field 9 generation is available.")
        else:
            st.error("SHADOW ONLY — production influence enabled = NO")
            st.json({"identity": field9.get("identity"), "readiness": field9.get("readiness"), "performance": field9.get("performance"), "limitations": field9.get("limitations"), "causal_status": _mapping(field9.get("policy_value")).get("status"), "promotion_readiness": "NOT_APPLICABLE"}, expanded=False)
            methods=[]
            titles={"intraday_periodicity":"Intraday Periodicity and Volatility Persistence in Financial Markets","macro_event_impact":"Micro Effects of Macro Announcements: Real-Time Price Discovery in Foreign Exchange","microstructure_proxy":"Order Flow and Exchange Rate Dynamics","volatility_adjustment":"A Simple Approximate Long-Memory Model of Realized Volatility","tail_dependence":"Modelling Asymmetric Exchange Rate Dependence","conditional_predictive_ability":"Tests of Conditional Predictive Ability","reality_check":"A Reality Check for Data Snooping","policy_value":"Policy Learning with Observational Data","double_ml":"Double/Debiased Machine Learning for Treatment and Structural Parameters","doubly_robust":"Doubly Robust Policy Evaluation and Learning"}
            for key,title in titles.items():
                value=_mapping(field9.get(key)); methods.append({"Exact research-paper title":title,"Method":key,"Status":value.get("status","UNAVAILABLE"),"Assumptions / limitations":json.dumps(value.get("limitations",value.get("reason","")),default=str),"Saved diagnostics":json.dumps(value,default=str,sort_keys=True)[:4000]})
            st.dataframe(pd.DataFrame(methods),use_container_width=True,hide_index=True,height=720)

    st.caption(
        "Improved data quality, uncertainty estimation, and calibration diagnostics do not guarantee future trading accuracy or profit."
    )


__all__ = ["show"]

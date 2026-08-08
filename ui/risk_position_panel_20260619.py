"""Responsive Lunch risk guardrail and progressive-disclosure controls."""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping
import pandas as pd
import streamlit as st

from core.canonical_runtime_20260617 import get_canonical
from core.compact_canonical_20260619 import get_compact_summary
from services.position_sizing import build_risk_plan, reference_table


def _m(value: Any) -> Mapping[str, Any]: return value if isinstance(value, Mapping) else {}


def _defaults(state: MutableMapping[str, Any]) -> None:
    defaults = {
        "risk_balance_20260619": float(state.get("account_balance", 600.0) or 600.0), "risk_leverage_20260619": 100.0,
        "risk_pct_20260619": 1.0, "risk_stop_pips_20260619": 20.0, "risk_existing_lots_20260619": 0.0,
        "risk_existing_combined_pct_20260619": 0.0, "risk_daily_realized_loss_20260619": 0.0,
        "risk_min_lot_20260619": 0.01, "risk_lot_step_20260619": 0.01,
        "risk_available_margin_20260619": float(state.get("free_margin", state.get("account_balance", 600.0)) or 600.0),
        "risk_max_margin_pct_20260619": 25.0, "risk_max_combined_pct_20260619": 2.0,
        "risk_max_idea_pct_20260619": 1.5, "risk_daily_block_pct_20260619": 3.0, "risk_related_entries_20260619": 0,
    }
    for key, value in defaults.items(): state.setdefault(key, value)


def _priority_defaults(state: MutableMapping[str, Any], summary: Mapping[str, Any]) -> None:
    identity = _m(summary.get("identity")); generation = identity.get("calculation_generation")
    if state.get("risk_disclosure_generation_20260619") == generation: return
    label = str(_m(summary.get("priority")).get("opportunity_quality") or "WATCH").upper()
    decision = str(_m(summary.get("decision")).get("current_decision") or "WAIT").upper()
    stale = str(_m(summary.get("validation")).get("stale_status") or "CURRENT").upper() != "CURRENT"
    high = "A+" in label or label == "A"
    weak = any(x in label for x in ("C", "AVOID"))
    state["risk_open_entry_20260619"] = bool(high and not stale)
    state["risk_open_plan_20260619"] = bool(high and not stale)
    state["risk_open_reasons_20260619"] = bool(high)
    state["risk_open_conflict_20260619"] = bool(decision == "WAIT" or "B" in label)
    state["risk_open_warning_20260619"] = bool(weak or stale)
    state["risk_disclosure_generation_20260619"] = generation


def _metric(col, label: str, value: str, delta: str = "") -> None:
    col.metric(label, value, delta=delta or None)


def render_position_sizing_panel(*, state: MutableMapping[str, Any] | None = None) -> dict[str, Any]:
    state = state if state is not None else st.session_state; _defaults(state)
    canonical = get_canonical(state); summary = get_compact_summary(state)
    if not canonical: return {}
    _priority_defaults(state, summary)
    with st.expander("Open / Close — position-sizing inputs and limits", expanded=False):
        a,b,c,d = st.columns(4)
        a.number_input("Balance ($)", min_value=1.0, step=50.0, key="risk_balance_20260619")
        b.number_input("Leverage", min_value=1.0, step=1.0, key="risk_leverage_20260619")
        c.number_input("Risk per idea (%)", min_value=0.1, max_value=2.0, step=0.1, key="risk_pct_20260619")
        d.number_input("Stop distance (pips)", min_value=0.0, step=1.0, key="risk_stop_pips_20260619")
        e,f,g,h = st.columns(4)
        e.number_input("Existing EURUSD lots", min_value=0.0, step=0.01, key="risk_existing_lots_20260619")
        f.number_input("Existing combined risk (%)", min_value=0.0, step=0.1, key="risk_existing_combined_pct_20260619")
        g.number_input("Daily realized loss ($)", min_value=0.0, step=1.0, key="risk_daily_realized_loss_20260619")
        h.number_input("Available margin ($)", min_value=0.0, step=10.0, key="risk_available_margin_20260619")
        i,j,k,l = st.columns(4)
        i.number_input("Broker minimum lot", min_value=0.001, step=0.01, format="%.3f", key="risk_min_lot_20260619")
        j.number_input("Broker lot step", min_value=0.001, step=0.01, format="%.3f", key="risk_lot_step_20260619")
        k.number_input("Maximum combined risk (%)", min_value=0.5, max_value=10.0, step=0.1, key="risk_max_combined_pct_20260619")
        l.number_input("Daily loss block (%)", min_value=0.5, max_value=10.0, step=0.5, key="risk_daily_block_pct_20260619")
    plan = build_risk_plan(state, canonical); state["position_sizing_plan_20260619"] = plan
    summary_identity = _m(summary.get("identity")); decision = _m(summary.get("decision")); regime = _m(summary.get("regime")); priority = _m(summary.get("priority")); validation = _m(summary.get("validation")); uncertainty = _m(summary.get("uncertainty")); final = _m(canonical.get("final_decision")); inputs = _m(plan.get("inputs"))
    st.markdown("#### Canonical snapshot and aggregate risk plan")
    st.markdown("""<style>@media(max-width:430px){[data-testid='column']{min-width:100%!important;flex:1 1 100%!important;}button{min-height:44px!important;}[data-testid='stMetric']{min-height:92px!important;}}</style>""", unsafe_allow_html=True)
    rows = [
        (("Snapshot generation", str(summary_identity.get("calculation_generation","-")), "same across tabs"),("Run status", str(validation.get("layer_status","-")), "immutable completed generation"),("Last completed H1 candle", str(summary_identity.get("latest_completed_candle_time","-"))[-22:], "completed candle only"),("Data freshness", str(validation.get("data_freshness","UNKNOWN")), str(validation.get("stale_status","-")))),
        (("Current decision", str(decision.get("current_decision","WAIT")), "protected decision"),("Less-risky decision", str(decision.get("less_risky_bias","WAIT")), "risk guardrail"),("Current regime", str(regime.get("directional_regime","UNKNOWN")), "Full Metric aligned"),("Priority", f"{priority.get('opportunity_quality','WATCH')} / {priority.get('current_rank','N/A')}", "canonical ranking")),
        (("Reliability", f"{float(regime.get('regime_reliability') or 0):.1f}%", "canonical"),("Uncertainty", f"{float(uncertainty.get('combined') or 0):.1f}%", str(uncertainty.get("main_source","-"))),("Error percentage", f"{float(final.get('error_estimate_pct') or 0):.1f}%", "display only"),("Recommended total lots", f"{float(plan.get('recommended_lots') or 0):.2f}", "aggregate, not per entry")),
        (("Scale-in entries", str(plan.get("scale_in_entries",0)), "+".join(f"{float(x):.2f}" for x in plan.get("scale_in_splits",[])) or "none"),("Stop distance", f"{float(inputs.get('stop_loss_pips') or 0):.1f} pips", "selected input"),("Planned dollar loss", f"${float(plan.get('planned_dollar_loss') or 0):.2f}", f"{float(plan.get('planned_risk_pct') or 0):.2f}%"),("Estimated margin", f"${float(plan.get('margin_estimate') or 0):.2f}", f"{float(plan.get('margin_pct') or 0):.2f}% of balance")),
        (("Combined open risk", f"{float(plan.get('combined_open_risk_pct') or 0):.2f}%", "related EURUSD idea"),("Daily risk remaining", f"${float(plan.get('daily_risk_remaining_dollars') or 0):.2f}", f"{float(plan.get('daily_risk_remaining_pct') or 0):.2f}%"),("Available margin", f"${float(plan.get('current_available_margin') or 0):.2f}", "current input"),("Risk status", str(plan.get("status","BLOCK")), str(plan.get("reason","-"))[:80])),
    ]
    for row in rows:
        cols=st.columns(4)
        for col,(label,value,delta) in zip(cols,row): _metric(col,label,value,delta)
    if plan.get("status") == "BLOCK": st.error(str(plan.get("reason")))
    elif plan.get("status") == "CAUTION": st.warning(str(plan.get("reason")))
    else: st.success("SAFE — aggregate risk and margin checks passed. This does not override the protected trading decision.")

    t1,t2,t3,t4,t5 = st.columns(5)
    t1.toggle("Entry plan", key="risk_open_entry_20260619")
    t2.toggle("Risk plan", key="risk_open_plan_20260619")
    t3.toggle("Key reasons", key="risk_open_reasons_20260619")
    t4.toggle("Conflict / watch", key="risk_open_conflict_20260619")
    t5.toggle("Risk warning", key="risk_open_warning_20260619")
    if state.get("risk_open_entry_20260619"):
        st.info(f"Approved aggregate size: {float(plan.get('recommended_lots') or 0):.2f} lot; allowed split: " + (" + ".join(f"{float(x):.2f}" for x in plan.get("scale_in_splits", [])) or "SKIP"))
    if state.get("risk_open_plan_20260619"):
        st.dataframe(pd.DataFrame(reference_table(float(inputs.get("balance") or 600), float(inputs.get("risk_pct") or 1), lot_step=float(inputs.get("broker_lot_step") or .01), minimum_lot=float(inputs.get("broker_minimum_lot") or .01))), use_container_width=True, hide_index=True)
        st.caption(f"Theoretical broker margin capacity: {float(plan.get('theoretical_margin_capacity_lots') or 0):.2f} lot. Safe risk-based lots are shown separately; the app never recommends using all theoretical margin.")
    if state.get("risk_open_reasons_20260619"):
        st.write("**Main reason:**", decision.get("main_reason","No reason available"))
    if state.get("risk_open_conflict_20260619"):
        st.warning("Watch condition: " + "; ".join(map(str, list(final.get("blocking_reasons") or [])[:4])) if final.get("blocking_reasons") else "Watch condition: no hard blocker; monitor uncertainty and regime transition risk.")
    if state.get("risk_open_warning_20260619"):
        st.error(f"Execution guardrail: {plan.get('status')} — {plan.get('reason')}")
    st.caption("Copy Short and Copy Full are available only at the top of Lunch.")
    return plan

__all__ = ["render_position_sizing_panel"]

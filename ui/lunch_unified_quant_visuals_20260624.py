"""Read-only Past/Present/Future visuals over saved canonical shadow evidence."""
from __future__ import annotations
from typing import Any, Mapping
import math
import pandas as pd
import streamlit as st


def _m(v): return v if isinstance(v, Mapping) else {}
def _f(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception: return None

def _payload(state): return _m(state.get("research_grade_system_v17_20260624"))

def _horizon_rows(payload):
    f2=_m(payload.get("field2")); rows=[]
    for h in (1,3,6):
        r=_m(f2.get(str(h))); m=_m(r.get("metrics"));
        rows.append({"horizon":h,"predicted_price":_f(r.get("point_forecast")),"lower":_f(r.get("origin_lower")),"upper":_f(r.get("origin_upper")),"coverage":_f(m.get("interval_coverage")),"mae":_f(m.get("mae")),"rmse":_f(m.get("rmse")),"stability":_f(r.get("whole_path_stability") or r.get("path_stability")),"status":r.get("evidence_status")})
    # H2 is a transparent read-only interpolation between independently stored H1 and H3 evidence.
    a,b=rows[0],rows[1]
    def mid(k):
        x,y=a.get(k),b.get(k)
        return None if x is None or y is None else (x+y)/2
    rows.insert(1,{"horizon":2,"predicted_price":mid("predicted_price"),"lower":mid("lower"),"upper":mid("upper"),"coverage":mid("coverage"),"mae":mid("mae"),"rmse":mid("rmse"),"stability":mid("stability"),"status":"DERIVED_DISPLAY_ONLY_FROM_H1_H3"})
    return rows

def _probabilities(payload):
    f9=_m(payload.get("field9")); out={"BUY":None,"WAIT":None,"SELL":None}
    for r in f9.get("action_results") or []:
        a=str(r.get("action","")).upper()
        if a in out: out[a]=_f(r.get("action_probability"))
    vals=[v for v in out.values() if v is not None]
    if not vals:
        h3=_m(_m(payload.get("field2")).get("3")); up=_f(h3.get("calibrated_direction_probability")) or .5
        out={"BUY":up,"SELL":1-up,"WAIT":max(0.0,1-abs(up-.5)*2)}
    s=sum(v or 0 for v in out.values()) or 1
    return {k:(v or 0)/s for k,v in out.items()}

def render_priority_summary(state, title="Current-Hour AI Priority Summary"):
    p=_payload(state)
    with st.expander(title, expanded=False):
        if not p: st.info("No saved canonical research evidence."); return
        c=_m(p.get("contract")); f3=_m(p.get("field3")); f9=_m(p.get("field9")); probs=_probabilities(p)
        ranked=sorted(probs.items(), key=lambda kv:kv[1], reverse=True)
        items=[
            ("Priority 1",f"{ranked[0][0]} ({ranked[0][1]:.1%})"),("Priority 2",f"{ranked[1][0]} ({ranked[1][1]:.1%})"),("Priority 3",f"{ranked[2][0]} ({ranked[2][1]:.1%})"),
            ("Current decision",c.get("decision")),("Less-risky action",f9.get("best_counterfactual_action") or "WAIT"),("Current regime",f3.get("production_regime")),
            ("Regime disagreement","YES" if not f3.get("production_shadow_agreement",True) else "NO"),("Prediction-path state",(_m(p.get("field2")).get("3") or {}).get("evidence_status")),
            ("Reliability",f3.get("persistence_probability")),("Uncertainty",f3.get("changepoint_probability")),("Principal reason",f9.get("main_supporting_factor") or "Saved multi-horizon evidence"),
            ("Principal risk",f3.get("transition_warning_state") or "No active warning"),("Reversal condition",f9.get("minimum_input_change_required")),("Evidence sufficiency",f9.get("evidence_sufficiency")),
            ("Broker candle time",c.get("broker_candle_time")),("Run ID",c.get("run_id")),]
        for i,(k,v) in enumerate(items,1): st.markdown(f"**{i}. {k}:** {v if v not in (None,'') else 'Insufficient evidence'}")

def render(state):
    p=_payload(state)
    with st.expander("Past, Present & Future Quant Visuals", expanded=False):
        if not p: st.info("Run Settings → Run Calculation + Open Lunch to publish evidence."); return
        rows=_horizon_rows(p); probs=_probabilities(p)
        st.markdown("#### A. Past")
        hist=state.get("prediction_outcomes") or []
        if hist:
            df=pd.DataFrame(hist)
            cols=[c for c in ["origin_candle_time","actual_return","predicted_return","origin_lower","origin_upper"] if c in df]
            d=df[cols].tail(120).copy()
            if "origin_candle_time" in d: d=d.set_index("origin_candle_time")
            st.line_chart(d, use_container_width=True)
            if {"actual_return","predicted_return"} <= set(df):
                e=(pd.to_numeric(df["actual_return"],errors="coerce")-pd.to_numeric(df["predicted_return"],errors="coerce")).abs()
                st.line_chart(pd.DataFrame({"absolute_error":e,"rolling_MAE":e.rolling(12,min_periods=1).mean()}),use_container_width=True)
        else: st.info("Insufficient matured historical observations; no history is fabricated.")
        st.markdown("#### B. Present")
        f3=_m(p.get("field3")); f9=_m(p.get("field9")); present={"BUY probability":probs["BUY"],"WAIT probability":probs["WAIT"],"SELL probability":probs["SELL"],"regime confidence":_f(f3.get("persistence_probability")) or 0,"three-standard agreement":1.0 if f3.get("production_shadow_agreement") else 0.0,"calibrated reliability":_f(f3.get("regime_reliability")) or 0,"forecast agreement":_f(f9.get("stability_across_models")) or 0,"path stability":_f((_m(p.get("field2")).get("3") or {}).get("whole_path_stability")) or 0,"drift safety":1-(_f(f3.get("changepoint_probability")) or 0),"evidence sufficiency":1.0 if f9.get("evidence_sufficiency") else 0.0}
        st.bar_chart(pd.Series(present).sort_values(),horizontal=True,use_container_width=True)
        st.metric("Expected value after costs",f9.get("net_expected_action_value") or "Insufficient evidence")
        st.markdown("#### C. Future")
        d=pd.DataFrame(rows).set_index("horizon")
        st.line_chart(d[[c for c in ["predicted_price","upper","lower"] if c in d]],use_container_width=True)
        c1,c2=st.columns([2,1]); c1.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        c2.dataframe(pd.DataFrame([{"action":k,"probability":v} for k,v in probs.items()]),use_container_width=True,hide_index=True)
        c2.caption("Probability summary; the path chart remains primary.")
        st.json({"reversal_probability":f3.get("changepoint_probability"),"adverse_excursion_probability":f9.get("downside_probability"),"expected_range":{"low":min([r["lower"] for r in rows if r["lower"] is not None],default=None),"high":max([r["upper"] for r in rows if r["upper"] is not None],default=None)},"interval_coverage_target":0.90,"trusted_horizon":max((r["horizon"] for r in rows if r.get("coverage") is not None and r["coverage"]>=.80),default="Insufficient evidence"),"H2_method":"display-only interpolation of saved H1/H3; not a new production forecast"},expanded=False)

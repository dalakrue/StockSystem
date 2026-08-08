from __future__ import annotations
import pandas as pd
import streamlit as st

def _p(state): return state.get("breakout_regime_shadow_20260624") if isinstance(state.get("breakout_regime_shadow_20260624"),dict) else {}

def render_field2(state):
    p=_p(state)
    if not p.get("ok"):
        st.info("Shadow breakout path unavailable: genuine historical evidence is insufficient or the Settings run has not published it."); return
    b=p["breakout"]; f=p["features"]
    st.caption("Shadow-only · causal · production decision unchanged")
    c=st.columns(4)
    c[0].metric("Breakout state",b["classification"].replace("_"," ").title(),help="A multi-evidence classification; no single indicator declares a breakout.")
    c[1].metric("Changepoint",f"{f['changepoint_probability']:.1%}",help="Online probability that the generating process changed.")
    c[2].metric("Volatility",f["volatility_state"].title())
    c[3].metric("Jump ratio",f"{f['jump_ratio']:.2f}",help="Robust fraction of realized variation attributed to discontinuous movement.")
    probs={k.replace("_"," ").title():v for k,v in b["probabilities"].items()}; st.dataframe(pd.DataFrame([probs]),use_container_width=True,hide_index=True)
    rows=[]
    for h in (1,3,6):
        i=p["adaptive_intervals"][h]; cand=p["candidate_paths"][h]
        rows.append({"Horizon":f"{h}h","Combined":i["forecast"],"Normal":cand["normal"],"Bull breakout":cand["bull_breakout"],"Bear breakout":cand["bear_breakout"],"Failed breakout":cand["failed_breakout"],"Lower":i["lower"],"Upper":i["upper"],"Uncertainty":i["uncertainty"],"Samples":i["calibration_sample_count"],"Fallback":i["calibration_fallback_level"],"Target coverage":i["target_coverage"],"Actual coverage":i["actual_coverage"]})
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    st.caption(p["explanation"])

def render_field3(state):
    p=_p(state)
    if not p.get("ok"):
        st.info("Shadow unified regime layer unavailable until a successful Settings run publishes sufficient causal H1 history."); return
    st.caption("Shadow-only master regime and decision; Field 1 and production decision remain unchanged.")
    c=st.columns(4); c[0].metric("Current regime",p["current_regime"]); c[1].metric("Master regime",p["master_regime"]); c[2].metric("Shadow decision",p["shadow_master_decision"]); c[3].metric("Evidence",p["evidence_sufficiency"],help="Requires probability, persistence, data quality, changepoint and conflict gates.")
    rows=[]
    for standard in ("lower","middle","higher","combined"):
        probs=p["regimes"][standard]; top=max(probs,key=probs.get)
        rows.append({"Standard":standard.title(),"Regime":top.replace("_"," ").title(),"Probability":probs[top],"Full probability vector":probs})
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    d=pd.DataFrame([{"BUY priority":p["priorities"]["BUY"],"SELL priority":p["priorities"]["SELL"],"WAIT priority":p["priorities"]["WAIT"],"Production":p["production_current_decision"],"Shadow master":p["shadow_master_decision"],"Agreement":p["decision_agreement"],"EV after cost":p["expected_value_after_cost"],"Adverse impact":p["expected_adverse_impact"],"Reversal trigger":p["reversal_trigger"]}])
    st.dataframe(d,use_container_width=True,hide_index=True)

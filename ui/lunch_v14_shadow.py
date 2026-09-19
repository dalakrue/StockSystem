from __future__ import annotations
import pandas as pd
import streamlit as st

def payload(state):
 v=state.get("quant_research_v14")
 if isinstance(v,dict): return v
 s=state.get("field_07_research_summary_v11")
 return (s.get("quant_research_v14") if isinstance(s,dict) else {}) or {}
def compact(state, keys, title):
 v=payload(state); st.markdown(title); st.caption("SHADOW ONLY · production decision and protected weights unchanged")
 rows=[]
 for k in keys:
  x=v.get(k,{}) if isinstance(v,dict) else {}; rows.append({"Method":k.replace("_"," ").title(),"Status":x.get("status","UNAVAILABLE"),"Evidence":str({a:b for a,b in x.items() if a not in ("history","events","actions","selected_features")})[:900]})
 st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

"""Question-triggered bounded local Plan B and deterministic Plan C."""
from __future__ import annotations
from collections import OrderedDict
from typing import Any,Mapping,MutableMapping
import hashlib,re,sqlite3,pandas as pd,numpy as np
from services.canonical_snapshot_store import DB_PATH
CACHE_KEY="ai_plan_b_cache_20260622";MAX_CACHE=20
def normalize_question(q):return re.sub(r"\s+"," ",str(q).strip().lower())
def classify_question(q):
 q=normalize_question(q)
 if any(x in q for x in ("survival","churn","remain valid")):return "signal_survival"
 if any(x in q for x in ("overlap","london","new york","session")):return "overlap_performance"
 if "xau" in q or ("compare" in q and "eur" in q):return "cross_market"
 if any(x in q for x in ("cvar","tail risk","tail")):return "tail_risk"
 if any(x in q for x in ("drift","time variance","variance change")):return "drift"
 return "current_facts"
def _generation(c):return str(c.get("calculation_generation") or c.get("generation") or c.get("canonical_calculation_id") or c.get("run_id") or "")
def _cache(state,g):
 c=state.get(CACHE_KEY)
 if not isinstance(c,OrderedDict):c=OrderedDict()
 for k in list(c):
  if not str(k).startswith(g+"|"):c.pop(k,None)
 state[CACHE_KEY]=c;return c
def _rows(intent,phone,db_path=DB_PATH):
 limit=600 if intent!="cross_market" else (600 if phone else 1500);con=sqlite3.connect(str(db_path));con.row_factory=sqlite3.Row
 try:
  exists=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='quant_research_v6_market_history'").fetchone()
  if not exists:return pd.DataFrame()
  cols={r[1] for r in con.execute("PRAGMA table_info(quant_research_v6_market_history)")};wanted=[c for c in ("event_time_utc","symbol","timeframe","session","london_new_york_overlap","return_1","direction_correct","absolute_forecast_error","signal_survival_probability","churn_risk","drift_state","close") if c in cols];return pd.read_sql_query(f"SELECT {','.join(wanted)} FROM quant_research_v6_market_history ORDER BY event_time_utc DESC LIMIT ?",con,params=[limit])
 finally:con.close()
def plan_c(question,canonical):
 f=canonical.get("final_decision") if isinstance(canonical.get("final_decision"),Mapping) else {};r=canonical.get("regime") if isinstance(canonical.get("regime"),Mapping) else {};rel=canonical.get("reliability") if isinstance(canonical.get("reliability"),Mapping) else {};facts={"decision":f.get("final_decision") or canonical.get("decision"),"direction":f.get("directional_market_view") or f.get("direction"),"regime":r.get("major_regime") or r.get("current_regime"),"reliability":rel.get("score"),"generation":_generation(canonical),"broker_candle":canonical.get("latest_completed_h1_utc") or canonical.get("latest_completed_candle_time")}
 valid={k:v for k,v in facts.items() if v not in (None,"")}
 if not valid:return {"route_label":"OFFLINE DIAGNOSTIC","answer":"OFFLINE DIAGNOSTIC\nNo valid canonical market facts are available. Run the authoritative Settings calculation; no trading value was fabricated.","intent":"offline","evidence":[],"sample_size":0,"confidence":0,"limitations":["No canonical facts"]}
 identity_lines=f"**Generation ID:** {canonical.get('canonical_calculation_id') or canonical.get('run_id') or _generation(canonical) or 'UNAVAILABLE'}\n**Broker timestamp used:** {facts.get('broker_candle') or 'UNAVAILABLE'}\n**Evidence coverage status:** PARTIAL ANSWER (current canonical facts only)"
 return {"route_label":"PLAN C SAFE FORMATTER","answer":"PLAN C SAFE FORMATTER\n"+identity_lines+"\n"+"\n".join(f"- {k}: {v}" for k,v in valid.items())+"\n- Limitation: deterministic current facts only; no new market calculation.","intent":"current_facts","evidence":list(valid),"sample_size":1,"confidence":60,"limitations":["Current canonical facts only"]}
def answer_plan_b(question,*,canonical:Mapping,state:MutableMapping,db_path=DB_PATH):
 intent=classify_question(question);g=_generation(canonical);contract=str((canonical.get("metadata") or {}).get("broker_time_contract_version") if isinstance(canonical.get("metadata"),Mapping) else "");key=g+"|"+hashlib.sha256((normalize_question(question)+"|"+intent+"|"+contract).encode()).hexdigest();cache=_cache(state,g)
 if key in cache:cache.move_to_end(key);return dict(cache[key])
 f=_rows(intent,bool(state.get("phone_mode",False)),db_path);broker=canonical.get("latest_completed_h1_utc") or canonical.get("latest_completed_candle_time");limitations=[]
 if f.empty:return plan_c(question,canonical)
 ans=[];confidence=55
 if intent=="signal_survival":
  s=pd.to_numeric(f.get("signal_survival_probability"),errors="coerce").dropna();ch=pd.to_numeric(f.get("churn_risk"),errors="coerce").dropna();ans=[f"Recent persisted survival evidence mean: {s.mean():.2%}" if len(s) else "Survival probability is unavailable in persisted rows.",f"Recent churn risk mean: {ch.mean():.2%}" if len(ch) else "Churn risk is unavailable."];confidence=70 if len(s)>=20 else 50
 elif intent=="overlap_performance":
  x=f[f.get("london_new_york_overlap",0).fillna(0).astype(int)==1] if "london_new_york_overlap" in f else pd.DataFrame();dc=pd.to_numeric(x.get("direction_correct"),errors="coerce").dropna() if not x.empty else pd.Series(dtype=float);ans=[f"London/New York overlap rows: {len(x)}",f"Settled direction correctness: {dc.mean():.2%}" if len(dc) else "Settled correctness unavailable; no value was invented."];confidence=70 if len(dc)>=20 else 50
 elif intent=="cross_market":
  ans=[f"{s} {t}: {len(gp)} compact rows, latest close {pd.to_numeric(gp.close,errors='coerce').dropna().iloc[0] if 'close' in gp and pd.to_numeric(gp.close,errors='coerce').notna().any() else 'UNAVAILABLE'}" for (s,t),gp in f.groupby(["symbol","timeframe"])]
 elif intent=="tail_risk":
  e=pd.to_numeric(f.get("absolute_forecast_error"),errors="coerce").dropna();
  if len(e)>=30:
   for q in (.9,.95,.99):v=e.quantile(q);ans.append(f"CVaR {int(q*100)}%: {e[e>=v].mean():.6g} (tail n={(e>=v).sum()})");confidence=75
  else:ans=[f"UNAVAILABLE — CVaR minimum sample gate requires 30 settled errors; available {len(e)}."];limitations.append("Minimum sample gate")
 elif intent=="drift":
  counts=f.get("drift_state",pd.Series(dtype=str)).value_counts();ans=["Drift states: "+", ".join(f"{k}={v}" for k,v in counts.items()) if len(counts) else "Drift state unavailable."]
 else:return plan_c(question,canonical)
 result={"route_label":"PLAN B BOUNDED CALCULATION","answer":"PLAN B BOUNDED CALCULATION\n"+"\n".join("- "+x for x in ans)+f"\n- Intent: {intent}\n- Broker candle: {broker}\n- Generation: {g}\n- Sample size loaded: {len(f)}\n- Confidence: {confidence}%\n- Limitations: {', '.join(limitations) if limitations else 'bounded persisted evidence; not profit probability'}","intent":intent,"evidence":["quant_research_v6_market_history"],"sample_size":len(f),"confidence":confidence,"limitations":limitations,"generation_id":g,"broker_candle":broker};cache[key]=result;cache.move_to_end(key)
 while len(cache)>MAX_CACHE:cache.popitem(last=False)
 state[CACHE_KEY]=cache;del f;return result

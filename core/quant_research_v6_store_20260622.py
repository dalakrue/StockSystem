"""One-shot Quant V6 transaction and atomic normalized persistence."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from typing import Any,Iterable,Mapping,MutableMapping
import gc,json,sqlite3,time,tracemalloc,pandas as pd
from core.quant_research_v6_contract_20260622 import IMPLEMENTATION_VERSION,identity_from_canonical,json_safe,normalize_completed_ohlc,normalize_settled
from services.canonical_snapshot_store import DB_PATH
BUNDLE_KEY="__quant_research_v6__";MIGRATION_PATH=Path(__file__).resolve().parents[1]/"migrations"/"20260622_quant_research_v6.sql";TABLES=("quant_research_v6_run","quant_research_v6_method_results","quant_research_v6_market_history")
def ensure_schema(conn):
 buf=[]
 for line in MIGRATION_PATH.read_text(encoding="utf-8").splitlines():
  s=line.strip()
  if not s or s.startswith("--"):continue
  buf.append(line);stmt="\n".join(buf).strip()
  if sqlite3.complete_statement(stmt):conn.execute(stmt);buf=[]
 if buf:raise sqlite3.OperationalError("incomplete V6 migration")
def _json(v):return json.dumps(json_safe(v),ensure_ascii=False,sort_keys=True,separators=(",",":"))
def _insert(conn,table,rows):
 ins=ign=0
 for raw in rows:
  row=dict(raw);cols=list(row);cur=conn.execute(f"INSERT OR IGNORE INTO {table}({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",[row[c] for c in cols]);ins+=int(cur.rowcount>0);ign+=int(cur.rowcount<=0)
 return {"inserted":ins,"idempotent_ignored":ign}
def insert_quant_v6_bundle(conn,bundle):
 ensure_schema(conn);return {t:_insert(conn,t,bundle.get(t,[])) for t in TABLES}
def _val(v):
 try:return None if pd.isna(v) else v
 except Exception:return v
def _market_rows(f):
 rows=[]
 if not isinstance(f,pd.DataFrame):return rows
 for x in f.to_dict("records"):
  rows.append({"event_time_utc":str(x.get("event_time_utc") or ""),"broker_time":str(x.get("Broker Time") or ""),"myanmar_time":str(x.get("Myanmar Time") or ""),"calculation_id":str(x.get("calculation_id") or ""),"generation_id":str(x.get("generation_id") or ""),"symbol":str(x.get("symbol") or ""),"timeframe":str(x.get("timeframe") or ""),"source":str(x.get("source") or ""),"completed_status":str(x.get("completed_status") or ""),"session":str(x.get("session") or ""),"london_active":int(bool(x.get("london_active"))),"new_york_active":int(bool(x.get("new_york_active"))),"london_new_york_overlap":int(bool(x.get("london_new_york_overlap"))),"close":_val(x.get("close")),"return_1":_val(x.get("return_1")),"candle_range":_val(x.get("candle_range")),"volatility":_val(x.get("ATR or existing volatility")),"spread":_val(x.get("available spread")),"slippage":_val(x.get("available slippage")),"expected_move":_val(x.get("expected move")),"regime":str(x.get("regime") or "UNAVAILABLE"),"protected_decision":str(x.get("protected decision") or "UNAVAILABLE"),"master_score":_val(x.get("master score")),"entry_score":_val(x.get("entry score")),"hold_score":_val(x.get("hold score")),"tp_quality":_val(x.get("TP quality")),"exit_risk":_val(x.get("exit risk")),"trend_capacity":_val(x.get("trend capacity")),"forecast_direction":str(x.get("forecast direction") or "UNAVAILABLE"),"forecast_confidence":_val(x.get("forecast confidence")),"realized_direction":str(x.get("realized direction when settled") or "UNAVAILABLE"),"direction_correct":_val(x.get("direction correct when settled")),"absolute_forecast_error":_val(x.get("absolute forecast error when settled")),"signal_survival_probability":_val(x.get("signal survival probability")),"churn_risk":_val(x.get("churn risk")),"drift_state":str(x.get("drift state") or "UNAVAILABLE"),"data_quality_status":str(x.get("data_quality_status") or "UNAVAILABLE"),"synchronization_status":str(x.get("synchronization_status") or "UNAVAILABLE"),"gap_flag":str(x.get("gap_flag") or ""),"logic_version":IMPLEMENTATION_VERSION})
 return rows
def build_bundle(result,market):
 i=result["identity"];m=result["methods"];p=result["performance"];s=result["summary"];calc=i["calculation_id"];gen=i["source_generation_id"];event=i["latest_completed_h1_utc"];b={t:[] for t in TABLES};b[TABLES[0]].append({"calculation_id":calc,"generation_id":gen,"event_time_utc":event,"status":s["overall_status"],"method_count":len(m),"sample_count":s["sample_count"],"runtime_ms":p["wall_time_ms"],"peak_traced_memory_mb":p["peak_traced_memory_mb"],"serialized_result_bytes":p["serialized_result_bytes"],"logic_version":IMPLEMENTATION_VERSION,"payload_json":_json({"summary":s,"statuses":result["market_statuses"],"performance":p})})
 for k,v in m.items():b[TABLES[1]].append({"calculation_id":calc,"generation_id":gen,"event_time_utc":event,"method_id":str(v.get("method_id") or k),"status":str(v.get("status") or "AVAILABLE"),"sample_count":int(v.get("sample_count") or 0),"horizon_hours":0,"score":v.get("transition_risk_score") or v.get("reconstruction_error"),"logic_version":IMPLEMENTATION_VERSION,"payload_json":_json(v)})
 b[TABLES[2]]=_market_rows(market);return b
def build_quant_research_v6_transaction(canonical:Mapping[str,Any],*,completed_h1:pd.DataFrame,settled_outcomes:pd.DataFrame|None,history_frame:pd.DataFrame|None,state:MutableMapping[str,Any],previous=None,market_fetcher=None):
 out=deepcopy(dict(canonical or {}));start=time.perf_counter();tracemalloc.start();f,meta=normalize_completed_ohlc(completed_h1,cutoff_utc=out.get("latest_completed_h1_utc") or out.get("latest_completed_candle_time"));settled=normalize_settled(settled_outcomes);identity=identity_from_canonical(out,meta)
 from core.quant_research_v6_state_space_20260622 import run_kalman_state,run_hamilton_style
 from core.quant_research_v6_survival_20260622 import run_signal_survival
 from core.quant_research_v6_low_rank_20260622 import run_low_rank_quality
 from core.quant_research_v6_explanation_20260622 import run_explanation
 from core.quant_research_v6_drift_tail_20260622 import run_drift_tail
 from core.quant_research_v6_market_history_20260622 import collect_multi_market_history
 methods={};methods["kalman_state"]=run_kalman_state(f);methods["hamilton_transition"]=run_hamilton_style(f,out);methods["signal_survival"]=run_signal_survival(history_frame,out);methods["low_rank_quality"]=run_low_rank_quality(f);methods["explanation"]=run_explanation(f,out,methods["low_rank_quality"]);methods["drift_tail_execution_tft"]=run_drift_tail(settled,out,f);market,statuses=collect_multi_market_history(state,out,current_h1=f,fetcher=market_fetcher);available=sum(isinstance(v,Mapping) and v.get("status")=="AVAILABLE" for v in methods.values());summary={"overall_status":"SHADOW_READY" if available>=4 else "LIMITED_EVIDENCE","available_method_count":available,"method_count":len(methods),"sample_count":len(f),"market_combinations_available":sum(x.get("status")=="AVAILABLE" for x in statuses),"market_combinations_total":4,"shadow_only":True,"production_influence_enabled":False};_,peak=tracemalloc.get_traced_memory();tracemalloc.stop();result={"version":IMPLEMENTATION_VERSION,"identity":identity,"summary":summary,"methods":methods,"market_statuses":statuses,"assumptions":["completed timestamps only","settled evidence only for drift/tail","no target leakage","no invented execution inputs"],"limitations":["shadow evidence does not guarantee profit","small samples use empirical fallbacks"],"performance":{"wall_time_ms":round((time.perf_counter()-start)*1000,3),"peak_traced_memory_mb":round(peak/1048576,3),"ohlc_rows":len(f),"settled_rows":len(settled),"market_rows":len(market)},"shadow_only":True,"production_influence_enabled":False};result["performance"]["serialized_result_bytes"]=len(_json(result).encode());out["quant_research_v6"]=result;out["quant_research_v6_ai_evidence"]={"identity":identity,"summary":summary,"market_statuses":statuses,"shadow_only":True};out.setdefault("metadata",{})["quant_research_v6_status"]=summary["overall_status"];bundle=build_bundle(result,market);state["quant_v6_market_history_page_20260622"]=market.head(240).copy(deep=False) if not market.empty else pd.DataFrame();state["quant_v6_market_statuses_20260622"]=statuses;del market,f,settled;gc.collect();return out,{BUNDLE_KEY:bundle},{"status":summary["overall_status"],"generation_id":identity["source_generation_id"],"market_statuses":statuses,"performance":result["performance"]}
def query_v6_market_history(*,search="",limit=240,db_path=DB_PATH):
 con=sqlite3.connect(str(db_path));ensure_schema(con);sql="SELECT * FROM quant_research_v6_market_history";params=[]
 if search:sql+=" WHERE upper(symbol||' '||timeframe||' '||session||' '||drift_state) LIKE ?";params.append(f"%{search.upper()}%")
 sql+=" ORDER BY event_time_utc DESC LIMIT ?";params.append(max(1,min(int(limit),2000)))
 try:return pd.read_sql_query(sql,con,params=params)
 finally:con.close()

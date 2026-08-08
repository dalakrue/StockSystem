"""Sequential compact EURUSD/XAUUSD H1/M1 history collection."""
from __future__ import annotations
from contextlib import contextmanager
from typing import Any,Callable,Mapping,MutableMapping
from zoneinfo import ZoneInfo
import gc,numpy as np,pandas as pd
from core.quant_research_v6_contract_20260622 import IMPLEMENTATION_VERSION,normalize_completed_ohlc
from core.shared_broker_time_20260622 import frame_to_shared_broker_clock,shared_broker_time_provider
LOGIC_VERSION=IMPLEMENTATION_VERSION
COMBINATIONS=(("EURUSD","H1"),("EURUSD","M1"),("XAUUSD","H1"),("XAUUSD","M1"));MAX_H1_ROWS=600;MAX_M1_ROWS=1500

def _active(h,s,e):return s<=h<e if s<=e else h>=s or h<e
def classify_sessions(ts_utc,state):
 ts=pd.Timestamp(ts_utc)
 if ts.tzinfo is None:ts=ts.tz_localize("UTC")
 else:ts=ts.tz_convert("UTC")
 lh=ts.tz_convert(ZoneInfo("Europe/London"));nh=ts.tz_convert(ZoneInfo("America/New_York"));lf=lh.hour+lh.minute/60;nf=nh.hour+nh.minute/60
 l=_active(lf,float(state.get("quant_v6_london_start_hour",8)),float(state.get("quant_v6_london_end_hour",17)));n=_active(nf,float(state.get("quant_v6_new_york_start_hour",8)),float(state.get("quant_v6_new_york_end_hour",17)));o=l and n
 return {"session":"LONDON_NEW_YORK_OVERLAP" if o else "LONDON" if l else "NEW_YORK" if n else "OTHER","london_active":bool(l),"new_york_active":bool(n),"london_new_york_overlap":bool(o)}
@contextmanager
def _preserve(state):
 keys=("last_df","symbol","timeframe","source","connected","last_fetch");old={k:state.get(k) for k in keys};exists={k:k in state for k in keys}
 try:yield
 finally:
  for k in keys:
   if exists[k]:state[k]=old[k]
   else:state.pop(k,None)
def _default_fetcher(state,symbol,timeframe,bars):
 from core.data_connectors import refresh_now
 return refresh_now(symbol=symbol,timeframe=timeframe,bars=bars,mode=str(state.get("connector_mode") or "") or None,api_key=state.get("twelve_api_key",""),bridge_url=state.get("doo_bridge_url",""),bridge_token=state.get("doo_bridge_token",""),allow_demo=bool(state.get("allow_safe_demo",False)))
def _facts(c):
 def m(k):return c.get(k) if isinstance(c.get(k),Mapping) else {}
 f=m("final_decision");s=m("scores");r=m("regime");fc=m("forecasts");rel=m("reliability")
 return {"regime":r.get("major_regime") or r.get("current_regime") or "UNAVAILABLE","decision":f.get("final_decision") or c.get("decision") or "UNAVAILABLE","direction":f.get("directional_market_view") or f.get("direction") or "UNAVAILABLE","master":s.get("master") or c.get("master_score"),"entry":s.get("entry") or c.get("entry_score"),"hold":s.get("hold") or c.get("hold_score"),"tp":s.get("tp") or c.get("tp_quality"),"exit":s.get("exit_risk") or c.get("exit_risk"),"trend":s.get("trend_capacity_remaining") or c.get("trend_capacity_remaining"),"forecast":fc.get("direction") or "UNAVAILABLE","confidence":fc.get("confidence") or rel.get("score")}
def compact_frame(raw,*,symbol,timeframe,source,state,canonical,current=False):
 f,_=normalize_completed_ohlc(raw,cutoff_utc=(canonical.get("latest_completed_h1_utc") or canonical.get("latest_completed_candle_time")) if current else None,max_rows=MAX_H1_ROWS if timeframe=="H1" else MAX_M1_ROWS);facts=_facts(canonical);clock=shared_broker_time_provider(state,canonical=canonical);calc=str(clock.get("calculation_id") or canonical.get("run_id") or "");gen=str(clock.get("calculation_generation") or canonical.get("calculation_generation") or calc)
 f["return_1"]=f.close.pct_change();f["candle_range"]=f.high-f.low;f["volatility"]=f.candle_range.rolling(14,min_periods=3).mean();rows=[]
 for i,row in f.iterrows():
  ts=row.event_time_utc;sess=classify_sessions(ts,state);is_cur=current and i==f.index[-1]
  rows.append({"event_time_utc":ts,"calculation_id":calc,"generation_id":gen,"symbol":symbol,"timeframe":timeframe,"source":source,"completed_status":"COMPLETED",**sess,"close":row.close,"return_1":row.return_1,"candle_range":row.candle_range,"ATR or existing volatility":row.volatility,"available spread":None,"available slippage":None,"expected move":None,"regime":facts["regime"] if is_cur else "UNAVAILABLE","protected decision":facts["decision"] if is_cur else "UNAVAILABLE","master score":facts["master"] if is_cur else None,"entry score":facts["entry"] if is_cur else None,"hold score":facts["hold"] if is_cur else None,"TP quality":facts["tp"] if is_cur else None,"exit risk":facts["exit"] if is_cur else None,"trend capacity":facts["trend"] if is_cur else None,"forecast direction":facts["forecast"] if is_cur else "UNAVAILABLE","forecast confidence":facts["confidence"] if is_cur else None,"realized direction when settled":"UNAVAILABLE","direction correct when settled":None,"absolute forecast error when settled":None,"signal survival probability":None,"churn risk":None,"drift state":"UNAVAILABLE","data_quality_status":"AVAILABLE","synchronization_status":"ALIGNED_UTC_BUCKET","logic_version":LOGIC_VERSION})
 out=pd.DataFrame(rows);return frame_to_shared_broker_clock(out,state,canonical=canonical,include_myanmar=True,reject_future_incomplete=False,hide_raw_utc=False) if not out.empty else out
def collect_multi_market_history(state:MutableMapping[str,Any],canonical:Mapping[str,Any],*,current_h1:pd.DataFrame,fetcher:Callable|None=None):
 fetcher=fetcher or _default_fetcher;parts=[];statuses=[];enabled=bool(state.get("quant_v6_multi_market_enabled",True))
 for symbol,timeframe in COMBINATIONS:
  raw=pd.DataFrame();source="UNAVAILABLE"
  try:
   if (symbol,timeframe)==("EURUSD","H1") and isinstance(current_h1,pd.DataFrame) and not current_h1.empty:raw=current_h1;ok=True;source=str(canonical.get("source") or state.get("source") or "CANONICAL");msg="reused canonical EURUSD H1"
   elif not enabled:ok=False;msg="multi-market collection disabled in connector expander"
   else:
    with _preserve(state):raw,ok,source,msg=fetcher(state,symbol,timeframe,600 if timeframe=="H1" else MAX_M1_ROWS)
   if ok and isinstance(raw,pd.DataFrame) and not raw.empty:
    compact=compact_frame(raw,symbol=symbol,timeframe=timeframe,source=str(source),state=state,canonical=canonical,current=(symbol,timeframe)==("EURUSD","H1"));parts.append(compact);statuses.append({"symbol":symbol,"timeframe":timeframe,"status":"AVAILABLE","source":source,"rows":len(compact),"message":msg})
   else:statuses.append({"symbol":symbol,"timeframe":timeframe,"status":"UNAVAILABLE","source":source,"rows":0,"reason":msg or "connector returned no evidence"})
  except Exception as e:statuses.append({"symbol":symbol,"timeframe":timeframe,"status":"UNAVAILABLE","source":source,"rows":0,"reason":f"{type(e).__name__}: {e}"})
  finally:
   del raw;gc.collect()
 combined=pd.DataFrame.from_records([record for part in parts for record in part.to_dict("records")]) if parts else pd.DataFrame()
 if not combined.empty:
  combined["_bucket"]=pd.to_datetime(combined.event_time_utc,utc=True).dt.floor("h");count=combined.groupby(["_bucket","timeframe"])["symbol"].transform("nunique");combined["gap_flag"]=np.where((combined.timeframe=="H1")&(count<2),"CROSS_SYMBOL_GAP","");combined=combined.drop(columns="_bucket").sort_values("event_time_utc",ascending=False).reset_index(drop=True)
 return combined,statuses

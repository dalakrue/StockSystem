"""Additive idempotent SQLite storage for Regime Intelligence snapshots."""
from __future__ import annotations
from typing import Any, Mapping
import json, sqlite3

DDL="""CREATE TABLE IF NOT EXISTS regime_intelligence_history_20260624(
 run_id TEXT NOT NULL, completed_candle_time TEXT NOT NULL, symbol TEXT NOT NULL,
 timeframe TEXT NOT NULL, regime_version TEXT NOT NULL, winning_regime TEXT,
 posterior_json TEXT NOT NULL, transition_json TEXT NOT NULL, regime_age REAL,
 expected_remaining_duration REAL, changepoint_probability REAL,
 structural_break_status TEXT, ood_score REAL, model_agreement REAL,
 reliability INTEGER NOT NULL, failed_gates_json TEXT NOT NULL,
 data_signature TEXT NOT NULL, provenance_json TEXT NOT NULL, payload_json TEXT NOT NULL,
 PRIMARY KEY(run_id, completed_candle_time, regime_version)
)"""

def save(conn:sqlite3.Connection,payload:Mapping[str,Any])->dict[str,Any]:
 conn.execute(DDL); cur=payload.get("current") or {}; ens=payload.get("ensemble") or {}; fil=payload.get("filardo") or {}; hs=payload.get("hsmm") or {}; boc=payload.get("bocpd") or {}; ood=payload.get("ood") or {}; prov=payload.get("provenance") or {}
 row=(str(payload.get("run_id")),str(payload.get("completed_candle_time") or "UNAVAILABLE"),str(payload.get("symbol") or "EURUSD"),str(payload.get("timeframe") or "H1"),str(payload.get("version")),cur.get("major_regime"),json.dumps(ens.get("posterior") or {},sort_keys=True),json.dumps(fil.get("matrix") or {},sort_keys=True),hs.get("current_age"),hs.get("expected_remaining_duration"),boc.get("changepoint_probability"),json.dumps(payload.get("structural_breaks") or {},sort_keys=True),ood.get("ood_score"),cur.get("model_agreement"),int(bool(cur.get("regime_reliability"))),json.dumps(cur.get("failed_gates") or []),str(prov.get("data_signature") or ""),json.dumps(prov,sort_keys=True),json.dumps(payload,sort_keys=True,default=str))
 conn.execute("INSERT OR REPLACE INTO regime_intelligence_history_20260624 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",row); conn.commit()
 return {"ok":True,"rows":1,"idempotent_key":[row[0],row[1],row[4]]}

__all__=["DDL","save"]

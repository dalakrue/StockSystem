"""Idempotent additive store for SHADOW governance and audit evidence."""
from __future__ import annotations
import json, sqlite3
from typing import Any, Mapping
SCHEMA_VERSION="shadow-intelligence-audit-1.0"

def ensure_schema(conn: sqlite3.Connection)->None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS shadow_forecast_origin_audit(
      run_id TEXT NOT NULL,symbol TEXT NOT NULL,timeframe TEXT NOT NULL,forecast_origin TEXT NOT NULL,horizon INTEGER NOT NULL,model_version TEXT NOT NULL,
      broker_candle_timestamp TEXT NOT NULL,production_decision TEXT NOT NULL,origin_forecast REAL,origin_lower REAL,origin_upper REAL,forecast_mean REAL,forecast_median REAL,
      quantiles_json TEXT NOT NULL,probability_up REAL,probability_down REAL,probability_neutral REAL,model_weights_json TEXT NOT NULL,model_disagreement REAL,interval_width REAL,
      calibration_start TEXT,calibration_end TEXT,calibration_fallback_reason TEXT,regime_at_origin TEXT,session_at_origin TEXT,samples_path TEXT,created_at TEXT NOT NULL,
      PRIMARY KEY(run_id,symbol,timeframe,forecast_origin,horizon,model_version));
    CREATE TABLE IF NOT EXISTS shadow_horizon_settlement_audit(
      run_id TEXT NOT NULL,forecast_origin TEXT NOT NULL,horizon INTEGER NOT NULL,model_version TEXT NOT NULL,maturity_time TEXT,actual REAL,status TEXT NOT NULL,
      crps REAL,crps_method TEXT,mae REAL,pinball_loss REAL,interval_score REAL,covered INTEGER,interval_width REAL,settled_at TEXT,
      PRIMARY KEY(run_id,forecast_origin,horizon,model_version));
    CREATE TABLE IF NOT EXISTS shadow_governance_audit(
      run_id TEXT NOT NULL,model_version TEXT NOT NULL,drift_state TEXT NOT NULL,validation_status TEXT NOT NULL,pbo_status TEXT NOT NULL,
      production_decision TEXT NOT NULL,production_decision_unchanged INTEGER NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL,
      PRIMARY KEY(run_id,model_version));
    """); conn.commit()

def save_governance(conn:sqlite3.Connection,payload:Mapping[str,Any])->dict[str,Any]:
    ensure_schema(conn); run_id=str(payload.get("run_id") or ""); version=str(payload.get("model_version") or "")
    if not run_id or not version:return {"ok":False,"reason":"RUN_ID_AND_MODEL_VERSION_REQUIRED"}
    created=str(payload.get("broker_candle_timestamp") or payload.get("created_at") or "")
    conn.execute("INSERT OR IGNORE INTO shadow_governance_audit VALUES(?,?,?,?,?,?,?,?,?)",(run_id,version,str(payload.get("drift_state") or "INSUFFICIENT_EVIDENCE"),str(payload.get("validation_status") or "INSUFFICIENT_SAMPLE"),str(payload.get("pbo_status") or "INSUFFICIENT_SAMPLE"),str(payload.get("production_decision") or "WAIT"),1,json.dumps(payload,sort_keys=True,default=str),created))
    conn.commit(); return {"ok":True,"run_id":run_id,"schema_version":SCHEMA_VERSION}
__all__=["ensure_schema","save_governance","SCHEMA_VERSION"]

"""Additive idempotent SQLite storage for research-grade v16 snapshots."""
from __future__ import annotations
import json, sqlite3

def ensure_schema(conn:sqlite3.Connection):
 conn.execute('''CREATE TABLE IF NOT EXISTS research_grade_v16_snapshot(run_id TEXT PRIMARY KEY, forecast_origin TEXT NOT NULL, model_version TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
 conn.execute('''CREATE TABLE IF NOT EXISTS research_grade_v16_origin(run_id TEXT NOT NULL,horizon INTEGER NOT NULL,forecast_origin TEXT NOT NULL,target_maturity TEXT,original_point_forecast REAL,origin_lower REAL,origin_upper REAL,settlement_status TEXT NOT NULL,model_version TEXT NOT NULL,payload_json TEXT NOT NULL,PRIMARY KEY(run_id,horizon))''')
 conn.commit()

def save(conn:sqlite3.Connection,payload):
 ensure_schema(conn); blob=json.dumps(payload,sort_keys=True,default=str)
 try:
  conn.execute('BEGIN')
  conn.execute('INSERT OR IGNORE INTO research_grade_v16_snapshot(run_id,forecast_origin,model_version,payload_json) VALUES(?,?,?,?)',(str(payload.get('run_id')),str(payload.get('forecast_origin')),str(payload.get('model_version')),blob))
  for h,row in (payload.get('ensemble') or {}).items():
   iv=row.get('calibrated_interval') or {}
   conn.execute('INSERT OR IGNORE INTO research_grade_v16_origin VALUES(?,?,?,?,?,?,?,?,?,?)',(str(payload.get('run_id')),int(h),str(payload.get('forecast_origin')),str((payload.get('target_maturity') or {}).get(str(h))),row.get('point'),iv.get('lower'),iv.get('upper'),str(payload.get('settlement_status')),str(payload.get('model_version')),json.dumps(row,sort_keys=True,default=str)))
  conn.commit(); return {'ok':True}
 except Exception:
  conn.rollback(); raise

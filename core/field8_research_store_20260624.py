"""Idempotent append-only SQLite schema for the 2026-06-24 shadow research stack."""
from __future__ import annotations
import sqlite3,time,json
from pathlib import Path
TABLES=('forecast_origin_distribution','horizon_settlement','conformal_state','probabilistic_scores','changepoint_history','shadow_regime_transition','conditional_predictive_tests','model_confidence_sets','challenger_forecasts','meta_labels','shadow_ensemble_weights','research_promotion_registry')
class ResearchStore:
 def __init__(self,path='data/field8_integrated_history.sqlite3'):self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.migrate()
 def connect(self):
  c=sqlite3.connect(self.path,timeout=30);c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA busy_timeout=30000');return c
 def migrate(self):
  with self.connect() as c:
   for t in TABLES:
    c.execute(f'''CREATE TABLE IF NOT EXISTS {t}(run_id TEXT NOT NULL,origin_time TEXT NOT NULL,symbol TEXT NOT NULL,timeframe TEXT NOT NULL,horizon INTEGER NOT NULL,model_version TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(run_id,origin_time,symbol,timeframe,horizon,model_version))''')
 def append(self,table,key,payload,retries=4):
  if table not in TABLES:raise ValueError('unknown research table')
  sql=f'INSERT INTO {table}(run_id,origin_time,symbol,timeframe,horizon,model_version,payload_json) VALUES(?,?,?,?,?,?,?)'
  vals=(*key,json.dumps(payload,sort_keys=True,default=str))
  for i in range(retries):
   try:
    with self.connect() as c:c.execute('BEGIN IMMEDIATE');c.execute(sql,vals)
    return True
   except sqlite3.IntegrityError:return False
   except sqlite3.OperationalError:
    if i+1==retries:raise
    time.sleep(.05*2**i)

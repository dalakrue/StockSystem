"""Append-only bounded persistence for v15 shadow evidence."""
from __future__ import annotations
import sqlite3,json
from pathlib import Path
TABLES=('shadow_dma_state_v15','model_confidence_set_v15','proper_scores_v15','sequential_conformal_v15','subset_ensemble_v15','changepoint_v15','hsmm_duration_v15','har_volatility_v15','venn_abers_v15','conformal_risk_v15','promotion_report_v15')
class V15Store:
 def __init__(self,path='data/field8_integrated_history.sqlite3',retention=5000):self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.retention=int(retention);self.migrate()
 def connect(self):
  c=sqlite3.connect(self.path,timeout=30);c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA busy_timeout=30000');return c
 def migrate(self):
  with self.connect() as c:
   for t in TABLES:c.execute(f'''CREATE TABLE IF NOT EXISTS {t}(run_id TEXT NOT NULL,origin_time TEXT NOT NULL,horizon INTEGER NOT NULL,entity_id TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(run_id,origin_time,horizon,entity_id))''')
 def append(self,table,run_id,origin_time,horizon,entity_id,payload):
  if table not in TABLES:raise ValueError(table)
  with self.connect() as c:
   try:c.execute(f'INSERT INTO {table}(run_id,origin_time,horizon,entity_id,payload_json) VALUES(?,?,?,?,?)',(run_id,origin_time,int(horizon),entity_id,json.dumps(payload,sort_keys=True,default=str)));inserted=True
   except sqlite3.IntegrityError:inserted=False
   c.execute(f'''DELETE FROM {table} WHERE rowid IN (SELECT rowid FROM {table} ORDER BY created_at DESC LIMIT -1 OFFSET ?)''',(self.retention,))
  return inserted

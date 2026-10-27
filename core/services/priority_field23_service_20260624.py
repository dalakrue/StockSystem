"""Settings-only publisher for priority Field 2/3 intelligence."""
from __future__ import annotations
from typing import Any, MutableMapping
import sqlite3, json, time
from core.storage.database import DB_PATH

KEY='priority_field23_intelligence_20260624'

def _migrate(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS priority_field23_snapshots (run_id TEXT NOT NULL, forecast_origin TEXT NOT NULL, created_at REAL NOT NULL, prediction_json TEXT NOT NULL, regime_json TEXT NOT NULL, model_version TEXT NOT NULL, PRIMARY KEY(run_id, forecast_origin))")
    conn.commit()

def build_and_publish_priority_field23(state:MutableMapping[str,Any], source_snapshot:Any|None=None)->dict[str,Any]:
    if source_snapshot is None:
        from core.canonical_sync_v9 import read_snapshot_for_lunch
        source_snapshot=read_snapshot_for_lunch(state)
    if source_snapshot is None:return {'ok':False,'status':'NO_CANONICAL_SNAPSHOT','shadow_only':True}
    from research.priority_field23_engine_20260624 import evaluate
    payload=evaluate(state,source_snapshot)
    if payload.get('ok'):
        with sqlite3.connect(str(DB_PATH)) as conn:
            _migrate(conn); p=payload['prediction_path_snapshot']; r=payload['regime_intelligence_snapshot']
            conn.execute('INSERT OR IGNORE INTO priority_field23_snapshots VALUES (?,?,?,?,?,?)',(payload['run_id'],p['forecast_origin'],time.time(),json.dumps(p,sort_keys=True),json.dumps(r,sort_keys=True),payload['model_version']));conn.commit()
        state[KEY]=payload; state['priority_field23_previous_weights']=payload['prediction_path_snapshot']['model_weights']
    return payload

def read_saved(state):
    p=state.get(KEY); return p if isinstance(p,dict) else {}

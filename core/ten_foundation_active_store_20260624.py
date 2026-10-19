"""Idempotent additive SQLite persistence for ten-foundation origin snapshots."""
from __future__ import annotations
import json, sqlite3
from typing import Any, Mapping

def migrate(conn:sqlite3.Connection)->None:
    with conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_versions(name TEXT PRIMARY KEY, version TEXT NOT NULL, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("""CREATE TABLE IF NOT EXISTS ten_foundation_snapshots(run_id TEXT PRIMARY KEY,broker_candle_time TEXT NOT NULL,symbol TEXT NOT NULL,timeframe TEXT NOT NULL,production_decision TEXT NOT NULL,payload_hash TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS ten_foundation_origins(run_id TEXT NOT NULL,horizon INTEGER NOT NULL,origin_broker_time TEXT NOT NULL,symbol TEXT NOT NULL,timeframe TEXT NOT NULL,settlement_status TEXT NOT NULL,origin_prediction REAL,origin_lower REAL,origin_upper REAL,origin_weights_json TEXT,origin_regime_json TEXT,origin_changepoint_json TEXT,origin_actionability_json TEXT,origin_counterfactual_json TEXT,actual REAL,realized_error REAL,settled_at TEXT,PRIMARY KEY(run_id,horizon))""")
        for sql in ("CREATE INDEX IF NOT EXISTS idx_ten_origin_time ON ten_foundation_origins(origin_broker_time)","CREATE INDEX IF NOT EXISTS idx_ten_symbol_tf ON ten_foundation_origins(symbol,timeframe)","CREATE INDEX IF NOT EXISTS idx_ten_status ON ten_foundation_origins(settlement_status)"): conn.execute(sql)
        conn.execute("INSERT OR IGNORE INTO schema_versions(name,version) VALUES('ten_foundation_active','1.0')")

def save(conn:sqlite3.Connection,p:Mapping[str,Any])->dict:
    migrate(conn); blob=json.dumps(p,sort_keys=True,default=str)
    with conn:
        conn.execute("INSERT OR IGNORE INTO ten_foundation_snapshots(run_id,broker_candle_time,symbol,timeframe,production_decision,payload_hash,payload_json) VALUES(?,?,?,?,?,?,?)",(str(p['run_id']),str(p.get('broker_candle_time','')),str(p.get('symbol','EURUSD')),str(p.get('timeframe','H1')),str(p.get('production_decision','WAIT')),str(p.get('payload_hash','')),blob))
        for hs,row in (p.get('horizons') or {}).items():
            conf=row.get('adaptive_conformal') or {}; ens=row.get('shadow_ensemble') or {}
            conn.execute("""INSERT OR IGNORE INTO ten_foundation_origins(run_id,horizon,origin_broker_time,symbol,timeframe,settlement_status,origin_prediction,origin_lower,origin_upper,origin_weights_json,origin_regime_json,origin_changepoint_json,origin_actionability_json,origin_counterfactual_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(str(p['run_id']),int(hs),str(p.get('broker_candle_time','')),str(p.get('symbol','EURUSD')),str(p.get('timeframe','H1')),'PENDING',row.get('production_prediction'),conf.get('origin_lower'),conf.get('origin_upper'),json.dumps(ens.get('weights',{}),sort_keys=True),json.dumps(p.get('markov_regime',{}),sort_keys=True),json.dumps(p.get('changepoint',{}),sort_keys=True),json.dumps(p.get('meta_label',{}),sort_keys=True),json.dumps(p.get('field9',{}),sort_keys=True)))
    return {'ok':True,'run_id':str(p['run_id']),'rows':len(p.get('horizons') or {})}

def settle(conn:sqlite3.Connection,run_id:str,horizon:int,actual:float,settled_at:str)->bool:
    """Settlement only fills settlement columns; immutable origin columns are untouched."""
    with conn:
        cur=conn.execute("UPDATE ten_foundation_origins SET actual=COALESCE(actual,?),realized_error=COALESCE(realized_error,ABS(?-origin_prediction)),settled_at=COALESCE(settled_at,?),settlement_status='FULLY_SETTLED' WHERE run_id=? AND horizon=? AND actual IS NULL",(actual,actual,settled_at,run_id,horizon))
    return cur.rowcount==1

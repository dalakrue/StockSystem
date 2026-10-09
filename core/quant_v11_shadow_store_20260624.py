from __future__ import annotations
import json, sqlite3
from pathlib import Path
from typing import Any, Mapping
MIGRATION=Path(__file__).resolve().parents[1]/'migrations'/'20260624_v11_advanced_validation.sql'
def ensure_schema(conn:sqlite3.Connection)->None: conn.executescript(MIGRATION.read_text(encoding='utf-8'))
def save(conn:sqlite3.Connection,payload:Mapping[str,Any])->dict[str,Any]:
 ensure_schema(conn); run_id=str(payload.get('run_id') or ''); research=payload.get('research') or {}
 conn.execute('''INSERT OR REPLACE INTO quant_v11_shadow_validation(run_id,prediction_id,symbol,timeframe,broker_candle_time,horizon,regime,model_version,feature_hash,configuration_hash,calculation_version,shadow_only,settled_status,data_quality_status,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(run_id,'',str(payload.get('symbol') or 'EURUSD'),str(payload.get('timeframe') or 'H1'),str(payload.get('broker_candle_time') or ''),0,'','v11-advanced-validation','',str(payload.get('snapshot_hash') or ''),'20260624',1,'MATURED_ONLY','OK',json.dumps(research,default=str,sort_keys=True)))
 conn.commit(); return {'ok':True,'run_id':run_id,'rows':1}
__all__=['ensure_schema','save']

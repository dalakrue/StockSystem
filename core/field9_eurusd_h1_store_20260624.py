from __future__ import annotations
import json,sqlite3
from datetime import datetime,timezone
SCHEMA_VERSION='field9-store-1.0'
def ensure_schema(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS field9_eurusd_h1_snapshot(run_id TEXT PRIMARY KEY,generation_id TEXT,snapshot_hash TEXT,payload_json TEXT NOT NULL,created_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS field9_eurusd_h1_history(origin_time_utc TEXT PRIMARY KEY,run_id TEXT NOT NULL,broker_candle_time TEXT,payload_json TEXT NOT NULL,created_at TEXT NOT NULL);''');conn.commit()
def save(conn,payload):
    ensure_schema(conn); now=datetime.now(timezone.utc).isoformat(); ident=payload.get('identity',{}); rid=str(ident.get('run_id') or '')
    if not rid:return {'ok':False,'reason':'RUN_ID_REQUIRED'}
    text=json.dumps(payload,sort_keys=True,default=str,separators=(',',':'))
    conn.execute('INSERT OR REPLACE INTO field9_eurusd_h1_snapshot VALUES(?,?,?,?,?)',(rid,str(ident.get('generation_id')or rid),str(ident.get('snapshot_hash')or''),text,now))
    for row in payload.get('history',[]):
        origin=str(row.get('origin_time_utc')or'')
        if origin: conn.execute('INSERT OR IGNORE INTO field9_eurusd_h1_history VALUES(?,?,?,?,?)',(origin,rid,str(row.get('broker_candle_time')or''),json.dumps(row,sort_keys=True,default=str),now))
    conn.commit();return {'ok':True,'run_id':rid,'serialized_result_size':len(text)}
def load_latest(conn):
    ensure_schema(conn);r=conn.execute('SELECT payload_json FROM field9_eurusd_h1_snapshot ORDER BY created_at DESC LIMIT 1').fetchone();return json.loads(r[0]) if r else {}

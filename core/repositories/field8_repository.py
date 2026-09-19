"""Transactional SQLite repository for immutable Field 8 publications."""
from __future__ import annotations
import json, sqlite3, math
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from core.field8_integrated_history_contract_20260624 import Field8Bundle, TABLE_COLUMNS
DEFAULT_PATH=Path('data/field8_integrated_history.sqlite3')
class Field8Repository:
    def __init__(self,path:Path|str=DEFAULT_PATH):self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.migrate()
    def connect(self):con=sqlite3.connect(str(self.path),timeout=20);con.execute('PRAGMA foreign_keys=ON');return con
    def migrate(self):
        with self.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS field8_publications(run_id TEXT NOT NULL,generation_id TEXT NOT NULL,snapshot_hash TEXT NOT NULL,symbol TEXT NOT NULL,timeframe TEXT NOT NULL,schema_version INTEGER NOT NULL,calculation_version TEXT NOT NULL,published INTEGER NOT NULL DEFAULT 0,row_count INTEGER NOT NULL DEFAULT 0,published_at TEXT,source_row_count INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(run_id,generation_id,snapshot_hash))')
            cols={r[1] for r in c.execute('PRAGMA table_info(field8_publications)')}
            if 'published_at' not in cols:c.execute('ALTER TABLE field8_publications ADD COLUMN published_at TEXT')
            if 'source_row_count' not in cols:c.execute('ALTER TABLE field8_publications ADD COLUMN source_row_count INTEGER NOT NULL DEFAULT 0')
            c.execute('CREATE TABLE IF NOT EXISTS field8_history(run_id TEXT NOT NULL,generation_id TEXT NOT NULL,snapshot_hash TEXT NOT NULL,broker_candle_time TEXT NOT NULL,forecast_origin_time TEXT NOT NULL,forecast_horizon INTEGER NOT NULL,target_time TEXT NOT NULL,symbol TEXT NOT NULL,timeframe TEXT NOT NULL,maturity_status TEXT NOT NULL,payload_json TEXT NOT NULL,PRIMARY KEY(run_id,generation_id,snapshot_hash,symbol,timeframe,broker_candle_time,forecast_origin_time,forecast_horizon,target_time))')
            c.execute('CREATE INDEX IF NOT EXISTS idx_f8_time ON field8_history(broker_candle_time DESC)');c.execute('CREATE INDEX IF NOT EXISTS idx_f8_identity ON field8_history(run_id,generation_id,snapshot_hash)')
    def _validate_row(self,r,b):
        if any(str(r.get(k))!=str(v) for k,v in [('run_id',b.run_id),('generation_id',b.generation_id),('snapshot_hash',b.snapshot_hash),('source_snapshot_hash',b.snapshot_hash)]):raise ValueError('mixed-run or mixed-hash publication')
        origin=pd.Timestamp(r['forecast_origin_time']);target=pd.Timestamp(r['target_time'])
        if target<origin:raise ValueError('future/target ordering invalid')
        for k,v in r.items():
            if 'probability' in k and v not in (None,''):
                try:
                    f=float(v)
                    if math.isfinite(f) and not 0<=f<=1:raise ValueError(f'probability outside [0,1]: {k}')
                except (TypeError,ValueError):
                    if isinstance(v,(int,float)):raise
        for h in (1,2,3,4,6):
            l,u=r.get(f'origin_lower_h{h}'),r.get(f'origin_upper_h{h}')
            try:
                if math.isfinite(float(l)) and math.isfinite(float(u)) and float(l)>float(u):raise ValueError('lower interval exceeds upper')
            except (TypeError,ValueError):pass
        w=r.get('model_weights')
        if isinstance(w,str):
            try:w=json.loads(w)
            except Exception:w={}
        if isinstance(w,dict) and len(w)>1 and abs(sum(float(x) for x in w.values())-1)>1e-6:raise ValueError('model weights do not sum to one')
    def publish(self,bundle:Field8Bundle):
        bundle.validate_identity();keys=set()
        for r in bundle.rows:
            self._validate_row(r,bundle);h=int(r.get('forecast_horizon') or 6);key=(r['run_id'],r['generation_id'],r['snapshot_hash'],r['symbol'],r['timeframe'],r['broker_candle_time'],r['forecast_origin_time'],h,r['target_time'])
            if key in keys:raise ValueError('duplicate Field 8 compound identity key')
            keys.add(key)
        con=self.connect()
        try:
            con.execute('BEGIN IMMEDIATE')
            for r in bundle.rows:
                h=int(r.get('forecast_horizon') or 6);con.execute('INSERT OR IGNORE INTO field8_history VALUES(?,?,?,?,?,?,?,?,?,?,?)',(bundle.run_id,bundle.generation_id,bundle.snapshot_hash,r['broker_candle_time'],r['forecast_origin_time'],h,r['target_time'],bundle.symbol,bundle.timeframe,r['maturity_status'],json.dumps(r,default=str,sort_keys=True)))
            con.execute('INSERT OR REPLACE INTO field8_publications(run_id,generation_id,snapshot_hash,symbol,timeframe,schema_version,calculation_version,published,row_count,published_at,source_row_count) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(bundle.run_id,bundle.generation_id,bundle.snapshot_hash,bundle.symbol,bundle.timeframe,bundle.schema_version,bundle.calculation_version,1,len(bundle.rows),datetime.now(timezone.utc).isoformat(),len(bundle.rows)));con.commit()
        except Exception:con.rollback();raise
        finally:con.close()
        return {'ok':True,'published':True,'rows':len(bundle.rows),'run_id':bundle.run_id,'generation_id':bundle.generation_id,'snapshot_hash':bundle.snapshot_hash,'database_path':str(self.path.resolve()),'publication_timestamp':datetime.now(timezone.utc).isoformat(),'calculation_version':bundle.calculation_version}
    def load(self,run_id,generation_id,snapshot_hash,days=25):
        with self.connect() as c:
            pub=c.execute('SELECT published FROM field8_publications WHERE run_id=? AND generation_id=? AND snapshot_hash=?',(run_id,generation_id,snapshot_hash)).fetchone()
            if not pub or int(pub[0])!=1:return pd.DataFrame(columns=TABLE_COLUMNS)
            rows=c.execute('SELECT payload_json FROM field8_history WHERE run_id=? AND generation_id=? AND snapshot_hash=? ORDER BY broker_candle_time DESC',(run_id,generation_id,snapshot_hash)).fetchall()
        return pd.DataFrame([json.loads(x[0]) for x in rows]).reindex(columns=TABLE_COLUMNS)
    def publication_metadata(self,run_id,generation_id,snapshot_hash):
        with self.connect() as c:
            row=c.execute("SELECT run_id,generation_id,snapshot_hash,published,row_count,published_at,calculation_version,source_row_count FROM field8_publications WHERE run_id=? AND generation_id=? AND snapshot_hash=?",(str(run_id),str(generation_id),str(snapshot_hash))).fetchone()
        if not row:return None
        keys=("run_id","generation_id","snapshot_hash","published","row_count","published_at","calculation_version","source_row_count")
        return dict(zip(keys,row))

    def latest_for_run(self,run_id):
        with self.connect() as c:
            row=c.execute("SELECT run_id,generation_id,snapshot_hash,published,row_count,published_at,calculation_version,source_row_count FROM field8_publications WHERE run_id=? AND published=1 ORDER BY published_at DESC LIMIT 1",(str(run_id),)).fetchone()
        if not row:return None
        keys=("run_id","generation_id","snapshot_hash","published","row_count","published_at","calculation_version","source_row_count")
        return dict(zip(keys,row))


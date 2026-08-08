from __future__ import annotations
import math, time
from typing import Any, Mapping, Sequence

def unavailable(reason="INSUFFICIENT_DATA"):
    return {"status": reason, "available": False, "shadow_only": True, "production_influence_enabled": False}

def finite(values):
    out=[]
    for v in values or []:
        try:
            x=float(v)
            if math.isfinite(x): out.append(x)
        except Exception: pass
    return out

def clip(x,lo,hi): return max(lo,min(hi,x))

import json, sqlite3
from pathlib import Path

def save(payload,path="data/quant_research_v14.sqlite3"):
 p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); con=sqlite3.connect(p); con.execute("CREATE TABLE IF NOT EXISTS quant_research_v14(run_id TEXT PRIMARY KEY,payload_json TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)"); rid=str((payload.get("identity") or {}).get("run_id") or "UNAVAILABLE"); con.execute("INSERT OR REPLACE INTO quant_research_v14(run_id,payload_json) VALUES (?,?)",(rid,json.dumps(payload,default=str,sort_keys=True))); con.commit(); con.close(); return {"ok":True,"run_id":rid,"path":str(p)}

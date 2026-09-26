from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]/"data"/"arcef_sv"; ROOT.mkdir(parents=True,exist_ok=True)
def _append(path, record, unique_key):
    rows=[]
    if path.exists():
        try: rows=json.loads(path.read_text(encoding="utf-8"))
        except Exception: rows=[]
    if any(str(x.get(unique_key))==str(record.get(unique_key)) for x in rows): return rows
    rows.append(record); path.write_text(json.dumps(rows,indent=2,default=str),encoding="utf-8"); return rows
def append_history(record): return _append(ROOT/"history.json",record,"run_id")[-25:][::-1]
def register_experiment(record): return _append(ROOT/"experiments.json",record,"experiment_id")
def version_history():
    p=ROOT/"experiments.json"
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return []

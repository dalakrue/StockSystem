"""Settings-only publisher for unified V19 shadow evidence."""
from dataclasses import asdict,is_dataclass
from typing import Mapping
from core.canonical.snapshot import load_canonical_snapshot
from core.unified_shadow_pipeline_v19_20260624 import publish
def _mapping(v):
    if isinstance(v,Mapping): return dict(v)
    if is_dataclass(v): return asdict(v)
    return dict(vars(v)) if hasattr(v,'__dict__') else {}
def build_and_publish_unified_shadow_v19(state):
    snap=load_canonical_snapshot(state)
    if snap is None:return {"ok":False,"status":"MISSING_CANONICAL","shadow_only":True}
    return publish(state,_mapping(snap),state.get("research_grade_system_v17_20260624"))

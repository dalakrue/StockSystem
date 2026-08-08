from dataclasses import asdict,is_dataclass
from typing import Mapping
from core.canonical.snapshot import load_canonical_snapshot
from core.research_adaptation_v18_20260624 import publish

def build_and_publish_research_adaptation_v18(state):
    snap=load_canonical_snapshot(state)
    if snap is None:return {'ok':False,'status':'MISSING','shadow_only':True}
    raw=dict(snap) if isinstance(snap,Mapping) else asdict(snap) if is_dataclass(snap) else vars(snap)
    return publish(state,raw)

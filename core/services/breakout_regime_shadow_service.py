from core.canonical.snapshot import load_canonical_snapshot
from core.breakout_regime_shadow_20260624 import publish

def build_and_publish_breakout_regime_shadow(state):
    snap=load_canonical_snapshot(state)
    if snap is None: return {"ok":False,"status":"NO_CANONICAL_SNAPSHOT","shadow_only":True}
    return publish(state,snap)

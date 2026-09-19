from __future__ import annotations

def build_view_model(context):
    return {"context": context, "decision": context.snapshot.decision, "reliability": context.snapshot.reliability}

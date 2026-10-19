from __future__ import annotations

def build_view_model(context):
    return {"context": context, "regime": context.snapshot.regime, "age": context.snapshot.regime_age}

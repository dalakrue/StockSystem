from __future__ import annotations

def build_view_model(context):
    return {"context": context, "predictions": dict(context.snapshot.predictions), "current_price": context.snapshot.current_price}

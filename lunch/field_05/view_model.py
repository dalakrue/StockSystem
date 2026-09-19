from __future__ import annotations

def build_view_model(context):
    return {"context": context, "fact_scope": ("decision", "regime", "priority", "reliability", "prediction", "research", "history")}

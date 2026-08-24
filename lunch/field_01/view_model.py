from __future__ import annotations

def build_view_model(context):
    return {"context": context, "run_id": context.snapshot.run_id, "broker_candle_time": context.snapshot.broker_candle_time}

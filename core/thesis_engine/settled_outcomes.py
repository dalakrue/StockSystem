from __future__ import annotations

def outcome_schema():
    return ("outcome_horizon","realized_return","realized_direction","maximum_favorable_excursion","maximum_adverse_excursion","target_hit","stop_hit","settlement_timestamp")
def exclude_incomplete(rows, completed_candle):
    return [r for r in rows if str(r.get("broker_candle") or r.get("time") or "") <= str(completed_candle)]

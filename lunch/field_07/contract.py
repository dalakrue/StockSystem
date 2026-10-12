from __future__ import annotations


def validate(context) -> list[str]:
    errors: list[str] = []
    if not context.snapshot.run_id:
        errors.append("Field 7 requires a valid canonical run ID.")
    if context.snapshot.symbol != "EURUSD" or context.snapshot.timeframe != "H1":
        errors.append("Field 7 is scientifically scoped to EURUSD H1; the production decision remains unchanged.")
    return errors

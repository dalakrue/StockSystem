"""Validation for the V11 immutable Lunch contract."""
from __future__ import annotations

from core.canonical.snapshot import CanonicalRunSnapshot


def validate_snapshot(snapshot: CanonicalRunSnapshot | None) -> list[str]:
    if snapshot is None:
        return ["No canonical snapshot is available. Use Settings → Run Calculation + Open Lunch."]
    errors: list[str] = []
    for name in ("run_id", "symbol", "timeframe", "decision", "regime"):
        if not str(getattr(snapshot, name, "") or "").strip():
            errors.append(f"Missing canonical {name}.")
    if snapshot.broker_candle_time.timestamp() <= 0:
        errors.append("Missing canonical broker candle time.")
    if snapshot.priority < 0 or snapshot.priority > 100:
        errors.append("Priority is outside 0–100.")
    if snapshot.reliability < 0 or snapshot.reliability > 100:
        errors.append("Reliability is outside 0–100.")
    if snapshot.uncertainty < 0 or snapshot.uncertainty > 100:
        errors.append("Uncertainty is outside 0–100.")
    return errors

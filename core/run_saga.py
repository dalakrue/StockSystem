"""Recoverable run saga for multi-symbol Field 10 authority workflow."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

@dataclass
class SagaStep:
    run_id: str
    stage: str
    status: str = "PENDING"
    retry_allowed: bool = True
    compensation_action: str = "record_failure_and_continue"
    last_error: str = ""
    completed_at: str = ""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_saga_ledger(run_id: str, stages: list[str]) -> list[dict[str, Any]]:
    return [asdict(SagaStep(run_id=run_id, stage=s)) for s in stages]


def mark_stage(ledger: list[dict[str, Any]], stage: str, status: str, error: str = "") -> list[dict[str, Any]]:
    found = False
    for item in ledger:
        if item.get("stage") == stage:
            item["status"] = status
            item["last_error"] = error
            item["completed_at"] = now_utc() if status in {"COMPLETE","FAILED","PARTIAL_READY"} else ""
            found = True
            break
    if not found:
        ledger.append(asdict(SagaStep(run_id=ledger[0].get("run_id", "run") if ledger else "run", stage=stage, status=status, last_error=error, completed_at=now_utc())))
    return ledger

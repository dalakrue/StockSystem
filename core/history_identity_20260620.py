"""Common identity contract for all disk-backed historical evidence.

This module is deliberately independent of Streamlit.  It standardizes the
identity and event-time fields that let every history row be traced back to one
completed canonical EURUSD H1 generation without changing any protected output.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Mapping

import pandas as pd

from core.generation_identity_20260707 import numeric_generation

IDENTITY_COLUMNS = (
    "calculation_id",
    "calculation_generation",
    "run_id",
    "symbol",
    "timeframe",
    "source",
    "latest_completed_h1",
    "record_time",
    "target_time",
    "horizon",
    "data_signature",
    "logic_version",
    "condition",
    "sample_count",
    "settled_status",
    "is_revision",
    "created_at",
)

HISTORY_LOGIC_VERSION = "history-evidence-20260620-v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    return None if pd.isna(ts) else ts.isoformat()


def canonical_history_identity(
    canonical: Mapping[str, Any],
    *,
    record_time: Any | None = None,
    target_time: Any | None = None,
    horizon: int | None = None,
    condition: str = "",
    sample_count: int | None = None,
    settled_status: str = "UNSETTLED",
    is_revision: bool = False,
    logic_version: str = HISTORY_LOGIC_VERSION,
) -> dict[str, Any]:
    """Build the shared history identity without deriving a trading decision."""
    calc_id = str(canonical.get("canonical_calculation_id") or canonical.get("calculation_id") or canonical.get("run_id") or "")
    completed = _iso(
        canonical.get("latest_completed_candle_time")
        or canonical.get("latest_completed_h1")
        or (canonical.get("market") or {}).get("latest_completed_candle_time")
    )
    record = _iso(record_time) or completed
    target = _iso(target_time)
    return {
        "calculation_id": calc_id,
        "calculation_generation": numeric_generation(canonical.get("calculation_generation") or canonical.get("generation") or canonical.get("generation_id"), default=1),
        "run_id": str(canonical.get("run_id") or calc_id),
        "symbol": str(canonical.get("symbol") or "EURUSD"),
        "timeframe": str(canonical.get("timeframe") or "H1"),
        "source": str(canonical.get("source") or "canonical"),
        "latest_completed_h1": completed,
        "record_time": record,
        "target_time": target,
        "horizon": int(horizon) if horizon not in (None, "") else None,
        "data_signature": str(canonical.get("data_signature") or ""),
        "logic_version": str(logic_version),
        "condition": str(condition or ""),
        "sample_count": int(sample_count) if sample_count not in (None, "") else None,
        "settled_status": str(settled_status or "UNSETTLED"),
        "is_revision": 1 if is_revision else 0,
        "created_at": utc_now_iso(),
    }


def history_record_key(table_name: str, identity: Mapping[str, Any], payload: Mapping[str, Any] | None = None) -> str:
    """Deterministic idempotency key for one logical evidence row."""
    stable = {
        "table": str(table_name),
        **{name: identity.get(name) for name in IDENTITY_COLUMNS if name != "created_at"},
        "payload": dict(payload or {}),
    }
    raw = json.dumps(stable, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def validate_history_time(identity: Mapping[str, Any]) -> tuple[bool, str]:
    """Reject rows that claim evidence after the authoritative completed H1."""
    completed = pd.to_datetime(identity.get("latest_completed_h1"), errors="coerce", utc=True)
    record = pd.to_datetime(identity.get("record_time"), errors="coerce", utc=True)
    target = pd.to_datetime(identity.get("target_time"), errors="coerce", utc=True)
    status = str(identity.get("settled_status") or "").upper()
    if pd.isna(completed):
        return False, "missing latest_completed_h1"
    if not pd.isna(record) and record > completed:
        return False, "record_time is in the future relative to completed H1"
    if status in {"SETTLED", "OBSERVED", "COMPLETED"} and not pd.isna(target) and target > completed:
        return False, "settled target_time is later than completed H1"
    return True, ""


__all__ = [
    "IDENTITY_COLUMNS", "HISTORY_LOGIC_VERSION", "canonical_history_identity",
    "history_record_key", "validate_history_time", "utc_now_iso",
]

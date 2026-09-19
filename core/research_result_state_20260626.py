"""Explicit research-result state taxonomy for Fields 7, 8 and 9."""
from __future__ import annotations
from typing import Any, Mapping

VALID_STATES = (
    "insufficient observations",
    "unsettled future outcome",
    "missing source data",
    "stale generation",
    "model failure",
    "valid but low-confidence result",
    "valid result",
)

def classify_research_result(value: Any, *, canonical_identity: tuple[Any, ...] | None = None) -> dict[str, str]:
    if value is None:
        return {"state": "missing source data", "reason": "The engine published no result object for this canonical generation."}
    if isinstance(value, Mapping):
        if value.get("error") or value.get("exception") or value.get("model_failure"):
            return {"state": "model failure", "reason": str(value.get("error") or value.get("exception") or "The model reported failure.")}
        n = value.get("effective_sample_size", value.get("sample_size", value.get("observations")))
        try:
            if n is not None and float(n) < float(value.get("minimum_observations", 20)):
                return {"state": "insufficient observations", "reason": f"Effective observations {n} are below the required minimum."}
        except Exception:
            pass
        status = str(value.get("outcome_status") or value.get("settlement_status") or "").lower()
        if status in {"pending", "unsettled", "open", "future"}:
            return {"state": "unsettled future outcome", "reason": "The forecast horizon has not completed, so correctness cannot yet be scored."}
        identity = (value.get("run_id"), value.get("generation_id"), value.get("snapshot_hash"))
        if canonical_identity and any(identity) and identity != canonical_identity[:3]:
            return {"state": "stale generation", "reason": "The result identity does not match the current Field 1 canonical snapshot."}
        confidence = value.get("confidence", value.get("reliability"))
        try:
            c = float(confidence)
            if c > 1: c /= 100.0
            if c < 0.55:
                return {"state": "valid but low-confidence result", "reason": f"A valid result exists, but confidence is only {c:.1%}."}
        except Exception:
            pass
        if value.get("ok") is False:
            return {"state": "missing source data", "reason": str(value.get("reason") or value.get("message") or "Required source inputs were not published.")}
    return {"state": "valid result", "reason": "The result is current and passed the available publication checks."}

"""Deterministic, question-focused answer planning from compact evidence."""
from __future__ import annotations
from typing import Any, Iterable, Mapping


def _display(value: Any) -> str:
    if value is None or value == "":
        return "not published"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _value_line(row: Mapping[str, Any]) -> str:
    metric = str(row.get("metric_name") or "evidence").replace("_", " ").title()
    explanation = str(row.get("short_explanation") or "").strip()
    suffix = f" — {explanation}" if explanation else ""
    return f"- **{metric}:** {_display(row.get('metric_value'))} ({row.get('source_name')}){suffix}"


def draft_answer(question: str, intent: str, evidence: Iterable[Mapping[str, Any]], identity: Mapping[str, Any]) -> str:
    rows = list(evidence)
    title = intent.replace("_", " ").title()
    if not rows:
        body = "No settled evidence matching this exact question is available in the current completed generation."
    else:
        body = "\n".join(_value_line(row) for row in rows[:8])
    return "\n".join([
        f"### {title}",
        f"**Question understood:** {str(question).strip()}",
        body,
        "",
        "**Interpretation:** The listed values were selected because they match this question's intent. They are read-only outputs from the published generation, not a repeated generic answer and not a new calculation.",
    ])


def revise_answer(draft: str, critic: Mapping[str, Any]) -> str:
    status = str(critic.get("status") or "INSUFFICIENT_EVIDENCE")
    missing = list(critic.get("missing_sources") or [])
    suffix = []
    if missing:
        suffix.append("Missing evidence categories: " + ", ".join(missing) + ".")
    if status in {"CONFLICTING_EVIDENCE", "STALE_GENERATION", "INSUFFICIENT_EVIDENCE"}:
        suffix.append("Do not infer an unreported price, probability, TP, SL, score, or regime.")
    return draft + ("\n\n" + " ".join(suffix) if suffix else "")


def final_structured_answer(revised: str, *, identity: Mapping[str, Any], sources: Iterable[Mapping[str, Any]], critic: Mapping[str, Any], calibration: Mapping[str, Any], freshness: str, conflict: str, limitations: Iterable[str]) -> str:
    source_names = []
    for row in sources:
        name = str(row.get("source_name") or "")
        if name and name not in source_names:
            source_names.append(name)
    lines = [
        revised,
        "",
        "---",
        f"**Completed candle time:** {identity.get('completed_candle') or '-'}",
        f"**Generation ID:** {identity.get('generation_id') or '-'}",
        f"**Evidence sources used:** {', '.join(source_names) if source_names else 'None'}",
        f"**Evidence coverage status:** {critic.get('status')}",
        f"**Freshness status:** {freshness}",
        f"**Conflict status:** {conflict}",
        f"**Calibrated evidence confidence:** {calibration.get('calibrated_confidence', 0)}%",
        "**Limitations:** " + ("; ".join(str(x) for x in limitations if str(x).strip()) or "No additional limitation recorded."),
    ]
    return "\n".join(lines)


__all__ = ["draft_answer", "revise_answer", "final_structured_answer"]

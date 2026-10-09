"""Bounded lexical/metadata evidence retrieval without a heavy embedding model."""
from __future__ import annotations
import re
from typing import Any, Iterable, Mapping


def _tokens(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9+_.%-]+", str(value or "").lower()))


def retrieve_evidence(question: str, registry: Iterable[Mapping[str, Any]], required_sources: Iterable[str], *, top_k: int = 6) -> list[dict[str, Any]]:
    """Return only evidence categories relevant to the classified question."""
    q = _tokens(question)
    required = {str(x).lower() for x in required_sources}
    aliases = {
        "warnings": {"warnings", "decision", "risk", "reliability", "system_health"},
        "forecast": {"forecast", "projection"},
        "history": {"history", "similar_day", "evidence"},
        "connector": {"connector", "system_health"},
        "identity": {"identity", "system_health"},
        "validation": {"validation", "system_health"},
        "uncertainty": {"uncertainty", "reliability"},
    }
    allowed = set(required)
    for item in list(required):
        allowed.update(aliases.get(item, set()))
    scored: list[tuple[float, dict[str, Any]]] = []
    for raw in registry:
        rec = dict(raw)
        field = str(rec.get("field", "")).lower()
        source_name = str(rec.get("source_name", "")).lower()
        category_match = (not allowed) or field in allowed or any(token in field or token in source_name for token in allowed)
        if not category_match:
            continue
        text = " ".join(str(rec.get(k, "")) for k in ("source_name", "field", "metric_name", "metric_value", "short_explanation", "evidence_status"))
        terms = _tokens(text)
        overlap = len(q & terms)
        source_bonus = 4.0 if field in required else 2.0
        settled_bonus = 1.0 if str(rec.get("evidence_status", "")).upper() in {"SETTLED", "OBSERVED", "COMPLETED"} else 0.0
        freshness_bonus = 1.0 if str(rec.get("freshness", "")).upper() in {"CURRENT", "FRESH", "READY"} else 0.0
        reliability = rec.get("reliability")
        try:
            reliability_bonus = min(max(float(reliability), 0.0), 100.0) / 100.0
        except Exception:
            reliability_bonus = 0.0
        score = overlap * 2.0 + source_bonus + settled_bonus + freshness_bonus + reliability_bonus
        rec["retrieval_score"] = round(score, 3)
        scored.append((score, rec))
    ranked = [r for _, r in sorted(scored, key=lambda x: (-x[0], str(x[1].get("metric_name"))))[: max(1, min(int(top_k), 8))]]
    if len(ranked) > 2:
        ranked = [ranked[0], *ranked[2:], ranked[1]]
    return ranked


__all__ = ["retrieve_evidence"]

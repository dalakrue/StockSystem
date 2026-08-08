"""Compact conversation memory: intent and evidence IDs only."""
from __future__ import annotations
from typing import Any, MutableMapping, Iterable, Mapping

MEMORY_KEY = "ai_compact_conversation_memory_20260621"
MAX_ITEMS = 20


def remember(state: MutableMapping[str, Any], *, question: str, intent: str, generation_id: str, evidence: Iterable[Mapping[str, Any]], status: str, answer: str = "") -> None:
    raw = state.get(MEMORY_KEY)
    items = list(raw) if isinstance(raw, list) else []
    items.append({
        "question_summary": " ".join(str(question or "").split())[:180],
        "intent": intent,
        "generation_id": generation_id,
        "evidence_ids": [str(r.get("evidence_id")) for r in list(evidence)[:8] if r.get("evidence_id")],
        "status": status,
        "question": " ".join(str(question or "").split())[:500],
        "answer": str(answer or "")[:12000],
    })
    state[MEMORY_KEY] = items[-MAX_ITEMS:]

__all__ = ["remember", "MEMORY_KEY", "MAX_ITEMS"]

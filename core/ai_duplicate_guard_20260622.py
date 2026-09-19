"""Lightweight duplicate-answer prevention for the local grounded assistant."""
from __future__ import annotations

from difflib import SequenceMatcher
from hashlib import sha1
import re
from typing import Any, Iterable, Mapping, MutableMapping

from core.ai_conversation_memory import MEMORY_KEY

SIMILARITY_THRESHOLD = 0.90


def _normalize(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return re.sub(r"[^a-z0-9.%+:/ -]", "", text)


def similarity(a: Any, b: Any) -> float:
    left, right = _normalize(a), _normalize(b)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _dedupe_lines(answer: str) -> str:
    seen: set[str] = set()
    output: list[str] = []
    for line in str(answer or "").splitlines():
        key = _normalize(line)
        if key and key in seen and not line.strip().startswith(("---", "###")):
            continue
        if key:
            seen.add(key)
        output.append(line)
    return "\n".join(output).strip()


def previous_answers(state: Mapping[str, Any], limit: int = 20) -> list[str]:
    raw = state.get(MEMORY_KEY)
    if not isinstance(raw, list):
        return []
    return [str(item.get("answer") or "") for item in raw[-limit:] if isinstance(item, Mapping) and item.get("answer")]


def prevent_duplicate_answer(
    state: MutableMapping[str, Any],
    *,
    question: str,
    answer: str,
    intent: str,
    evidence: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Regenerate a deterministic question-specific form when >90% duplicated."""
    cleaned = _dedupe_lines(answer)
    prior = previous_answers(state, 20)
    maximum = max((similarity(cleaned, item) for item in prior), default=0.0)
    regenerated = maximum > SIMILARITY_THRESHOLD
    if regenerated:
        rows = list(evidence or [])
        strongest = [row for row in rows if isinstance(row, Mapping)][:4]
        digest = sha1(str(question).encode("utf-8", "ignore")).hexdigest()
        variant = int(digest[:2], 16) % 3
        headings = (
            "Question-specific analyst view",
            "Focused evidence review",
            "Current-generation response",
        )
        focus_lines = []
        for row in strongest:
            metric = str(row.get("metric_name") or "evidence").replace("_", " ").title()
            value = row.get("metric_value")
            source = row.get("source_name") or "published source"
            focus_lines.append(f"- {metric}: {value} ({source})")
        if not focus_lines:
            focus_lines.append("- No additional distinct settled evidence was available; the current generation remains unchanged.")
        footer = ""
        if "\n---\n" in cleaned:
            footer = cleaned.split("\n---\n", 1)[1].strip()
        cleaned = "\n".join([
            f"### {headings[variant]}",
            f"**Question:** {str(question).strip()}",
            f"**Classified as:** {str(intent).replace('_', ' ').title()}",
            *focus_lines,
            "",
            "**Analyst conclusion:** The response was restructured because the first draft was too similar to a recent answer. Only evidence relevant to this question is shown; no new calculation was run.",
            *( ["", "---", footer] if footer else [] ),
        ])
    return {
        "answer": cleaned,
        "regenerated": regenerated,
        "maximum_similarity": round(maximum, 4),
        "threshold": SIMILARITY_THRESHOLD,
    }


__all__ = ["SIMILARITY_THRESHOLD", "similarity", "prevent_duplicate_answer", "previous_answers"]

"""Bounded resource routing for the local grounded assistant."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ResourceBudget:
    complexity: str
    top_k: int
    max_registry_records: int
    max_history_tables: int
    max_answer_chars: int


def select_budget(question: str, intent: str) -> ResourceBudget:
    words = len(str(question or "").split())
    complex_intents = {"historical_comparison", "similar_day", "system_health", "risk_position_sizing"}
    complex_query = words > 18 or intent in complex_intents
    if complex_query:
        return ResourceBudget("complex", 8, 80, 6, 3600)
    return ResourceBudget("simple", 4, 48, 3, 2200)

__all__ = ["ResourceBudget", "select_budget"]

"""Shared immutable render context for all Lunch fields."""
from __future__ import annotations

from dataclasses import dataclass

from core.canonical.snapshot import CanonicalRunSnapshot
from core.repositories.history_repository import HistoryRepository
from core.repositories.outcome_repository import OutcomeRepository
from core.repositories.research_repository import ResearchRepository
from core.repositories.run_repository import RunRepository


@dataclass(frozen=True)
class LunchRenderContext:
    snapshot: CanonicalRunSnapshot
    run_repository: RunRepository
    history_repository: HistoryRepository
    outcome_repository: OutcomeRepository
    research_repository: ResearchRepository
    selected_field: str
    search_query: str
    mobile_mode: bool

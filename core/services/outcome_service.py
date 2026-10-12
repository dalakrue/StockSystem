"""Outcome reporting service."""
from __future__ import annotations
from core.repositories.outcome_repository import OutcomeRepository


def settled_outcomes(limit: int = 500):
    return OutcomeRepository().settled(limit)

"""Bounded read-only history adapter for modular Lunch fields."""
from __future__ import annotations
from typing import Any, Mapping, MutableMapping
import pandas as pd


class HistoryRepository:
    def __init__(self, state: MutableMapping[str, Any] | None = None):
        self.state = state if state is not None else {}

    def frame(self, *keys: str, limit: int = 25) -> pd.DataFrame:
        for key in keys:
            value = self.state.get(key)
            if isinstance(value, pd.DataFrame) and not value.empty:
                return value.head(int(limit)).copy()
            if isinstance(value, list) and value:
                return pd.DataFrame(value).head(int(limit))
        return pd.DataFrame()

    @staticmethod
    def from_mapping(value: Any, limit: int = 25) -> pd.DataFrame:
        if isinstance(value, pd.DataFrame):
            return value.head(int(limit)).copy()
        if isinstance(value, list):
            return pd.DataFrame(value).head(int(limit))
        if isinstance(value, Mapping):
            return pd.DataFrame([dict(value)])
        return pd.DataFrame()

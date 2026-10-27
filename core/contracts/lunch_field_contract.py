"""Protocol shared by every modular Lunch field."""
from __future__ import annotations

from typing import Any, Protocol


class LunchFieldContract(Protocol):
    def validate(self, context: Any) -> list[str]: ...
    def build_view_model(self, context: Any) -> Any: ...
    def render(self, view_model: Any) -> None: ...

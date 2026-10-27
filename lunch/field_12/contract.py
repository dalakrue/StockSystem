from __future__ import annotations

from typing import Any


def validate(context: Any) -> list[str]:
    return [] if context is not None else ["Field 12 requires a Lunch render context."]

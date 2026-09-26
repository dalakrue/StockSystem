from __future__ import annotations

def validate(context) -> list[str]:
    return [] if context.snapshot.regime else ["Field 3 requires canonical regime data."]

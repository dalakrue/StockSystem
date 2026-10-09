from __future__ import annotations

def validate(context) -> list[str]:
    return [] if context.snapshot.run_id else ["Field 2 requires a valid canonical run ID."]

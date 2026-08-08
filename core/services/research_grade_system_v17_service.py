"""Settings-only publisher for the unified research-grade shadow sidecar."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from core.canonical.snapshot import load_canonical_snapshot
from core.research_grade_system_v17_20260624 import publish


def _snapshot_mapping(snapshot: Any) -> dict[str, Any]:
    if isinstance(snapshot, Mapping):
        return dict(snapshot)
    if is_dataclass(snapshot):
        return asdict(snapshot)
    if hasattr(snapshot, "to_dict"):
        try:
            return dict(snapshot.to_dict())
        except Exception:
            pass
    return {key: value for key, value in vars(snapshot).items() if not key.startswith("_")} if hasattr(snapshot, "__dict__") else {}


def build_and_publish_research_grade_v17(state):
    """Run only inside Settings → Run Calculation + Open Lunch."""
    snap = load_canonical_snapshot(state)
    if snap is None:
        return {"ok": False, "status": "MISSING", "reason": "NO_CANONICAL_SNAPSHOT", "shadow_only": True}
    raw = _snapshot_mapping(snap)
    result = publish(state, raw)
    try:
        from core.services.breakout_regime_shadow_service import build_and_publish_breakout_regime_shadow
        result["breakout_regime_shadow"] = build_and_publish_breakout_regime_shadow(state)
    except Exception as exc:
        result["breakout_regime_shadow"] = {"ok": False, "shadow_only": True, "error": f"{type(exc).__name__}: {exc}"}
    try:
        from core.ground_ai_research_upgrade_20260624 import publish as publish_ground_ai
        result["ground_ai"] = publish_ground_ai(state, raw, state.get("research_grade_system_v17_20260624"))
    except Exception as exc:
        result["ground_ai"] = {"ok": False, "status": "FAILED_VALIDATION", "shadow_only": True, "error": f"{type(exc).__name__}: {exc}"}
    return result


__all__ = ["build_and_publish_research_grade_v17"]

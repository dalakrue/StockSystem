"""View-model snapshot hash guard for Field 10, Dinner, Visualization and Export."""
from __future__ import annotations
from collections.abc import Mapping, MutableMapping
from typing import Any


def verify_view_model_sync(state: Mapping[str, Any]) -> dict[str, Any]:
    def h(obj: Any) -> str:
        if isinstance(obj, Mapping): return str(obj.get("snapshot_hash") or "")
        return str(getattr(obj, "snapshot_hash", "") or "")
    field10 = h(state.get("field10_authority_view_model_20260709")) or h(state.get("field10_unified_snapshot_20260709"))
    dinner = h(state.get("dinner_view_model_20260709"))
    viz = h(state.get("visualization_view_model_20260709"))
    export = h(state.get("field10_export_manifest_20260709"))
    hashes = {"Field 10": field10, "Dinner": dinner, "Data Visualization": viz, "Export": export}
    nonempty = [v for v in hashes.values() if v]
    ok = bool(nonempty) and len(set(nonempty)) == 1
    return {"ok": ok, "status": "SYNC_OK" if ok else "SYNC_ERROR", "hashes": hashes, "snapshot_hash": nonempty[0] if ok else ""}


def render_sync_status_panel(st, state: MutableMapping[str, Any]) -> None:
    report = verify_view_model_sync(state)
    state["field10_dinner_visualization_sync_20260709"] = report
    if report["ok"]:
        st.success(f"SYNC_OK — Field 10, Dinner, Data Visualization and Export use snapshot {report['snapshot_hash']}.")
    else:
        st.error("SYNC_ERROR — final trusted result blocked until all view models share one snapshot hash.")
        st.json(report["hashes"])

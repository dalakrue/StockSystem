"""Background orchestrator facade for ADX Quant Pro authority snapshot.

The existing Settings calculation still owns heavy trading logic.  This layer
materializes a synchronized authority snapshot after those results exist, so UI
rendering does not recompute heavy models.
"""
from __future__ import annotations
from collections.abc import MutableMapping
from datetime import datetime, timezone
from typing import Any
from core.run_saga import create_saga_ledger, mark_stage

STAGES = [
    "build_canonical_universe", "load_symbol_data", "validate_symbol_data", "create_child_symbol_snapshots",
    "compute_existing_trading_logic", "compute_background_functions", "materialize_field10_view",
    "materialize_dinner_view", "materialize_visualization_view", "prepare_export_manifest", "publish_snapshot",
]


def run_authority_materialization(state: MutableMapping[str, Any], *, reason: str = "ui_materialization") -> dict[str, Any]:
    from core.field10_unified_authority_20260709 import build_unified_field10_authority
    run_id = str(state.get("multi_symbol_parent_run_id_20260701") or state.get("adx_current_run_id_20260708") or f"authority-{datetime.now(timezone.utc).timestamp():.0f}")
    ledger = create_saga_ledger(run_id, STAGES)
    state["field10_authority_saga_ledger_20260709"] = ledger
    for stage in STAGES:
        try:
            if stage in {"compute_background_functions", "materialize_field10_view", "materialize_dinner_view", "materialize_visualization_view", "prepare_export_manifest", "publish_snapshot"}:
                result = build_unified_field10_authority(state, persist=True)
                state["field10_authority_materialization_20260709"] = result
            ledger = mark_stage(ledger, stage, "COMPLETE")
        except Exception as exc:
            ledger = mark_stage(ledger, stage, "FAILED", f"{type(exc).__name__}: {exc}")
            break
    state["field10_authority_saga_ledger_20260709"] = ledger
    return {"run_id": run_id, "ledger": ledger, "reason": reason}

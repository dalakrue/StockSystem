from __future__ import annotations

from typing import MutableMapping

from core.ai_canonical_intents_v10 import build_ai_evidence_contract, validate_ai_evidence_contract
from core.canonical.snapshot import load_canonical_snapshot
from core.field6_session_bayesian_fusion_20260625 import build_field6_session_bayesian_fusion
from core.field7_session_drift_cpa_20260625 import build_field7_session_drift_cpa
from core.field8_session_calibration_spa_20260625 import build_field8_session_calibration_spa
from core.field9_counterfactual_policy_20260625 import build_field9_counterfactual_policy
from core.publication_identity_20260625 import freeze_publication_identity


def build_and_publish_session_ai_field6_9(state: MutableMapping[str, object]) -> dict[str, object]:
    scope = str(state.get("settings_calculation_scope_20260625") or "FULL").upper()
    if scope == "QUICK":
        status = {
            "ok": False,
            "status": "SKIPPED_FOR_QUICK_RUN",
            "identity": freeze_publication_identity(state, None),
            "ai_ready": False,
            "ai_missing_components": ["full_run_required_for_ai_and_fields_6_9"],
            "shadow_only": True,
        }
        state["session_ai_field6_9_status_20260625"] = status
        return status
    snapshot = load_canonical_snapshot(state)
    if snapshot is None:
        status = {"ok": False, "status": "NO_CANONICAL_SNAPSHOT", "identity": freeze_publication_identity(state, None), "shadow_only": True}
        state["session_ai_field6_9_status_20260625"] = status
        return status
    identity = freeze_publication_identity(state, snapshot)
    state["publication_identity_20260625"] = identity
    field6 = build_field6_session_bayesian_fusion(state, snapshot)
    field7 = build_field7_session_drift_cpa(state, snapshot)
    field8 = build_field8_session_calibration_spa(state, snapshot)
    field9 = build_field9_counterfactual_policy(state, snapshot)
    contract = build_ai_evidence_contract(state)
    contract["identity"] = identity
    contract["system_health"] = {**(contract.get("system_health") or {}), "publication_status": "READY" if all(bool(identity.get(k)) for k in ("run_id", "generation_id", "snapshot_hash")) else "NOT_READY", "calculation_scope": scope}
    validation = validate_ai_evidence_contract(contract)
    state["ai_evidence_contract_20260625"] = contract
    status = {
        "ok": all(item.get("status") == "OK" for item in (field6, field7, field8, field9)) and bool(validation.get("ready")),
        "status": "READY" if bool(validation.get("ready")) else "NOT_READY",
        "identity": identity,
        "field6": field6.get("status"),
        "field7": field7.get("status"),
        "field8": field8.get("status"),
        "field9": field9.get("status"),
        "ai_ready": bool(validation.get("ready")),
        "ai_missing_components": list(validation.get("missing_components") or []),
        "shadow_only": True,
    }
    state["session_ai_field6_9_status_20260625"] = status
    return status

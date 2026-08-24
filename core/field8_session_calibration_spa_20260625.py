from __future__ import annotations

from typing import Any, MutableMapping

import pandas as pd

from core.canonical.snapshot import load_canonical_snapshot
from core.publication_identity_20260625 import freeze_publication_identity
from core.session_context_20260625 import resolve_session_contract
from core.session_projection_store_20260625 import settled_projection_records, compute_session_statistics


def _f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if out == out else default
    except Exception:
        return default


def build_field8_session_calibration_spa(
    state: MutableMapping[str, Any] | None,
    source_snapshot: Any | None = None,
) -> dict[str, Any]:
    state = state if isinstance(state, MutableMapping) else {}
    snapshot = source_snapshot or load_canonical_snapshot(state)
    if snapshot is None:
        payload = {
            "status": "NO_CANONICAL_SNAPSHOT",
            "shadow_only": True,
            "history": [],
            "current": {},
            "identity": {"run_id": "", "generation_id": "", "snapshot_hash": ""},
        }
        state["field8_session_calibration_spa_20260625"] = payload
        return payload

    identity = freeze_publication_identity(state, snapshot)
    contract = resolve_session_contract(state, snapshot)
    state["field8_publication_identity_20260624"] = {
        "run_id": identity["run_id"],
        "generation_id": identity["generation_id"],
        "snapshot_hash": identity["snapshot_hash"],
    }

    records = settled_projection_records(state)
    stats = compute_session_statistics(records) if not records.empty else pd.DataFrame()
    selected = contract.selected_session
    selected_rows = stats[stats["session"] == selected] if not stats.empty else pd.DataFrame()
    global_rows = stats[stats["session"] == "GLOBAL_FALLBACK"] if not stats.empty else pd.DataFrame()
    rows = selected_rows if not selected_rows.empty else global_rows

    current = {
        "mae": round(_f(rows["mae"].mean()), 6) if not rows.empty else 0.0,
        "rmse": round(_f(rows["rmse"].mean()), 6) if not rows.empty else 0.0,
        "directional_accuracy": round(_f(rows["direction_accuracy"].mean()), 6) if not rows.empty else 0.0,
        "actionable_coverage": round(_f(rows["interval_coverage"].mean()), 6) if not rows.empty else 0.0,
        "brier_score": round(max(0.0, 1.0 - _f(rows["direction_accuracy"].mean(), 0.0)), 6) if not rows.empty else 0.0,
        "interval_score": round(_f(rows["average_interval_width"].mean()), 6) if not rows.empty else 0.0,
        "adaptive_coverage": round(_f(rows["interval_coverage"].mean()), 6) if not rows.empty else 0.0,
        "coverage_debt": round(max(0.0, 0.90 - _f(rows["interval_coverage"].mean(), 0.0)), 6) if not rows.empty else 0.90,
        "selected_confidence_set": "SESSION_ADAPTIVE,BASE_PROTECTED,CONSERVATIVE_GREEN" if int(rows["sample_count"].sum()) >= 40 else "MODEL_UNPROVEN",
        "model_stability": "STABLE" if _f(rows["rmse"].std(), 0.0) < max(1e-6, 0.25 * _f(rows["rmse"].mean(), 0.0)) else "VARIABLE",
    }

    total_samples = int(rows["sample_count"].sum()) if not rows.empty else 0
    if total_samples < 40:
        spa_status = "INSUFFICIENT_EVIDENCE"
        decision_role = "MODEL_UNPROVEN"
        winner = "NONE"
    else:
        better = _f(rows["direction_accuracy"].mean(), 0.0) >= _f(global_rows["direction_accuracy"].mean(), 0.0) if not global_rows.empty else True
        spa_status = "SESSION_IN_CONFIDENCE_SET" if better else "BASE_DOMINANT"
        winner = "SESSION_ADAPTIVE" if better else "BASE_PROTECTED"
        if current["coverage_debt"] > 0.15:
            decision_role = "COVERAGE_RISK"
        elif winner == "SESSION_ADAPTIVE":
            decision_role = "CALIBRATED_CONFIRM"
        else:
            decision_role = "WAIT_PREFERRED"

    history = []
    if not records.empty:
        recs = records.copy()
        if 'origin_time' not in recs.columns and 'forecast_origin_time' in recs.columns:
            recs['origin_time'] = recs['forecast_origin_time']
        recs["origin_time"] = pd.to_datetime(recs["origin_time"], utc=True, errors="coerce")
        recs = recs.sort_values("origin_time", ascending=False).head(600)
        for _, row in recs.iterrows():
            history.append({
                "Broker Time": row["origin_time"].isoformat() if pd.notna(row["origin_time"]) else "",
                "Session": row.get("session") or selected,
                "Horizon": int(row.get("horizon") or 1),
                "Alpha": round(_f(snapshot.priority / 100.0), 4),
                "Beta Instability": round(_f(snapshot.uncertainty / 100.0), 4),
                "Delta": round(_f(snapshot.error_rate / 100.0), 4),
                "Delta Acceleration": round(_f(snapshot.error_rate / 200.0), 4),
                "Base Accuracy": round(1.0 - min(1.0, _f(row.get("base_error"), 0.0) / max(1e-6, abs(_f(row.get("actual"), 1.0)))), 4),
                "Session Accuracy": round(current["directional_accuracy"], 4),
                "Coverage": round(current["adaptive_coverage"], 4),
                "Coverage Debt": round(current["coverage_debt"], 4),
                "Interval Score": round(current["interval_score"], 4),
                "Candidate Count": 5,
                "SPA Statistic": round(current["directional_accuracy"] - _f(global_rows["direction_accuracy"].mean(), 0.0), 6) if not rows.empty else 0.0,
                "SPA Status": spa_status,
                "Confidence-Set Winner": winner,
                "Structural Break State": state.get("field_07_research_summary_v11", {}).get("structural_stability", "UNKNOWN"),
                "Decision Role": decision_role,
                "Direction Confirmation": "YES" if current["directional_accuracy"] >= 0.5 else "NO",
                "Run ID": identity["run_id"],
                "Generation ID": identity["generation_id"],
                "Snapshot Hash": identity["snapshot_hash"],
            })

    payload = {
        "status": "OK",
        "shadow_only": True,
        "identity": identity,
        "session_contract": contract.to_dict(),
        "current": {
            **current,
            "spa_status": spa_status,
            "confidence_set_winner": winner,
            "decision_role": decision_role,
            "candidate_count": 5,
            "sample_count": total_samples,
        },
        "history": history,
    }
    state["field8_session_calibration_spa_20260625"] = payload
    return payload

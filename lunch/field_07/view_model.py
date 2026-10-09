"""Build Field 7 from stored Settings-run research plus read-only H1 evidence."""
from __future__ import annotations
from typing import Any
import pandas as pd
from lunch.field_07.tables import prepare_history


def build_view_model(context) -> dict[str, Any]:
    summary = dict(context.snapshot.research_summary)
    if not summary:
        summary = context.research_repository.latest_summary(run_id=context.snapshot.run_id)
    history = prepare_history(context.research_repository.history(25), context.search_query, 25)
    horizons = context.research_repository.horizons(context.snapshot.run_id)
    models = context.research_repository.models(context.snapshot.run_id)
    try:
        from core.lunch_h1_data_quality_v13 import build_h1_decision_evidence
        decision_evidence = build_h1_decision_evidence(
            context.history_repository.state,
            context.snapshot.to_dict(),
            days=25,
            limit=600,
        )
    except Exception:
        decision_evidence = pd.DataFrame()
    warnings: list[str] = []
    if not summary:
        warnings.append(
            "No stored Field 7 research certificate exists for this run. "
            "Completed-H1 shadow decision evidence remains available below without manufacturing validation results."
        )
    if int(summary.get("sample_size") or 0) < 25:
        warnings.append(
            "SETTLED VALIDATION IS INSUFFICIENT: fewer than 25 settled/comparable outcomes are available. "
            "This does not hide the separate 25-day H1 decision-support table."
        )
    if summary.get("structural_stability") in {"TRANSITION", "HIGH RISK"}:
        warnings.append("Structural-change risk limits the approved forecast horizon.")
    if summary.get("event_state") not in {None, "NORMAL"}:
        warnings.append(f"Event embargo active: {summary.get('event_state')}.")
    additive_payload = context.history_repository.state.get('field7_session_drift_cpa_20260625') or {}
    if additive_payload.get('status') == 'OK':
        warnings = [w for w in warnings if 'No stored Field 7 research certificate exists' not in w]
    return {
        "context": context,
        "summary": summary,
        "history": history,
        "horizons": horizons,
        "models": models,
        "decision_evidence": decision_evidence,
        "warnings": warnings,
        "session_drift_cpa": additive_payload,
    }

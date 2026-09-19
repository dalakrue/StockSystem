"""Settings-owned Field 7 shadow calculation service."""
from __future__ import annotations

import logging
import time
from typing import Any, MutableMapping

from core.canonical.snapshot import adapt_v10_snapshot
from core.repositories.outcome_repository import OutcomeRepository
from core.repositories.research_repository import ResearchRepository
from research.research_gate import evaluate
from research.v12_orchestrator import evaluate_v12
from research.v13_orchestrator import evaluate_v13
from research.v14_orchestrator import evaluate_v14
from research.v11_advanced_validation import evaluate as evaluate_v11_advanced
from research.advanced_causal_forecast_20260624 import evaluate as evaluate_advanced_causal

LOGGER = logging.getLogger("quant_v11.research")


def build_and_store_shadow_research(
    state: MutableMapping[str, Any],
    source_snapshot: Any | None = None,
) -> dict[str, Any]:
    """Run after Settings publishes; never overwrite canonical production data."""
    started = time.perf_counter()
    if source_snapshot is None:
        from core.canonical_sync_v9 import read_snapshot_for_lunch
        source_snapshot = read_snapshot_for_lunch(state)
    if source_snapshot is None:
        return {
            "ok": False,
            "status": "NO_CANONICAL_SNAPSHOT",
            "shadow_only": True,
            "production_decision_unchanged": True,
        }

    snapshot = adapt_v10_snapshot(source_snapshot)
    try:
        repository = ResearchRepository()
        settled_frame = OutcomeRepository().settled(5000)
        settled = settled_frame.to_dict("records") if not settled_frame.empty else []
        prior_frame = repository.history(500)
        prior = prior_frame.to_dict("records") if not prior_frame.empty else []
        result = evaluate(snapshot, settled_outcomes=settled, prior_research=prior)
        summary = dict(result.summary)
        horizons = [dict(row) for row in result.horizons]
        models = [dict(row) for row in result.models]
        diagnostics = dict(result.diagnostics)

        v12_snapshot = evaluate_v12(snapshot, settled)
        v12_store = repository.save_v12_snapshot(v12_snapshot, history_cap=500)
        v12_payload = v12_snapshot.to_dict()
        summary["v12_research"] = {
            "snapshot_hash": v12_snapshot.snapshot_hash,
            "calculation_generation": v12_snapshot.calculation_generation,
            "schema_version": v12_snapshot.schema_version,
            "module_statuses": v12_payload["module_statuses"],
            "sample_sizes": v12_payload["sample_sizes"],
            "warnings": v12_payload["warnings"],
            "compact_results": v12_payload["compact_results"],
            "store": v12_store,
            "shadow_only": True,
            "production_changed": False,
        }
        diagnostics["v12_snapshot_ref"] = {
            "snapshot_hash": v12_snapshot.snapshot_hash,
            "schema_version": v12_snapshot.schema_version,
            "shadow_only": True,
        }

        # V13 remains Settings-owned and shadow-only.  A V13 failure cannot
        # invalidate the protected canonical publication or V11/V12 research.
        try:
            v13_payload = evaluate_v13(snapshot, settled, state)
        except Exception as exc:
            v13_payload = {
                "schema_version": "research-v13-shadow-1.0",
                "run_id": snapshot.run_id,
                "status": "FAILED_SAFELY",
                "error": f"{type(exc).__name__}: {exc}",
                "shadow_only": True,
                "production_changed": False,
                "compact_results": {"mode": "SHADOW ONLY", "available_layers": 0, "total_layers": 10},
                "warnings": ["V13 failed safely; protected production outputs were not changed."],
            }
        summary["v13_research"] = v13_payload
        # V14 is additive, bounded, Settings-owned and always shadow-only.
        try:
            v14_payload = evaluate_v14(snapshot, settled, state)
            from core.quant_research_v14_store_20260623 import save as save_v14
            v14_store = save_v14(v14_payload)
        except Exception as exc:
            v14_payload = {"status":"FAILED_SAFELY","error":f"{type(exc).__name__}: {exc}","shadow_only":True,"production_influence_enabled":False,"production_decision_changed":False,"protected_weights_changed":False,"readiness":{"available_methods":0,"total_methods":10,"production_changed":"NO"}}
            v14_store = {"ok":False}
        summary["quant_research_v14"] = v14_payload
        # Advanced V11 forecast/regime validation is additive and shadow-only.
        try:
            advanced_v11 = evaluate_v11_advanced(snapshot, settled, state)
        except Exception as exc:
            advanced_v11 = {"status":"FAILED_SAFELY","error":f"{type(exc).__name__}: {exc}","shadow_only":True,"production_influence_enabled":False}
        summary["advanced_v11_validation"] = advanced_v11
        state["advanced_v11_validation"] = advanced_v11
        # Complete ten-layer causal forecast/regime stack. Settings-owned only.
        try:
            advanced_causal = evaluate_advanced_causal(snapshot, settled, state)
            from core.advanced_causal_store_20260624 import save as save_advanced_causal
            import sqlite3
            from core.storage.database import DB_PATH as DEFAULT_DB_PATH
            with sqlite3.connect(str(DEFAULT_DB_PATH)) as _conn:
                advanced_causal_store = save_advanced_causal(_conn, advanced_causal)
        except Exception as exc:
            advanced_causal = {"status":"FAILED_SAFELY","error":f"{type(exc).__name__}: {exc}","shadow_only":True,"production_influence_enabled":False,"production_decision_changed":False}
            advanced_causal_store = {"ok":False}
        summary["advanced_causal_forecast_20260624"] = advanced_causal
        state["advanced_causal_forecast_20260624"] = advanced_causal
        diagnostics["advanced_causal_snapshot_ref"] = {"snapshot_hash":advanced_causal.get("snapshot_hash"),"schema_version":advanced_causal.get("schema_version"),"shadow_only":True,"store":advanced_causal_store}

        # Research-grade named challenger stack. It is executed only inside the
        # Settings-owned transaction and consumes the completed-H1 frame plus
        # immutable matured origin records. Any failure remains shadow-only and
        # cannot invalidate the canonical publication.
        try:
            from research.research_grade_shadow_models_20260624 import evaluate as evaluate_research_grade
            from core.research_grade_shadow_store_20260624 import save as save_research_grade
            import sqlite3
            from core.storage.database import DB_PATH as DEFAULT_DB_PATH
            research_grade = evaluate_research_grade(snapshot, settled, state, chronos_enabled=False)
            with sqlite3.connect(str(DEFAULT_DB_PATH)) as _rg_conn:
                research_grade_store = save_research_grade(_rg_conn, research_grade)
        except Exception as exc:
            research_grade = {
                "status": "FAILED_SAFELY", "error": f"{type(exc).__name__}: {exc}",
                "shadow_only": True, "production_influence_enabled": False,
                "production_decision_changed": False, "field1_immutable_source": True,
            }
            research_grade_store = {"ok": False, "error": research_grade["error"]}
        summary["research_grade_shadow_20260624"] = research_grade
        state["research_grade_shadow_20260624"] = research_grade
        diagnostics["research_grade_shadow_ref"] = {
            "snapshot_hash": research_grade.get("snapshot_hash"),
            "schema_version": research_grade.get("schema_version"),
            "shadow_only": True, "store": research_grade_store,
        }
        # V16 requested named shadow stack. Settings-owned; never used on ordinary reruns.
        try:
            from research.research_grade_v16_20260624 import evaluate as evaluate_v16
            from core.research_grade_v16_store_20260624 import save as save_v16
            import sqlite3
            from core.storage.database import DB_PATH as DEFAULT_DB_PATH
            v16_payload = evaluate_v16(snapshot, settled, state)
            with sqlite3.connect(str(DEFAULT_DB_PATH)) as _v16_conn:
                v16_store = save_v16(_v16_conn, v16_payload)
        except Exception as exc:
            v16_payload = {"status":"FAILED_SAFELY","error":f"{type(exc).__name__}: {exc}","shadow_only":True,"production_influence_enabled":False,"production_decision_changed":False}
            v16_store = {"ok":False,"error":v16_payload["error"]}
        summary["research_grade_v16_20260624"] = v16_payload
        state["research_grade_v16_20260624"] = v16_payload
        diagnostics["research_grade_v16_ref"] = {"shadow_only":True,"store":v16_store,"model_version":v16_payload.get("model_version")}

        # Exact ten-foundation active stack requested on 2026-06-24.
        # It is bounded, Settings-owned, persisted additively, and never mutates Field 1.
        try:
            from research.ten_foundation_active_engine_20260624 import evaluate as evaluate_ten_foundation
            from core.ten_foundation_active_store_20260624 import save as save_ten_foundation
            import sqlite3
            from core.storage.database import DB_PATH as DEFAULT_DB_PATH
            ten_foundation = evaluate_ten_foundation(snapshot, settled, state)
            with sqlite3.connect(str(DEFAULT_DB_PATH)) as _tf_conn:
                ten_foundation_store = save_ten_foundation(_tf_conn, ten_foundation)
        except Exception as exc:
            ten_foundation = {"status":"FAILED_SAFELY","error":f"{type(exc).__name__}: {exc}","shadow_only":True,"production_decision_changed":False,"field1_immutable_source":True}
            ten_foundation_store = {"ok":False,"error":ten_foundation["error"]}
        summary["ten_foundation_active_20260624"] = ten_foundation
        state["ten_foundation_active_20260624"] = ten_foundation
        diagnostics["ten_foundation_active_ref"] = {"shadow_only":True,"store":ten_foundation_store,"payload_hash":ten_foundation.get("payload_hash")}

        # Coordinated Regime Intelligence Stack. Settings-owned, additive, shadow-only.
        try:
            from core.regime_intelligence_stack_20260624 import build_regime_intelligence
            from core.regime_intelligence_store_20260624 import save as save_regime_intelligence
            import sqlite3
            from core.storage.database import DB_PATH as DEFAULT_DB_PATH
            regime_intelligence = build_regime_intelligence(snapshot, state, settled)
            with sqlite3.connect(str(DEFAULT_DB_PATH)) as _ri_conn:
                regime_intelligence_store = save_regime_intelligence(_ri_conn, regime_intelligence)
        except Exception as exc:
            regime_intelligence = {"status":"FAILED_SAFELY","error":f"{type(exc).__name__}: {exc}","shadow_only":True,"production_decision_changed":False,"field1_immutable_source":True}
            regime_intelligence_store = {"ok":False,"error":regime_intelligence["error"]}
        summary["regime_intelligence_20260624"] = regime_intelligence
        state["regime_intelligence_20260624"] = regime_intelligence
        diagnostics["regime_intelligence_ref"] = {"shadow_only":True,"store":regime_intelligence_store,"version":regime_intelligence.get("version")}

        # Institutional Field 3 lifecycle monitor. This is a separate additive
        # sidecar: the preserved 20260624 stack and all production Field 3
        # calculations above remain byte-for-byte available and unchanged.
        try:
            from core.field3_regime_lifecycle_monitor_20260701 import build_field3_regime_lifecycle_monitor
            from core.field3_regime_lifecycle_store_20260701 import save as save_field3_lifecycle
            import sqlite3
            from core.storage.database import DB_PATH as DEFAULT_DB_PATH
            field3_lifecycle = build_field3_regime_lifecycle_monitor(snapshot, state)
            with sqlite3.connect(str(DEFAULT_DB_PATH)) as _f3_conn:
                field3_lifecycle_store = save_field3_lifecycle(_f3_conn, field3_lifecycle)
        except Exception as exc:
            field3_lifecycle = {
                "status": "FAILED_SAFELY", "error": f"{type(exc).__name__}: {exc}",
                "shadow_only": True, "production_decision_changed": False,
                "protected_regime_calculations_changed": False,
            }
            field3_lifecycle_store = {"ok": False, "error": field3_lifecycle["error"]}
        summary["field3_regime_lifecycle_monitor_20260701"] = field3_lifecycle
        state["field3_regime_lifecycle_monitor_20260701"] = field3_lifecycle
        diagnostics["field3_regime_lifecycle_monitor_ref"] = {
            "shadow_only": True, "store": field3_lifecycle_store,
            "version": field3_lifecycle.get("version"), "run_id": field3_lifecycle.get("run_id"),
            "snapshot_hash": field3_lifecycle.get("snapshot_hash"),
        }

        # Unified governance sidecar: compact, additive, and saved only in the
        # Settings-owned calculation transaction. Lunch reads the saved summary.
        try:
            from core.shadow_intelligence_governance_20260624 import build_governance_summary
            from core.shadow_intelligence_store_20260624 import save_governance
            governance = build_governance_summary(snapshot.to_dict() if hasattr(snapshot, "to_dict") else snapshot, research_grade)
            with sqlite3.connect(str(DEFAULT_DB_PATH)) as _gov_conn:
                governance_store = save_governance(_gov_conn, governance)
        except Exception as exc:
            governance = {"status":"FAILED_SAFELY","error":f"{type(exc).__name__}: {exc}","shadow_only":True,"production_decision_unchanged":True}
            governance_store = {"ok":False,"error":governance["error"]}
        summary["shadow_intelligence_governance_20260624"] = governance
        state["shadow_intelligence_governance_20260624"] = governance
        diagnostics["shadow_intelligence_governance_ref"] = {"shadow_only":True,"store":governance_store,"model_version":governance.get("model_version")}
        diagnostics["v14_snapshot_ref"] = {"snapshot_hash":v14_payload.get("snapshot_hash"),"schema_version":v14_payload.get("schema_version"),"shadow_only":True,"production_changed":False}
        diagnostics["v13_snapshot_ref"] = {
            "snapshot_hash": v13_payload.get("snapshot_hash"),
            "schema_version": v13_payload.get("schema_version"),
            "shadow_only": True,
            "production_changed": False,
        }
        # Priority Field 2/3 engine: Settings-owned, immutable sidecar only.
        try:
            from core.services.priority_field23_service_20260624 import build_and_publish_priority_field23
            priority_field23 = build_and_publish_priority_field23(state, snapshot)
        except Exception as exc:
            priority_field23 = {"ok": False, "status": "FAILED_SAFELY", "error": f"{type(exc).__name__}: {exc}", "shadow_only": True, "production_decision_unchanged": True}
        summary["priority_field23_intelligence_20260624"] = priority_field23
        diagnostics["priority_field23_ref"] = {"run_id": priority_field23.get("run_id"), "model_version": priority_field23.get("model_version"), "shadow_only": True}
        summary["research_diagnostics"] = diagnostics
        repository.save(summary, horizons, models, diagnostics)

        state["field_07_research_summary_v11"] = summary
        state["field_07_research_v12_compact"] = summary["v12_research"]
        state["field_07_research_v13_compact"] = summary["v13_research"]
        state["quant_research_v14"] = summary["quant_research_v14"]
        state["field_07_research_horizons_v11"] = horizons
        state["field_07_research_models_v11"] = models
        state["field_07_research_diagnostics_v11"] = diagnostics
        state["field_07_research_history_v11"] = repository.history(25)
        status = {
            "ok": True,
            "run_id": snapshot.run_id,
            "research_status": summary.get("research_status"),
            "research_trust_score": summary.get("research_trust_score"),
            "risk_multiplier": summary.get("risk_multiplier"),
            "shadow_only": True,
            "production_decision_unchanged": True,
            "v12_snapshot_hash": v12_snapshot.snapshot_hash,
            "v12_store": v12_store,
            "v13_snapshot_hash": v13_payload.get("snapshot_hash"),
            "v13_available_layers": (v13_payload.get("compact_results") or {}).get("available_layers", 0),
            "v14_available_methods": (v14_payload.get("readiness") or {}).get("available_methods", 0),
            "v14_store": v14_store,
            "research_grade_snapshot_hash": research_grade.get("snapshot_hash"),
            "research_grade_store": research_grade_store,
            "research_grade_shadow_only": True,
        }
        LOGGER.info(
            "field_07_shadow_stored",
            extra={
                "run_id": snapshot.run_id,
                "broker_candle_time": snapshot.broker_candle_time.isoformat(),
                "field_id": "field_07",
                "operation": "settings_shadow_research",
                "duration": time.perf_counter() - started,
                "status": "OK",
                "error_type": "",
            },
        )
        return status
    except Exception as exc:
        LOGGER.exception(
            "field_07_shadow_failed",
            extra={
                "run_id": snapshot.run_id,
                "broker_candle_time": snapshot.broker_candle_time.isoformat(),
                "field_id": "field_07",
                "operation": "settings_shadow_research",
                "duration": time.perf_counter() - started,
                "status": "ERROR",
                "error_type": type(exc).__name__,
            },
        )
        raise


__all__ = ["build_and_store_shadow_research"]

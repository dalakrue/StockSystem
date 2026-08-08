"""Atomic builder and compact SQLite persistence for Advanced Quant Research V4."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping
import json
import sqlite3
import time
import tracemalloc

import pandas as pd

from core.quant_research_v4_contract_20260622 import (
    IMPLEMENTATION_VERSION,
    guard_direction,
    identity_from_canonical,
    json_safe,
    normalize_completed_h1,
    normalize_settled_outcomes,
    utc_now_iso,
)
from services.canonical_snapshot_store import DB_PATH

VERSION = "quant-research-v4-store-20260622-v1"
BUNDLE_KEY = "__quant_research_v4__"
MIGRATION_PATH = Path(__file__).resolve().parents[1] / "migrations" / "20260622_quant_research_v4.sql"
TABLES = (
    "quant_research_v4_run",
    "quant_research_v4_method_results",
    "quant_research_v4_regime_probabilities",
    "quant_research_v4_transition_probabilities",
    "quant_research_v4_volatility_evaluation",
    "quant_research_v4_probability_decomposition",
    "quant_research_v4_direction_tests",
    "quant_research_v4_interval_tests",
    "quant_research_v4_es_tests",
    "quant_research_v4_sequential_monitor_states",
)


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Apply the idempotent migration without implicitly committing a caller transaction.

    sqlite3.Connection.executescript() issues an implicit COMMIT.  V4 rows are
    staged inside the canonical BEGIN IMMEDIATE boundary, so execute each
    complete DDL statement individually instead.
    """
    buffer: list[str] = []
    for line in MIGRATION_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        statement = "\n".join(buffer).strip()
        if sqlite3.complete_statement(statement):
            conn.execute(statement)
            buffer.clear()
    if buffer:
        raise sqlite3.OperationalError("incomplete Quant V4 migration statement")
    # Upgrade an early V4 preview schema without relying on non-portable
    # ALTER TABLE ... ADD COLUMN IF NOT EXISTS syntax.
    monitor_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(quant_research_v4_sequential_monitor_states)")}
    if monitor_columns and "status" not in monitor_columns:
        conn.execute("ALTER TABLE quant_research_v4_sequential_monitor_states ADD COLUMN status TEXT NOT NULL DEFAULT 'AVAILABLE'")


def _json(value: Any) -> str:
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _insert_rows(conn: sqlite3.Connection, table: str, rows: Iterable[Mapping[str, Any]]) -> tuple[int, int]:
    inserted = ignored = 0
    for raw in rows:
        row = dict(raw)
        columns = list(row)
        placeholders = ",".join("?" for _ in columns)
        sql = f"INSERT OR IGNORE INTO {table}({','.join(columns)}) VALUES({placeholders})"
        cursor = conn.execute(sql, [row[c] for c in columns])
        if cursor.rowcount:
            inserted += 1
        else:
            ignored += 1
    return inserted, ignored


def insert_quant_v4_bundle(conn: sqlite3.Connection, bundle: Mapping[str, Iterable[Mapping[str, Any]]]) -> dict[str, Any]:
    ensure_schema(conn)
    started = time.perf_counter()
    details = {}
    for table in TABLES:
        inserted, ignored = _insert_rows(conn, table, bundle.get(table, []))
        details[table] = {"inserted": inserted, "idempotent_ignored": ignored}
    details["database_write_time_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
    return details


def _base(identity: Mapping[str, Any], method: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_generation_id": str(identity.get("source_generation_id") or ""),
        "calculation_id": str(identity.get("calculation_id") or ""),
        "completed_h1_time": str(identity.get("latest_completed_broker_h1_time") or ""),
        "method_id": str(method.get("method_id") or "UNKNOWN"),
        "status": str(method.get("status") or "UNAVAILABLE"),
        "evaluated_at": str(method.get("evaluated_at") or utc_now_iso()),
    }


def build_persistence_bundle(result: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    identity = dict(result.get("identity") or {})
    summary = dict(result.get("summary") or {})
    bundle: dict[str, list[dict[str, Any]]] = {name: [] for name in TABLES}
    perf = dict(result.get("performance") or {})
    bundle["quant_research_v4_run"].append({
        "source_generation_id": str(identity.get("source_generation_id") or ""),
        "calculation_id": str(identity.get("calculation_id") or ""),
        "completed_h1_time": str(identity.get("latest_completed_broker_h1_time") or ""),
        "status": str(summary.get("overall_status") or "UNAVAILABLE"),
        "method_count": int(summary.get("method_count") or 0),
        "error_count": int(len(result.get("errors") or [])),
        "runtime_ms": perf.get("v4_total_wall_time_ms"),
        "peak_traced_memory_mb": perf.get("peak_traced_memory_mb"),
        "rss_delta_mb": perf.get("process_rss_delta_mb"),
        "serialized_result_bytes": perf.get("serialized_result_bytes"),
        "evaluated_at": str(result.get("evaluated_at") or utc_now_iso()),
        "payload_json": _json({"summary": summary, "identity": identity, "performance": perf}),
    })
    methods = {
        key: dict(result.get(key) or {}) for key in (
            "regime_probability", "transition_probability", "realized_garch", "rough_volatility",
            "volatility_evaluation", "probability_decomposition", "directional_skill",
            "interval_backtest", "expected_shortfall_backtest", "sequential_monitor",
        )
    }
    for key, method in methods.items():
        base = _base(identity, method)
        bundle["quant_research_v4_method_results"].append({
            **base,
            "horizon_hours": 0,
            "condition_key": "GLOBAL",
            "sample_count": int(method.get("sample_count") or 0),
            "effective_sample_count": int(method.get("effective_sample_count") or 0),
            "score": method.get("score"),
            "p_value": method.get("p_value"),
            "payload_json": _json({k: v for k, v in method.items() if not str(k).startswith("internal_")}),
        })
    regime = methods["regime_probability"]
    for state, probability in (regime.get("state_probabilities") or {}).items():
        bundle["quant_research_v4_regime_probabilities"].append({
            **_base(identity, regime), "state_name": str(state), "probability": probability,
            "entropy": regime.get("state_entropy"), "payload_json": _json({"duration": (regime.get("expected_state_duration_hours") or {}).get(state)}),
        })
    transition = methods["transition_probability"]
    for horizon in (1, 3, 6):
        value = transition.get(f"transition_probability_{horizon}h")
        bundle["quant_research_v4_transition_probabilities"].append({
            **_base(identity, transition), "horizon_hours": horizon, "probability": value,
            "hazard": transition.get("transition_hazard"), "payload_json": _json({"stability_score": transition.get("stability_score")}),
        })
    vol_eval = methods["volatility_evaluation"]
    ranking = list(vol_eval.get("candidate_ranking") or [])
    for rank, model in enumerate(ranking, 1):
        bundle["quant_research_v4_volatility_evaluation"].append({
            **_base(identity, vol_eval), "model_id": str(model),
            "qlike": (vol_eval.get("qlike_by_model") or {}).get(model),
            "qlike_skill": (vol_eval.get("qlike_skill_vs_baseline") or {}).get(model),
            "rank_number": rank, "support_count": int(vol_eval.get("support_count") or 0),
            "payload_json": _json((vol_eval.get("paired_loss_differences") or {}).get(model) or {}),
        })
    probability = methods["probability_decomposition"]
    for event_id, event in (probability.get("events") or {}).items():
        for horizon, item in (event.get("horizons") or {}).items():
            bundle["quant_research_v4_probability_decomposition"].append({
                **_base(identity, probability), "event_id": str(event_id), "horizon_hours": int(horizon),
                "brier_score": item.get("brier_score"), "reliability_component": item.get("reliability_component"),
                "resolution_component": item.get("resolution_component"), "uncertainty_component": item.get("uncertainty_component"),
                "support_count": int(item.get("sample_count") or 0), "status": str(item.get("status") or ("AVAILABLE" if item.get("brier_score") is not None else "INSUFFICIENT_EVIDENCE")),
                "payload_json": _json(item),
            })
    direction = methods["directional_skill"]
    for condition, item in (direction.get("tests") or {}).items():
        horizon = int(condition[1:]) if str(condition).startswith("H") and str(condition)[1:].isdigit() else 0
        bundle["quant_research_v4_direction_tests"].append({
            **_base(identity, direction), "condition_key": str(condition), "horizon_hours": horizon,
            "hit_rate": item.get("hit_rate"), "expected_hit_rate": item.get("expected_hit_rate_under_independence"),
            "test_statistic": item.get("PT_statistic"), "p_value": item.get("block_bootstrap_p_value") or item.get("asymptotic_p_value"),
            "support_count": int(item.get("sample_count") or 0), "status": str(item.get("direction_skill_status") or item.get("status") or "NOT_TESTABLE"),
            "payload_json": _json(item),
        })
    interval = methods["interval_backtest"]
    for horizon, levels in (interval.get("tests") or {}).items():
        for level, item in (levels or {}).items():
            bundle["quant_research_v4_interval_tests"].append({
                **_base(identity, interval), "horizon_hours": int(horizon), "nominal_coverage": float(level) / 100.0,
                "empirical_coverage": item.get("empirical_coverage"), "lr_uc": item.get("LR_uc"), "lr_ind": item.get("LR_ind"),
                "lr_cc": item.get("LR_cc"), "p_cc": item.get("p_cc"), "support_count": int(item.get("sample_count") or 0),
                "status": str(item.get("conditional_coverage_status") or item.get("status") or "NOT_TESTABLE"), "payload_json": _json(item),
            })
    es = methods["expected_shortfall_backtest"]
    bundle["quant_research_v4_es_tests"].append({
        **_base(identity, es), "condition_key": "GLOBAL", "exception_count": es.get("exception_count"),
        "exception_rate": es.get("exception_rate"), "test_statistic": es.get("test_statistic"), "p_value": es.get("bootstrap_p_value"),
        "severity_underestimation": int(bool(es.get("severity_underestimation"))),
        "status": str(es.get("ES_backtest_status") or es.get("status") or "NOT_TESTABLE"), "payload_json": _json(es),
    })
    monitor = methods["sequential_monitor"]
    for monitor_id, item in (monitor.get("monitors") or {}).items():
        bundle["quant_research_v4_sequential_monitor_states"].append({
            **_base(identity, monitor), "monitor_id": str(monitor_id), "epoch_id": str(item.get("epoch_id") or monitor.get("epoch_id") or "EPOCH_1"),
            "log_lr": float(item.get("log_LR") or 0.0), "state": str(item.get("state") or "CONTINUE_MONITORING"),
            "observation_count": int(item.get("observation_count") or 0), "new_unique_observations": int(item.get("new_unique_observations") or 0),
            "reset_reason": str(item.get("reset_reason") or monitor.get("reset_reason") or "INITIALIZATION"), "payload_json": _json(item),
        })
    return bundle


def _rss_mb() -> float | None:
    try:
        import psutil
        return float(psutil.Process().memory_info().rss / (1024 * 1024))
    except Exception:
        return None


def _protected_regime(canonical: Mapping[str, Any]) -> Any:
    regime = canonical.get("regime") if isinstance(canonical.get("regime"), Mapping) else {}
    return regime.get("major_regime") or regime.get("current_regime") or canonical.get("current_regime")


def _compact_method(method: Mapping[str, Any]) -> dict[str, Any]:
    return {str(k): deepcopy(v) for k, v in method.items() if not str(k).startswith("internal_")}


def build_quant_research_v4_transaction(
    canonical: Mapping[str, Any],
    *,
    completed_h1: pd.DataFrame,
    settled_outcomes: pd.DataFrame | None = None,
    previous: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build V4 once for the Settings transaction and stage all rows atomically."""
    canonical_out = deepcopy(dict(canonical or {}))
    previous = dict(previous or {})
    started = time.perf_counter()
    rss_before = _rss_mb()
    tracemalloc.start()
    try:
        frame, frame_meta = normalize_completed_h1(
            completed_h1,
            completed_h1_time=canonical_out.get("latest_completed_candle_time"),
            max_rows=3000,
        )
        settled = normalize_settled_outcomes(settled_outcomes, max_rows=3000)
        identity = identity_from_canonical(canonical_out, frame_meta)

        from core.hamilton_regime_research_v4_20260622 import run_hamilton_regime_model
        from core.filardo_transition_research_v4_20260622 import run_filardo_transition_model
        from core.realized_garch_research_v4_20260622 import run_realized_garch
        from core.rough_volatility_research_v4_20260622 import run_rough_volatility
        from core.patton_volatility_evaluation_v4_20260622 import run_patton_evaluation
        from core.murphy_probability_decomposition_v4_20260622 import run_murphy_decomposition
        from core.pesaran_timmermann_direction_v4_20260622 import run_pesaran_timmermann
        from core.christoffersen_interval_backtest_v4_20260622 import run_christoffersen_backtest
        from core.expected_shortfall_backtest_v4_20260622 import run_expected_shortfall_backtest
        from core.wald_sequential_monitor_v4_20260622 import run_wald_monitors

        hamilton = run_hamilton_regime_model(frame, identity, settled_outcomes=settled, protected_regime=_protected_regime(canonical_out))
        filardo = run_filardo_transition_model(frame, identity, hamilton, settled_outcomes=settled, canonical=canonical_out)
        realized = run_realized_garch(frame, identity, canonical=canonical_out)
        rough = run_rough_volatility(frame, identity)
        patton = run_patton_evaluation(identity, realized, canonical=canonical_out)
        murphy = run_murphy_decomposition(identity, settled)
        pt = run_pesaran_timmermann(identity, settled, bootstrap_replications=500)
        christoffersen = run_christoffersen_backtest(identity, settled)
        es = run_expected_shortfall_backtest(identity, settled, bootstrap_replications=500)
        previous_v4 = previous.get("quant_research_v4") if isinstance(previous.get("quant_research_v4"), Mapping) else {}
        previous_monitor = (previous_v4.get("sequential_monitor") or {}) if isinstance(previous_v4, Mapping) else {}
        wald = run_wald_monitors(identity, settled, canonical=canonical_out, previous_states={
            **dict(previous_monitor.get("monitors") or {}),
            "epoch_id": previous_monitor.get("epoch_id") or "QUANT_V4_EPOCH_1",
            "reset_reason": previous_monitor.get("reset_reason") or "INITIALIZATION",
        })

        methods = [hamilton, filardo, realized, rough, patton, murphy, pt, christoffersen, es, wald]
        errors = [
            {"method_id": m.get("method_id"), "status": m.get("status"), "error": m.get("error")}
            for m in methods if m.get("error") or m.get("status") == "UNAVAILABLE"
        ]
        available_count = sum(str(m.get("status")) == "AVAILABLE" for m in methods)
        insufficient_count = sum(str(m.get("status")) == "INSUFFICIENT_EVIDENCE" for m in methods)
        regime_probs = hamilton.get("state_probabilities") or {}
        regime_probability = max(regime_probs.values()) if regime_probs else None
        probability_status = (
            "OVERCONFIDENT_WARNING" if murphy.get("overall_overconfidence_warning") else
            "UNDERCONFIDENT_WARNING" if murphy.get("overall_underconfidence_warning") else
            ("AVAILABLE" if murphy.get("status") == "AVAILABLE" else "INSUFFICIENT_EVIDENCE")
        )
        summary = {
            "direction_skill": pt.get("direction_skill_status") or "INSUFFICIENT_EVIDENCE",
            "direction_skill_p_value": pt.get("block_bootstrap_p_value") or pt.get("asymptotic_p_value"),
            "probability_reliability": probability_status,
            "interval_conditional_coverage": christoffersen.get("conditional_coverage_status") or "INSUFFICIENT_EVIDENCE",
            "regime_state_probability": regime_probability,
            "regime_state": hamilton.get("most_likely_shadow_state") or "INSUFFICIENT_EVIDENCE",
            "transition_risk_6h": filardo.get("transition_probability_6h"),
            "volatility_model_status": realized.get("model_status") or realized.get("status") or "UNAVAILABLE",
            "preferred_shadow_volatility_method": patton.get("preferred_shadow_volatility_method") or "INSUFFICIENT_EVIDENCE",
            "tail_risk_backtest": es.get("ES_backtest_status") or "INSUFFICIENT_EVIDENCE",
            "sequential_monitor": wald.get("sequential_monitor_status") or "CONTINUE_MONITORING",
            "overall_status": "SHADOW_READY" if available_count >= 6 else ("LIMITED_EVIDENCE" if available_count else "INSUFFICIENT_EVIDENCE"),
            "method_count": 10,
            "available_method_count": available_count,
            "insufficient_method_count": insufficient_count,
            "shadow_only": True,
            "production_influence_enabled": False,
            "generation_id": identity.get("source_generation_id"),
            "broker_h1_time": identity.get("latest_completed_broker_h1_time"),
        }
        protected = str((canonical_out.get("final_decision") or {}).get("final_decision") or "WAIT").upper()
        wait_only = bool(es.get("severity_underestimation") or wald.get("sequential_monitor_status") == "DEGRADATION_EVIDENCE")
        proposed = "WAIT" if wait_only else protected
        after_guard = guard_direction(protected, proposed)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss_after = _rss_mb()
        performance = {
            "v4_total_wall_time_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "peak_traced_memory_mb": round(peak / (1024 * 1024), 3),
            "process_rss_before_mb": rss_before,
            "process_rss_after_mb": rss_after,
            "process_rss_delta_mb": (round(rss_after - rss_before, 3) if rss_before is not None and rss_after is not None else None),
            "ohlc_rows": int(len(frame)),
            "settled_outcome_rows": int(len(settled)),
            "bootstrap_replications": 500,
        }
        result = {
            "version": IMPLEMENTATION_VERSION,
            "identity": identity,
            "regime_probability": _compact_method(hamilton),
            "transition_probability": _compact_method(filardo),
            "realized_garch": _compact_method(realized),
            "rough_volatility": _compact_method(rough),
            "volatility_evaluation": _compact_method(patton),
            "probability_decomposition": _compact_method(murphy),
            "directional_skill": _compact_method(pt),
            "interval_backtest": _compact_method(christoffersen),
            "expected_shortfall_backtest": _compact_method(es),
            "sequential_monitor": _compact_method(wald),
            "summary": summary,
            "errors": errors,
            "performance": performance,
            "promotion_policy": {
                "automatic_promotion": False,
                "manual_configuration_required": True,
                "permitted_future_influence": ["reduce confidence", "reduce priority", "widen uncertainty", "lower risk", "recommend WAIT"],
                "forbidden_influence": ["BUY to SELL reversal", "SELL to BUY reversal", "risk multiplier increase"],
            },
            "protected_direction": protected,
            "shadow_wait_recommendation": proposed,
            "direction_after_guard": after_guard,
            "direction_reversal_possible": False,
            "evaluated_at": utc_now_iso(),
            "input_contract": {**frame_meta, "settled_outcome_rows": int(len(settled)), "current_incomplete_candle_excluded": True},
            "shadow_only": True,
            "production_influence_enabled": False,
        }
        # Size is measured on the compact publishable object.
        result["performance"]["serialized_result_bytes"] = len(_json(result).encode("utf-8"))
        canonical_out["quant_research_v4"] = result
        canonical_out["quant_research_v4_ai_evidence"] = {
            "generation_id": identity.get("source_generation_id"),
            "broker_h1_time": identity.get("latest_completed_broker_h1_time"),
            "summary": summary,
            "errors": errors,
            "shadow_only": True,
            "production_influence_enabled": False,
        }
        canonical_out.setdefault("metadata", {})["quant_research_v4_status"] = summary["overall_status"]
        canonical_out["metadata"]["quant_research_v4_production_influence_enabled"] = False
        bundle = build_persistence_bundle(result)
        return canonical_out, {BUNDLE_KEY: bundle}, {
            "version": VERSION,
            "status": summary["overall_status"],
            "generation_id": identity.get("source_generation_id"),
            "completed_h1_time": identity.get("latest_completed_broker_h1_time"),
            "rows_staged": sum(len(v) for v in bundle.values()),
            "runtime_ms": performance["v4_total_wall_time_ms"],
            "production_influence_enabled": False,
            "protected_direction_unchanged_or_wait_only": after_guard in {protected, "WAIT"},
        }
    except Exception as exc:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        previous_v4 = previous.get("quant_research_v4") if isinstance(previous.get("quant_research_v4"), Mapping) else None
        if previous_v4:
            canonical_out["quant_research_v4"] = deepcopy(dict(previous_v4))
            canonical_out["quant_research_v4"]["current_generation_error"] = str(exc)[:1000]
            canonical_out["quant_research_v4"]["last_valid_shadow_result_preserved"] = True
        canonical_out.setdefault("metadata", {})["quant_research_v4_status"] = "FAILED_SAFELY"
        canonical_out["metadata"]["quant_research_v4_error"] = str(exc)[:1000]
        return canonical_out, {}, {
            "version": VERSION, "status": "FAILED_SAFELY", "error": str(exc),
            "production_influence_enabled": False,
            "last_valid_shadow_result_preserved": bool(previous_v4),
        }


def latest_quant_v4_summary(*, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_schema(conn)
        row = conn.execute("SELECT payload_json FROM quant_research_v4_run ORDER BY completed_h1_time DESC, evaluated_at DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else {}
    finally:
        conn.close()


def query_quant_v4_table(table: str, *, search: str = "", limit: int = 120, db_path: Path | str = DB_PATH) -> pd.DataFrame:
    if table not in TABLES:
        return pd.DataFrame()
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_schema(conn)
        frame = pd.read_sql_query(f"SELECT * FROM {table} ORDER BY completed_h1_time DESC, evaluated_at DESC LIMIT ?", conn, params=(int(limit),))
    finally:
        conn.close()
    if search.strip() and not frame.empty:
        term = search.strip().lower()
        mask = frame.astype(str).apply(lambda col: col.str.lower().str.contains(term, regex=False, na=False)).any(axis=1)
        frame = frame.loc[mask]
    return frame.reset_index(drop=True)


__all__ = [
    "VERSION", "BUNDLE_KEY", "TABLES", "ensure_schema", "insert_quant_v4_bundle",
    "build_persistence_bundle", "build_quant_research_v4_transaction", "latest_quant_v4_summary",
    "query_quant_v4_table", "guard_direction",
]

"""SQLite persistence for the 2026-06-21 research-validation layer.

All normal calculation rows are inserted by the caller's canonical
``BEGIN IMMEDIATE`` transaction. Rejected generations use a standalone atomic
write because no canonical snapshot is published for them.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping
import json
import sqlite3

from core.research_validation_common_20260621 import json_safe, stable_hash, utc_now_iso
from services.canonical_snapshot_store import DB_PATH

VERSION = "research-validation-store-20260621-v1"
BUNDLE_KEY = "__research_validation_20260621__"

SCHEMAS: dict[str, str] = {
    "data_quality_generation": """
      generation_id TEXT PRIMARY KEY, source_hash TEXT NOT NULL, source_generation_id TEXT,
      evaluated_at TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL,
      source_row_count INTEGER, cleaned_row_count INTEGER, latest_timestamp TEXT,
      critical_failure_count INTEGER, warning_count INTEGER, calculation_version TEXT,
      payload_json TEXT NOT NULL
    """,
    "data_quality_constraint_result": """
      record_key TEXT PRIMARY KEY, generation_id TEXT NOT NULL, constraint_name TEXT NOT NULL,
      status TEXT NOT NULL, severity TEXT NOT NULL, observed_json TEXT, expected_json TEXT,
      violation_count INTEGER, detail TEXT, evaluated_at TEXT NOT NULL,
      calculation_version TEXT, payload_json TEXT NOT NULL
    """,
    "data_quality_metric_history": """
      record_key TEXT PRIMARY KEY, generation_id TEXT NOT NULL, metric_name TEXT NOT NULL,
      value_numeric REAL, value_text TEXT, evaluated_at TEXT NOT NULL,
      calculation_version TEXT, payload_json TEXT NOT NULL
    """,
    "rejected_calculation_generation": """
      rejection_id TEXT PRIMARY KEY, generation_id TEXT, source_hash TEXT,
      rejected_at TEXT NOT NULL, stage TEXT NOT NULL, reason TEXT NOT NULL,
      failed_constraints_json TEXT NOT NULL, previous_valid_run_id TEXT,
      previous_valid_generation INTEGER, calculation_version TEXT, payload_json TEXT NOT NULL
    """,
    "conditional_predictive_ability_history": """
      evaluation_id TEXT PRIMARY KEY, evaluated_at TEXT NOT NULL, condition_name TEXT,
      condition_value TEXT, horizon INTEGER, model_a TEXT, model_b TEXT, loss_name TEXT,
      settled_sample_count INTEGER, mean_loss_a REAL, mean_loss_b REAL,
      mean_loss_difference REAL, effect_size REAL, test_statistic REAL, p_value REAL,
      evidence_status TEXT, stability_pass INTEGER, source_generation_id TEXT,
      calculation_version TEXT, payload_json TEXT NOT NULL
    """,
    "research_spa_results": """
      evaluation_id TEXT PRIMARY KEY, benchmark_id TEXT, challenger_family TEXT,
      number_of_challengers INTEGER, loss_name TEXT, horizon INTEGER,
      bootstrap_method TEXT, block_length INTEGER, bootstrap_iterations INTEGER,
      spa_statistic REAL, spa_p_value REAL, best_challenger_id TEXT,
      best_effect_size REAL, minimum_sample_pass INTEGER, stability_pass INTEGER,
      resource_budget_pass INTEGER, promotion_allowed INTEGER, source_generation_id TEXT,
      evaluated_at TEXT, calculation_version TEXT, payload_json TEXT NOT NULL
    """,
    "covariate_shift_conformal_history": """
      evaluation_id TEXT PRIMARY KEY, evaluated_at TEXT, source_generation_id TEXT,
      horizon INTEGER, status TEXT, sample_count INTEGER, effective_sample_size REAL,
      maximum_weight_share REAL, weighted_residual_quantile REAL,
      promotion_allowed INTEGER, calculation_version TEXT, payload_json TEXT NOT NULL
    """,
    "fforma_shadow_history": """
      evaluation_id TEXT PRIMARY KEY, evaluated_at TEXT, artifact_id TEXT, status TEXT,
      source_generation_id TEXT, promotion_allowed INTEGER, calculation_version TEXT,
      payload_json TEXT NOT NULL
    """,
    "expert_weight_history": """
      record_key TEXT PRIMARY KEY, settlement_id TEXT NOT NULL, settled_at TEXT NOT NULL,
      expert_id TEXT NOT NULL, previous_weight REAL, new_weight REAL, settled_loss REAL,
      learning_rate REAL, share_rate REAL, minimum_weight REAL, maximum_weight REAL,
      maximum_hourly_weight_change REAL, calculation_version TEXT, payload_json TEXT NOT NULL
    """,
    "expert_tracker_state": """
      state_id TEXT PRIMARY KEY, updated_at TEXT NOT NULL, last_settlement_id TEXT,
      update_count INTEGER, mode TEXT, promotion_allowed INTEGER, weights_json TEXT NOT NULL,
      calculation_version TEXT, payload_json TEXT NOT NULL
    """,
    "expert_tracker_comparison": """
      comparison_id TEXT PRIMARY KEY, settlement_id TEXT, settled_at TEXT,
      maximum_absolute_change REAL, normalization_error REAL, calculation_version TEXT,
      payload_json TEXT NOT NULL
    """,
    "ml_production_readiness_history": """
      evaluation_id TEXT PRIMARY KEY, evaluated_at TEXT, data_readiness_score REAL,
      model_readiness_score REAL, infrastructure_readiness_score REAL,
      monitoring_readiness_score REAL, overall_readiness_score REAL,
      critical_failure_count INTEGER, warning_count INTEGER, promotion_allowed INTEGER,
      calculation_version TEXT, payload_json TEXT NOT NULL
    """,
    "sliding_monitoring_state": """
      state_id TEXT PRIMARY KEY, updated_at TEXT, calculation_version TEXT,
      payload_json TEXT NOT NULL
    """,
    "bounded_quantile_monitoring_state": """
      state_id TEXT PRIMARY KEY, updated_at TEXT, relative_error_tolerance REAL,
      calculation_version TEXT, payload_json TEXT NOT NULL
    """,
    "model_x_knockoff_feature_history": """
      record_key TEXT PRIMARY KEY, source_generation_id TEXT NOT NULL, window_id TEXT,
      window_start TEXT, window_end TEXT, train_start TEXT, train_end TEXT,
      test_start TEXT, test_end TEXT, feature_name TEXT, feature_group TEXT,
      knockoff_statistic REAL, test_effect REAL, selected_state INTEGER, threshold REAL, fdr_target REAL,
      sample_support INTEGER, test_sample_support INTEGER, regime_support INTEGER, input_hash TEXT,
      calculation_version TEXT, evaluated_at TEXT, payload_json TEXT NOT NULL
    """,
    "online_fdr_test_history": """
      record_key TEXT PRIMARY KEY, source_generation_id TEXT NOT NULL, test_key TEXT,
      test_family TEXT, source_module TEXT, raw_p_value REAL, allocated_alpha REAL,
      adjusted_result TEXT, wealth_before REAL, wealth_after REAL, test_index INTEGER,
      dependence_assumption TEXT, calculation_version TEXT, evaluated_at TEXT,
      payload_json TEXT NOT NULL
    """,
    "online_fdr_state": """
      state_id TEXT PRIMARY KEY, source_generation_id TEXT, state_version TEXT,
      wealth REAL, test_index INTEGER, updated_at TEXT, calculation_version TEXT,
      payload_json TEXT NOT NULL
    """,
    "reject_option_history": """
      record_key TEXT PRIMARY KEY, source_generation_id TEXT NOT NULL,
      protected_decision TEXT, shadow_decision TEXT, rejection_cost REAL,
      accepted_risk_estimate REAL, status TEXT, calculation_version TEXT,
      evaluated_at TEXT, payload_json TEXT NOT NULL
    """,
    "flexible_loss_history": """
      evaluation_id TEXT PRIMARY KEY, source_generation_id TEXT, window_id TEXT,
      window_start TEXT, window_end TEXT, train_start TEXT, train_end TEXT,
      test_start TEXT, test_end TEXT, sample_count INTEGER, status TEXT,
      mean_flexible_loss REAL, loss_definition_version TEXT, calculation_version TEXT,
      evaluated_at TEXT, payload_json TEXT NOT NULL
    """,
    "model_explanation_cache": """
      explanation_id TEXT PRIMARY KEY, canonical_calculation_id TEXT,
      source_generation_id TEXT, status TEXT, input_hash TEXT, output_hash TEXT,
      calculation_version TEXT, evaluated_at TEXT, payload_json TEXT NOT NULL
    """,
    "monotonicity_validation_history": """
      record_key TEXT PRIMARY KEY, source_generation_id TEXT, contract_name TEXT,
      input_name TEXT, output_name TEXT, expected_direction TEXT, status TEXT,
      sample_support INTEGER, violation_rate REAL, calculation_version TEXT,
      evaluated_at TEXT, payload_json TEXT NOT NULL
    """,
    "delta_maintenance_history": """
      record_key TEXT PRIMARY KEY, source_generation_id TEXT, status TEXT, mode TEXT,
      source_row_count INTEGER, exact_full_recompute_equal INTEGER,
      optimization_accepted INTEGER, calculation_version TEXT, evaluated_at TEXT,
      payload_json TEXT NOT NULL
    """,
    "exact_delta_state": """
      state_id TEXT PRIMARY KEY, source_generation_id TEXT, mode TEXT,
      source_row_count INTEGER, prefix_hash TEXT, updated_at TEXT,
      calculation_version TEXT, payload_json TEXT NOT NULL
    """,
    "provenance_node": """
      node_id TEXT PRIMARY KEY, source_generation_id TEXT, node_type TEXT,
      immutable_identity TEXT, natural_key TEXT, payload_hash TEXT, label TEXT, calculation_version TEXT,
      evaluated_at TEXT, payload_json TEXT NOT NULL
    """,
    "provenance_edge": """
      edge_id TEXT PRIMARY KEY, source_generation_id TEXT, source_node_id TEXT,
      target_node_id TEXT, relation_type TEXT, calculation_version TEXT,
      evaluated_at TEXT, payload_json TEXT NOT NULL
    """,
    "metamorphic_test_history": """
      record_key TEXT PRIMARY KEY, source_generation_id TEXT, relation_name TEXT,
      status TEXT, detail TEXT, calculation_version TEXT, evaluated_at TEXT,
      payload_json TEXT NOT NULL
    """,
    "calm_operation_classification": """
      record_key TEXT PRIMARY KEY, source_generation_id TEXT, operation_name TEXT,
      monotonicity_class TEXT, coordination_required INTEGER, reason TEXT,
      calculation_version TEXT, evaluated_at TEXT, payload_json TEXT NOT NULL
    """,
    "evidence_gate_history": """
      record_key TEXT PRIMARY KEY, source_generation_id TEXT, gate_name TEXT,
      gate_pass INTEGER, calculation_version TEXT, evaluated_at TEXT,
      payload_json TEXT NOT NULL
    """,
    "research_paper_run": """
      record_key TEXT PRIMARY KEY, source_generation_id TEXT, paper_number INTEGER,
      paper_title TEXT, status TEXT, mode TEXT, input_hash TEXT, output_hash TEXT,
      schema_version INTEGER, production_influence_enabled INTEGER, all_gates_pass INTEGER,
      calculation_version TEXT, evaluated_at TEXT, payload_json TEXT NOT NULL
    """,
}

REQUIRED_COLUMN_ALTERS: dict[str, dict[str, str]] = {
    "model_x_knockoff_feature_history": {
        "train_start": "TEXT", "train_end": "TEXT", "test_start": "TEXT", "test_end": "TEXT",
        "test_effect": "REAL", "test_sample_support": "INTEGER",
    },
    "flexible_loss_history": {
        "train_start": "TEXT", "train_end": "TEXT", "test_start": "TEXT", "test_end": "TEXT",
    },
    "provenance_node": {"natural_key": "TEXT", "payload_hash": "TEXT"},
}


PRIMARY_KEYS = {
    "data_quality_generation": "generation_id",
    "data_quality_constraint_result": "record_key",
    "data_quality_metric_history": "record_key",
    "rejected_calculation_generation": "rejection_id",
    "conditional_predictive_ability_history": "evaluation_id",
    "research_spa_results": "evaluation_id",
    "covariate_shift_conformal_history": "evaluation_id",
    "fforma_shadow_history": "evaluation_id",
    "expert_weight_history": "record_key",
    "expert_tracker_state": "state_id",
    "expert_tracker_comparison": "comparison_id",
    "ml_production_readiness_history": "evaluation_id",
    "sliding_monitoring_state": "state_id",
    "bounded_quantile_monitoring_state": "state_id",
    "model_x_knockoff_feature_history": "record_key",
    "online_fdr_test_history": "record_key",
    "online_fdr_state": "state_id",
    "reject_option_history": "record_key",
    "flexible_loss_history": "evaluation_id",
    "model_explanation_cache": "explanation_id",
    "monotonicity_validation_history": "record_key",
    "delta_maintenance_history": "record_key",
    "exact_delta_state": "state_id",
    "provenance_node": "node_id",
    "provenance_edge": "edge_id",
    "metamorphic_test_history": "record_key",
    "calm_operation_classification": "record_key",
    "evidence_gate_history": "record_key",
    "research_paper_run": "record_key",
}


def ensure_schema(conn: sqlite3.Connection) -> None:
    for table, columns in SCHEMAS.items():
        conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}"({columns})')
    for table, additions in REQUIRED_COLUMN_ALTERS.items():
        existing = {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
        for column, declaration in additions.items():
            if column not in existing:
                conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {declaration}')
    conn.executescript("""
      CREATE INDEX IF NOT EXISTS idx_dq_generation_time ON data_quality_generation(evaluated_at DESC);
      CREATE INDEX IF NOT EXISTS idx_dq_constraint_generation ON data_quality_constraint_result(generation_id,status,severity);
      CREATE INDEX IF NOT EXISTS idx_cpa_slice ON conditional_predictive_ability_history(horizon,condition_name,condition_value,evaluated_at DESC);
      CREATE INDEX IF NOT EXISTS idx_spa_eval ON research_spa_results(evaluated_at DESC,horizon);
      CREATE INDEX IF NOT EXISTS idx_expert_weight_time ON expert_weight_history(settled_at DESC,expert_id);
      CREATE INDEX IF NOT EXISTS idx_model_x_generation ON model_x_knockoff_feature_history(source_generation_id,window_id,selected_state);
      CREATE INDEX IF NOT EXISTS idx_online_fdr_generation ON online_fdr_test_history(source_generation_id,test_index);
      CREATE INDEX IF NOT EXISTS idx_online_fdr_state_time ON online_fdr_state(updated_at DESC);
      CREATE INDEX IF NOT EXISTS idx_reject_option_generation ON reject_option_history(source_generation_id);
      CREATE INDEX IF NOT EXISTS idx_flexible_loss_generation ON flexible_loss_history(source_generation_id,window_id);
      CREATE INDEX IF NOT EXISTS idx_explanation_calculation ON model_explanation_cache(canonical_calculation_id);
      CREATE INDEX IF NOT EXISTS idx_monotonicity_generation ON monotonicity_validation_history(source_generation_id,contract_name);
      CREATE INDEX IF NOT EXISTS idx_delta_state_time ON exact_delta_state(updated_at DESC);
      CREATE INDEX IF NOT EXISTS idx_provenance_node_generation ON provenance_node(source_generation_id,node_type);
      CREATE INDEX IF NOT EXISTS idx_provenance_edge_to ON provenance_edge(source_generation_id,target_node_id);
      CREATE INDEX IF NOT EXISTS idx_metamorphic_generation ON metamorphic_test_history(source_generation_id,relation_name);
      CREATE INDEX IF NOT EXISTS idx_gate_generation ON evidence_gate_history(source_generation_id,gate_name);
      CREATE INDEX IF NOT EXISTS idx_paper_run_generation ON research_paper_run(source_generation_id,paper_number);
    """)


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _normalise(table: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(json_safe(raw))
    payload = dict(row)
    row["payload_json"] = json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))
    for key, value in list(row.items()):
        if isinstance(value, (dict, list, tuple)):
            if key.endswith("_json"):
                row[key] = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
            elif key not in {"payload_json", "payload"}:
                row[key + "_json"] = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    for key in (
        "promotion_allowed", "minimum_sample_pass", "stability_pass", "resource_budget_pass",
        "selected_state", "exact_full_recompute_equal", "optimization_accepted",
        "coordination_required", "gate_pass", "production_influence_enabled", "all_gates_pass",
    ):
        if key in row and row[key] is not None:
            row[key] = 1 if bool(row[key]) else 0
    pk = PRIMARY_KEYS[table]
    if not row.get(pk):
        row[pk] = f"{table[:4].upper()}-" + stable_hash([table, payload])[:24]
    row.setdefault("calculation_version", VERSION)
    row.setdefault("evaluated_at", row.get("updated_at") or row.get("settled_at") or utc_now_iso())
    return row


def insert_research_validation_bundle(conn: sqlite3.Connection, bundle: Mapping[str, Iterable[Mapping[str, Any]]]) -> dict[str, Any]:
    ensure_schema(conn)
    result: dict[str, Any] = {}
    for table, rows in bundle.items():
        if table not in SCHEMAS:
            continue
        allowed = _columns(conn, table)
        inserted = ignored = 0
        for raw in rows or []:
            row = _normalise(table, raw)
            selected = [name for name in row if name in allowed]
            values = [row[name] for name in selected]
            sql = f'INSERT OR IGNORE INTO "{table}"({",".join(chr(34)+name+chr(34) for name in selected)}) VALUES({",".join("?" for _ in selected)})'
            before = conn.total_changes
            conn.execute(sql, values)
            if conn.total_changes > before: inserted += 1
            else: ignored += 1
        result[table] = {"inserted": inserted, "idempotent_ignored": ignored}
    return result


def record_rejected_generation(
    report: Any,
    *,
    reason: str,
    db_path: Path | str = DB_PATH,
    previous_valid: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    report_dict = report.as_dict() if hasattr(report, "as_dict") else dict(report or {})
    previous = dict(previous_valid or {})
    failed = report_dict.get("failed_constraints") or [row for row in report_dict.get("constraints", []) if row.get("status") == "FAIL"]
    row = {
        "rejection_id": "REJ-" + stable_hash([report_dict.get("generation_id"), report_dict.get("stage"), failed, reason])[:24],
        "generation_id": report_dict.get("generation_id"),
        "source_hash": report_dict.get("source_hash"),
        "rejected_at": utc_now_iso(),
        "stage": report_dict.get("stage") or "UNKNOWN",
        "reason": str(reason),
        "failed_constraints_json": failed,
        "previous_valid_run_id": previous.get("run_id"),
        "previous_valid_generation": previous.get("calculation_generation") or previous.get("generation"),
        "calculation_version": report_dict.get("calculation_version") or VERSION,
    }
    path = Path(db_path); path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL"); conn.execute("PRAGMA busy_timeout=30000"); conn.execute("BEGIN IMMEDIATE")
        result = insert_research_validation_bundle(conn, {"rejected_calculation_generation": [row]})
        conn.commit()
        return {"ok": True, "row": row, "result": result}
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()


def latest_expert_state(conn: sqlite3.Connection | None = None, *, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    owned = conn is None
    connection = conn or sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    try:
        ensure_schema(connection)
        row = connection.execute("SELECT payload_json FROM expert_tracker_state ORDER BY updated_at DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else {}
    finally:
        if owned: connection.close()


def _latest_payload(table: str, order_column: str, conn: sqlite3.Connection | None = None, *, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    owned = conn is None
    connection = conn or sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    try:
        ensure_schema(connection)
        row = connection.execute(f'SELECT payload_json FROM "{table}" ORDER BY "{order_column}" DESC LIMIT 1').fetchone()
        return json.loads(row[0]) if row else {}
    finally:
        if owned:
            connection.close()


def latest_online_fdr_state(conn: sqlite3.Connection | None = None, *, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    return _latest_payload("online_fdr_state", "updated_at", conn, db_path=db_path)


def latest_delta_state(conn: sqlite3.Connection | None = None, *, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    return _latest_payload("exact_delta_state", "updated_at", conn, db_path=db_path)


def query_provenance_lineage(
    result_node_id: str,
    *,
    source_generation_id: str | None = None,
    max_depth: int = 6,
    max_nodes: int = 200,
    conn: sqlite3.Connection | None = None,
    db_path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Return a bounded reverse lineage graph for one displayed research result."""
    owned = conn is None
    connection = conn or sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    try:
        ensure_schema(connection)
        generation_clause = " AND source_generation_id=?" if source_generation_id else ""
        params_tail = [source_generation_id] if source_generation_id else []
        frontier = [str(result_node_id)]
        seen: set[str] = set()
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for _depth in range(max(0, min(int(max_depth), 12)) + 1):
            if not frontier or len(seen) >= max_nodes:
                break
            current = [node for node in frontier if node not in seen][: max_nodes - len(seen)]
            frontier = []
            if not current:
                continue
            marks = ",".join("?" for _ in current)
            node_rows = connection.execute(
                f'SELECT payload_json FROM provenance_node WHERE node_id IN ({marks}){generation_clause}',
                current + params_tail,
            ).fetchall()
            for row in node_rows:
                payload = json.loads(row[0])
                node_id = str(payload.get("node_id") or payload.get("immutable_identity") or "")
                if node_id and node_id not in seen:
                    seen.add(node_id); nodes.append(payload)
            edge_rows = connection.execute(
                f'SELECT payload_json FROM provenance_edge WHERE target_node_id IN ({marks}){generation_clause} LIMIT ?',
                current + params_tail + [max_nodes * 4],
            ).fetchall()
            for row in edge_rows:
                payload = json.loads(row[0]); edges.append(payload)
                parent = str(payload.get("source_node_id") or "")
                if parent and parent not in seen:
                    frontier.append(parent)
        return {
            "result_node_id": str(result_node_id),
            "source_generation_id": source_generation_id,
            "nodes": nodes[:max_nodes],
            "edges": edges[: max_nodes * 4],
            "bounded": True,
        }
    finally:
        if owned:
            connection.close()


__all__ = [
    "VERSION", "BUNDLE_KEY", "SCHEMAS", "ensure_schema", "insert_research_validation_bundle",
    "record_rejected_generation", "latest_expert_state", "latest_online_fdr_state",
    "latest_delta_state", "query_provenance_lineage",
]

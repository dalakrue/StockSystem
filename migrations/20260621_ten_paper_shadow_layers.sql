-- ADX Quant Pro: ten-paper shadow-layer schema
-- Version: 20260621. Idempotent: CREATE TABLE/INDEX IF NOT EXISTS.
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS "model_x_knockoff_feature_history"(record_key TEXT PRIMARY KEY, source_generation_id TEXT NOT NULL, window_id TEXT,
      window_start TEXT, window_end TEXT, train_start TEXT, train_end TEXT,
      test_start TEXT, test_end TEXT, feature_name TEXT, feature_group TEXT,
      knockoff_statistic REAL, test_effect REAL, selected_state INTEGER, threshold REAL, fdr_target REAL,
      sample_support INTEGER, test_sample_support INTEGER, regime_support INTEGER, input_hash TEXT,
      calculation_version TEXT, evaluated_at TEXT, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS "online_fdr_test_history"(record_key TEXT PRIMARY KEY, source_generation_id TEXT NOT NULL, test_key TEXT,
      test_family TEXT, source_module TEXT, raw_p_value REAL, allocated_alpha REAL,
      adjusted_result TEXT, wealth_before REAL, wealth_after REAL, test_index INTEGER,
      dependence_assumption TEXT, calculation_version TEXT, evaluated_at TEXT,
      payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS "online_fdr_state"(state_id TEXT PRIMARY KEY, source_generation_id TEXT, state_version TEXT,
      wealth REAL, test_index INTEGER, updated_at TEXT, calculation_version TEXT,
      payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS "reject_option_history"(record_key TEXT PRIMARY KEY, source_generation_id TEXT NOT NULL,
      protected_decision TEXT, shadow_decision TEXT, rejection_cost REAL,
      accepted_risk_estimate REAL, status TEXT, calculation_version TEXT,
      evaluated_at TEXT, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS "flexible_loss_history"(evaluation_id TEXT PRIMARY KEY, source_generation_id TEXT, window_id TEXT,
      window_start TEXT, window_end TEXT, train_start TEXT, train_end TEXT,
      test_start TEXT, test_end TEXT, sample_count INTEGER, status TEXT,
      mean_flexible_loss REAL, loss_definition_version TEXT, calculation_version TEXT,
      evaluated_at TEXT, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS "model_explanation_cache"(explanation_id TEXT PRIMARY KEY, canonical_calculation_id TEXT,
      source_generation_id TEXT, status TEXT, input_hash TEXT, output_hash TEXT,
      calculation_version TEXT, evaluated_at TEXT, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS "monotonicity_validation_history"(record_key TEXT PRIMARY KEY, source_generation_id TEXT, contract_name TEXT,
      input_name TEXT, output_name TEXT, expected_direction TEXT, status TEXT,
      sample_support INTEGER, violation_rate REAL, calculation_version TEXT,
      evaluated_at TEXT, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS "delta_maintenance_history"(record_key TEXT PRIMARY KEY, source_generation_id TEXT, status TEXT, mode TEXT,
      source_row_count INTEGER, exact_full_recompute_equal INTEGER,
      optimization_accepted INTEGER, calculation_version TEXT, evaluated_at TEXT,
      payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS "exact_delta_state"(state_id TEXT PRIMARY KEY, source_generation_id TEXT, mode TEXT,
      source_row_count INTEGER, prefix_hash TEXT, updated_at TEXT,
      calculation_version TEXT, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS "provenance_node"(node_id TEXT PRIMARY KEY, source_generation_id TEXT, node_type TEXT,
      immutable_identity TEXT, natural_key TEXT, payload_hash TEXT, label TEXT, calculation_version TEXT,
      evaluated_at TEXT, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS "provenance_edge"(edge_id TEXT PRIMARY KEY, source_generation_id TEXT, source_node_id TEXT,
      target_node_id TEXT, relation_type TEXT, calculation_version TEXT,
      evaluated_at TEXT, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS "metamorphic_test_history"(record_key TEXT PRIMARY KEY, source_generation_id TEXT, relation_name TEXT,
      status TEXT, detail TEXT, calculation_version TEXT, evaluated_at TEXT,
      payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS "calm_operation_classification"(record_key TEXT PRIMARY KEY, source_generation_id TEXT, operation_name TEXT,
      monotonicity_class TEXT, coordination_required INTEGER, reason TEXT,
      calculation_version TEXT, evaluated_at TEXT, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS "evidence_gate_history"(record_key TEXT PRIMARY KEY, source_generation_id TEXT, gate_name TEXT,
      gate_pass INTEGER, calculation_version TEXT, evaluated_at TEXT,
      payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS "research_paper_run"(record_key TEXT PRIMARY KEY, source_generation_id TEXT, paper_number INTEGER,
      paper_title TEXT, status TEXT, mode TEXT, input_hash TEXT, output_hash TEXT,
      schema_version INTEGER, production_influence_enabled INTEGER, all_gates_pass INTEGER,
      calculation_version TEXT, evaluated_at TEXT, payload_json TEXT NOT NULL);
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
PRAGMA user_version=20260621;
COMMIT;

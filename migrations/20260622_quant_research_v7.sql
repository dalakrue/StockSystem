CREATE TABLE IF NOT EXISTS quant_research_v7_run(
 calculation_id TEXT NOT NULL, generation_id TEXT NOT NULL, event_time_utc TEXT NOT NULL,
 completed_broker_time TEXT, status TEXT NOT NULL, method_count INTEGER NOT NULL,
 available_method_count INTEGER NOT NULL, sample_count INTEGER NOT NULL, runtime_ms REAL,
 peak_traced_memory_mb REAL, serialized_result_bytes INTEGER, logic_version TEXT NOT NULL,
 payload_json TEXT NOT NULL, PRIMARY KEY(calculation_id,generation_id));
CREATE TABLE IF NOT EXISTS quant_research_v7_method_results(
 calculation_id TEXT NOT NULL, generation_id TEXT NOT NULL, event_time_utc TEXT NOT NULL,
 method_id TEXT NOT NULL, paper_title TEXT NOT NULL, status TEXT NOT NULL,
 sample_count INTEGER NOT NULL, minimum_sample_required INTEGER NOT NULL,
 logic_version TEXT NOT NULL, payload_json TEXT NOT NULL,
 PRIMARY KEY(calculation_id,generation_id,method_id));
CREATE TABLE IF NOT EXISTS quant_research_v7_feature_stability(
 calculation_id TEXT NOT NULL, generation_id TEXT NOT NULL, event_time_utc TEXT NOT NULL,
 feature_name TEXT NOT NULL, selection_probability REAL, rank_index INTEGER,
 status TEXT, logic_version TEXT NOT NULL,
 PRIMARY KEY(calculation_id,generation_id,feature_name));
CREATE TABLE IF NOT EXISTS quant_research_v7_bootstrap_results(
 calculation_id TEXT NOT NULL, generation_id TEXT NOT NULL, event_time_utc TEXT NOT NULL,
 result_key TEXT NOT NULL, replication_count INTEGER, mean_block_length REAL,
 confidence_level REAL, seed_hash TEXT, status TEXT, logic_version TEXT NOT NULL,
 payload_json TEXT NOT NULL, PRIMARY KEY(calculation_id,generation_id,result_key));
CREATE TABLE IF NOT EXISTS quant_research_v7_covariance_state(
 calculation_id TEXT NOT NULL, generation_id TEXT NOT NULL, event_time_utc TEXT NOT NULL,
 shrinkage_intensity REAL, raw_condition_number REAL, shrunk_condition_number REAL,
 positive_semidefinite INTEGER, status TEXT, logic_version TEXT NOT NULL,
 payload_json TEXT NOT NULL, PRIMARY KEY(calculation_id,generation_id));
CREATE TABLE IF NOT EXISTS quant_research_v7_dcc_state(
 calculation_id TEXT NOT NULL, generation_id TEXT NOT NULL, event_time_utc TEXT NOT NULL,
 current_correlation REAL, correlation_shock REAL, diversification_loss_score REAL,
 conflict_state TEXT, status TEXT, logic_version TEXT NOT NULL,
 payload_json TEXT NOT NULL, PRIMARY KEY(calculation_id,generation_id));
CREATE TABLE IF NOT EXISTS quant_research_v7_gas_state(
 calculation_id TEXT NOT NULL, generation_id TEXT NOT NULL, event_time_utc TEXT NOT NULL,
 current_error_scale REAL, suggested_uncertainty_multiplier REAL, tail_warning_state TEXT,
 status TEXT, logic_version TEXT NOT NULL, payload_json TEXT NOT NULL,
 PRIMARY KEY(calculation_id,generation_id));
CREATE TABLE IF NOT EXISTS quant_research_v7_hsmm_duration(
 calculation_id TEXT NOT NULL, generation_id TEXT NOT NULL, event_time_utc TEXT NOT NULL,
 current_regime TEXT, current_age REAL, expected_total_duration REAL,
 survival_h1 REAL, survival_h6 REAL, next_regime TEXT, status TEXT,
 logic_version TEXT NOT NULL, payload_json TEXT NOT NULL,
 PRIMARY KEY(calculation_id,generation_id));
CREATE TABLE IF NOT EXISTS quant_research_v7_midas_summary(
 calculation_id TEXT NOT NULL, generation_id TEXT NOT NULL, event_time_utc TEXT NOT NULL,
 latest_m1_time TEXT, return_pressure REAL, directional_consistency REAL,
 realized_volatility REAL, status TEXT, logic_version TEXT NOT NULL,
 payload_json TEXT NOT NULL, PRIMARY KEY(calculation_id,generation_id));
CREATE TABLE IF NOT EXISTS quant_research_v7_bds_tests(
 calculation_id TEXT NOT NULL, generation_id TEXT NOT NULL, event_time_utc TEXT NOT NULL,
 test_key TEXT NOT NULL, embedding_dimension INTEGER, epsilon_multiplier REAL,
 statistic REAL, raw_p_value REAL, adjusted_decision TEXT, status TEXT,
 logic_version TEXT NOT NULL, payload_json TEXT NOT NULL,
 PRIMARY KEY(calculation_id,generation_id,test_key));
CREATE TABLE IF NOT EXISTS quant_research_v7_trading_advisory(
 calculation_id TEXT NOT NULL, generation_id TEXT NOT NULL, event_time_utc TEXT NOT NULL,
 advisory_label TEXT, urgency REAL, turnover_warning TEXT, order_placement INTEGER,
 status TEXT, logic_version TEXT NOT NULL, payload_json TEXT NOT NULL,
 PRIMARY KEY(calculation_id,generation_id));
CREATE TABLE IF NOT EXISTS quant_research_v7_coherent_risk(
 calculation_id TEXT NOT NULL, generation_id TEXT NOT NULL, event_time_utc TEXT NOT NULL,
 risk_score REAL, risk_budget REAL, risk_state TEXT, coherence_status TEXT,
 shadow_tradeability TEXT, status TEXT, logic_version TEXT NOT NULL,
 payload_json TEXT NOT NULL, PRIMARY KEY(calculation_id,generation_id));
CREATE TABLE IF NOT EXISTS quant_research_v7_error_history(
 error_key TEXT PRIMARY KEY, calculation_id TEXT, generation_id TEXT, event_time_utc TEXT,
 method_id TEXT, error_type TEXT, error_message TEXT, failed_safely INTEGER NOT NULL,
 logic_version TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_quant_v7_run_time ON quant_research_v7_run(event_time_utc DESC);
CREATE INDEX IF NOT EXISTS idx_quant_v7_method_time ON quant_research_v7_method_results(event_time_utc DESC,method_id);
CREATE INDEX IF NOT EXISTS idx_quant_v7_error_time ON quant_research_v7_error_history(event_time_utc DESC);

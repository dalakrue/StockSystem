BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS "quant_research_v3_run"(
  record_key TEXT PRIMARY KEY,
  run_id TEXT, canonical_calculation_id TEXT, source_generation_id TEXT NOT NULL,
  symbol TEXT, timeframe TEXT, broker_timezone TEXT, completed_h1_time TEXT,
  calculation_created_at TEXT, source_data_signature TEXT,
  method_name TEXT, method_version TEXT, horizon_hours INTEGER,
  condition_key TEXT, sample_count INTEGER, minimum_sample_required INTEGER,
  fallback_level TEXT, reliability_status TEXT, assumption_status TEXT,
  shadow_only INTEGER NOT NULL DEFAULT 1,
  production_influence_enabled INTEGER NOT NULL DEFAULT 0,
  calculation_error TEXT, exact_limitations_json TEXT,
  settled_target_time TEXT, status TEXT, value_numeric REAL, value_text TEXT,
  evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_quant_research_v3_run_completed" ON "quant_research_v3_run"(completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS "idx_quant_research_v3_run_generation" ON "quant_research_v3_run"(source_generation_id);
CREATE INDEX IF NOT EXISTS "idx_quant_research_v3_run_horizon" ON "quant_research_v3_run"(horizon_hours);
CREATE INDEX IF NOT EXISTS "idx_quant_research_v3_run_reliability" ON "quant_research_v3_run"(reliability_status);
CREATE INDEX IF NOT EXISTS "idx_quant_research_v3_run_condition" ON "quant_research_v3_run"(condition_key);
CREATE INDEX IF NOT EXISTS "idx_quant_research_v3_run_settled" ON "quant_research_v3_run"(settled_target_time);
CREATE TABLE IF NOT EXISTS "yz_volatility_history"(
  record_key TEXT PRIMARY KEY,
  run_id TEXT, canonical_calculation_id TEXT, source_generation_id TEXT NOT NULL,
  symbol TEXT, timeframe TEXT, broker_timezone TEXT, completed_h1_time TEXT,
  calculation_created_at TEXT, source_data_signature TEXT,
  method_name TEXT, method_version TEXT, horizon_hours INTEGER,
  condition_key TEXT, sample_count INTEGER, minimum_sample_required INTEGER,
  fallback_level TEXT, reliability_status TEXT, assumption_status TEXT,
  shadow_only INTEGER NOT NULL DEFAULT 1,
  production_influence_enabled INTEGER NOT NULL DEFAULT 0,
  calculation_error TEXT, exact_limitations_json TEXT,
  settled_target_time TEXT, status TEXT, value_numeric REAL, value_text TEXT,
  evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_yz_volatility_history_completed" ON "yz_volatility_history"(completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS "idx_yz_volatility_history_generation" ON "yz_volatility_history"(source_generation_id);
CREATE INDEX IF NOT EXISTS "idx_yz_volatility_history_horizon" ON "yz_volatility_history"(horizon_hours);
CREATE INDEX IF NOT EXISTS "idx_yz_volatility_history_reliability" ON "yz_volatility_history"(reliability_status);
CREATE INDEX IF NOT EXISTS "idx_yz_volatility_history_condition" ON "yz_volatility_history"(condition_key);
CREATE INDEX IF NOT EXISTS "idx_yz_volatility_history_settled" ON "yz_volatility_history"(settled_target_time);
CREATE TABLE IF NOT EXISTS "har_volatility_forecast_history"(
  record_key TEXT PRIMARY KEY,
  run_id TEXT, canonical_calculation_id TEXT, source_generation_id TEXT NOT NULL,
  symbol TEXT, timeframe TEXT, broker_timezone TEXT, completed_h1_time TEXT,
  calculation_created_at TEXT, source_data_signature TEXT,
  method_name TEXT, method_version TEXT, horizon_hours INTEGER,
  condition_key TEXT, sample_count INTEGER, minimum_sample_required INTEGER,
  fallback_level TEXT, reliability_status TEXT, assumption_status TEXT,
  shadow_only INTEGER NOT NULL DEFAULT 1,
  production_influence_enabled INTEGER NOT NULL DEFAULT 0,
  calculation_error TEXT, exact_limitations_json TEXT,
  settled_target_time TEXT, status TEXT, value_numeric REAL, value_text TEXT,
  evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_har_volatility_forecast_history_completed" ON "har_volatility_forecast_history"(completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS "idx_har_volatility_forecast_history_generation" ON "har_volatility_forecast_history"(source_generation_id);
CREATE INDEX IF NOT EXISTS "idx_har_volatility_forecast_history_horizon" ON "har_volatility_forecast_history"(horizon_hours);
CREATE INDEX IF NOT EXISTS "idx_har_volatility_forecast_history_reliability" ON "har_volatility_forecast_history"(reliability_status);
CREATE INDEX IF NOT EXISTS "idx_har_volatility_forecast_history_condition" ON "har_volatility_forecast_history"(condition_key);
CREATE INDEX IF NOT EXISTS "idx_har_volatility_forecast_history_settled" ON "har_volatility_forecast_history"(settled_target_time);
CREATE TABLE IF NOT EXISTS "bipower_jump_proxy_history"(
  record_key TEXT PRIMARY KEY,
  run_id TEXT, canonical_calculation_id TEXT, source_generation_id TEXT NOT NULL,
  symbol TEXT, timeframe TEXT, broker_timezone TEXT, completed_h1_time TEXT,
  calculation_created_at TEXT, source_data_signature TEXT,
  method_name TEXT, method_version TEXT, horizon_hours INTEGER,
  condition_key TEXT, sample_count INTEGER, minimum_sample_required INTEGER,
  fallback_level TEXT, reliability_status TEXT, assumption_status TEXT,
  shadow_only INTEGER NOT NULL DEFAULT 1,
  production_influence_enabled INTEGER NOT NULL DEFAULT 0,
  calculation_error TEXT, exact_limitations_json TEXT,
  settled_target_time TEXT, status TEXT, value_numeric REAL, value_text TEXT,
  evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_bipower_jump_proxy_history_completed" ON "bipower_jump_proxy_history"(completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS "idx_bipower_jump_proxy_history_generation" ON "bipower_jump_proxy_history"(source_generation_id);
CREATE INDEX IF NOT EXISTS "idx_bipower_jump_proxy_history_horizon" ON "bipower_jump_proxy_history"(horizon_hours);
CREATE INDEX IF NOT EXISTS "idx_bipower_jump_proxy_history_reliability" ON "bipower_jump_proxy_history"(reliability_status);
CREATE INDEX IF NOT EXISTS "idx_bipower_jump_proxy_history_condition" ON "bipower_jump_proxy_history"(condition_key);
CREATE INDEX IF NOT EXISTS "idx_bipower_jump_proxy_history_settled" ON "bipower_jump_proxy_history"(settled_target_time);
CREATE TABLE IF NOT EXISTS "caviar_quantile_history"(
  record_key TEXT PRIMARY KEY,
  run_id TEXT, canonical_calculation_id TEXT, source_generation_id TEXT NOT NULL,
  symbol TEXT, timeframe TEXT, broker_timezone TEXT, completed_h1_time TEXT,
  calculation_created_at TEXT, source_data_signature TEXT,
  method_name TEXT, method_version TEXT, horizon_hours INTEGER,
  condition_key TEXT, sample_count INTEGER, minimum_sample_required INTEGER,
  fallback_level TEXT, reliability_status TEXT, assumption_status TEXT,
  shadow_only INTEGER NOT NULL DEFAULT 1,
  production_influence_enabled INTEGER NOT NULL DEFAULT 0,
  calculation_error TEXT, exact_limitations_json TEXT,
  settled_target_time TEXT, status TEXT, value_numeric REAL, value_text TEXT,
  evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_caviar_quantile_history_completed" ON "caviar_quantile_history"(completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS "idx_caviar_quantile_history_generation" ON "caviar_quantile_history"(source_generation_id);
CREATE INDEX IF NOT EXISTS "idx_caviar_quantile_history_horizon" ON "caviar_quantile_history"(horizon_hours);
CREATE INDEX IF NOT EXISTS "idx_caviar_quantile_history_reliability" ON "caviar_quantile_history"(reliability_status);
CREATE INDEX IF NOT EXISTS "idx_caviar_quantile_history_condition" ON "caviar_quantile_history"(condition_key);
CREATE INDEX IF NOT EXISTS "idx_caviar_quantile_history_settled" ON "caviar_quantile_history"(settled_target_time);
CREATE TABLE IF NOT EXISTS "joint_var_es_score_history"(
  record_key TEXT PRIMARY KEY,
  run_id TEXT, canonical_calculation_id TEXT, source_generation_id TEXT NOT NULL,
  symbol TEXT, timeframe TEXT, broker_timezone TEXT, completed_h1_time TEXT,
  calculation_created_at TEXT, source_data_signature TEXT,
  method_name TEXT, method_version TEXT, horizon_hours INTEGER,
  condition_key TEXT, sample_count INTEGER, minimum_sample_required INTEGER,
  fallback_level TEXT, reliability_status TEXT, assumption_status TEXT,
  shadow_only INTEGER NOT NULL DEFAULT 1,
  production_influence_enabled INTEGER NOT NULL DEFAULT 0,
  calculation_error TEXT, exact_limitations_json TEXT,
  settled_target_time TEXT, status TEXT, value_numeric REAL, value_text TEXT,
  evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_joint_var_es_score_history_completed" ON "joint_var_es_score_history"(completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS "idx_joint_var_es_score_history_generation" ON "joint_var_es_score_history"(source_generation_id);
CREATE INDEX IF NOT EXISTS "idx_joint_var_es_score_history_horizon" ON "joint_var_es_score_history"(horizon_hours);
CREATE INDEX IF NOT EXISTS "idx_joint_var_es_score_history_reliability" ON "joint_var_es_score_history"(reliability_status);
CREATE INDEX IF NOT EXISTS "idx_joint_var_es_score_history_condition" ON "joint_var_es_score_history"(condition_key);
CREATE INDEX IF NOT EXISTS "idx_joint_var_es_score_history_settled" ON "joint_var_es_score_history"(settled_target_time);
CREATE TABLE IF NOT EXISTS "semiparametric_var_es_history"(
  record_key TEXT PRIMARY KEY,
  run_id TEXT, canonical_calculation_id TEXT, source_generation_id TEXT NOT NULL,
  symbol TEXT, timeframe TEXT, broker_timezone TEXT, completed_h1_time TEXT,
  calculation_created_at TEXT, source_data_signature TEXT,
  method_name TEXT, method_version TEXT, horizon_hours INTEGER,
  condition_key TEXT, sample_count INTEGER, minimum_sample_required INTEGER,
  fallback_level TEXT, reliability_status TEXT, assumption_status TEXT,
  shadow_only INTEGER NOT NULL DEFAULT 1,
  production_influence_enabled INTEGER NOT NULL DEFAULT 0,
  calculation_error TEXT, exact_limitations_json TEXT,
  settled_target_time TEXT, status TEXT, value_numeric REAL, value_text TEXT,
  evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_semiparametric_var_es_history_completed" ON "semiparametric_var_es_history"(completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS "idx_semiparametric_var_es_history_generation" ON "semiparametric_var_es_history"(source_generation_id);
CREATE INDEX IF NOT EXISTS "idx_semiparametric_var_es_history_horizon" ON "semiparametric_var_es_history"(horizon_hours);
CREATE INDEX IF NOT EXISTS "idx_semiparametric_var_es_history_reliability" ON "semiparametric_var_es_history"(reliability_status);
CREATE INDEX IF NOT EXISTS "idx_semiparametric_var_es_history_condition" ON "semiparametric_var_es_history"(condition_key);
CREATE INDEX IF NOT EXISTS "idx_semiparametric_var_es_history_settled" ON "semiparametric_var_es_history"(settled_target_time);
CREATE TABLE IF NOT EXISTS "cvar_risk_budget_history"(
  record_key TEXT PRIMARY KEY,
  run_id TEXT, canonical_calculation_id TEXT, source_generation_id TEXT NOT NULL,
  symbol TEXT, timeframe TEXT, broker_timezone TEXT, completed_h1_time TEXT,
  calculation_created_at TEXT, source_data_signature TEXT,
  method_name TEXT, method_version TEXT, horizon_hours INTEGER,
  condition_key TEXT, sample_count INTEGER, minimum_sample_required INTEGER,
  fallback_level TEXT, reliability_status TEXT, assumption_status TEXT,
  shadow_only INTEGER NOT NULL DEFAULT 1,
  production_influence_enabled INTEGER NOT NULL DEFAULT 0,
  calculation_error TEXT, exact_limitations_json TEXT,
  settled_target_time TEXT, status TEXT, value_numeric REAL, value_text TEXT,
  evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_cvar_risk_budget_history_completed" ON "cvar_risk_budget_history"(completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS "idx_cvar_risk_budget_history_generation" ON "cvar_risk_budget_history"(source_generation_id);
CREATE INDEX IF NOT EXISTS "idx_cvar_risk_budget_history_horizon" ON "cvar_risk_budget_history"(horizon_hours);
CREATE INDEX IF NOT EXISTS "idx_cvar_risk_budget_history_reliability" ON "cvar_risk_budget_history"(reliability_status);
CREATE INDEX IF NOT EXISTS "idx_cvar_risk_budget_history_condition" ON "cvar_risk_budget_history"(condition_key);
CREATE INDEX IF NOT EXISTS "idx_cvar_risk_budget_history_settled" ON "cvar_risk_budget_history"(settled_target_time);
CREATE TABLE IF NOT EXISTS "density_pit_history"(
  record_key TEXT PRIMARY KEY,
  run_id TEXT, canonical_calculation_id TEXT, source_generation_id TEXT NOT NULL,
  symbol TEXT, timeframe TEXT, broker_timezone TEXT, completed_h1_time TEXT,
  calculation_created_at TEXT, source_data_signature TEXT,
  method_name TEXT, method_version TEXT, horizon_hours INTEGER,
  condition_key TEXT, sample_count INTEGER, minimum_sample_required INTEGER,
  fallback_level TEXT, reliability_status TEXT, assumption_status TEXT,
  shadow_only INTEGER NOT NULL DEFAULT 1,
  production_influence_enabled INTEGER NOT NULL DEFAULT 0,
  calculation_error TEXT, exact_limitations_json TEXT,
  settled_target_time TEXT, status TEXT, value_numeric REAL, value_text TEXT,
  evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_density_pit_history_completed" ON "density_pit_history"(completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS "idx_density_pit_history_generation" ON "density_pit_history"(source_generation_id);
CREATE INDEX IF NOT EXISTS "idx_density_pit_history_horizon" ON "density_pit_history"(horizon_hours);
CREATE INDEX IF NOT EXISTS "idx_density_pit_history_reliability" ON "density_pit_history"(reliability_status);
CREATE INDEX IF NOT EXISTS "idx_density_pit_history_condition" ON "density_pit_history"(condition_key);
CREATE INDEX IF NOT EXISTS "idx_density_pit_history_settled" ON "density_pit_history"(settled_target_time);
CREATE TABLE IF NOT EXISTS "berkowitz_density_test_history"(
  record_key TEXT PRIMARY KEY,
  run_id TEXT, canonical_calculation_id TEXT, source_generation_id TEXT NOT NULL,
  symbol TEXT, timeframe TEXT, broker_timezone TEXT, completed_h1_time TEXT,
  calculation_created_at TEXT, source_data_signature TEXT,
  method_name TEXT, method_version TEXT, horizon_hours INTEGER,
  condition_key TEXT, sample_count INTEGER, minimum_sample_required INTEGER,
  fallback_level TEXT, reliability_status TEXT, assumption_status TEXT,
  shadow_only INTEGER NOT NULL DEFAULT 1,
  production_influence_enabled INTEGER NOT NULL DEFAULT 0,
  calculation_error TEXT, exact_limitations_json TEXT,
  settled_target_time TEXT, status TEXT, value_numeric REAL, value_text TEXT,
  evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_berkowitz_density_test_history_completed" ON "berkowitz_density_test_history"(completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS "idx_berkowitz_density_test_history_generation" ON "berkowitz_density_test_history"(source_generation_id);
CREATE INDEX IF NOT EXISTS "idx_berkowitz_density_test_history_horizon" ON "berkowitz_density_test_history"(horizon_hours);
CREATE INDEX IF NOT EXISTS "idx_berkowitz_density_test_history_reliability" ON "berkowitz_density_test_history"(reliability_status);
CREATE INDEX IF NOT EXISTS "idx_berkowitz_density_test_history_condition" ON "berkowitz_density_test_history"(condition_key);
CREATE INDEX IF NOT EXISTS "idx_berkowitz_density_test_history_settled" ON "berkowitz_density_test_history"(settled_target_time);
CREATE TABLE IF NOT EXISTS "execution_cost_shadow_history"(
  record_key TEXT PRIMARY KEY,
  run_id TEXT, canonical_calculation_id TEXT, source_generation_id TEXT NOT NULL,
  symbol TEXT, timeframe TEXT, broker_timezone TEXT, completed_h1_time TEXT,
  calculation_created_at TEXT, source_data_signature TEXT,
  method_name TEXT, method_version TEXT, horizon_hours INTEGER,
  condition_key TEXT, sample_count INTEGER, minimum_sample_required INTEGER,
  fallback_level TEXT, reliability_status TEXT, assumption_status TEXT,
  shadow_only INTEGER NOT NULL DEFAULT 1,
  production_influence_enabled INTEGER NOT NULL DEFAULT 0,
  calculation_error TEXT, exact_limitations_json TEXT,
  settled_target_time TEXT, status TEXT, value_numeric REAL, value_text TEXT,
  evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_execution_cost_shadow_history_completed" ON "execution_cost_shadow_history"(completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS "idx_execution_cost_shadow_history_generation" ON "execution_cost_shadow_history"(source_generation_id);
CREATE INDEX IF NOT EXISTS "idx_execution_cost_shadow_history_horizon" ON "execution_cost_shadow_history"(horizon_hours);
CREATE INDEX IF NOT EXISTS "idx_execution_cost_shadow_history_reliability" ON "execution_cost_shadow_history"(reliability_status);
CREATE INDEX IF NOT EXISTS "idx_execution_cost_shadow_history_condition" ON "execution_cost_shadow_history"(condition_key);
CREATE INDEX IF NOT EXISTS "idx_execution_cost_shadow_history_settled" ON "execution_cost_shadow_history"(settled_target_time);
CREATE TABLE IF NOT EXISTS "quant_research_v3_error_history"(
  record_key TEXT PRIMARY KEY,
  run_id TEXT, canonical_calculation_id TEXT, source_generation_id TEXT NOT NULL,
  symbol TEXT, timeframe TEXT, broker_timezone TEXT, completed_h1_time TEXT,
  calculation_created_at TEXT, source_data_signature TEXT,
  method_name TEXT, method_version TEXT, horizon_hours INTEGER,
  condition_key TEXT, sample_count INTEGER, minimum_sample_required INTEGER,
  fallback_level TEXT, reliability_status TEXT, assumption_status TEXT,
  shadow_only INTEGER NOT NULL DEFAULT 1,
  production_influence_enabled INTEGER NOT NULL DEFAULT 0,
  calculation_error TEXT, exact_limitations_json TEXT,
  settled_target_time TEXT, status TEXT, value_numeric REAL, value_text TEXT,
  evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_quant_research_v3_error_history_completed" ON "quant_research_v3_error_history"(completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS "idx_quant_research_v3_error_history_generation" ON "quant_research_v3_error_history"(source_generation_id);
CREATE INDEX IF NOT EXISTS "idx_quant_research_v3_error_history_horizon" ON "quant_research_v3_error_history"(horizon_hours);
CREATE INDEX IF NOT EXISTS "idx_quant_research_v3_error_history_reliability" ON "quant_research_v3_error_history"(reliability_status);
CREATE INDEX IF NOT EXISTS "idx_quant_research_v3_error_history_condition" ON "quant_research_v3_error_history"(condition_key);
CREATE INDEX IF NOT EXISTS "idx_quant_research_v3_error_history_settled" ON "quant_research_v3_error_history"(settled_target_time);
PRAGMA user_version=20260622;
COMMIT;

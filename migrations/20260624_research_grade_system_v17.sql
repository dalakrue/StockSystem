-- Unified research-grade shadow sidecar migration (additive/idempotent).
-- No Field 1 or production table is altered.
CREATE TABLE IF NOT EXISTS rg17_run(
  run_id TEXT PRIMARY KEY, origin_id TEXT NOT NULL, broker_candle_time TEXT NOT NULL,
  status TEXT NOT NULL, payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rg17_origin(
  origin_id TEXT NOT NULL, horizon INTEGER NOT NULL, run_id TEXT NOT NULL, forecast_origin TEXT NOT NULL,
  mean REAL, median REAL, std REAL, q10 REAL, q25 REAL, q50 REAL, q75 REAL, q90 REAL,
  origin_lower REAL, origin_upper REAL, calibration_status TEXT, sample_size INTEGER,
  PRIMARY KEY(origin_id,horizon)
);
CREATE TABLE IF NOT EXISTS rg17_forecast_origins(
  run_id TEXT NOT NULL, origin_id TEXT NOT NULL, broker_candle_time TEXT NOT NULL, data_cutoff TEXT NOT NULL,
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL, horizon INTEGER, method_version TEXT NOT NULL, status TEXT NOT NULL,
  created_time TEXT NOT NULL, point_forecast REAL, median_forecast REAL, lower_quantile REAL, upper_quantile REAL,
  raw_direction_probability REAL, calibrated_direction_probability REAL, selected_models_json TEXT,
  model_weights_json TEXT, uncertainty_score REAL, disagreement_score REAL, fallback_reason TEXT, evidence_status TEXT,
  UNIQUE(origin_id,horizon,method_version)
);
CREATE TABLE IF NOT EXISTS rg17_horizon_outcomes(
  run_id TEXT NOT NULL, origin_id TEXT NOT NULL, broker_candle_time TEXT NOT NULL, data_cutoff TEXT NOT NULL,
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL, horizon INTEGER, method_version TEXT NOT NULL, status TEXT NOT NULL,
  created_time TEXT NOT NULL, maturity_time TEXT, actual_return REAL, settlement_status TEXT, metrics_json TEXT,
  UNIQUE(origin_id,horizon,maturity_time,method_version)
);
CREATE TABLE IF NOT EXISTS rg17_origin_intervals(
  run_id TEXT NOT NULL, origin_id TEXT NOT NULL, broker_candle_time TEXT NOT NULL, data_cutoff TEXT NOT NULL,
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL, horizon INTEGER, method_version TEXT NOT NULL, status TEXT NOT NULL,
  created_time TEXT NOT NULL, origin_lower REAL, origin_upper REAL, calibration_sample_size INTEGER,
  fallback_level TEXT, coverage_debt REAL, UNIQUE(origin_id,horizon,method_version)
);
CREATE TABLE IF NOT EXISTS rg17_probability_calibration(
  run_id TEXT NOT NULL, origin_id TEXT NOT NULL, broker_candle_time TEXT NOT NULL, data_cutoff TEXT NOT NULL,
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL, horizon INTEGER, method_version TEXT NOT NULL, status TEXT NOT NULL,
  created_time TEXT NOT NULL, target_name TEXT NOT NULL, raw_probability REAL, calibrated_probability REAL,
  calibration_method TEXT, calibration_sample_size INTEGER, brier_score REAL, log_loss REAL, ece REAL, mce REAL,
  reliability_bins_json TEXT, UNIQUE(origin_id,horizon,target_name,method_version)
);
CREATE TABLE IF NOT EXISTS rg17_regime_posteriors(
  run_id TEXT NOT NULL, origin_id TEXT NOT NULL, broker_candle_time TEXT NOT NULL, data_cutoff TEXT NOT NULL,
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL, horizon INTEGER, method_version TEXT NOT NULL, status TEXT NOT NULL,
  created_time TEXT NOT NULL, regime_name TEXT NOT NULL, posterior_probability REAL, persistence_probability REAL,
  expected_duration REAL, UNIQUE(origin_id,regime_name,method_version)
);
CREATE TABLE IF NOT EXISTS rg17_changepoint_posteriors(
  run_id TEXT NOT NULL, origin_id TEXT NOT NULL, broker_candle_time TEXT NOT NULL, data_cutoff TEXT NOT NULL,
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL, horizon INTEGER, method_version TEXT NOT NULL, status TEXT NOT NULL,
  created_time TEXT NOT NULL, run_length INTEGER NOT NULL, posterior_probability REAL, changepoint_probability REAL,
  UNIQUE(origin_id,run_length,method_version)
);
CREATE TABLE IF NOT EXISTS rg17_conditional_model_evidence(
  run_id TEXT NOT NULL, origin_id TEXT NOT NULL, broker_candle_time TEXT NOT NULL, data_cutoff TEXT NOT NULL,
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL, horizon INTEGER, method_version TEXT NOT NULL, status TEXT NOT NULL,
  created_time TEXT NOT NULL, model_name TEXT NOT NULL, condition_key TEXT NOT NULL, statistic REAL, p_value REAL,
  sample_size INTEGER, evidence_json TEXT, UNIQUE(origin_id,horizon,model_name,condition_key,method_version)
);
CREATE TABLE IF NOT EXISTS rg17_model_confidence_set_results(
  run_id TEXT NOT NULL, origin_id TEXT NOT NULL, broker_candle_time TEXT NOT NULL, data_cutoff TEXT NOT NULL,
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL, horizon INTEGER, method_version TEXT NOT NULL, status TEXT NOT NULL,
  created_time TEXT NOT NULL, model_name TEXT NOT NULL, member INTEGER NOT NULL, elimination_order INTEGER,
  test_statistic REAL, p_value REAL, sample_size INTEGER, UNIQUE(origin_id,horizon,model_name,method_version)
);
CREATE TABLE IF NOT EXISTS rg17_spa_results(
  run_id TEXT NOT NULL, origin_id TEXT NOT NULL, broker_candle_time TEXT NOT NULL, data_cutoff TEXT NOT NULL,
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL, horizon INTEGER, method_version TEXT NOT NULL, status TEXT NOT NULL,
  created_time TEXT NOT NULL, model_name TEXT NOT NULL, gross_improvement REAL, net_improvement REAL,
  spa_statistic REAL, bootstrap_p_value REAL, sample_size INTEGER, eligible INTEGER, rejection_reason TEXT,
  UNIQUE(origin_id,horizon,model_name,method_version)
);
CREATE TABLE IF NOT EXISTS rg17_dm_results(
  run_id TEXT NOT NULL, origin_id TEXT NOT NULL, broker_candle_time TEXT NOT NULL, data_cutoff TEXT NOT NULL,
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL, horizon INTEGER, method_version TEXT NOT NULL, status TEXT NOT NULL,
  created_time TEXT NOT NULL, model_name TEXT NOT NULL, comparison_block TEXT NOT NULL, mean_loss_difference REAL,
  dm_statistic REAL, p_value REAL, sample_size INTEGER, comparison_status TEXT,
  UNIQUE(origin_id,horizon,model_name,comparison_block,method_version)
);
CREATE TABLE IF NOT EXISTS rg17_decision_impact_results(
  run_id TEXT NOT NULL, origin_id TEXT NOT NULL, broker_candle_time TEXT NOT NULL, data_cutoff TEXT NOT NULL,
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL, horizon INTEGER, method_version TEXT NOT NULL, status TEXT NOT NULL,
  created_time TEXT NOT NULL, action TEXT NOT NULL, expected_gross REAL, expected_after_cost REAL, downside_impact REAL,
  action_probability REAL, evidence_weighted_value REAL, historical_counterfactual REAL, realized_regret REAL,
  evidence_sufficient INTEGER, UNIQUE(origin_id,action,method_version)
);
CREATE TABLE IF NOT EXISTS rg17_validation_warnings(
  run_id TEXT NOT NULL, origin_id TEXT NOT NULL, broker_candle_time TEXT NOT NULL, data_cutoff TEXT NOT NULL,
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL, horizon INTEGER, method_version TEXT NOT NULL, status TEXT NOT NULL,
  created_time TEXT NOT NULL, warning_code TEXT NOT NULL, warning_text TEXT,
  UNIQUE(origin_id,warning_code,method_version)
);
CREATE TABLE IF NOT EXISTS rg17_field8(
  run_id TEXT NOT NULL, horizon INTEGER NOT NULL, model_version TEXT NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY(run_id,horizon,model_version)
);
CREATE TABLE IF NOT EXISTS rg17_field9(
  run_id TEXT NOT NULL, action TEXT NOT NULL, model_version TEXT NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY(run_id,action,model_version)
);
CREATE TABLE IF NOT EXISTS rg17_ai(
  message_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, normalized_question TEXT NOT NULL,
  answer_json TEXT NOT NULL, created_at TEXT NOT NULL
);

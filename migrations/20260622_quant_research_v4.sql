-- Advanced Quant Research V4 compact normalized storage. Idempotent by design.
CREATE TABLE IF NOT EXISTS quant_research_v4_run (
  source_generation_id TEXT NOT NULL,
  calculation_id TEXT NOT NULL,
  completed_h1_time TEXT,
  status TEXT NOT NULL,
  method_count INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  runtime_ms REAL,
  peak_traced_memory_mb REAL,
  rss_delta_mb REAL,
  serialized_result_bytes INTEGER,
  evaluated_at TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  PRIMARY KEY(source_generation_id, calculation_id)
);

CREATE TABLE IF NOT EXISTS quant_research_v4_method_results (
  source_generation_id TEXT NOT NULL,
  calculation_id TEXT NOT NULL,
  completed_h1_time TEXT,
  method_id TEXT NOT NULL,
  horizon_hours INTEGER NOT NULL DEFAULT 0,
  condition_key TEXT NOT NULL DEFAULT 'GLOBAL',
  status TEXT NOT NULL,
  sample_count INTEGER NOT NULL DEFAULT 0,
  effective_sample_count INTEGER NOT NULL DEFAULT 0,
  score REAL,
  p_value REAL,
  evaluated_at TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  PRIMARY KEY(source_generation_id, calculation_id, method_id, horizon_hours, condition_key)
);

CREATE TABLE IF NOT EXISTS quant_research_v4_regime_probabilities (
  source_generation_id TEXT NOT NULL, calculation_id TEXT NOT NULL, completed_h1_time TEXT,
  method_id TEXT NOT NULL, state_name TEXT NOT NULL, probability REAL, entropy REAL, status TEXT NOT NULL,
  evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY(source_generation_id, calculation_id, state_name)
);

CREATE TABLE IF NOT EXISTS quant_research_v4_transition_probabilities (
  source_generation_id TEXT NOT NULL, calculation_id TEXT NOT NULL, completed_h1_time TEXT,
  method_id TEXT NOT NULL, horizon_hours INTEGER NOT NULL, probability REAL, hazard REAL, status TEXT NOT NULL,
  evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY(source_generation_id, calculation_id, horizon_hours)
);

CREATE TABLE IF NOT EXISTS quant_research_v4_volatility_evaluation (
  source_generation_id TEXT NOT NULL, calculation_id TEXT NOT NULL, completed_h1_time TEXT,
  method_id TEXT NOT NULL, model_id TEXT NOT NULL, qlike REAL, qlike_skill REAL, rank_number INTEGER,
  support_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY(source_generation_id, calculation_id, method_id, model_id)
);

CREATE TABLE IF NOT EXISTS quant_research_v4_probability_decomposition (
  source_generation_id TEXT NOT NULL, calculation_id TEXT NOT NULL, completed_h1_time TEXT,
  method_id TEXT NOT NULL, event_id TEXT NOT NULL, horizon_hours INTEGER NOT NULL,
  brier_score REAL, reliability_component REAL, resolution_component REAL, uncertainty_component REAL,
  support_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY(source_generation_id, calculation_id, event_id, horizon_hours)
);

CREATE TABLE IF NOT EXISTS quant_research_v4_direction_tests (
  source_generation_id TEXT NOT NULL, calculation_id TEXT NOT NULL, completed_h1_time TEXT,
  method_id TEXT NOT NULL, condition_key TEXT NOT NULL, horizon_hours INTEGER NOT NULL DEFAULT 0,
  hit_rate REAL, expected_hit_rate REAL, test_statistic REAL, p_value REAL,
  support_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY(source_generation_id, calculation_id, condition_key, horizon_hours)
);

CREATE TABLE IF NOT EXISTS quant_research_v4_interval_tests (
  source_generation_id TEXT NOT NULL, calculation_id TEXT NOT NULL, completed_h1_time TEXT,
  method_id TEXT NOT NULL, horizon_hours INTEGER NOT NULL, nominal_coverage REAL NOT NULL,
  empirical_coverage REAL, lr_uc REAL, lr_ind REAL, lr_cc REAL, p_cc REAL,
  support_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY(source_generation_id, calculation_id, horizon_hours, nominal_coverage)
);

CREATE TABLE IF NOT EXISTS quant_research_v4_es_tests (
  source_generation_id TEXT NOT NULL, calculation_id TEXT NOT NULL, completed_h1_time TEXT,
  method_id TEXT NOT NULL, condition_key TEXT NOT NULL DEFAULT 'GLOBAL', exception_count INTEGER,
  exception_rate REAL, test_statistic REAL, p_value REAL, severity_underestimation INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL, evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY(source_generation_id, calculation_id, condition_key)
);

CREATE TABLE IF NOT EXISTS quant_research_v4_sequential_monitor_states (
  source_generation_id TEXT NOT NULL, calculation_id TEXT NOT NULL, completed_h1_time TEXT,
  method_id TEXT NOT NULL, monitor_id TEXT NOT NULL, epoch_id TEXT NOT NULL,
  log_lr REAL NOT NULL, state TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'AVAILABLE', observation_count INTEGER NOT NULL DEFAULT 0,
  new_unique_observations INTEGER NOT NULL DEFAULT 0, reset_reason TEXT,
  evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY(source_generation_id, calculation_id, monitor_id, epoch_id)
);

CREATE INDEX IF NOT EXISTS idx_qrv4_run_generation ON quant_research_v4_run(source_generation_id, completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS idx_qrv4_method_generation ON quant_research_v4_method_results(source_generation_id, method_id, completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS idx_qrv4_regime_h1 ON quant_research_v4_regime_probabilities(completed_h1_time DESC, method_id);
CREATE INDEX IF NOT EXISTS idx_qrv4_transition_horizon ON quant_research_v4_transition_probabilities(horizon_hours, completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS idx_qrv4_vol_model ON quant_research_v4_volatility_evaluation(model_id, completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS idx_qrv4_prob_event ON quant_research_v4_probability_decomposition(event_id, horizon_hours, completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS idx_qrv4_direction_horizon ON quant_research_v4_direction_tests(horizon_hours, completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS idx_qrv4_interval_horizon ON quant_research_v4_interval_tests(horizon_hours, completed_h1_time DESC);
CREATE INDEX IF NOT EXISTS idx_qrv4_es_h1 ON quant_research_v4_es_tests(completed_h1_time DESC, method_id);
CREATE INDEX IF NOT EXISTS idx_qrv4_monitor_state ON quant_research_v4_sequential_monitor_states(monitor_id, epoch_id, completed_h1_time DESC);

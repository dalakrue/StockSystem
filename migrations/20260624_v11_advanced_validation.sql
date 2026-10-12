CREATE TABLE IF NOT EXISTS quant_v11_shadow_validation (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 run_id TEXT NOT NULL, prediction_id TEXT NOT NULL DEFAULT '', symbol TEXT NOT NULL,
 timeframe TEXT NOT NULL, broker_candle_time TEXT NOT NULL, horizon INTEGER NOT NULL DEFAULT 0,
 regime TEXT NOT NULL DEFAULT '', model_version TEXT NOT NULL, feature_hash TEXT NOT NULL DEFAULT '',
 configuration_hash TEXT NOT NULL DEFAULT '', calculation_version TEXT NOT NULL,
 shadow_only INTEGER NOT NULL DEFAULT 1, settled_status TEXT NOT NULL DEFAULT 'UNKNOWN',
 data_quality_status TEXT NOT NULL DEFAULT 'UNKNOWN', payload_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(run_id,prediction_id,horizon,model_version,configuration_hash)
);
CREATE INDEX IF NOT EXISTS idx_qv11_shadow_time ON quant_v11_shadow_validation(broker_candle_time DESC);
CREATE TABLE IF NOT EXISTS quant_v11_experiment_registry (
 experiment_id TEXT PRIMARY KEY, creation_time TEXT NOT NULL, feature_hash TEXT NOT NULL,
 parameter_hash TEXT NOT NULL, train_range TEXT, validation_range TEXT, test_range TEXT,
 alternatives_searched INTEGER NOT NULL DEFAULT 0, in_sample_rank REAL, out_of_sample_rank REAL,
 degradation REAL, pbo_estimate REAL, promotion_eligibility INTEGER NOT NULL DEFAULT 0,
 payload_json TEXT NOT NULL
);

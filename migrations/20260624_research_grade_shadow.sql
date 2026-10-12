-- Research-grade shadow evidence sidecar schema.
-- Additive only: no Field 1 or production tables are altered.
CREATE TABLE IF NOT EXISTS research_grade_shadow_snapshot (
    run_id TEXT PRIMARY KEY,
    generation_id TEXT NOT NULL,
    origin_candle_time TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    model_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_grade_shadow_origin (
    run_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    horizon INTEGER NOT NULL,
    origin_time TEXT NOT NULL,
    origin_price REAL,
    mean REAL,
    median REAL,
    lower REAL,
    upper REAL,
    direction_probability REAL,
    origin_regime TEXT,
    origin_features_json TEXT NOT NULL,
    model_version TEXT NOT NULL,
    shadow_only INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    PRIMARY KEY (model_id, horizon, origin_time, model_version)
);
CREATE INDEX IF NOT EXISTS idx_rg_shadow_origin_run
    ON research_grade_shadow_origin(run_id, horizon, origin_time);
CREATE TABLE IF NOT EXISTS research_grade_shadow_score (
    run_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    horizon INTEGER NOT NULL,
    sample_count INTEGER NOT NULL,
    crps REAL,
    crps_method TEXT,
    mae REAL,
    rmse REAL,
    directional_accuracy REAL,
    log_score REAL,
    interval_score REAL,
    interval_coverage REAL,
    interval_width REAL,
    coverage_debt REAL,
    score_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, model_id, horizon)
);
CREATE TABLE IF NOT EXISTS research_grade_promotion_report (
    run_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    promotion_eligible INTEGER NOT NULL,
    automatic_promotion_enabled INTEGER NOT NULL,
    blockers_json TEXT NOT NULL,
    leakage_tests TEXT NOT NULL,
    causality_tests TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, model_id)
);

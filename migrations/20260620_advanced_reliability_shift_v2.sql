-- Idempotent migration for the hidden second-generation reliability transaction.
CREATE TABLE IF NOT EXISTS advanced_reliability_shift_snapshots_v2 (
    calculation_id TEXT PRIMARY KEY,
    calculation_generation INTEGER NOT NULL,
    latest_completed_h1_time TEXT,
    data_hash TEXT NOT NULL,
    version TEXT NOT NULL,
    publication_status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    published_at TEXT
);
CREATE TABLE IF NOT EXISTS advanced_reliability_shift_vectors_v2 (
    calculation_id TEXT NOT NULL,
    calculation_generation INTEGER NOT NULL,
    stream_type TEXT NOT NULL,
    vector_time TEXT,
    score REAL,
    vector_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(calculation_id, stream_type)
);
CREATE INDEX IF NOT EXISTS idx_advanced_shift_generation_v2
ON advanced_reliability_shift_snapshots_v2(calculation_generation);
CREATE INDEX IF NOT EXISTS idx_advanced_shift_vector_time_v2
ON advanced_reliability_shift_vectors_v2(stream_type, vector_time);

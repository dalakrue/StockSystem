-- ADX Quant Pro 20260702 symbol identity / Field 10 publication migration
-- Idempotent table creation. Conditional publication_status column upgrades are
-- performed by core.child_generation_contract_20260702.migrate_child_publication_contract.
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=8000;

CREATE TABLE IF NOT EXISTS child_generation_registry (
    parent_run_id TEXT NOT NULL,
    child_run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    canonical_run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    completed_broker_candle TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    runtime_snapshot_path TEXT NOT NULL,
    runtime_snapshot_sha256 TEXT NOT NULL,
    bundle_fingerprint TEXT NOT NULL,
    calculation_status TEXT NOT NULL,
    publication_status TEXT NOT NULL,
    diagnostic TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,completed_broker_candle)
);

CREATE TABLE IF NOT EXISTS field1_table4_current_evidence (
    parent_run_id TEXT NOT NULL, child_run_id TEXT NOT NULL, symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL, canonical_run_id TEXT NOT NULL, source_id TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL, broker_timestamp TEXT NOT NULL,
    evidence_json TEXT NOT NULL, source_status TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,broker_timestamp)
);

CREATE TABLE IF NOT EXISTS field1_table4_history_evidence (
    parent_run_id TEXT NOT NULL, child_run_id TEXT NOT NULL, symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL, canonical_run_id TEXT NOT NULL, snapshot_hash TEXT NOT NULL,
    broker_timestamp TEXT NOT NULL, row_number INTEGER NOT NULL,
    evidence_json TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,broker_timestamp,row_number)
);

CREATE TABLE IF NOT EXISTS field3_standard_evidence (
    parent_run_id TEXT NOT NULL, child_run_id TEXT NOT NULL, symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL, canonical_run_id TEXT NOT NULL, snapshot_hash TEXT NOT NULL,
    broker_timestamp TEXT NOT NULL, standard TEXT NOT NULL,
    evidence_json TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,broker_timestamp,standard)
);

CREATE TABLE IF NOT EXISTS field3_history_evidence (
    parent_run_id TEXT NOT NULL, child_run_id TEXT NOT NULL, symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL, canonical_run_id TEXT NOT NULL, snapshot_hash TEXT NOT NULL,
    broker_timestamp TEXT NOT NULL, standard TEXT NOT NULL, row_number INTEGER NOT NULL,
    evidence_json TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,broker_timestamp,standard,row_number)
);

CREATE TABLE IF NOT EXISTS child_runtime_snapshot_metadata (
    parent_run_id TEXT NOT NULL, child_run_id TEXT NOT NULL, symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL, canonical_run_id TEXT NOT NULL, snapshot_hash TEXT NOT NULL,
    broker_timestamp TEXT NOT NULL, runtime_snapshot_path TEXT NOT NULL,
    runtime_snapshot_sha256 TEXT NOT NULL, source_signature_json TEXT NOT NULL,
    timing_json TEXT NOT NULL, resource_json TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,broker_timestamp)
);

CREATE TABLE IF NOT EXISTS publication_diagnostics (
    diagnostic_id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_run_id TEXT, child_run_id TEXT, symbol TEXT, timeframe TEXT,
    canonical_run_id TEXT, snapshot_hash TEXT, broker_timestamp TEXT,
    status TEXT NOT NULL, detail_json TEXT NOT NULL, created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_child_registry_lookup
    ON child_generation_registry(parent_run_id,symbol,timeframe,completed_broker_candle DESC);
CREATE INDEX IF NOT EXISTS idx_field1_history_symbol_time
    ON field1_table4_history_evidence(symbol,timeframe,broker_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_field3_history_symbol_time
    ON field3_history_evidence(symbol,timeframe,broker_timestamp DESC,standard);

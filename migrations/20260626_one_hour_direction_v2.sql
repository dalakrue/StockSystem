-- Additive migration. Does not alter protected production tables.
CREATE INDEX IF NOT EXISTS idx_oh_origin ON one_hour_direction_ledger_20260626(forecast_origin_time);
CREATE INDEX IF NOT EXISTS idx_oh_target ON one_hour_direction_ledger_20260626(target_h1_close_time, settlement_status);
CREATE INDEX IF NOT EXISTS idx_oh_session ON one_hour_direction_ledger_20260626(session);
CREATE INDEX IF NOT EXISTS idx_oh_identity ON one_hour_direction_ledger_20260626(run_id, generation_id, snapshot_hash);
-- Column additions are applied idempotently by OneHourLedger.initialize because
-- SQLite does not support ADD COLUMN IF NOT EXISTS consistently.

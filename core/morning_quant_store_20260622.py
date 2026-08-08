"""Idempotent normalized V8 Morning, calibration, drift and governance storage."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Iterable, Mapping
import hashlib, json, re, sqlite3
import pandas as pd

VERSION = "morning-quant-store-v8-20260622"
BUNDLE_KEY = "__quant_research_v8_bundle__"
DB_PATH = Path("data") / "canonical_snapshots.sqlite"

TABLE_COLUMNS = {
"morning_account_state_history": ["event_time_utc","broker_time","myanmar_time","calculation_id","generation_id","balance","equity","floating_profit","used_margin","free_margin","margin_level","drawdown_pct","open_position_count","data_quality_status"],
"morning_position_exposure_history": ["event_time_utc","broker_time","calculation_id","generation_id","symbol","position_id_or_stable_key","side","lots","entry_price","current_price","notional_exposure","stop_distance","atr_risk","unrealized_profit","exposure_concentration","source"],
"morning_risk_budget_stress_history": ["event_time_utc","broker_time","calculation_id","generation_id","risk_per_trade","planned_trade_count","planned_total_risk","used_daily_risk","remaining_daily_risk","expected_shortfall_95","expected_shortfall_99","stress_1atr","stress_2atr","stress_3atr","risk_status"],
"morning_forecast_outcome_history": ["forecast_event_time_utc","settlement_time_utc","broker_forecast_time","calculation_id","generation_id","horizon_hours","raw_prediction","calibrated_prediction","lower_80","upper_80","lower_90","upper_90","lower_95","upper_95","actual_price","absolute_error","error_pct","direction_correct","covered_80","covered_90","covered_95","reliability","regime","session"],
"morning_execution_api_health_history": ["event_time_utc","broker_time","calculation_id","generation_id","connector","connection_status","symbol","timeframe","fetch_duration_ms","row_count","latest_completed_h1_utc","freshness_lag_seconds","spread","slippage","retry_count","failure_type","last_safe_error","data_quality_status"],
"clock_sync_audit_history": ["event_time_utc","broker_time","myanmar_time","broker_offset_minutes","broker_timezone","clock_resolution_source","latest_completed_h1_utc","field1_latest_utc","calculation_id","generation_id","symbol","timeframe","contract_version","field1_sync_status","cross_table_sync_status","reason"],
}
EXTRA_TABLES = {
"conformal_calibration_state_v8": ["event_time_utc","calculation_id","generation_id","horizon_hours","target_coverage","achieved_coverage","sample_count","interval_width","interval_score","calibration_age","fallback_level","alpha","payload_json"],
"conformal_alpha_history_v8": ["event_time_utc","generation_id","horizon_hours","alpha_before","alpha_after","miss","learning_rate","drift_epoch"],
"research_experiment_registry_v8": ["experiment_id","creation_time","hypothesis","parameters_json","date_range","benchmark","metrics_json","author_source","logic_version","status","promotion_decision","production_influence_enabled"],
"drift_epoch_history_v8": ["event_time_utc","stream_name","old_epoch","new_epoch","drift_magnitude","status","payload_json"],
"quant_readiness_history_v8": ["event_time_utc","calculation_id","generation_id","visible_status","score_pct","critical_failure_count","payload_json"],
}


def _q(name: str) -> str: return '"' + name.replace('"','') + '"'

def _sql_type(column: str) -> str:
    if column.endswith("_count") or column in {"generation_id","horizon_hours","row_count","retry_count","sample_count","calibration_age","old_epoch","new_epoch","critical_failure_count","planned_trade_count"}: return "INTEGER"
    if column.endswith("_json") or column in {"payload_json","parameters_json","metrics_json","reason","last_safe_error","hypothesis","date_range","benchmark","author_source","logic_version","status","promotion_decision","failure_type","source","connector","connection_status","data_quality_status","field1_sync_status","cross_table_sync_status","contract_version","broker_timezone","clock_resolution_source","symbol","timeframe","side","position_id_or_stable_key","calculation_id","experiment_id","session","regime","visible_status","stream_name"}: return "TEXT"
    if column.startswith("covered_") or column in {"direction_correct","miss","production_influence_enabled"}: return "INTEGER"
    if column.endswith("time") or column.endswith("_utc") or column in {"broker_time","myanmar_time","creation_time","broker_forecast_time"}: return "TEXT"
    return "REAL"


def ensure_schema(conn: sqlite3.Connection, *, commit: bool = True) -> None:
    for table, columns in {**TABLE_COLUMNS, **EXTRA_TABLES}.items():
        definitions = ",".join(f"{_q(c)} {_sql_type(c)}" for c in columns)
        if table == "morning_account_state_history": unique = "UNIQUE(event_time_utc,calculation_id,generation_id)"
        elif table == "morning_position_exposure_history": unique = "UNIQUE(event_time_utc,calculation_id,generation_id,position_id_or_stable_key)"
        elif table == "morning_risk_budget_stress_history": unique = "UNIQUE(event_time_utc,calculation_id,generation_id)"
        elif table == "morning_forecast_outcome_history": unique = "UNIQUE(forecast_event_time_utc,calculation_id,generation_id,horizon_hours)"
        elif table == "morning_execution_api_health_history": unique = "UNIQUE(event_time_utc,connector,symbol,timeframe,calculation_id,generation_id)"
        elif table == "clock_sync_audit_history": unique = "UNIQUE(event_time_utc,calculation_id,generation_id,symbol,timeframe)"
        elif table == "research_experiment_registry_v8": unique = "UNIQUE(experiment_id)"
        elif table == "conformal_calibration_state_v8": unique = "UNIQUE(calculation_id,generation_id,horizon_hours,target_coverage)"
        elif table == "conformal_alpha_history_v8": unique = "UNIQUE(event_time_utc,generation_id,horizon_hours)"
        elif table == "drift_epoch_history_v8": unique = "UNIQUE(event_time_utc,stream_name,new_epoch)"
        else: unique = "UNIQUE(event_time_utc,calculation_id,generation_id)"
        conn.execute(f"CREATE TABLE IF NOT EXISTS {_q(table)} ({definitions},{unique})")
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({_q(table)})")}
        for c in columns:
            if c not in existing: conn.execute(f"ALTER TABLE {_q(table)} ADD COLUMN {_q(c)} {_sql_type(c)}")
        for c in ("event_time_utc","forecast_event_time_utc","calculation_id","generation_id","symbol","timeframe","horizon_hours","status"):
            if c in columns: conn.execute(f"CREATE INDEX IF NOT EXISTS {_q('idx_'+table+'_'+c)} ON {_q(table)}({_q(c)})")
    if commit:
        conn.commit()


def _redact_text(value: str) -> str:
    text = str(value)
    patterns = (
        r"(?i)(api[_ -]?key\s*[:=]\s*)[^,;\s]+", r"(?i)(password\s*[:=]\s*)[^,;\s]+",
        r"(?i)(secret\s*[:=]\s*)[^,;\s]+", r"(?i)(bridge[_ -]?token\s*[:=]\s*)[^,;\s]+",
        r"(?i)(bearer\s+)[A-Za-z0-9._~+\-/=]+",
    )
    for pattern in patterns:
        text = re.sub(pattern, lambda m: m.group(1) + "[REDACTED]", text)
    return text


def _clean(value: Any) -> Any:
    if isinstance(value, bool): return int(value)
    if isinstance(value, (dict,list,tuple)):
        return _redact_text(json.dumps(value, ensure_ascii=False, default=str, separators=(",",":")))
    if value is None: return None
    try:
        if pd.isna(value): return None
    except Exception: pass
    if isinstance(value, pd.Timestamp): return str(value)
    return _redact_text(value) if isinstance(value, str) else value


def insert_bundle(conn: sqlite3.Connection, bundle: Mapping[str, Iterable[Mapping[str, Any]]]) -> dict[str, int]:
    ensure_schema(conn, commit=False); counts = {}
    for table, rows in bundle.items():
        columns = ({**TABLE_COLUMNS, **EXTRA_TABLES}).get(table)
        if columns is None: continue
        materialized = [dict(r) for r in rows or []]
        if not materialized: counts[table] = 0; continue
        if table == "morning_forecast_outcome_history":
            key_cols = ("forecast_event_time_utc", "calculation_id", "generation_id", "horizon_hours")
            update_cols = [c for c in columns if c not in key_cols]
            assignments = ",".join(
                f"{_q(c)}=CASE WHEN excluded.actual_price IS NOT NULL THEN excluded.{_q(c)} ELSE {_q(table)}.{_q(c)} END"
                for c in update_cols
            )
            sql = (
                f"INSERT INTO {_q(table)} ({','.join(_q(c) for c in columns)}) VALUES ({','.join('?' for _ in columns)}) "
                f"ON CONFLICT({','.join(_q(c) for c in key_cols)}) DO UPDATE SET {assignments}"
            )
        else:
            sql = f"INSERT OR IGNORE INTO {_q(table)} ({','.join(_q(c) for c in columns)}) VALUES ({','.join('?' for _ in columns)})"
        before = conn.total_changes
        conn.executemany(sql, [[_clean(r.get(c)) for c in columns] for r in materialized])
        counts[table] = conn.total_changes - before
    return counts


def query_history(table: str, *, search: str = "", limit: int = 200, db_path: Path | str = DB_PATH) -> pd.DataFrame:
    if table not in {**TABLE_COLUMNS, **EXTRA_TABLES}: raise ValueError("unsupported V8 history table")
    conn = sqlite3.connect(str(db_path)); ensure_schema(conn)
    try:
        cols = ({**TABLE_COLUMNS, **EXTRA_TABLES})[table]; time_col = "forecast_event_time_utc" if "forecast_event_time_utc" in cols else "event_time_utc" if "event_time_utc" in cols else "creation_time"
        params=[]; sql=f"SELECT * FROM {_q(table)}"
        if search:
            sql += " WHERE " + " OR ".join(f"UPPER(CAST({_q(c)} AS TEXT)) LIKE ?" for c in cols); params.extend([f"%{search.upper()}%"]*len(cols))
        sql += f" ORDER BY {_q(time_col)} DESC LIMIT ?"; params.append(max(1,min(int(limit),2000)))
        return pd.read_sql_query(sql, conn, params=params)
    finally: conn.close()


def position_stable_key(row: Mapping[str, Any]) -> str:
    explicit = row.get("position_id_or_stable_key") or row.get("ticket") or row.get("position_id")
    if explicit not in (None, ""): return str(explicit)
    raw = "|".join(str(row.get(k,"")) for k in ("symbol","side","entry_price","lots","source"))
    return hashlib.sha256(raw.encode()).hexdigest()[:20]

__all__ = ["VERSION","BUNDLE_KEY","DB_PATH","TABLE_COLUMNS","EXTRA_TABLES","ensure_schema","insert_bundle","query_history","position_stable_key"]

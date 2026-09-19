"""Validated, incremental candle storage shared by every field."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import math
import sqlite3

import pandas as pd

from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH, migrate_deployment_schema
from core.runtime_selection_20260705 import normalize_symbol, normalize_timeframe, timeframe_seconds

STANDARD_COLUMNS = (
    "symbol", "timeframe", "open_time", "close_time", "open", "high", "low",
    "close", "volume", "provider", "fetched_at", "is_complete", "broker_time",
    "data_quality_score", "validation_status", "source_status", "provider_symbol", "provider_key_alias",
)


def _utc(value: Any) -> pd.Timestamp:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return pd.Timestamp(parsed) if pd.notna(parsed) else pd.NaT


def validate_candle(candle: Mapping[str, Any], *, require_complete: bool = True) -> tuple[bool, str]:
    open_time = _utc(candle.get("open_time") or candle.get("time") or candle.get("datetime"))
    if pd.isna(open_time):
        return False, "INVALID_TIMESTAMP"
    try:
        o, h, l, c = (float(candle.get(name)) for name in ("open", "high", "low", "close"))
    except Exception:
        return False, "NON_NUMERIC_OHLC"
    if not all(math.isfinite(value) and value > 0 for value in (o, h, l, c)):
        return False, "NON_FINITE_OR_NON_POSITIVE_OHLC"
    if h < max(o, c) or l > min(o, c) or h < l:
        return False, "INVALID_OHLC_RELATION"
    if require_complete and not bool(candle.get("is_complete", False)):
        return False, "INCOMPLETE_CANDLE"
    return True, "VALID"


def normalize_frame(
    frame: pd.DataFrame,
    *,
    symbol: Any,
    timeframe: Any,
    provider: str,
    provider_symbol: str | None = None,
    source_status: str = "LIVE_PRIMARY",
    now: datetime | None = None,
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    result = frame.copy()
    aliases = {str(c).strip().lower(): c for c in result.columns}
    time_col = next((aliases[name] for name in ("open_time", "time", "datetime", "timestamp", "date") if name in aliases), None)
    if time_col is None and isinstance(result.index, pd.DatetimeIndex):
        result = result.reset_index().rename(columns={result.index.name or "index": "open_time"})
        time_col = "open_time"
    if time_col is None:
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    rename = {}
    for target, names in {
        "open": ("open", "o"), "high": ("high", "h"), "low": ("low", "l"),
        "close": ("close", "c"), "volume": ("volume", "tick_volume", "v"),
    }.items():
        column = next((aliases[name] for name in names if name in aliases), None)
        if column is not None:
            rename[column] = target
    rename[time_col] = "open_time"
    result = result.rename(columns=rename)
    for required in ("open", "high", "low", "close"):
        if required not in result.columns:
            return pd.DataFrame(columns=STANDARD_COLUMNS)
        result[required] = pd.to_numeric(result[required], errors="coerce")
    if "volume" not in result.columns:
        result["volume"] = pd.NA
    else:
        result["volume"] = pd.to_numeric(result["volume"], errors="coerce")
    result["open_time"] = pd.to_datetime(result["open_time"], errors="coerce", utc=True)
    result = result.dropna(subset=["open_time", "open", "high", "low", "close"])
    tf = normalize_timeframe(timeframe)
    seconds = timeframe_seconds(tf)
    result["close_time"] = result["open_time"] + pd.to_timedelta(seconds, unit="s")
    now_ts = pd.Timestamp(now or datetime.now(timezone.utc))
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    else:
        now_ts = now_ts.tz_convert("UTC")
    result["is_complete"] = result["close_time"] <= now_ts
    result["symbol"] = normalize_symbol(symbol)
    result["timeframe"] = tf
    result["provider"] = str(provider or "UNKNOWN").upper()
    result["provider_symbol"] = str(provider_symbol or symbol)
    if "provider_key_alias" not in result.columns:
        result["provider_key_alias"] = pd.NA
    result["provider_key_alias"] = result["provider_key_alias"].fillna("").astype(str).str.upper().replace({"NAN": "", "NONE": ""})
    result["fetched_at"] = now_ts
    result["broker_time"] = result["open_time"]
    result["source_status"] = str(source_status)
    validation: list[str] = []
    quality: list[float] = []
    for row in result.to_dict("records"):
        ok, reason = validate_candle(row, require_complete=False)
        validation.append(reason)
        quality.append(100.0 if ok and bool(row.get("is_complete")) else 75.0 if ok else 0.0)
    result["validation_status"] = validation
    result["data_quality_score"] = quality
    return result.loc[:, list(STANDARD_COLUMNS)].sort_values("open_time").drop_duplicates(
        subset=["symbol", "timeframe", "open_time"], keep="last"
    ).reset_index(drop=True)


class CandleRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        migrate_deployment_schema(self.db_path)

    def connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=20)
        conn.execute("PRAGMA busy_timeout=12000")
        return conn

    def upsert(self, frame: pd.DataFrame, *, run_id: str = "", require_complete: bool = True) -> dict[str, int]:
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            return {"inserted": 0, "rejected": 0, "duplicates": 0}
        inserted = rejected = duplicates = 0
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for row in frame.to_dict("records"):
                ok, reason = validate_candle(row, require_complete=require_complete)
                if not ok:
                    rejected += 1
                    continue
                symbol = normalize_symbol(row.get("symbol"))
                timeframe = normalize_timeframe(row.get("timeframe"))
                open_time = _utc(row.get("open_time"))
                close_time = _utc(row.get("close_time"))
                existing = conn.execute(
                    "SELECT data_quality_score,validation_status FROM candles WHERE symbol=? AND timeframe=? AND broker_open_time=?",
                    (symbol, timeframe, open_time.isoformat()),
                ).fetchone()
                if existing is not None:
                    # Valid existing rows are immutable unless the replacement has higher quality.
                    if float(existing[0] or 0) >= float(row.get("data_quality_score") or 0):
                        duplicates += 1
                        continue
                conn.execute(
                    """INSERT INTO candles(
                       symbol,timeframe,broker_open_time,broker_close_time,open,high,low,close,volume,
                       provider,fetched_at,is_complete,broker_time,data_quality_score,validation_status,
                       source_status,run_id,provider_symbol,provider_key_alias,data_age_seconds)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(symbol,timeframe,broker_open_time) DO UPDATE SET
                       broker_close_time=excluded.broker_close_time,open=excluded.open,high=excluded.high,
                       low=excluded.low,close=excluded.close,volume=excluded.volume,provider=excluded.provider,
                       fetched_at=excluded.fetched_at,is_complete=excluded.is_complete,broker_time=excluded.broker_time,
                       data_quality_score=excluded.data_quality_score,validation_status=excluded.validation_status,
                       source_status=excluded.source_status,run_id=excluded.run_id,provider_symbol=excluded.provider_symbol,
                       provider_key_alias=excluded.provider_key_alias,data_age_seconds=excluded.data_age_seconds""",
                    (
                        symbol, timeframe, open_time.isoformat(), close_time.isoformat(),
                        float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]),
                        None if pd.isna(row.get("volume")) else float(row.get("volume")),
                        str(row.get("provider") or "UNKNOWN"), _utc(row.get("fetched_at")).isoformat(),
                        int(bool(row.get("is_complete"))), _utc(row.get("broker_time") or open_time).isoformat(),
                        float(row.get("data_quality_score") or 0), str(reason),
                        str(row.get("source_status") or "CACHED_VALID"), str(run_id or ""),
                        str(row.get("provider_symbol") or symbol), str(row.get("provider_key_alias") or ""),
                        max(0.0, (pd.Timestamp.now(tz="UTC") - open_time).total_seconds()),
                    ),
                )
                conn.execute(
                    """INSERT OR REPLACE INTO accepted_candles_by_provider_20260708(
                           symbol,timeframe,candle_time,provider,provider_key_alias,open,high,low,close,volume,run_id,created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        symbol, timeframe, open_time.isoformat(), str(row.get("provider") or "UNKNOWN"),
                        str(row.get("provider_key_alias") or ""),
                        float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]),
                        None if pd.isna(row.get("volume")) else float(row.get("volume")),
                        str(run_id or ""), datetime.now(timezone.utc).isoformat(),
                    ),
                )
                inserted += 1
            conn.commit()
        return {"inserted": inserted, "rejected": rejected, "duplicates": duplicates}

    def load(self, symbol: Any, timeframe: Any, *, limit: int = 600, completed_only: bool = True) -> pd.DataFrame:
        where = "AND is_complete=1" if completed_only else ""
        with self.connection() as conn:
            frame = pd.read_sql_query(
                f"""SELECT symbol,timeframe,broker_open_time AS open_time,broker_close_time AS close_time,
                    open,high,low,close,volume,provider,fetched_at,is_complete,broker_time,
                    data_quality_score,validation_status,source_status,provider_symbol,provider_key_alias
                    FROM candles WHERE symbol=? AND timeframe=? {where}
                    ORDER BY broker_open_time DESC LIMIT ?""",
                conn,
                params=(normalize_symbol(symbol), normalize_timeframe(timeframe), int(limit)),
            )
        if frame.empty:
            return frame
        for column in ("open_time", "close_time", "fetched_at", "broker_time"):
            frame[column] = pd.to_datetime(frame[column], errors="coerce", utc=True)
        return frame.sort_values("open_time").reset_index(drop=True)

    def latest(self, symbol: Any, timeframe: Any) -> dict[str, Any] | None:
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT * FROM candles WHERE symbol=? AND timeframe=? AND is_complete=1
                   ORDER BY broker_open_time DESC LIMIT 1""",
                (normalize_symbol(symbol), normalize_timeframe(timeframe)),
            ).fetchone()
        return dict(row) if row else None

    def missing_from(self, symbol: Any, timeframe: Any, expected_latest: Any) -> bool:
        latest = self.latest(symbol, timeframe)
        if not latest:
            return True
        stored = _utc(latest.get("broker_open_time"))
        expected = _utc(expected_latest)
        return bool(pd.isna(stored) or pd.isna(expected) or stored < expected)

    def count(self, symbol: Any | None = None, timeframe: Any | None = None) -> int:
        clauses, params = [], []
        if symbol:
            clauses.append("symbol=?"); params.append(normalize_symbol(symbol))
        if timeframe:
            clauses.append("timeframe=?"); params.append(normalize_timeframe(timeframe))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connection() as conn:
            return int(conn.execute(f"SELECT COUNT(*) FROM candles{where}", params).fetchone()[0])


__all__ = ["STANDARD_COLUMNS", "validate_candle", "normalize_frame", "CandleRepository"]

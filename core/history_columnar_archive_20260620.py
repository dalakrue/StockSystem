"""Threshold-gated columnar archive for very large history tables.

SQLite remains authoritative for canonical transactions and ordinary 25-day H1
history. Partitioned Parquet and DuckDB are used only after measured row/size
thresholds are exceeded and only from an explicit maintenance command.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import sqlite3
from typing import Any, Iterable, Sequence

import pandas as pd

from core.history_evidence_store_20260620 import COMMON_DB_COLUMNS, SPEC_BY_NAME
from services.canonical_snapshot_store import DB_PATH

DEFAULT_ROW_THRESHOLD = 250_000
DEFAULT_DB_SIZE_THRESHOLD = 128 * 1024 * 1024


@dataclass(frozen=True)
class ArchiveDecision:
    table_name: str
    row_count: int
    database_size_bytes: int
    row_threshold: int
    size_threshold_bytes: int
    justified: bool
    reason: str


def archive_decision(
    table_name: str, *, db_path: Path | str = DB_PATH,
    row_threshold: int = DEFAULT_ROW_THRESHOLD,
    size_threshold_bytes: int = DEFAULT_DB_SIZE_THRESHOLD,
) -> ArchiveDecision:
    if table_name not in SPEC_BY_NAME:
        raise KeyError(f"Unknown history table: {table_name}")
    path = Path(db_path)
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        row_count = int(conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0])
    except sqlite3.OperationalError:
        row_count = 0
    finally:
        conn.close()
    size = path.stat().st_size if path.exists() else 0
    justified = row_count >= int(row_threshold) or size >= int(size_threshold_bytes)
    reason = (
        "Measured history exceeds the configured row/database-size threshold."
        if justified else
        "SQLite remains the lower-complexity authority; measured history does not justify columnar migration."
    )
    return ArchiveDecision(table_name, row_count, size, int(row_threshold), int(size_threshold_bytes), justified, reason)


def archive_partitioned_parquet(
    table_name: str, *, destination: Path | str,
    db_path: Path | str = DB_PATH, force: bool = False, chunk_rows: int = 50_000,
) -> dict[str, Any]:
    """Export one measured-large table; never called by a renderer or tab switch."""
    decision = archive_decision(table_name, db_path=db_path)
    if not decision.justified and not force:
        return {"status": "NOT_JUSTIFIED", **asdict(decision)}
    # Optional libraries are imported only after threshold/explicit-force checks.
    import pyarrow as pa
    import pyarrow.dataset as ds

    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30)
    written = 0
    try:
        query = f'SELECT * FROM "{table_name}" ORDER BY latest_completed_h1, record_time'
        for index, chunk in enumerate(pd.read_sql_query(query, conn, chunksize=max(1_000, int(chunk_rows)))):
            if chunk.empty:
                continue
            completed = pd.to_datetime(chunk["latest_completed_h1"], errors="coerce", utc=True)
            chunk = chunk.assign(
                partition_symbol=chunk["symbol"].astype(str),
                partition_timeframe=chunk["timeframe"].astype(str),
                partition_date=completed.dt.strftime("%Y-%m-%d").fillna("unknown"),
            )
            table = pa.Table.from_pandas(chunk, preserve_index=False)
            ds.write_dataset(
                table, base_dir=str(destination), format="parquet",
                partitioning=["partition_symbol", "partition_timeframe", "partition_date"],
                existing_data_behavior="overwrite_or_ignore",
                basename_template=f"{table_name}-{index}-{{i}}.parquet",
            )
            written += len(chunk)
    finally:
        conn.close()
    manifest = {
        "status": "ARCHIVED", "table_name": table_name, "rows": written,
        "destination": str(destination), "decision": asdict(decision),
        "sqlite_authority_retained": True, "reversible": True,
    }
    (destination / "archive_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def query_partitioned_parquet(
    destination: Path | str, *, columns: Sequence[str], limit: int = 100,
    symbol: str = "EURUSD", timeframe: str = "H1",
) -> pd.DataFrame:
    """DuckDB column projection over an existing archive; bounded by LIMIT."""
    allowed = [c for c in columns if c in COMMON_DB_COLUMNS]
    if not allowed:
        return pd.DataFrame()
    import duckdb

    root = str(Path(destination) / "**" / "*.parquet").replace("'", "''")
    projection = ",".join(f'"{c}"' for c in allowed)
    sql = (
        f"SELECT {projection} FROM read_parquet('{root}', hive_partitioning=true) "
        "WHERE partition_symbol=? AND partition_timeframe=? "
        "ORDER BY latest_completed_h1 DESC, record_time DESC LIMIT ?"
    )
    with duckdb.connect(database=":memory:") as conn:
        return conn.execute(sql, [str(symbol), str(timeframe), max(1, min(int(limit), 500))]).fetchdf()


__all__ = [
    "ArchiveDecision", "archive_decision", "archive_partitioned_parquet",
    "query_partitioned_parquet", "DEFAULT_ROW_THRESHOLD", "DEFAULT_DB_SIZE_THRESHOLD",
]

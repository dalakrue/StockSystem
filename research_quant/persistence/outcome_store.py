from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping
from research_quant.persistence.research_store import DEFAULT_DB_PATH, connect, dumps, initialize_database


def store_pending_outcome(row: Mapping[str, Any], *, db_path: str | Path = DEFAULT_DB_PATH) -> bool:
    initialize_database(db_path)
    values = (
        str(row.get("run_id") or ""), str(row.get("generation_id") or ""), str(row.get("symbol") or ""),
        str(row.get("timeframe") or ""), str(row.get("completed_broker_candle") or ""),
        str(row.get("model_name") or "CRCEF-SV"), str(row.get("model_version") or "CRCEF-SV-1.0.0"),
        str(row.get("forecast_horizon") or ""), str(row.get("target_candle") or ""),
        row.get("actual_value"), row.get("realized_return"), int(bool(row.get("settled", False))),
        row.get("settlement_timestamp"), dumps(row),
    )
    with connect(db_path) as connection:
        cursor = connection.execute(
            """INSERT OR IGNORE INTO prediction_outcomes VALUES
            (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values
        )
        connection.commit()
        return cursor.rowcount > 0


def settle_outcome(identity: Mapping[str, Any], horizon: str, *, actual_value: float, realized_return: float, settlement_timestamp: str, db_path: str | Path = DEFAULT_DB_PATH) -> int:
    initialize_database(db_path)
    with connect(db_path) as connection:
        cursor = connection.execute(
            """UPDATE prediction_outcomes SET actual_value=?, realized_return=?, settled=1,
            settlement_timestamp=? WHERE run_id=? AND generation_id=? AND symbol=? AND timeframe=?
            AND completed_broker_candle=? AND forecast_horizon=? AND settled=0""",
            (actual_value, realized_return, settlement_timestamp, str(identity.get("run_id") or ""),
             str(identity.get("generation_id") or ""), str(identity.get("symbol") or ""),
             str(identity.get("timeframe") or ""), str(identity.get("completed_broker_candle") or ""), str(horizon)),
        )
        connection.commit()
        return cursor.rowcount

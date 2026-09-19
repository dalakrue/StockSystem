from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping
from research_quant.persistence.research_store import DEFAULT_DB_PATH, connect, dumps, initialize_database


def register_model(model: Mapping[str, Any], *, db_path: str | Path = DEFAULT_DB_PATH) -> bool:
    initialize_database(db_path)
    row = (
        str(model.get("model_name") or ""), str(model.get("model_version") or ""),
        str(model.get("training_window") or ""), str(model.get("input_schema_hash") or ""),
        str(model.get("artifact_path") or ""), str(model.get("status") or "RESEARCH_ONLY"),
        dumps(model), str(model.get("created_at_broker_time") or ""),
    )
    with connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT OR IGNORE INTO research_model_registry VALUES (?,?,?,?,?,?,?,?)", row
        )
        connection.commit()
        return cursor.rowcount > 0


def model_versions(model_name: str, *, db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    initialize_database(db_path)
    with connect(db_path) as connection:
        connection.row_factory = __import__("sqlite3").Row
        rows = connection.execute(
            "SELECT * FROM research_model_registry WHERE model_name=? ORDER BY created_at_broker_time DESC",
            (model_name,),
        ).fetchall()
    return [dict(row) for row in rows]

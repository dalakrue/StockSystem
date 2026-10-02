"""Export builder for materialized Field 10 authority snapshots."""
from __future__ import annotations
from collections.abc import Mapping
from typing import Any
import pandas as pd
from core.field10_unified_authority_20260709 import authority_csv_bytes, full_snapshot_zip_bytes, UNIFIED_TABLE_KEY, DINNER_TABLE_KEY, VIZ_TABLE_KEY, BACKGROUND_TABLE_KEY, UNIFIED_SNAPSHOT_KEY
from core.background_function_registry import function_status_frame


def build_export_payloads(state: Mapping[str, Any]) -> dict[str, bytes]:
    snap = state.get(UNIFIED_SNAPSHOT_KEY) if isinstance(state.get(UNIFIED_SNAPSHOT_KEY), Mapping) else {}
    payloads: dict[str, bytes] = {}
    for name, key in (("field10_unified_rank.csv", UNIFIED_TABLE_KEY), ("dinner_evidence.csv", DINNER_TABLE_KEY), ("data_visualization.csv", VIZ_TABLE_KEY)):
        frame = state.get(key)
        if isinstance(frame, pd.DataFrame):
            payloads[name] = authority_csv_bytes(frame, snap)
    payloads["background_function_status.csv"] = authority_csv_bytes(function_status_frame(str(snap.get("snapshot_hash") or "")), snap)
    payloads["full_snapshot_export.zip"] = full_snapshot_zip_bytes(state)
    return payloads

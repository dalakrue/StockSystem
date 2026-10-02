"""Identity-locked exports for the global symbol publication.

All export formats are derived from the same saved DataFrame and
GlobalSymbolContext. No provider or calculation code is imported here.
"""
from __future__ import annotations
from collections.abc import MutableMapping
from io import BytesIO
from typing import Any
import json
import pandas as pd

EXPORT_COLUMNS = {
    "Active Display Symbol": "active_display_symbol",
    "Global Timeframe": "timeframe",
    "Universe ID": "universe_id",
    "Generation": "generation",
    "Parent Run ID": "parent_run_id",
    "Snapshot Hash": "snapshot_hash",
    "Completed Candle": "latest_completed_candle",
    "Publication Status": "publication_status",
}


def identity_enriched_frame(frame: Any, context: Any) -> pd.DataFrame:
    base = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    for column, attr in EXPORT_COLUMNS.items():
        value = getattr(context, attr, "")
        if column in base.columns:
            base[column] = value
        else:
            base.insert(len(base.columns), column, value)
    return base


def build_export_bundle(frame: Any, context: Any) -> dict[str, Any]:
    enriched = identity_enriched_frame(frame, context)
    records = json.loads(enriched.to_json(orient="records", date_format="iso")) if not enriched.empty else []
    api = {
        "identity": {attr: getattr(context, attr, "") for attr in EXPORT_COLUMNS.values()},
        "rows": records,
    }
    csv_bytes = enriched.to_csv(index=False).encode("utf-8")
    copy_text = enriched.to_csv(index=False, sep="\t")
    excel = BytesIO()
    with pd.ExcelWriter(excel, engine="openpyxl") as writer:
        enriched.to_excel(writer, index=False, sheet_name="Global Publication")
        pd.DataFrame([api["identity"]]).to_excel(writer, index=False, sheet_name="Identity")
    return {
        "frame": enriched,
        "csv": csv_bytes,
        "excel": excel.getvalue(),
        "copy": copy_text,
        "api": api,
        "powerbi": enriched.copy(),
    }


def refresh_global_export_payloads(state: MutableMapping[str, Any], context: Any) -> dict[str, Any]:
    source = state.get("field3_multisymbol_regime_20260708")
    if not isinstance(source, pd.DataFrame) or source.empty:
        source = state.get("field10_institutional_ranking_20260708")
    bundle = build_export_bundle(source, context)
    state["global_symbol_export_frame_v2"] = bundle["frame"]
    state["global_symbol_export_csv_v2"] = bundle["csv"]
    state["global_symbol_export_excel_v2"] = bundle["excel"]
    state["global_symbol_export_copy_v2"] = bundle["copy"]
    state["global_symbol_export_api_v2"] = bundle["api"]
    state["global_symbol_export_powerbi_v2"] = bundle["powerbi"]
    return bundle

__all__ = ["identity_enriched_frame", "build_export_bundle", "refresh_global_export_payloads"]

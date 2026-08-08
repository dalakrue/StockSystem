"""Immutable QUICK source-signature and bounded phase instrumentation.

This module is orchestration-only. It never changes protected calculations.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Mapping, MutableMapping

import pandas as pd

SIGNATURE_KEY = "quick_source_signature_20260626"
MANIFEST_KEY = "quick_publication_manifest_20260626"
VERSION = "quick-source-signature-20260626-v2"


def _frame(state: Mapping[str, Any]) -> pd.DataFrame:
    for key in ("canonical_completed_ohlc_df_20260617", "last_df", "dv_pp_df", "lunch_5layer_powerbi_df"):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value
    return pd.DataFrame()


def _normalized_digest(frame: pd.DataFrame) -> tuple[str, str]:
    if frame.empty:
        return "", ""
    names = {str(c).strip().lower().replace("_", " "): c for c in frame.columns}
    time_col = next((names.get(x) for x in ("time", "datetime", "timestamp", "date") if names.get(x) is not None), None)
    cols = [names.get(x) for x in ("open", "high", "low", "close") if names.get(x) is not None]
    if time_col is None or len(cols) < 4:
        return "", ""
    work = pd.DataFrame({"time": pd.to_datetime(frame[time_col], errors="coerce", utc=True)})
    for name, col in zip(("open", "high", "low", "close"), cols):
        work[name] = pd.to_numeric(frame[col], errors="coerce")
    work = work.dropna().sort_values("time").drop_duplicates("time", keep="last")
    if work.empty:
        return "", ""
    completed = pd.Timestamp(work["time"].iloc[-1]).isoformat()
    payload = work.tail(1200).to_csv(index=False, float_format="%.10f", date_format="%Y-%m-%dT%H:%M:%S%z")
    return completed, hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_quick_source_signature(state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None) -> dict[str, Any]:
    canonical = canonical if isinstance(canonical, Mapping) else {}
    completed, digest = _normalized_digest(_frame(state))
    connector = str(
        canonical.get("data_source") or canonical.get("source") or state.get("active_data_source")
        or state.get("connector_source_identity_20260625") or "UNKNOWN_SOURCE"
    )
    protected = str(
        canonical.get("protected_hash") or canonical.get("protected_version")
        or state.get("field1_protected_hash_20260624") or state.get("protected_logic_hash") or "LEGACY_PROTECTED"
    )
    body = {
        "symbol": str(canonical.get("symbol") or state.get("symbol") or "EURUSD").upper(),
        "timeframe": str(canonical.get("timeframe") or state.get("timeframe") or "H1").upper(),
        "latest_completed_candle_time": completed or str(canonical.get("latest_completed_candle_time") or ""),
        "ohlc_digest": digest,
        "connector_source_identity": connector,
        "protected_version_hash": protected,
        "session_mode": str(state.get("shared_fx_session_mode") or state.get("session_mode") or "AUTO").upper(),
        "selected_session": str(state.get("shared_fx_session_selected") or state.get("field2_session_selector_20260625") or "AUTO").upper(),
        "session_layer_version": "session-shadow-20260626-v1",
        "feature_version": "blue24-red120-v1",
        "contract_version": VERSION,
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    body["source_signature"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return body


def publish_quick_manifest(state: MutableMapping[str, Any], status: MutableMapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    signature = build_quick_source_signature(state, canonical)
    perf = status.get("performance") if isinstance(status.get("performance"), Mapping) else {}
    manifest = {
        **signature,
        "run_id": canonical.get("run_id"),
        "generation_id": canonical.get("generation_id") or canonical.get("calculation_generation"),
        "snapshot_hash": canonical.get("source_snapshot_hash") or canonical.get("snapshot_hash") or canonical.get("data_signature") or state.get("canonical_snapshot_hash_20260617"),
        "source_snapshot_hash": canonical.get("source_snapshot_hash") or canonical.get("snapshot_hash") or canonical.get("data_signature") or state.get("canonical_snapshot_hash_20260617"),
        "broker_candle_time": canonical.get("broker_candle_time") or canonical.get("latest_completed_candle_time") or signature.get("latest_completed_candle_time"),
        "completed_broker_candle": canonical.get("broker_candle_time") or canonical.get("latest_completed_candle_time") or signature.get("latest_completed_candle_time"),
        "cache_reused": bool(status.get("quick_reuse")),
        "timing": {
            "source_load": status.get("source_load_seconds", 0.0),
            "normalization": status.get("normalization_seconds", 0.0),
            "field_1": status.get("field_1_seconds", 0.0),
            "field_2_central_cache": status.get("field_2_seconds", 0.0),
            "field_2_session_shadow": status.get("field_2_shadow_seconds", 0.0),
            "field_3": status.get("field_3_seconds", 0.0),
            "publication": status.get("publication_seconds", 0.0),
            "routing": status.get("routing_seconds", 0.0),
            "total_duration": perf.get("duration_seconds", status.get("elapsed_seconds", 0.0)),
            "peak_server_rss_bytes": perf.get("peak_rss_bytes", 0),
        },
        "published_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    state[SIGNATURE_KEY] = signature
    state[MANIFEST_KEY] = manifest
    status["quick_publication_manifest"] = manifest
    return manifest


__all__ = ["build_quick_source_signature", "publish_quick_manifest", "SIGNATURE_KEY", "MANIFEST_KEY"]

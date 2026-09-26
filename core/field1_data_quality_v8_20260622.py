"""Causal completed-H1 normalization and Field 1 identity validation."""
from __future__ import annotations
from typing import Any, Mapping
import pandas as pd

VERSION = "field1-quality-v8-20260622"


def _utc(value: Any) -> pd.Timestamp | None:
    try:
        ts = pd.to_datetime(value, errors="coerce", utc=True)
        if pd.isna(ts): return None
        return pd.Timestamp(ts).tz_convert("UTC")
    except Exception:
        return None


def normalize_field1_history(frame: pd.DataFrame, *, latest_completed_h1_utc: Any, symbol: str = "EURUSD", timeframe: str = "H1", max_rows: int = 3000) -> tuple[pd.DataFrame, dict[str, Any]]:
    watermark = _utc(latest_completed_h1_utc)
    if not isinstance(frame, pd.DataFrame) or frame.empty or watermark is None:
        return pd.DataFrame(), {"status": "FAIL", "reason": "history or completed-H1 watermark unavailable"}
    out = frame.copy(deep=False)
    candidates = ["event_time_utc", "time", "Time", "datetime", "Datetime", "timestamp", "Timestamp", "record_time"]
    col = next((c for c in candidates if c in out.columns), None)
    if col is None and isinstance(out.index, pd.DatetimeIndex):
        out = out.assign(event_time_utc=pd.to_datetime(out.index, utc=True, errors="coerce")); col = "event_time_utc"
    if col is None:
        return pd.DataFrame(), {"status": "FAIL", "reason": "authoritative timestamp missing"}
    out = out.assign(event_time_utc=pd.to_datetime(out[col], errors="coerce", utc=True)).dropna(subset=["event_time_utc"])
    future_count = int((out.event_time_utc > watermark).sum())
    out = out[out.event_time_utc <= watermark]
    duplicate_count = int(out.duplicated(subset=["event_time_utc"], keep="last").sum())
    out = out.drop_duplicates(subset=["event_time_utc"], keep="last").sort_values("event_time_utc")
    monotonic = bool(out.event_time_utc.is_monotonic_increasing)
    diffs = out.event_time_utc.diff().dropna()
    missing_h1 = int(((diffs > pd.Timedelta(hours=1)) & (out.event_time_utc.dt.dayofweek.iloc[1:].to_numpy() < 5)).sum()) if len(out) > 1 else 0
    out["symbol"] = out.get("symbol", symbol)
    out["timeframe"] = out.get("timeframe", timeframe)
    out = out.tail(max(1, min(int(max_rows), 10000))).sort_values("event_time_utc", ascending=False).reset_index(drop=True)
    latest = out.event_time_utc.iloc[0] if len(out) else None
    status = "PASS" if len(out) and latest == watermark and monotonic and duplicate_count == 0 and future_count == 0 else "WARN" if len(out) and latest <= watermark else "FAIL"
    return out, {"status": status, "latest_timestamp": latest.isoformat() if latest is not None else None, "watermark": watermark.isoformat(), "future_rows_rejected": future_count, "duplicate_rows_rejected": duplicate_count, "monotonic_after_normalization": monotonic, "unexpected_h1_gap_count": missing_h1, "row_count": int(len(out)), "version": VERSION}


def validate_field1_identity(*, field1_meta: Mapping[str, Any], canonical: Mapping[str, Any], broker_contract: Mapping[str, Any]) -> dict[str, Any]:
    market = canonical.get("market") if isinstance(canonical.get("market"), Mapping) else {}
    expected = {
        "latest_timestamp": canonical.get("latest_completed_h1_utc") or canonical.get("latest_completed_candle_time") or market.get("latest_completed_h1"),
        "calculation_id": canonical.get("calculation_id") or canonical.get("canonical_calculation_id") or canonical.get("run_id"),
        "generation_id": canonical.get("calculation_generation") or canonical.get("generation_id"),
        "symbol": canonical.get("symbol") or market.get("symbol"),
        "timeframe": canonical.get("timeframe") or market.get("timeframe"),
        "broker_offset_minutes": broker_contract.get("broker_offset_minutes"),
        "contract_version": broker_contract.get("contract_version"),
    }
    aliases = {"generation_id": ("generation_id", "generation", "calculation_generation"), "latest_timestamp": ("latest_timestamp", "latest_completed_h1_utc", "event_time_utc")}
    checks: dict[str, bool] = {}
    reasons: list[str] = []
    for key, exp in expected.items():
        names = aliases.get(key, (key,))
        actual = next((field1_meta.get(n) for n in names if field1_meta.get(n) is not None), None)
        if key == "latest_timestamp":
            ok = _utc(actual) == _utc(exp) if _utc(actual) is not None and _utc(exp) is not None else False
        else:
            ok = str(actual) == str(exp) if exp is not None else actual in (None, "")
        checks[key] = bool(ok)
        if not ok: reasons.append(f"{key} mismatch")
    quality_ok = str(field1_meta.get("status", "")).upper() in {"PASS", "SYNCED"}
    checks["data_quality"] = quality_ok
    if not quality_ok: reasons.append("data-quality checks not PASS")
    synced = all(checks.values())
    return {"status": "SYNCED" if synced else "NOT SYNCED", "checks": checks, "reason": "all required checks passed" if synced else "; ".join(reasons), "version": VERSION}


__all__ = ["normalize_field1_history", "validate_field1_identity", "VERSION"]

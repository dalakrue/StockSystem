"""Canonical pre-calculation and pre-publication validation gate.

The gate is additive to the existing validator. It does not clean or repair
price data. It returns deterministic identities and exact failed constraints so
callers can preserve the previous valid canonical generation.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from core.declarative_data_quality_20260621 import (
    Constraint,
    ConstraintResult,
    evaluate_constraints,
    shared_frame_aggregates,
)
from core.research_validation_common_20260621 import (
    find_column,
    json_safe,
    mapping,
    stable_hash,
    utc_now_iso,
    utc_timestamp,
)

VERSION = "canonical-data-validation-20260621-v1"
SCHEMA_VERSION = "canonical-data-validation-1.0.0"
_REQUIRED_PRICE_ALIASES = {
    "open": ("open", "o"),
    "high": ("high", "h"),
    "low": ("low", "l"),
    "close": ("close", "c"),
}


@dataclass(frozen=True)
class ValidationReport:
    generation_id: str
    source_hash: str
    evaluated_at: str
    stage: str
    status: str
    critical_failure_count: int
    warning_count: int
    source_row_count: int
    cleaned_row_count: int
    latest_timestamp: str | None
    constraints: tuple[ConstraintResult, ...]
    metrics: Mapping[str, Any]
    calculation_version: str = VERSION

    @property
    def publication_allowed(self) -> bool:
        return self.critical_failure_count == 0

    @property
    def failed_constraints(self) -> list[dict[str, Any]]:
        return [item.as_dict() for item in self.constraints if item.status == "FAIL"]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["publication_allowed"] = self.publication_allowed
        payload["constraints"] = [item.as_dict() for item in self.constraints]
        return json_safe(payload)

    def atomic_rows(self, *, source_generation_id: str = "") -> dict[str, list[dict[str, Any]]]:
        generation = {
            "generation_id": self.generation_id,
            "source_hash": self.source_hash,
            "source_generation_id": str(source_generation_id or self.generation_id),
            "evaluated_at": self.evaluated_at,
            "stage": self.stage,
            "status": self.status,
            "source_row_count": self.source_row_count,
            "cleaned_row_count": self.cleaned_row_count,
            "latest_timestamp": self.latest_timestamp,
            "critical_failure_count": self.critical_failure_count,
            "warning_count": self.warning_count,
            "calculation_version": self.calculation_version,
            "details_json": self.as_dict(),
        }
        constraints = [
            {
                "generation_id": self.generation_id,
                "constraint_name": item.constraint_name,
                "status": item.status,
                "severity": item.severity,
                "record_key": stable_hash([self.generation_id, item.constraint_name]),
                "observed_json": item.observed_value,
                "expected_json": item.expected_value,
                "violation_count": item.failed_rows,
                "detail": item.detail,
                "evaluated_at": self.evaluated_at,
            }
            for item in self.constraints
        ]
        metric_rows = []
        for name, value in self.metrics.items():
            numeric = value if isinstance(value, (int, float, np.integer, np.floating)) and np.isfinite(float(value)) else None
            metric_rows.append({
                "record_key": stable_hash([self.generation_id, name]),
                "generation_id": self.generation_id,
                "metric_name": str(name),
                "value_numeric": float(numeric) if numeric is not None else None,
                "value_text": None if numeric is not None else str(value),
                "evaluated_at": self.evaluated_at,
            })
        return {
            "data_quality_generation": [generation],
            "data_quality_constraint_result": constraints,
            "data_quality_metric_history": metric_rows,
        }


def _source_projection(frame: pd.DataFrame, time_col: str, columns: Mapping[str, str]) -> list[dict[str, Any]]:
    view = frame[[time_col, *columns.values()]].copy(deep=False)
    view = view.tail(4096)
    records = []
    times = pd.to_datetime(view[time_col], errors="coerce", utc=True)
    for index, row in view.iterrows():
        records.append({
            "time": str(times.loc[index]) if index in times.index else str(row.get(time_col)),
            **{name: row.get(column) for name, column in columns.items()},
        })
    return records


def validate_source_frame(
    frame: Any,
    *,
    symbol: str = "EURUSD",
    timeframe: str = "H1",
    source: str = "UNKNOWN",
    stage: str = "PRE_CALCULATION",
    source_row_count: int | None = None,
    expected_feature_schema: Sequence[str] | None = None,
    training_transform_signature: str | None = None,
    production_transform_signature: str | None = None,
    now: Any = None,
    max_staleness_hours: float = 8.0,
) -> ValidationReport:
    evaluated_at = utc_now_iso()
    if not isinstance(frame, pd.DataFrame):
        frame = pd.DataFrame()
    raw_rows = int(source_row_count if source_row_count is not None else len(frame))
    time_col = find_column(frame, ("time", "timestamp", "datetime", "date")) if not frame.empty else None
    if time_col is None and isinstance(frame.index, pd.DatetimeIndex) and not frame.empty:
        frame = frame.copy(deep=False)
        frame["__time_index__"] = frame.index
        time_col = "__time_index__"
    price_columns = {name: find_column(frame, aliases) for name, aliases in _REQUIRED_PRICE_ALIASES.items()} if not frame.empty else {}
    missing_columns = [name for name, column in price_columns.items() if column is None]
    if time_col is None:
        missing_columns.append("time")

    if missing_columns:
        source_hash = stable_hash({"symbol": symbol, "timeframe": timeframe, "source": source, "rows": raw_rows, "missing": missing_columns})
        generation_id = "DQ-" + stable_hash([stage, source_hash, VERSION])[:24]
        constraints = (
            ConstraintResult("required_columns", "FAIL", "CRITICAL", sorted(set(missing_columns)), ["time", "open", "high", "low", "close"], len(missing_columns), "Required OHLC/time columns are missing."),
        )
        return ValidationReport(generation_id, source_hash, evaluated_at, stage, "REJECT", 1, 0, raw_rows, int(len(frame)), None, constraints, {"rows": len(frame)})

    columns = {name: str(column) for name, column in price_columns.items() if column is not None}
    aggregates = shared_frame_aggregates(frame, time_col=str(time_col), price_cols=list(columns.values()))
    numeric = aggregates["numeric"]
    times = aggregates["times"]
    open_s = numeric[columns["open"]]
    high_s = numeric[columns["high"]]
    low_s = numeric[columns["low"]]
    close_s = numeric[columns["close"]]
    latest = aggregates["latest_time"]
    now_ts = utc_timestamp(now) or pd.Timestamp.now(tz="UTC")
    staleness = float((now_ts - latest).total_seconds() / 3600.0) if latest is not None else float("inf")
    current_hour = now_ts.floor("h")
    newest_complete = bool(latest is not None and latest < current_hour)
    spread_col = find_column(frame, ("spread", "bid_ask_spread"))
    spread = pd.to_numeric(frame[spread_col], errors="coerce") if spread_col else pd.Series(dtype=float)
    expected_schema = list(expected_feature_schema or [])
    actual_schema = [str(column) for column in frame.columns]

    context = {
        "frame": frame,
        "times": times,
        "numeric": numeric,
        "open": open_s,
        "high": high_s,
        "low": low_s,
        "close": close_s,
        "aggregates": aggregates,
        "spread": spread,
        "latest": latest,
        "staleness": staleness,
        "newest_complete": newest_complete,
        "expected_schema": expected_schema,
        "actual_schema": actual_schema,
        "training_transform_signature": training_transform_signature,
        "production_transform_signature": production_transform_signature,
    }

    def simple(name: str, severity: str, description: str, fn):
        return Constraint(name, severity, description, fn)

    constraints = [
        simple("required_columns", "CRITICAL", "OHLC/time columns must exist.", lambda c: (True, sorted(["time", *columns]), ["time", "open", "high", "low", "close"], 0, "All required columns are present.")),
        simple("non_empty", "CRITICAL", "At least one completed row is required.", lambda c: (len(frame) > 0, len(frame), ">0", 0 if len(frame) else 1, "Input frame row count.")),
        simple("datetime_type", "CRITICAL", "Timestamps must parse.", lambda c: (aggregates["invalid_time_count"] == 0, aggregates["invalid_time_count"], 0, aggregates["invalid_time_count"], "Unparseable timestamps are rejected.")),
        simple("numeric_types", "CRITICAL", "OHLC must be numeric.", lambda c: (int(numeric.isna().sum().sum()) == 0, int(numeric.isna().sum().sum()), 0, int(numeric.isna().any(axis=1).sum()), "NaN/non-numeric OHLC values.")),
        simple("finite_numbers", "CRITICAL", "OHLC must be finite.", lambda c: (aggregates["nonfinite_count"] == 0, aggregates["nonfinite_count"], 0, int((~aggregates["finite_mask"]).any(axis=1).sum()), "Infinite OHLC values.")),
        simple("unique_timestamps", "CRITICAL", "Timestamps must be unique.", lambda c: (aggregates["duplicate_count"] == 0, aggregates["duplicate_count"], 0, aggregates["duplicate_count"], "Duplicate H1 candles are not silently deduplicated by this gate.")),
        simple("monotonic_timestamps", "CRITICAL", "Timestamps must increase.", lambda c: (aggregates["monotonic"], aggregates["monotonic"], True, 0 if aggregates["monotonic"] else 1, "Input must already be chronologically ordered.")),
        simple("expected_h1_frequency", "WARNING", "Interior weekday gaps should be explained.", lambda c: (aggregates["missing_candle_estimate"] == 0, aggregates["missing_candle_estimate"], 0, aggregates["missing_candle_estimate"], "Weekend gaps are excluded; interior weekday H1 gaps are counted.")),
        simple("timezone_consistency", "CRITICAL", "All timestamps normalize consistently to UTC.", lambda c: (times.notna().all(), "UTC-normalizable", "UTC-normalizable", int(times.isna().sum()), "Timestamps are normalized to UTC for validation only.")),
        simple("latest_candle_complete", "CRITICAL", "Newest row must be a completed H1 candle.", lambda c: (newest_complete, str(latest), f"< {current_hour.isoformat()}", 0 if newest_complete else 1, "Open/current H1 candle cannot enter the canonical calculation.")),
        simple("source_freshness", "WARNING", "Latest completed candle should be fresh.", lambda c: (staleness <= max_staleness_hours, round(staleness, 4), f"<= {max_staleness_hours} hours", 0 if staleness <= max_staleness_hours else 1, "Stale sources reduce trust but do not fabricate rows.")),
        simple("low_le_open_le_high", "CRITICAL", "Low <= Open <= High.", lambda c: (bool(((low_s <= open_s) & (open_s <= high_s)).all()), int((~((low_s <= open_s) & (open_s <= high_s))).sum()), 0, int((~((low_s <= open_s) & (open_s <= high_s))).sum()), "Invalid open range.")),
        simple("low_le_close_le_high", "CRITICAL", "Low <= Close <= High.", lambda c: (bool(((low_s <= close_s) & (close_s <= high_s)).all()), int((~((low_s <= close_s) & (close_s <= high_s))).sum()), 0, int((~((low_s <= close_s) & (close_s <= high_s))).sum()), "Invalid close range.")),
        simple("high_ge_low", "CRITICAL", "High >= Low.", lambda c: (bool((high_s >= low_s).all()), int((high_s < low_s).sum()), 0, int((high_s < low_s).sum()), "Negative candle range.")),
        simple("nonnegative_spread", "CRITICAL", "Spread cannot be negative.", lambda c: (spread.empty or bool((spread.dropna() >= 0).all()), int((spread.dropna() < 0).sum()) if not spread.empty else 0, 0, int((spread.dropna() < 0).sum()) if not spread.empty else 0, "Spread column is optional; when present it must be nonnegative.")),
        simple("row_count_reconciliation", "WARNING", "Source and cleaned counts must reconcile explicitly.", lambda c: (raw_rows >= len(frame), {"source": raw_rows, "cleaned": len(frame), "difference": raw_rows-len(frame)}, "source >= cleaned", 0 if raw_rows >= len(frame) else 1, "No price repair is performed; upstream removals remain visible.")),
        simple("feature_schema_consistency", "CRITICAL" if expected_schema else "INFO", "Expected feature schema must be present.", lambda c: (not expected_schema or set(expected_schema).issubset(set(actual_schema)), sorted(set(expected_schema)-set(actual_schema)), [], len(set(expected_schema)-set(actual_schema)), "Missing expected production features." if expected_schema else "No explicit expected feature schema was supplied.")),
        simple("training_production_transform_consistency", "CRITICAL" if training_transform_signature and production_transform_signature else "INFO", "Training and production transforms must match.", lambda c: (not (training_transform_signature and production_transform_signature) or training_transform_signature == production_transform_signature, production_transform_signature, training_transform_signature, 0 if training_transform_signature == production_transform_signature else 1, "Transform signatures compared when both are available.")),
    ]
    results = tuple(evaluate_constraints(context, constraints))
    critical = sum(item.status == "FAIL" and item.severity == "CRITICAL" for item in results)
    warnings = sum(item.status == "FAIL" and item.severity in {"WARNING", "INFO"} for item in results)
    source_hash = stable_hash({
        "identity": [str(symbol).upper(), str(timeframe).upper(), str(source)],
        "rows": _source_projection(frame, str(time_col), columns),
    })
    generation_id = "DQ-" + stable_hash([stage, source_hash, VERSION])[:24]
    metrics = {
        "row_count": int(len(frame)),
        "source_row_count": raw_rows,
        "missing_candle_estimate": aggregates["missing_candle_estimate"],
        "duplicate_timestamp_count": aggregates["duplicate_count"],
        "nonfinite_count": aggregates["nonfinite_count"],
        "staleness_hours": round(staleness, 6),
        "critical_failure_count": critical,
        "warning_count": warnings,
    }
    return ValidationReport(
        generation_id=generation_id,
        source_hash=source_hash,
        evaluated_at=evaluated_at,
        stage=stage,
        status="PASS" if critical == 0 else "REJECT",
        critical_failure_count=int(critical),
        warning_count=int(warnings),
        source_row_count=raw_rows,
        cleaned_row_count=int(len(frame)),
        latest_timestamp=latest.isoformat() if latest is not None else None,
        constraints=results,
        metrics=metrics,
    )


def validate_canonical_payload(canonical: Mapping[str, Any], *, now: Any = None) -> ValidationReport:
    """Validate publication-only invariants without mutating the payload."""
    market = mapping(canonical.get("market"))
    latest = canonical.get("latest_completed_candle_time") or market.get("latest_completed_candle_time")
    now_ts = utc_timestamp(now) or pd.Timestamp.now(tz="UTC")
    latest_ts = utc_timestamp(latest)
    source_hash = str(canonical.get("data_signature") or stable_hash(canonical))
    generation_id = "DQ-" + stable_hash(["PRE_PUBLICATION", source_hash, canonical.get("calculation_generation"), VERSION])[:24]
    evaluated_at = utc_now_iso()

    probability_failures: list[str] = []
    score_failures: list[str] = []
    temporal_failures: list[str] = []

    # Percentage-like names are not automatically bounded. Trading payloads
    # legitimately contain signed return/change/error/skill percentages. The old
    # broad ``_pct`` rule rejected those valid values and could leave Lunch/AI on
    # an older generation while Field 3 displayed the newly staged tables.
    signed_percent_tokens = (
        "return", "change", "delta", "alpha", "skill", "error", "bias",
        "move", "pnl", "profit", "loss", "edge", "residual", "deviation",
        "drift", "spread_change", "price_change", "performance",
    )
    bounded_percent_tokens = (
        "confidence", "reliability", "accuracy", "coverage", "quality",
        "completeness", "agreement", "uncertainty", "freshness", "readiness",
        "tradeability", "probability", "probab", "success_rate", "hit_rate",
        "win_rate", "sample_coverage", "band_coverage", "risk_pct",
    )

    def is_bounded_percent_name(name: str) -> bool:
        if any(token in name for token in signed_percent_tokens):
            return False
        if "score_0_100" in name:
            return True
        is_percent_form = "_pct" in name or "percent" in name or "percentage" in name
        return bool(is_percent_form and any(token in name for token in bounded_percent_tokens))

    def walk(value: Any, path: str = "") -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                current = f"{path}.{key}" if path else str(key)
                lower = str(key).lower()
                if isinstance(item, (int, float, np.integer, np.floating)) and np.isfinite(float(item)):
                    number = float(item)
                    if "probab" in lower and not (0.0 <= number <= 1.0 or 0.0 <= number <= 100.0):
                        probability_failures.append(current)
                    if any(token in lower for token in ("score_0_10", "/10")) and not (0 <= number <= 10):
                        score_failures.append(current)
                    if is_bounded_percent_name(lower) and not (0 <= number <= 100):
                        score_failures.append(current)
                walk(item, current)
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value[:1000]):
                walk(item, f"{path}[{index}]")

    walk(canonical)
    forecasts = mapping(canonical.get("forecasts"))
    horizons = mapping(forecasts.get("horizons"))
    for name, item in horizons.items():
        row = mapping(item)
        origin = utc_timestamp(row.get("forecast_origin_time") or canonical.get("latest_completed_candle_time"))
        target = utc_timestamp(row.get("target_time"))
        settled = utc_timestamp(row.get("settlement_timestamp") or row.get("settled_at"))
        created = utc_timestamp(row.get("prediction_created_at") or origin)
        if origin is not None and target is not None and not origin < target:
            temporal_failures.append(f"{name}: origin must precede target")
        if settled is not None and created is not None and settled < created:
            temporal_failures.append(f"{name}: settlement precedes prediction creation")
        if target is not None and latest_ts is not None and row.get("settled_status") in {"SETTLED", "OBSERVED", "COMPLETED"} and target > latest_ts:
            temporal_failures.append(f"{name}: future target marked settled")

    identity_symbol = str(canonical.get("symbol") or "").strip().upper().replace("/", "")
    identity_timeframe = str(canonical.get("timeframe") or "").strip().upper()
    selected_scope = canonical.get("selected_symbols")
    if not isinstance(selected_scope, (list, tuple, set)):
        selected_scope = []
    normalized_scope = {str(item).strip().upper().replace("/", "") for item in selected_scope}
    identity_ok = bool(identity_symbol) and identity_timeframe in {"H1", "H4"}
    if normalized_scope:
        identity_ok = identity_ok and identity_symbol in normalized_scope
    boundary_ok = latest_ts is not None and latest_ts <= now_ts.floor("h")
    if boundary_ok and identity_timeframe == "H4":
        boundary_ok = bool(latest_ts.minute == 0 and latest_ts.second == 0 and latest_ts.hour % 4 == 0)
    elif boundary_ok and identity_timeframe == "H1":
        boundary_ok = bool(latest_ts.minute == 0 and latest_ts.second == 0)
    checks = [
        ConstraintResult("canonical_mapping", "PASS" if isinstance(canonical, Mapping) and bool(canonical) else "FAIL", "CRITICAL", bool(canonical), True, 0 if canonical else 1, "Canonical payload must be a non-empty mapping."),
        ConstraintResult("latest_completed_candle", "PASS" if boundary_ok else "FAIL", "CRITICAL", str(latest), f"completed {identity_timeframe or 'selected-timeframe'} boundary <= {now_ts.floor('h').isoformat()}", 0 if boundary_ok else 1, "The canonical timestamp must be a completed boundary for the selected timeframe."),
        ConstraintResult("probability_domains", "PASS" if not probability_failures else "FAIL", "CRITICAL", probability_failures, "all probabilities in [0,1] or documented percent form", len(probability_failures), "Probability fields are range checked recursively."),
        ConstraintResult("score_domains", "PASS" if not score_failures else "FAIL", "CRITICAL", score_failures, "documented 0-10/0-100 domains", len(score_failures), "Only explicitly named score domains are enforced."),
        ConstraintResult("forecast_temporal_order", "PASS" if not temporal_failures else "FAIL", "CRITICAL", temporal_failures, "origin < target and creation <= settlement <= completed cutoff", len(temporal_failures), "Forecast settlement chronology."),
        ConstraintResult("source_identity", "PASS" if identity_ok else "FAIL", "CRITICAL", [identity_symbol, identity_timeframe], ["selected symbol", "H1 or H4"], 0 if identity_ok else 1, "Operational identity must match the selected symbol scope and selected timeframe."),
    ]
    critical = sum(item.status == "FAIL" and item.severity == "CRITICAL" for item in checks)
    return ValidationReport(
        generation_id=generation_id,
        source_hash=source_hash,
        evaluated_at=evaluated_at,
        stage="PRE_PUBLICATION",
        status="PASS" if critical == 0 else "REJECT",
        critical_failure_count=critical,
        warning_count=0,
        source_row_count=int(market.get("source_row_count") or market.get("row_count") or 0),
        cleaned_row_count=int(market.get("row_count") or 0),
        latest_timestamp=latest_ts.isoformat() if latest_ts is not None else None,
        constraints=tuple(checks),
        metrics={"probability_failure_count": len(probability_failures), "score_failure_count": len(score_failures), "temporal_failure_count": len(temporal_failures)},
    )


__all__ = ["VERSION", "SCHEMA_VERSION", "ValidationReport", "validate_source_frame", "validate_canonical_payload"]

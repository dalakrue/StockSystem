"""Settings-owned orchestrator for Project Quant Lunch V13 shadow layers.

The function is called only by the existing Settings research service.  It
reads cached completed-H1 data, never imports a production predictor, and
returns a hashable shadow result that cannot overwrite protected decisions.
"""
from __future__ import annotations

from datetime import timezone
from typing import Any, Iterable, Mapping
import math

import numpy as np
import pandas as pd

from core.canonical.snapshot import CanonicalRunSnapshot
from research.run_snapshot_v12 import stable_hash
from research.v12_orchestrator import chronological_settled_outcomes
from research.v13_catalog import catalog_by_slug, catalog_rows
from research.v13_quantile_volatility import EVALUATORS as QUANTILE_VOL_EVALUATORS
from research.v13_robust_patterns import EVALUATORS as ROBUST_PATTERN_EVALUATORS

SCHEMA_VERSION = "research-v13-shadow-1.0"
CONFIGURATION = {
    "maximum_h1_rows": 600,
    "history_days": 25,
    "chronological_split": True,
    "purge_target_overlap": True,
    "overlapping_horizon_embargo": True,
    "future_actual_leakage_allowed": False,
    "shadow_only": True,
    "automatic_promotion": False,
}


def _column(frame: pd.DataFrame, *aliases: str) -> Any | None:
    lookup = {str(column).strip().lower().replace("_", " "): column for column in frame.columns}
    for alias in aliases:
        hit = lookup.get(alias.strip().lower().replace("_", " "))
        if hit is not None:
            return hit
    return None


def _standardize_h1(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=["event_time_utc", "open", "high", "low", "close"])
    columns = {
        "event_time_utc": _column(frame, "event_time_utc", "Time", "Datetime", "Timestamp"),
        "open": _column(frame, "open", "o"),
        "high": _column(frame, "high", "h"),
        "low": _column(frame, "low", "l"),
        "close": _column(frame, "close", "c", "last"),
    }
    if columns["event_time_utc"] is None or columns["close"] is None:
        return pd.DataFrame(columns=["event_time_utc", "open", "high", "low", "close"])
    out = pd.DataFrame({
        "event_time_utc": pd.to_datetime(frame[columns["event_time_utc"]], errors="coerce", utc=True),
        "close": pd.to_numeric(frame[columns["close"]], errors="coerce"),
    })
    for name in ("open", "high", "low"):
        source = columns[name]
        out[name] = pd.to_numeric(frame[source], errors="coerce") if source is not None else out["close"]
    return (
        out.replace([np.inf, -np.inf], np.nan)
        .dropna(subset=["event_time_utc", "close"])
        .sort_values("event_time_utc", kind="mergesort")
        .drop_duplicates("event_time_utc", keep="last")
        .tail(CONFIGURATION["maximum_h1_rows"])
        .reset_index(drop=True)
    )


def _cached_h1(state: Mapping[str, Any], snapshot: CanonicalRunSnapshot) -> tuple[pd.DataFrame, dict[str, Any]]:
    try:
        from core.lunch_h1_data_quality_v13 import cached_completed_ohlc, completed_h1_frame, quality_report
        source = cached_completed_ohlc(state)
        projected = completed_h1_frame(
            source,
            completed_h1=snapshot.broker_candle_time,
            days=CONFIGURATION["history_days"],
            maximum_rows=CONFIGURATION["maximum_h1_rows"],
            descending=False,
        )
        standardized = _standardize_h1(projected)
        report = quality_report(
            source,
            projected=standardized,
            completed_h1=snapshot.broker_candle_time,
            provenance="cached_canonical_completed_h1_ohlc",
        )
        return standardized, report
    except Exception as exc:
        return pd.DataFrame(), {"status": "FAIL", "flags": [f"H1_SOURCE_ERROR:{type(exc).__name__}"], "error": str(exc)}


def _context(snapshot: CanonicalRunSnapshot, settled: list[Mapping[str, Any]]) -> dict[str, Any]:
    metrics = dict(snapshot.metrics) if isinstance(snapshot.metrics, Mapping) else {}
    predictions = dict(snapshot.predictions) if isinstance(snapshot.predictions, Mapping) else {}
    spread = metrics.get("spread_pips") or metrics.get("spread") or predictions.get("spread_pips") or 0.8
    expected = predictions.get("expected_return_pips") or predictions.get("expected_move_pips") or 0.0
    try:
        spread = float(spread)
        spread = spread if math.isfinite(spread) else 0.8
    except Exception:
        spread = 0.8
    try:
        expected = float(expected)
        expected = expected if math.isfinite(expected) else 0.0
    except Exception:
        expected = 0.0
    return {
        "transaction_cost_pips": abs(spread),
        "spread_pips": abs(spread),
        "expected_return_pips": expected,
        "signal_pips": expected,
        "settled_outcome_count": len(settled),
        "symbol": snapshot.symbol,
        "timeframe": snapshot.timeframe,
    }


def evaluate_v13(
    snapshot: CanonicalRunSnapshot,
    settled_outcomes: Iterable[Mapping[str, Any]],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate all ten layers against one immutable completed-H1 watermark."""
    cutoff = snapshot.broker_candle_time
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    settled, warnings = chronological_settled_outcomes(
        settled_outcomes, cutoff=cutoff, apply_embargo=True
    )
    h1, quality = _cached_h1(state, snapshot)
    if h1.empty:
        warnings.append("cached completed-H1 OHLC unavailable; all price-history layers remain unavailable")
    if len(settled) < 25:
        warnings.append(
            f"settled validation remains sparse ({len(settled)} matured embargoed outcomes); no edge or promotion is certified"
        )

    evaluators = {**QUANTILE_VOL_EVALUATORS, **ROBUST_PATTERN_EVALUATORS}
    catalog = catalog_by_slug()
    context = _context(snapshot, settled)
    full_results: dict[str, Any] = {}
    for slug, evaluator in evaluators.items():
        try:
            if slug in ROBUST_PATTERN_EVALUATORS:
                result = evaluator(h1, context)
            else:
                result = evaluator(h1)
        except Exception as exc:
            result = {
                "status": "FAILED_SAFELY",
                "sample_size": 0,
                "shadow_only": True,
                "production_changed": False,
                "outputs": {"reason": f"{type(exc).__name__}: {exc}"},
            }
        result["research_title"] = catalog[slug]["title"]
        result["prediction_time_availability"] = catalog[slug]["prediction_time_availability"]
        result["promotion_gate"] = catalog[slug]["promotion_gate"]
        full_results[slug] = result

    module_statuses = {slug: str(result.get("status") or "UNAVAILABLE") for slug, result in full_results.items()}
    sample_sizes = {slug: int(result.get("sample_size") or 0) for slug, result in full_results.items()}
    available = sum(status in {"AVAILABLE_SHADOW", "ROBUST_ACTIONABLE_SHADOW"} or status.endswith("WARNING") for status in module_statuses.values())
    compact_results = {
        "mode": "SHADOW ONLY",
        "available_layers": available,
        "total_layers": 10,
        "completed_h1_rows": len(h1),
        "matured_embargoed_outcomes": len(settled),
        "data_quality_status": quality.get("status", "UNAVAILABLE"),
        "future_actual_leakage": "PROHIBITED",
        "automatic_promotion": False,
        "production_changed": False,
    }
    source_hashes = {
        "canonical_snapshot": snapshot.source_snapshot_hash or stable_hash(snapshot.to_dict()),
        "completed_h1": stable_hash(h1.to_dict("records")),
        "settled_outcomes": stable_hash(settled),
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": snapshot.run_id,
        "calculation_generation": snapshot.generation_id or snapshot.run_id,
        "broker_time": cutoff.isoformat(),
        "candle_time": cutoff.isoformat(),
        "symbol": snapshot.symbol,
        "timeframe": snapshot.timeframe,
        "settled_outcome_cutoff": cutoff.isoformat(),
        "source_hashes": source_hashes,
        "configuration": dict(CONFIGURATION),
        "configuration_hash": stable_hash(CONFIGURATION),
        "module_statuses": module_statuses,
        "sample_sizes": sample_sizes,
        "warnings": list(dict.fromkeys(warnings + list(quality.get("flags") or []))),
        "compact_results": compact_results,
        "data_quality": quality,
        "catalog": catalog_rows(),
        "full_results": full_results,
        "shadow_only": True,
        "production_changed": False,
        "protected_decision": snapshot.decision,
    }
    payload["snapshot_hash"] = stable_hash(payload)
    return payload


__all__ = ["SCHEMA_VERSION", "CONFIGURATION", "evaluate_v13"]

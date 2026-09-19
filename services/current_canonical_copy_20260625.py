"""Current-only canonical copy payloads for visible Copy Short / Copy Full controls.

Legacy history/export serializers are intentionally left untouched for backward
compatibility.  This module includes only present values from the immutable
current generation and never serializes history DataFrames or unavailable
placeholders.
"""
from __future__ import annotations

import json
import math
from typing import Any, Mapping, MutableMapping

import pandas as pd

from services.canonical_exports import PayloadStats, payload_stats

_INVALID_EXACT = {
    "",
    "-",
    "—",
    "NONE",
    "NULL",
    "NAN",
    "N/A",
    "NA",
    "UNAVAILABLE",
    "NOT AVAILABLE",
    "NOT PUBLISHED",
    "UNKNOWN",
}
_INVALID_CONTAINS = (
    "UNAVAILABLE",
    "NOT PUBLISHED",
    "NOT AVAILABLE",
    "RUN CALCULATION FIRST",
    "NO PUBLISHED",
    "FAILED SAFELY",
    "SOURCE_HASH_UNAVAILABLE",
)
_HISTORY_TOKENS = ("history", "historical", "last_25", "last 25", "rows")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        try:
            return math.isfinite(float(value))
        except Exception:
            return False
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in _INVALID_EXACT:
            return False
        return not any(token in normalized for token in _INVALID_CONTAINS)
    if isinstance(value, pd.DataFrame):
        return False
    if isinstance(value, pd.Series):
        return False
    if isinstance(value, Mapping):
        return any(_present(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_present(v) for v in value)
    return True


def _clean(value: Any, *, drop_history_keys: bool = True) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lower = key_text.lower()
            if drop_history_keys and any(token in lower for token in _HISTORY_TOKENS):
                continue
            cleaned = _clean(item, drop_history_keys=drop_history_keys)
            if _present(cleaned):
                out[key_text] = cleaned
        return out
    if isinstance(value, (list, tuple, set)):
        out = [_clean(item, drop_history_keys=drop_history_keys) for item in value]
        return [item for item in out if _present(item)]
    if isinstance(value, pd.DataFrame) or isinstance(value, pd.Series):
        return None
    if isinstance(value, float):
        return round(value, 8) if math.isfinite(value) else None
    return value if _present(value) else None


def _first(*values: Any) -> Any:
    for value in values:
        if _present(value):
            return value
    return None


def _canonical(state: Mapping[str, Any]) -> Mapping[str, Any]:
    from core.canonical_lookup_20260626 import resolve_canonical
    return resolve_canonical(state)


def _time_column(frame: pd.DataFrame) -> str | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    preferred = ("Time", "Datetime", "DateTime", "Timestamp", "Broker Time", "candle_time", "Hour")
    for name in preferred:
        if name in frame.columns:
            return name
    for column in frame.columns:
        lower = str(column).strip().lower()
        if any(token in lower for token in ("timestamp", "datetime", "candle time", "broker time")):
            return str(column)
    return None


def _drop_empty_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    keep: list[str] = []
    for column in frame.columns:
        series = frame[column]
        normalized = series.astype(str).str.strip().str.upper()
        valid = series.notna() & ~normalized.isin(_INVALID_EXACT)
        valid &= ~normalized.apply(lambda text: any(token in text for token in _INVALID_CONTAINS))
        if bool(valid.any()):
            keep.append(str(column))
    return frame.loc[:, keep] if keep else pd.DataFrame(index=frame.index)


def _current_rows(
    frame: pd.DataFrame, *, target_candle: Any = None, maximum_rows: int = 24, maximum_columns: int = 40
) -> list[dict[str, Any]]:
    """Extract rows for the exact canonical completed candle, never a stale latest row."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return []
    work = frame.copy(deep=False)
    time_col = _time_column(work)
    if time_col:
        parsed = pd.to_datetime(work[time_col], errors="coerce", utc=True, format="mixed").dt.floor("h")
        if parsed.notna().any():
            target = pd.to_datetime(target_candle, errors="coerce", utc=True)
            if pd.notna(target):
                exact = parsed.eq(pd.Timestamp(target).floor("h"))
                if not bool(exact.any()):
                    return []
                work = work.loc[exact]
            else:
                work = work.loc[parsed.eq(parsed.max())]
    work = _drop_empty_columns(work).head(maximum_rows)
    if work.empty:
        return []
    if len(work.columns) > maximum_columns:
        important_tokens = ("time", "decision", "direction", "bias", "score", "pressure", "regime", "reliab", "confidence", "price", "priority")
        important = [c for c in work.columns if any(t in str(c).lower() for t in important_tokens)]
        ordered = list(dict.fromkeys(list(work.columns[:10]) + important))[:maximum_columns]
        work = work.loc[:, ordered]
    records = work.to_dict(orient="records")
    return [_clean(record, drop_history_keys=False) for record in records if _present(record)]


def _current_lunch_tables(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    """Collect current-candle Lunch tables without serializing 25-day history."""
    candidates = (
        ("field1_table1_current", "full_metric_history_df_20260618"),
        ("field1_table2_current", "one_hour_direction_confirmation_20260626"),
        ("field1_table3_current", "canonical_priority_table_20260617"),
        ("field1_table4_current", "field1_table4_current_20260627"),
        ("field1_table5_current", "field1_table5_integrated_decision_collection_20260627"),
        ("regime_three_standard_current", "regime_standard_table_20260617"),
        ("priority_current", "finder_readonly_priority_table_20260618"),
        ("quick_decision_current", "lunch_quick_decision_merged_table_20260617"),
    )
    out: dict[str, Any] = {}
    target_candle = (
        canonical.get("completed_broker_candle")
        or canonical.get("broker_candle_time")
        or canonical.get("latest_completed_candle_time")
        or _mapping(canonical.get("market")).get("latest_completed_candle_time")
    )
    for label, key in candidates:
        frame = state.get(key)
        rows = _current_rows(frame, target_candle=target_candle) if isinstance(frame, pd.DataFrame) else []
        if rows:
            out[label] = rows
    return out


def _forecast_rows(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    session_payload = state.get("session_adaptive_projection_20260625")
    session_frame = _mapping(session_payload).get("horizons")
    if isinstance(session_frame, pd.DataFrame) and not session_frame.empty:
        for _, row in session_frame.sort_values("horizon").iterrows():
            item = {
                "horizon_h": row.get("horizon"),
                "base_price": row.get("Base Prediction"),
                "session_price": row.get("Session Prediction"),
                "lower": row.get("lower"),
                "upper": row.get("upper"),
                "session": row.get("Selected Session"),
                "evidence_tier": row.get("evidence_tier"),
                "settled_samples": row.get("sample_count"),
                "completed_h1_prior_samples": row.get("intraday_prior_sample_count"),
            }
            cleaned = _clean(item)
            if cleaned:
                rows.append(cleaned)
        return rows
    forecasts = _mapping(canonical.get("forecasts"))
    horizons = _mapping(forecasts.get("horizons"))
    for key, value in horizons.items():
        horizon = _mapping(value)
        item = _clean({
            "horizon": key,
            "central_price": _first(horizon.get("central_price"), horizon.get("predicted_price"), horizon.get("price")),
            "lower": _first(horizon.get("lower_bound"), horizon.get("lower")),
            "upper": _first(horizon.get("upper_bound"), horizon.get("upper")),
            "direction": horizon.get("direction"),
            "confidence_pct": _first(horizon.get("confidence_pct"), horizon.get("confidence")),
            "reliability_pct": _first(horizon.get("reliability_pct"), horizon.get("reliability")),
            "target_time": _first(horizon.get("target_time"), horizon.get("time")),
        })
        if item:
            rows.append(item)
    return rows



def _field10_copy_sections(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    """Read current Field 10 and saved three-standard evidence only."""
    try:
        from core.symbol_context_20260702 import resolve_symbol_context
        from core.multi_symbol_field10_20260701 import DB_PATH
        from core.field10_integrated_evidence_20260702 import load_integrated_current
        from core.child_generation_contract_20260702 import load_child_contract_tables
        context = resolve_symbol_context(state, "Lunch")
        parent_run_id = str(context.parent_run_id or state.get("multi_symbol_parent_run_id_20260701") or "")
        current = load_integrated_current(parent_run_id) if parent_run_id else pd.DataFrame()
        if not current.empty and "Symbol" in current.columns:
            current = current.loc[current["Symbol"].astype(str).str.upper() == context.lunch_display_symbol]
        current_rows = _current_rows(current, target_candle=context.completed_broker_candle, maximum_columns=48) if not current.empty else []
        contract = load_child_contract_tables(
            path=DB_PATH, parent_run_id=parent_run_id, symbol=context.lunch_display_symbol,
            timeframe=context.timeframe, child_run_id=context.child_run_id,
        ) if parent_run_id else {}
        standards = contract.get("field3_current") if isinstance(contract, Mapping) else pd.DataFrame()
        standards_rows = standards.to_dict("records") if isinstance(standards, pd.DataFrame) and not standards.empty else []
        metadata = contract.get("metadata") if isinstance(contract, Mapping) and isinstance(contract.get("metadata"), Mapping) else {}
        return _clean({
            "field_10_current_integrated": current_rows[:1],
            "field_3_three_standard_quick_look": standards_rows[:3],
            "field_10_publication_status": metadata.get("publication_status") or (current.iloc[0].get("Publication Status") if not current.empty and "Publication Status" in current else None),
            "field_10_data_quality": current.iloc[0].get("Data Quality Grade") if not current.empty and "Data Quality Grade" in current else None,
            "protected_final_action": current.iloc[0].get("Protected Final Action") if not current.empty and "Protected Final Action" in current else None,
            "field_10_identity": {
                "parent_run_id": metadata.get("parent_run_id") or context.parent_run_id,
                "child_run_id": metadata.get("child_run_id") or context.child_run_id,
                "canonical_run_id": metadata.get("canonical_run_id") or context.canonical_run_id,
                "snapshot_hash": metadata.get("snapshot_hash") or context.snapshot_hash,
                "completed_broker_candle": metadata.get("completed_broker_candle") or context.completed_broker_candle,
            },
        })
    except Exception as exc:
        return {"field_10_publication_status": "UNAVAILABLE", "field_10_diagnostic": f"{type(exc).__name__}: {exc}"}


def build_current_snapshot(
    state: MutableMapping[str, Any] | Mapping[str, Any],
    canonical: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    canonical = dict(canonical or _canonical(state))
    if not canonical:
        return {}
    try:
        from core.symbol_context_20260702 import resolve_symbol_context
        symbol_context = resolve_symbol_context(state, "Lunch")
    except Exception:
        symbol_context = None
    final = _mapping(canonical.get("final_decision"))
    market = _mapping(canonical.get("market"))
    regime = _mapping(canonical.get("regime"))
    reliability = _mapping(canonical.get("reliability"))
    scores = _mapping(canonical.get("scores"))
    priority = _mapping(canonical.get("priority"))
    uncertainty = _mapping(canonical.get("uncertainty"))
    risk = _mapping(canonical.get("risk_plan"))

    try:
        from core.session_context_20260625 import resolve_session_contract

        session = resolve_session_contract(state, canonical).to_dict()
    except Exception:
        session = _mapping(state.get("shared_fx_session_contract_20260625"))

    locked = state.get("daily_locked_regime_20260625")
    if not isinstance(locked, Mapping) and isinstance(state, MutableMapping):
        try:
            from core.daily_locked_regime_20260625 import ensure_daily_locked_regime

            locked = ensure_daily_locked_regime(state, canonical)
        except Exception:
            locked = {}
    locked = _mapping(locked)

    current = {
        "identity": {
            "symbol": symbol_context.lunch_display_symbol if symbol_context is not None else _first(canonical.get("symbol"), "EURUSD"),
            "timeframe": _first(canonical.get("timeframe"), "H1"),
            "run_id": _first(canonical.get("run_id"), canonical.get("canonical_calculation_id")),
            "generation": canonical.get("calculation_generation"),
            "snapshot_hash": _first(canonical.get("snapshot_hash"), canonical.get("source_snapshot_hash")),
            "latest_completed_candle": _first(
                canonical.get("latest_completed_candle_time"),
                market.get("latest_completed_candle_time"),
                canonical.get("broker_candle_time"),
            ),
            "created_at": canonical.get("created_at"),
            "expires_at": canonical.get("expires_at"),
        },
        "field_1_current_decision": {
            "decision": _first(final.get("final_decision"), canonical.get("decision")),
            "tradeability": final.get("tradeability_decision"),
            "less_risky_decision": final.get("less_risky_decision"),
            "directional_market_view": _first(final.get("directional_market_view"), canonical.get("full_metric_direction")),
            "selected_horizon_h": final.get("selected_horizon"),
            "priority": _first(priority.get("opportunity_quality"), priority.get("knn_priority"), final.get("priority")),
            "reason": _first(final.get("primary_reason"), final.get("reason")),
            "scores_out_of_10": {
                "master": scores.get("master"),
                "entry": scores.get("entry"),
                "hold": scores.get("hold"),
                "tp": scores.get("tp"),
                "exit_risk": scores.get("exit_risk"),
                "trend_capacity_remaining": scores.get("trend_capacity_remaining"),
            },
            "quick_tp": _first(final.get("quick_tp"), final.get("take_profit"), risk.get("take_profit")),
            "quick_sl": _first(final.get("quick_sl"), final.get("stop_loss"), risk.get("stop_loss")),
        },
        "field_2_current_projection": {
            "current_price": _first(
                market.get("current_price"),
                market.get("last_close"),
                canonical.get("current_price"),
            ),
            "session": {
                "mode": session.get("session_mode"),
                "detected": session.get("detected_session"),
                "effective": session.get("selected_session"),
                "reason": session.get("reason_code"),
            },
            "forecast_horizons": _forecast_rows(state, canonical),
            "confidence_pct": _first(final.get("confidence_pct"), reliability.get("confidence_pct"), canonical.get("confidence_pct")),
            "reliability_pct": _first(reliability.get("score"), reliability.get("reliability_pct"), regime.get("reliability")),
            "uncertainty_pct": _first(uncertainty.get("combined"), canonical.get("uncertainty_pct")),
            "error_pct": _first(final.get("error_estimate_pct"), canonical.get("error_pct")),
        },
        "field_3_current_regime": {
            "production_major_regime": _first(regime.get("major_regime"), regime.get("current_regime")),
            "production_reliability_pct": _first(regime.get("reliability"), regime.get("regime_reliability")),
            "lower_rolling_24h": locked.get("lower"),
            "middle_locked_120h": locked.get("middle"),
            "higher_locked_600h": locked.get("higher"),
            "next_daily_review": locked.get("next_review_broker_time"),
            "hours_until_review": locked.get("hours_until_next_review"),
            "intraday_candidate_differs": locked.get("intraday_change_detected"),
        },
        "current_risk_plan": {
            "status": risk.get("status"),
            "recommended_lots": risk.get("recommended_lots"),
            "planned_risk_pct": risk.get("planned_risk_pct"),
            "planned_dollar_loss": risk.get("planned_dollar_loss"),
            "reason": risk.get("reason"),
        },
        "data_quality": {
            "status": _first(_mapping(canonical.get("data_quality")).get("status"), canonical.get("data_quality_status")),
            "score": _first(_mapping(canonical.get("data_quality")).get("score"), canonical.get("data_quality_score")),
        },
        "current_lunch_tables": _current_lunch_tables(state, canonical),
        "field_1_current_ai_summary": _clean(state.get("lunch_field1_ai_summary_20260628") or {}),
        **_field10_copy_sections(state, canonical),
    }
    return _clean(current)


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.5f}".rstrip("0").rstrip(".")
    return str(value)


def build_current_short_payload(
    state: MutableMapping[str, Any] | Mapping[str, Any],
    canonical: Mapping[str, Any] | None = None,
) -> tuple[str, PayloadStats]:
    """Build a readable, current-candle summary capped at 100 lines."""
    snapshot = build_current_snapshot(state, canonical)
    if not snapshot:
        text = "No current canonical generation is published."
        return text, payload_stats(text)

    lines: list[str] = ["ADX Quant Pro — CURRENT LUNCH IMPORTANT DATA"]

    def emit(prefix: str, value: Any, depth: int = 0) -> None:
        if len(lines) >= 100 or depth > 5:
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                if len(lines) >= 100:
                    break
                next_prefix = f"{prefix}.{key}" if prefix else str(key)
                emit(next_prefix, item, depth + 1)
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                if len(lines) >= 100:
                    break
                emit(f"{prefix}[{index + 1}]", item, depth + 1)
            return
        if _present(value):
            lines.append(f"{prefix}: {_format_value(value)}")

    # Order identity and current decision/projection/regime before table details.
    for section in ("identity", "field_1_current_decision", "field_2_current_projection",
                    "field_3_current_regime", "field_3_three_standard_quick_look",
                    "field_10_current_integrated", "protected_final_action",
                    "field_10_data_quality", "field_10_publication_status", "field_10_identity",
                    "current_risk_plan", "data_quality", "field_1_current_ai_summary", "current_lunch_tables"):
        emit(section, snapshot.get(section))
    text = "\n".join(lines[:100])
    return text, payload_stats(text)


def build_current_full_payload(
    state: MutableMapping[str, Any] | Mapping[str, Any],
    canonical: Mapping[str, Any] | None = None,
) -> tuple[str, PayloadStats]:
    snapshot = build_current_snapshot(state, canonical)
    if not snapshot:
        text = "No current canonical generation is published."
        return text, payload_stats(text)
    text = "ADX Quant Pro — CURRENT FIELDS 1–3 + FIELD 10\n" + json.dumps(snapshot, indent=2, ensure_ascii=False, default=str)
    return text, payload_stats(text)


__all__ = [
    "build_current_snapshot",
    "build_current_short_payload",
    "build_current_full_payload",
]

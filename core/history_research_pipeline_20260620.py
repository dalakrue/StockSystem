"""History-first research evidence transaction for one completed H1 generation.

This module is deliberately read-only with respect to protected trading logic.
It derives auditable evidence from an already completed canonical payload and
returns rows that are committed in the same SQLite transaction as the canonical
snapshot.  It never changes BUY/SELL/WAIT, TP, SL, weights, thresholds, or paths.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import time
import tracemalloc
from typing import Any, Mapping, MutableMapping, Sequence

import numpy as np
import pandas as pd

from core.history_identity_20260620 import canonical_history_identity
from core.history_evidence_store_20260620 import SPECS
from core.research_evidence_algorithms_20260620 import (
    TinyLFUCache,
    conformalized_quantile_interval,
    diebold_mariano_test,
    matrix_profile_current_matches,
    mint_reconcile_display_paths,
    pelt_mean_changes,
)

LOGIC_VERSION = "history-research-pipeline-20260620-v1"
PROTECTED_METRICS = (
    "master_score", "entry_score", "buy_score", "sell_score", "hold_safety",
    "tp_quality", "exit_risk", "trend_capacity_remaining", "market_quality",
    "forecast_agreement",
)


def _map(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if np.isfinite(number) else None
    except Exception:
        return None


def _time_column(frame: pd.DataFrame) -> str | None:
    for name in ("time", "timestamp", "datetime", "date", "record_time", "target_time"):
        if name in frame.columns:
            return name
    normalized = {str(c).strip().lower(): str(c) for c in frame.columns}
    return next((normalized[n] for n in ("time", "timestamp", "datetime", "date") if n in normalized), None)


def _completed_frame(frame: pd.DataFrame, canonical: Mapping[str, Any]) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    work = frame.copy(deep=False)
    tc = _time_column(work)
    if tc:
        parsed = pd.to_datetime(work[tc], errors="coerce", utc=True)
        completed = pd.to_datetime(
            canonical.get("latest_completed_candle_time")
            or canonical.get("latest_completed_h1")
            or _map(canonical.get("market")).get("latest_completed_candle_time"),
            errors="coerce", utc=True,
        )
        if pd.isna(completed):
            completed = parsed.max()
        work = work.loc[parsed.notna() & (parsed <= completed)].copy()
        work[tc] = parsed.loc[work.index]
        work = work.sort_values(tc)
    return work.tail(24 * 50).reset_index(drop=True)


def _row(
    canonical: Mapping[str, Any], *, condition: str = "", record_time: Any = None,
    target_time: Any = None, horizon: int | None = None, sample_count: int | None = None,
    settled_status: str = "UNSETTLED", payload: Mapping[str, Any] | None = None,
    metric_name: str | None = None, value_numeric: Any = None, value_text: Any = None,
    rank_value: int | None = None, lower_value: Any = None, median_value: Any = None,
    upper_value: Any = None, actual_value: Any = None, residual_value: Any = None,
    coverage_flag: bool | None = None, tab_name: str | None = None,
    renderer_name: str | None = None, row_count: int | None = None,
    browser_rows: int | None = None, payload_bytes: int | None = None,
    duration_ms: float | None = None, python_allocation_bytes: int | None = None,
    rss_mb: float | None = None, cache_status: str | None = None,
) -> dict[str, Any]:
    identity = canonical_history_identity(
        canonical, record_time=record_time, target_time=target_time, horizon=horizon,
        condition=condition, sample_count=sample_count, settled_status=settled_status,
        logic_version=LOGIC_VERSION,
    )
    return {
        **identity,
        "metric_name": metric_name,
        "value_numeric": _finite(value_numeric),
        "value_text": None if value_text is None else str(value_text),
        "rank_value": rank_value,
        "lower_value": _finite(lower_value),
        "median_value": _finite(median_value),
        "upper_value": _finite(upper_value),
        "actual_value": _finite(actual_value),
        "residual_value": _finite(residual_value),
        "coverage_flag": coverage_flag,
        "tab_name": tab_name,
        "renderer_name": renderer_name,
        "row_count": row_count,
        "browser_rows": browser_rows,
        "payload_bytes": payload_bytes,
        "duration_ms": duration_ms,
        "python_allocation_bytes": python_allocation_bytes,
        "rss_mb": rss_mb,
        "cache_status": cache_status,
        "payload": dict(payload or {}),
    }


def _horizon_number(key: Any, item: Mapping[str, Any]) -> int | None:
    for raw in (item.get("horizon_hours"), item.get("horizon"), key):
        try:
            text = str(raw).lower().replace("hours", "").replace("hour", "").replace("h", "").strip()
            return int(float(text))
        except Exception:
            continue
    return None


def _forecast_rows(canonical: Mapping[str, Any], settled: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    forecasts = _map(_map(canonical.get("forecasts")).get("horizons"))
    latest = pd.to_datetime(canonical.get("latest_completed_candle_time"), errors="coerce", utc=True)
    rows: list[dict[str, Any]] = []
    parsed: dict[int, dict[str, Any]] = {}
    for key, raw in forecasts.items():
        item = _map(raw)
        h = _horizon_number(key, item)
        if h not in {1, 2, 3, 4, 5, 6}:
            continue
        point = _finite(item.get("point_forecast") or item.get("median") or item.get("forecast_close"))
        lower = _finite(item.get("lower_bound") or item.get("lower"))
        upper = _finite(item.get("upper_bound") or item.get("upper"))
        ordered = [v for v in (lower, point, upper) if v is not None]
        if len(ordered) == 3:
            lower, point, upper = sorted(ordered)
        target = latest + pd.Timedelta(hours=h) if not pd.isna(latest) else None
        actual = None
        status = "PENDING"
        if isinstance(settled, pd.DataFrame) and not settled.empty:
            hcol = next((c for c in ("horizon", "horizon_hours", "Horizon") if c in settled), None)
            tcol = next((c for c in ("target_time", "Target Time", "target") if c in settled), None)
            acol = next((c for c in ("actual_close", "actual", "Actual Close") if c in settled), None)
            subset = settled
            if hcol:
                subset = subset[pd.to_numeric(subset[hcol], errors="coerce") == h]
            if tcol and target is not None:
                t = pd.to_datetime(subset[tcol], errors="coerce", utc=True)
                subset = subset.loc[t == target]
            if acol and not subset.empty:
                vals = pd.to_numeric(subset[acol], errors="coerce").dropna()
                if not vals.empty and target is not None and target <= latest:
                    actual = float(vals.iloc[-1]); status = "SETTLED"
        residual = None if actual is None or point is None else actual - point
        coverage = None if actual is None or lower is None or upper is None else lower <= actual <= upper
        payload = {
            "direction": item.get("direction"), "reliability": item.get("reliability"),
            "band_width": None if lower is None or upper is None else upper - lower,
            "path_disagreement": item.get("path_disagreement"),
            "model_contributor_weights": item.get("model_contributor_weights") or item.get("weights"),
            "settlement_or_censorship": status,
        }
        rows.append(_row(
            canonical, condition=f"H+{h}", target_time=target, horizon=h,
            settled_status=status, payload=payload, metric_name="forecast_close",
            lower_value=lower, median_value=point, upper_value=upper,
            actual_value=actual, residual_value=residual, coverage_flag=coverage,
        ))
        parsed[h] = {"point": point, "lower": lower, "upper": upper, "target": target, "item": item}
    return rows, parsed


def _extract_paths(canonical: Mapping[str, Any], calibrated_bundle: Mapping[str, Any] | None) -> dict[str, list[float]]:
    paths: dict[str, list[float]] = {}
    bundle = _map(calibrated_bundle)
    for name in ("red", "yellow", "blue"):
        raw = bundle.get(name)
        if isinstance(raw, pd.DataFrame) and not raw.empty:
            candidates = [c for c in raw.columns if "path" in str(c).lower() or "price" in str(c).lower() or "close" in str(c).lower()]
            if candidates:
                values = pd.to_numeric(raw[candidates[-1]], errors="coerce").dropna().tolist()
                if values:
                    paths[name] = [float(v) for v in values[:6]]
        elif isinstance(raw, Mapping):
            seq = raw.get("path") or raw.get(f"{name}_path") or raw.get("values")
            if isinstance(seq, Sequence) and not isinstance(seq, (str, bytes)):
                vals = pd.to_numeric(pd.Series(list(seq)), errors="coerce").dropna().tolist()
                if vals:
                    paths[name] = [float(v) for v in vals[:6]]
    probabilistic = _map(canonical.get("probabilistic_projection"))
    for name in ("red", "yellow", "blue"):
        if name in paths:
            continue
        raw = probabilistic.get(name) or probabilistic.get(f"{name}_path")
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            vals = pd.to_numeric(pd.Series(list(raw)), errors="coerce").dropna().tolist()
            if vals:
                paths[name] = [float(v) for v in vals[:6]]
    return paths


def build_history_research_transaction(
    canonical: Mapping[str, Any], *, completed_h1: pd.DataFrame,
    priority_table: pd.DataFrame | None = None, settled_predictions: pd.DataFrame | None = None,
    calibrated_bundle: Mapping[str, Any] | None = None, previous: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Build all affected history rows once, before atomic publication."""
    started = time.perf_counter()
    tracing_was_active = tracemalloc.is_tracing()
    if not tracing_was_active:
        tracemalloc.start()
    output = dict(canonical)
    frame = _completed_frame(completed_h1, output)
    settled = settled_predictions if isinstance(settled_predictions, pd.DataFrame) else pd.DataFrame()
    bundle: dict[str, list[dict[str, Any]]] = {spec.name: [] for spec in SPECS}
    completed_time = output.get("latest_completed_candle_time")
    if not completed_time and not frame.empty:
        tc = _time_column(frame)
        completed_time = frame[tc].iloc[-1] if tc else None
        if completed_time is None and isinstance(frame.index, pd.DatetimeIndex) and len(frame.index):
            completed_time = frame.index.max()
        if completed_time is not None:
            output["latest_completed_candle_time"] = pd.to_datetime(completed_time, utc=True).isoformat()

    # FIELD 1: protected values are copied verbatim as historical evidence.
    final = _map(output.get("final_decision")); regime = _map(output.get("regime"))
    metric_payload = {name: output.get(name) for name in PROTECTED_METRICS}
    metric_payload.update({"decision": final.get("final_decision"), "direction": final.get("directional_market_view")})
    bundle["full_metric_overall_history"].append(_row(output, payload=metric_payload, metric_name="full_metric", value_numeric=output.get("master_score")))
    for index, name in enumerate(PROTECTED_METRICS, 1):
        bundle["protected_decision_history"].append(_row(output, condition=name, payload={"protected_index": index}, metric_name=name, value_numeric=output.get(name)))
    decision11 = _map(output.get("medium_standard_regime_bias"))
    bundle["decision11_support_history"].append(_row(output, payload=decision11, metric_name="medium_standard_regime_bias", value_numeric=decision11.get("score"), value_text=decision11.get("decision")))
    prior = _map(previous); prior_final = _map(prior.get("final_decision"))
    change_payload = {
        "previous_calculation_id": prior.get("canonical_calculation_id") or prior.get("run_id"),
        "previous_decision": prior_final.get("final_decision"), "current_decision": final.get("final_decision"),
        "protected_logic_changed": False,
    }
    bundle["decision_change_audit_history"].append(_row(output, payload=change_payload, metric_name="decision_changed", value_numeric=float(change_payload["previous_decision"] not in (None, change_payload["current_decision"]))))
    dq = _map(output.get("data_quality"))
    bundle["input_data_quality_history"].append(_row(output, payload={**dq, "completed_rows": len(frame)}, metric_name="data_quality", value_numeric=dq.get("score")))
    for name in PROTECTED_METRICS:
        value = output.get(name)
        bundle["metric_availability_history"].append(_row(output, condition=name, payload={"available": value is not None}, metric_name=name, value_numeric=0 if value is None else 1))

    # FIELD 2: ledger, original paths, display-only reconciliation and calibration.
    forecast_rows, forecasts = _forecast_rows(output, settled)
    bundle["powerbi_prediction_ledger"].extend(forecast_rows)
    source_paths = _extract_paths(output, calibrated_bundle)
    close_col = next((c for c in ("close", "Close", "CLOSE") if c in frame), None)
    anchor = float(pd.to_numeric(frame[close_col], errors="coerce").dropna().iloc[-1]) if close_col and not frame.empty else 0.0
    for source_name, values in source_paths.items():
        for h, value in enumerate(values[:6], 1):
            bundle["powerbi_source_path_history"].append(_row(output, condition=source_name, horizon=h, target_time=pd.to_datetime(completed_time, utc=True)+pd.Timedelta(hours=h), payload={"protected_original": True}, metric_name="source_path", median_value=value))
    reconciliation = mint_reconcile_display_paths(source_paths, anchor_price=anchor) if source_paths and anchor else {"status": "INSUFFICIENT DATA", "original_paths": source_paths, "reconciled_path": []}
    for h, value in enumerate(reconciliation.get("reconciled_path") or [], 1):
        originals = {name: vals[h-1] for name, vals in source_paths.items() if len(vals) >= h}
        delta = value - float(np.mean(list(originals.values()))) if originals else 0.0
        bundle["powerbi_reconciled_path_history"].append(_row(output, condition="DISPLAY_ONLY", horizon=h, target_time=pd.to_datetime(completed_time, utc=True)+pd.Timedelta(hours=h), payload={"original_values": originals, "weights": reconciliation.get("weights"), "protected_paths_changed": False}, metric_name="reconciled_display_path", median_value=value, residual_value=delta))
    for row in forecast_rows:
        if row.get("settled_status") == "SETTLED":
            settlement = dict(row); settlement["payload"] = {**_map(row.get("payload")), "outcome": "OBSERVED"}
            bundle["powerbi_forecast_settlement_history"].append(settlement)

    # CQR is validation only and remains separate by horizon.
    cqr: dict[str, Any] = {}
    for h, values in forecasts.items():
        if all(values.get(k) is not None for k in ("point", "lower", "upper")):
            cqr[str(h)] = conformalized_quantile_interval(settled, point=values["point"], lower=values["lower"], upper=values["upper"], horizon=h)

    # FIELD 3: regime, standards, PELT evidence and conflicts.
    bundle["regime_overall_history"].append(_row(output, payload=regime, metric_name="major_regime", value_text=regime.get("major_regime")))
    for level, aliases in {"lower": ("lower_standard_regime", "lower"), "medium": ("middle_standard_regime", "medium"), "higher": ("higher_standard_regime", "higher")}.items():
        value = next((regime.get(a) for a in aliases if regime.get(a) is not None), None)
        bundle["regime_standard_history"].append(_row(output, condition=level, payload={"standard": level}, metric_name="regime_standard", value_text=value))
    bundle["regime_transition_reliability_history"].append(_row(output, payload={"transition_probability": regime.get("transition_probability"), "reliability": regime.get("reliability")}, metric_name="transition_reliability", value_numeric=regime.get("reliability")))
    bundle["regime_alpha_delta_history"].append(_row(output, payload={"alpha": regime.get("alpha"), "delta": regime.get("delta"), "delta_acceleration": regime.get("delta_acceleration")}, metric_name="alpha_delta", value_numeric=regime.get("delta")))
    conflict = _map(output.get("conflict")) or _map(output.get("regime_prediction_conflict"))
    for name, value in (conflict.items() if conflict else [("overall", final.get("conflict_warning"))]):
        bundle["regime_conflict_history"].append(_row(output, condition=str(name), payload={"value": value}, metric_name="regime_conflict", value_text=value))

    pelt_results: dict[str, Any] = {}
    if close_col and len(frame) >= 24:
        close = pd.to_numeric(frame[close_col], errors="coerce")
        returns = close.pct_change().dropna()
        high_col = next((c for c in ("high", "High", "HIGH") if c in frame), None)
        low_col = next((c for c in ("low", "Low", "LOW") if c in frame), None)
        signals = {"returns": returns, "volatility": returns.rolling(12).std().dropna()}
        if high_col and low_col:
            signals["range"] = (pd.to_numeric(frame[high_col], errors="coerce") - pd.to_numeric(frame[low_col], errors="coerce")).dropna()
        tc = _time_column(frame)
        for signal, series in signals.items():
            result = pelt_mean_changes(series)
            pelt_results[signal] = result
            for cp in result.get("changepoints") or []:
                rt = frame[tc].iloc[min(int(cp), len(frame)-1)] if tc else completed_time
                bundle["regime_changepoint_history"].append(_row(output, condition=signal, record_time=rt, sample_count=result.get("sample_count"), payload={"penalty": result.get("penalty"), "direction_created": False}, metric_name="changepoint", rank_value=int(cp)))
    bundle["regime_duration_history"].append(_row(output, condition=str(regime.get("major_regime") or "UNKNOWN"), payload={"days_since_change": regime.get("days_since_change") or regime.get("days_since_last_change"), "expected_days": regime.get("expected_days")}, metric_name="regime_duration", value_numeric=regime.get("days_since_change") or regime.get("days_since_last_change")))

    # FIELD 4A: matrix-profile matches, motifs, discords, outcomes.
    mp = matrix_profile_current_matches(pd.to_numeric(frame[close_col], errors="coerce").dropna().tolist()) if close_col else {"windows": {}, "motifs": [], "discords": []}
    tc = _time_column(frame)
    for window, result in _map(mp.get("windows")).items():
        matches = result.get("matches") or []
        bundle["similar_day_query_history"].append(_row(output, condition=f"window_{window}", sample_count=result.get("candidate_count"), payload={k:v for k,v in result.items() if k != "matches"}, metric_name="matrix_profile_query", value_text=result.get("status")))
        distances = [m.get("distance") for m in matches if m.get("distance") is not None]
        for rank, match in enumerate(matches, 1):
            start = int(match.get("start_index", 0)); end = int(match.get("end_index", start))
            rt = frame[tc].iloc[end] if tc and end < len(frame) else completed_time
            bundle["similar_day_ranked_match_history"].append(_row(output, condition=f"window_{window}", record_time=rt, rank_value=rank, payload=match, metric_name="distance", value_numeric=match.get("distance")))
            for horizon in (1, 2, 3, 6):
                if close_col and end + horizon < len(frame):
                    base = _finite(frame[close_col].iloc[end]); future = _finite(frame[close_col].iloc[end+horizon])
                    if base and future is not None:
                        segment = pd.to_numeric(frame[close_col].iloc[end+1:end+horizon+1], errors="coerce").dropna()
                        mfe = float(segment.max()-base) if not segment.empty else None
                        mae = float(segment.min()-base) if not segment.empty else None
                        bundle["similar_day_outcome_history"].append(_row(output, condition=f"window_{window}_rank_{rank}", record_time=rt, horizon=horizon, settled_status="OBSERVED", payload={"mfe": mfe, "mae": mae}, metric_name="historical_outcome", value_numeric=future-base))
        bundle["match_quality_calibration_history"].append(_row(output, condition=f"window_{window}", sample_count=len(matches), payload={"distance_distribution": distances}, metric_name="median_distance", value_numeric=np.median(distances) if distances else None))
    for rank, motif in enumerate(mp.get("motifs") or [], 1):
        bundle["motif_history"].append(_row(output, condition=f"window_{motif.get('window')}", rank_value=rank, payload=motif, metric_name="motif_distance", value_numeric=motif.get("distance")))
    for rank, discord in enumerate(mp.get("discords") or [], 1):
        bundle["discord_history"].append(_row(output, condition=f"window_{discord.get('window')}", rank_value=rank, payload=discord, metric_name="discord_distance", value_numeric=discord.get("distance")))

    # FIELD 4B: priorities remain separate from Similar-Day state/calculation.
    priority = priority_table if isinstance(priority_table, pd.DataFrame) else pd.DataFrame()
    for rank, (_, raw) in enumerate(priority.head(48).iterrows(), 1):
        item = raw.to_dict(); rt = item.get(_time_column(priority)) if _time_column(priority) else completed_time
        base = _row(output, condition=str(item.get("Priority") or item.get("priority_label") or "candidate"), record_time=rt, rank_value=rank, payload=item, metric_name="priority_score", value_numeric=item.get("Priority Score") or item.get("priority_score"))
        bundle["canonical_priority_history"].append(base)
        bundle["knn_rank_history"].append({**base, "payload": {**item, "ranking_method": "KNN", "read_only": True}})
        bundle["greedy_rank_history"].append({**base, "payload": {**item, "ranking_method": "GREEDY", "read_only": True}})
    reliability = _map(output.get("reliability")) or _map(output.get("trust_validation"))
    bundle["reliability_conflict_history"].append(_row(output, condition="overall", payload={"reliability": reliability, "conflict": conflict}, metric_name="reliability", value_numeric=reliability.get("score") or reliability.get("calibrated_score_0_100")))
    components = {"forecasts": bool(forecasts), "priority": not priority.empty, "regime": bool(regime), "similar_day": bool(_map(output.get("similar_day_intelligence"))), "settled_predictions": not settled.empty}
    for component, available in components.items():
        bundle["component_availability_history"].append(_row(output, condition=component, payload={"available": available}, metric_name="component_available", value_numeric=int(available)))
    explanation = {"protected_decision": final.get("final_decision"), "direction_reversed": False, "components": components, "research_use": "validation/display only"}
    bundle["combined_evidence_explanation_history"].append(_row(output, payload=explanation, metric_name="combined_evidence", value_text="VALIDATION ONLY"))
    bundle["canonical_generation_change_history"].append(_row(output, payload={**change_payload, "previous_generation": prior.get("calculation_generation"), "current_generation": output.get("calculation_generation")}, metric_name="generation_change", value_numeric=(output.get("calculation_generation") or 0)-(prior.get("calculation_generation") or 0)))

    # DM validation by horizon against any named benchmark columns when aligned.
    dm: dict[str, Any] = {}
    if not settled.empty:
        for h in (1, 2, 3, 6):
            actual_col = next((c for c in ("actual_close", "actual", "y_true") if c in settled), None)
            pred_col = next((c for c in ("prediction", "point_forecast", "predicted_close") if c in settled), None)
            benchmark_col = next((c for c in ("benchmark_prediction", "naive_prediction", "benchmark") if c in settled), None)
            hcol = next((c for c in ("horizon", "horizon_hours") if c in settled), None)
            subset = settled
            if hcol: subset = subset[pd.to_numeric(subset[hcol], errors="coerce") == h]
            if actual_col and pred_col and benchmark_col:
                actual = pd.to_numeric(subset[actual_col], errors="coerce")
                dm[str(h)] = diebold_mariano_test((actual-pd.to_numeric(subset[pred_col], errors="coerce"))**2, (actual-pd.to_numeric(subset[benchmark_col], errors="coerce"))**2, horizon=h)
            else:
                dm[str(h)] = {"status": "INSUFFICIENT DATA", "sample_count": 0, "horizon": h}

    # SYSTEM diagnostics. No secret values or cache keys are persisted.
    cache = TinyLFUCache(max_entries=16, max_bytes=2_000_000)
    for key, value in (("matrix_profile", mp), ("pelt", pelt_results), ("reconciliation", reconciliation)):
        encoded = json.dumps(value, default=str, separators=(",", ":")).encode("utf-8")
        cache.get(key); cache.put(key, value, size_bytes=len(encoded)); cache.get(key)
    cache_diag = cache.diagnostics()
    bundle["cache_diagnostics_history"].append(_row(output, condition="research_display_artifacts", payload=cache_diag, metric_name="cache_hit_ratio", value_numeric=cache_diag.get("hit_ratio"), cache_status="MEASURED"))

    current, peak = tracemalloc.get_traced_memory()
    if not tracing_was_active:
        tracemalloc.stop()
    duration = (time.perf_counter()-started)*1000.0
    rows_written = sum(len(v) for v in bundle.values())
    bundle["performance_history"].append(_row(
        output, condition="history_research_transaction",
        tab_name="SETTINGS", renderer_name="build_history_research_transaction",
        row_count=rows_written, browser_rows=0, payload_bytes=0,
        duration_ms=duration, python_allocation_bytes=int(peak), cache_status="MISS",
        payload={"python_current_bytes": current, "python_peak_bytes": peak, "rows_written": rows_written},
        metric_name="duration_ms", value_numeric=duration,
    ))

    summary = {
        "version": LOGIC_VERSION,
        "calculation_id": output.get("canonical_calculation_id") or output.get("run_id"),
        "tables_affected": {name: len(rows) for name, rows in bundle.items() if rows},
        "total_rows": sum(len(rows) for rows in bundle.values()),
        "matrix_profile": {k: {"status": v.get("status"), "matches": len(v.get("matches") or [])} for k,v in _map(mp.get("windows")).items()},
        "pelt": {k: {"status": v.get("status"), "changepoints": len(v.get("changepoints") or [])} for k,v in pelt_results.items()},
        "conformalized_quantile_regression": cqr,
        "mint_display_reconciliation": reconciliation,
        "diebold_mariano": dm,
        "cache": cache_diag,
        "duration_ms": round(duration, 3),
        "python_current_bytes": int(current),
        "python_peak_bytes": int(peak),
        "protected_outputs_changed": False,
        "event_time_watermark": output.get("latest_completed_candle_time"),
        "atomic_publication_required": True,
    }
    output["history_research_evidence_20260620"] = summary
    return output, {name: rows for name, rows in bundle.items() if rows}, summary


__all__ = ["build_history_research_transaction", "LOGIC_VERSION", "PROTECTED_METRICS"]

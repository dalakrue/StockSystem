"""Repair publication aliases after a successful Settings run.

This module performs no trading calculation. It only publishes identity and
Table-1 display inputs from already-calculated metric/OHLC objects when legacy
publishers completed but failed to bind the canonical aliases consumed by Lunch.
"""
from __future__ import annotations
from hashlib import sha256
from typing import Any, Mapping, MutableMapping
import pandas as pd

from core.generation_identity_20260707 import generation_id, numeric_generation

ALIASES=(
    "canonical_decision_result_20260617","last_valid_canonical_decision_result_20260617",
    "canonical_decision_result","canonical_result_20260617","canonical_result",
)

def _mapping(v: Any) -> dict[str, Any]:
    return dict(v) if isinstance(v, Mapping) else {}

def _utc(value: Any) -> pd.Timestamp | None:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return pd.Timestamp(parsed) if pd.notna(parsed) else None

def _canonical_time(value: Mapping[str, Any]) -> pd.Timestamp | None:
    market = value.get("market") if isinstance(value.get("market"), Mapping) else {}
    for item in (value.get("latest_completed_candle_time"), market.get("latest_completed_candle_time"), value.get("broker_candle_time")):
        stamp = _utc(item)
        if stamp is not None:
            return stamp.floor("h")
    return None

def _metric(state: Mapping[str, Any]) -> Mapping[str, Any]:
    candidates: list[tuple[pd.Timestamp | None, int, Mapping[str, Any]]] = []
    keys = (
        "lunch_metric_result_cache", "full_metric_result_cache_20260618",
        "lunch_metric_result_published_20260618", "lunch_metric_result_20260619",
        "eurusd_h1_matrix_result", "eurusd_h1_matrix_export",
    )
    for priority, key in enumerate(keys):
        value = state.get(key)
        if isinstance(value, Mapping) and value.get("ok", True) is not False:
            candidates.append((_utc(_history_time(value)), priority, value))
    authority = state.get("full_metric_authority_20260618")
    if isinstance(authority, Mapping):
        value = authority.get("metric_result") or authority.get("source_result")
        if isinstance(value, Mapping) and value.get("ok", True) is not False:
            candidates.append((_utc(_history_time(value)), len(keys), value))
    if not candidates:
        return {}
    # A later completed H1 always wins. Stable priority breaks ties only.
    return max(candidates, key=lambda item: (item[0] or pd.Timestamp.min.tz_localize("UTC"), -item[1]))[2]

def _frame(state: Mapping[str, Any]) -> pd.DataFrame:
    candidates: list[tuple[pd.Timestamp | None, int, pd.DataFrame]] = []
    keys = (
        "canonical_completed_ohlc_df_20260617", "last_df", "dv_pp_df", "custom_h1_df",
        "home_df", "prepared_lunch_df", "lunch_visual_df", "lunch_5layer_powerbi_df",
    )
    for priority, key in enumerate(keys):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            candidates.append((_utc(_latest_time(value)), priority, value))
    if not candidates:
        return pd.DataFrame()
    return max(candidates, key=lambda item: (item[0] or pd.Timestamp.min.tz_localize("UTC"), -item[1]))[2]

def _latest_time(frame: pd.DataFrame):
    if frame.empty: return None
    names={str(c).strip().lower().replace("_"," "):c for c in frame.columns}
    col=next((names.get(k) for k in ("time","datetime","timestamp","date") if names.get(k) is not None),None)
    parsed=pd.to_datetime(frame[col],errors="coerce",utc=True) if col is not None else pd.to_datetime(frame.index,errors="coerce",utc=True)
    valid=parsed.dropna()
    return pd.Timestamp(valid.max()).isoformat() if len(valid) else None

def _history_time(metric: Mapping[str, Any]):
    frames=[]
    history=metric.get("history")
    if isinstance(history,pd.DataFrame) and not history.empty: frames.append(history)
    factors=metric.get("history_by_factor")
    if isinstance(factors,Mapping): frames.extend(v for v in factors.values() if isinstance(v,pd.DataFrame) and not v.empty)
    latest: list[pd.Timestamp] = []
    for frame in frames:
        col=next((c for c in ("event_time_utc","Broker Candle Time","broker_candle_time","Completed Broker Candle","time","datetime","DateTime","timestamp") if c in frame.columns),None)
        if col is None and isinstance(frame.index, pd.DatetimeIndex):
            parsed = pd.to_datetime(frame.index, errors="coerce", utc=True)
        elif col is not None:
            parsed = pd.to_datetime(frame[col],errors="coerce",utc=True)
        else:
            continue
        valid = pd.Series(parsed).dropna()
        if len(valid): latest.append(pd.Timestamp(valid.max()))
    return max(latest).isoformat() if latest else None

def ensure_field1_publication(state: MutableMapping[str, Any], status: MutableMapping[str, Any] | None=None) -> dict[str, Any]:
    from core.canonical_lookup_20260626 import resolve_canonical
    existing=resolve_canonical(state)
    status=_mapping(status or state.get("settings_run_status_20260617"))
    metric=_metric(state)
    source_stamp = _utc(_latest_time(_frame(state)))
    metric_stamp = _utc(_history_time(metric)) if metric else None
    existing_stamp = _canonical_time(existing) if existing else None
    # A canonical generation is reusable only when it is not older than the
    # loaded completed H1 source.  If the just-calculated metric history reaches
    # the new candle, rebind identity from that publication; otherwise explicitly
    # demand a calculation instead of silently restoring the stale generation.
    source_hour = source_stamp.floor("h") if source_stamp is not None else None
    metric_hour = metric_stamp.floor("h") if metric_stamp is not None else None
    if existing and (source_hour is None or existing_stamp is None or source_hour <= existing_stamp):
        return {"ok":True,"repaired":False,"canonical":existing}
    if existing and source_hour is not None and existing_stamp is not None and source_hour > existing_stamp:
        if metric_hour is None or metric_hour < source_hour:
            return {
                "ok": False, "repaired": False, "status": "STALE_CANONICAL_RECALC_REQUIRED",
                "reason": "Loaded completed H1 is newer than both canonical and Field 1 metric publication.",
                "source_candle": source_hour.isoformat(), "canonical_candle": existing_stamp.isoformat(),
                "metric_candle": metric_hour.isoformat() if metric_hour is not None else None,
            }
    if not metric:
        return {"ok":False,"reason":"no calculated Field 1 metric result"}
    candle=_latest_time(_frame(state)) or _history_time(metric) or status.get("latest_completed_candle_time")
    run_id=status.get("run_id") or _mapping(status.get("canonical")).get("run_id")
    raw_generation=(
        status.get("calculation_generation")
        or _mapping(status.get("canonical")).get("calculation_generation")
        or state.get("successful_calculation_generation_20260617")
        or state.get("canonical_calculation_generation_20260617")
    )
    raw_generation_id=(
        status.get("generation_id")
        or _mapping(status.get("canonical")).get("generation_id")
    )
    if not candle:
        return {"ok":False,"reason":"successful outputs exist but completed candle is incomplete"}
    seed=sha256((str(candle)+"|"+str(sorted(metric.keys()))+"|"+str(len(_frame(state)))).encode()).hexdigest()
    run_id = str(run_id or ("FIELD1-" + seed[:20]))
    # ``calculation_generation`` is a strict positive integer contract.  Keep
    # the historical GEN-* label only in ``generation_id`` so publication and
    # SQLite validation can never fail with ``invalid literal for int()``.
    if raw_generation in (None, ""):
        try:
            from core.canonical_runtime_20260617 import proposed_generation
            numeric = int(proposed_generation(state))
        except Exception:
            numeric = numeric_generation(seed[20:36], default=1)
    else:
        numeric = numeric_generation(raw_generation, default=1)
    readable_generation = generation_id(raw_generation_id or ("GEN-" + seed[20:36]), fallback_seed=seed)
    digest=sha256((str(run_id)+"|"+str(numeric)+"|"+str(candle)).encode()).hexdigest()
    scores=_mapping(metric.get("scores")); decision=str(scores.get("Decision") or scores.get("Direction") or "WAIT")
    canonical={
        "run_id":str(run_id),"canonical_calculation_id":str(run_id),
        "generation_id":readable_generation,"calculation_generation":numeric,
        "symbol":str(state.get("symbol") or "EURUSD"),"timeframe":str(state.get("timeframe") or "H1"),
        "broker_candle_time":candle,"latest_completed_candle_time":candle,
        "source_snapshot_hash":digest,"snapshot_hash":digest,
        "source_signature":"rebound-existing-calculated-outputs:"+digest[:24],
        "full_metric_direction":decision,
        "final_decision":{"final_decision":decision},
        "metadata":{"publication_repair":"identity rebound from successful calculated outputs; no calculation performed"},
    }
    for key in ALIASES: state[key]=canonical
    state["successful_calculation_generation_20260617"] = numeric
    state["canonical_calculation_generation_20260617"] = numeric
    state["lunch_metric_result_cache"]=metric
    state["full_metric_result_cache_20260618"]=metric
    if isinstance(status,MutableMapping):
        status.setdefault("canonical",{}).update({
            "ok":True,"run_id":str(run_id),
            "generation_id":readable_generation,"calculation_generation":numeric,
        })
        status["field1_publication_bridge_20260626"]={"ok":True,"repaired":True}
        state["settings_run_status_20260617"]=status
    return {"ok":True,"repaired":True,"canonical":canonical}

__all__=["ensure_field1_publication"]

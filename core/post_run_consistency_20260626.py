"""Post-publication consistency repair for one immutable canonical generation.

This module performs no trading calculation and creates no synthetic forecast or
history. It only normalizes identity aliases, binds already-built component
caches to the active generation, and publishes the current completed-candle
confirmation row from already-published canonical values.
"""
from __future__ import annotations
from typing import Any, Mapping, MutableMapping
import pandas as pd

from core.generation_identity_20260707 import generation_id, numeric_generation

IDENTITY_ALIASES=(
    "canonical_decision_result_20260617","last_valid_canonical_decision_result_20260617",
    "canonical_decision_result","canonical_result_20260617","canonical_result",
)

def _m(v: Any)->dict[str,Any]:
    return dict(v) if isinstance(v, Mapping) else {}

def _first(m: Mapping[str,Any], *keys: str):
    for k in keys:
        v=m.get(k)
        if v not in (None,""): return v
    return None

def _current_confirmation(c: Mapping[str,Any])->dict[str,Any]:
    final=_m(c.get("final_decision")); metrics=_m(c.get("metrics")); rel=_m(c.get("reliability")); market=_m(c.get("market"))
    candle=_first(c,"completed_broker_candle","broker_candle_time","latest_completed_candle_time","completed_candle_utc") or _first(market,"broker_candle_time","latest_completed_candle_time")
    row={
      "broker_candle_time":candle,
      "run_id":_first(c,"run_id","canonical_calculation_id"),
      "generation_id":_first(c,"generation_id","calculation_generation"),
      "final_decision":_first(final,"final_decision","decision") or _first(c,"full_metric_direction","decision") or "WAIT",
      "master_decision":_first(final,"final_decision","decision") or _first(c,"full_metric_direction","decision") or "WAIT",
      "direction_confirmation_decision":_first(c,"direction_confirmation_decision","one_hour_direction") or _first(final,"final_decision","decision") or "WAIT",
      "decision_confidence":_first(final,"confidence","decision_confidence") or _first(rel,"confidence","reliability_pct"),
      "decision_reliability":_first(rel,"reliability_pct","calibrated_reliability","confidence"),
      "uncertainty_percentage":_first(c,"uncertainty_percentage","uncertainty_pct"),
      "error_percentage":_first(c,"error_percentage","error_pct"),
      "settlement_status":"PENDING",
      "fx_session":_first(c,"current_session","session") or _first(market,"session"),
    }
    # Copy only existing published metric values. Missing remains absent/N/A.
    names=("entry_strength_score","sell_pressure_score","buy_pressure_score","net_pressure_score",
           "pullback_readiness_score","m1_confirmation_score","hold_safety_score","tp_quality_score",
           "master_decision_score","direction_confirmation_score")
    for name in names:
        val=_first(c,name) or _first(metrics,name)
        if val is not None: row[name]=val
    for name in ("entry_strength_decision","sell_pressure_decision","buy_pressure_decision","pressure_decision",
                 "pullback_readiness_decision","m1_confirmation_decision","hold_safety_decision","tp_quality_decision"):
        val=_first(c,name) or _first(metrics,name)
        if val is not None: row[name]=val
    return {k:v for k,v in row.items() if v is not None}

def enforce_post_run_consistency(state: MutableMapping[str,Any], status: MutableMapping[str,Any]|None=None)->dict[str,Any]:
    from core.canonical_lookup_20260626 import resolve_canonical
    canonical=resolve_canonical(state)
    if not canonical:
        return {"ok":False,"reason":"no valid canonical generation"}
    c=dict(canonical)
    run_id=str(_first(c,"run_id","canonical_calculation_id") or "")
    raw_generation_id=_first(c,"generation_id")
    raw_generation=_first(c,"calculation_generation","generation", "generation_id")
    generation_number=numeric_generation(raw_generation, default=1)
    generation_label=generation_id(raw_generation_id or generation_number, fallback_seed=run_id)
    candle=_first(c,"completed_broker_candle","broker_candle_time","latest_completed_candle_time","completed_candle_utc")
    if not (run_id and generation_number and candle):
        return {"ok":False,"reason":"canonical identity incomplete"}
    c["run_id"]=run_id; c["canonical_calculation_id"]=run_id
    c["generation_id"]=generation_label; c["calculation_generation"]=generation_number
    c["completed_broker_candle"]=candle; c["broker_candle_time"]=candle; c["latest_completed_candle_time"]=candle; c["latest_completed_h1_utc"]=candle
    c.setdefault("symbol","EURUSD"); c.setdefault("timeframe","H1")
    try:
        from core.quick_source_signature_20260626 import build_quick_source_signature, SIGNATURE_KEY
        sig=build_quick_source_signature(state,c)
        state[SIGNATURE_KEY]=sig
        c["source_signature"]=sig.get("source_signature")
        c["source_snapshot_hash"]=c.get("source_snapshot_hash") or c.get("snapshot_hash") or sig.get("ohlc_digest")
        c["snapshot_hash"]=c.get("source_snapshot_hash")
    except Exception:
        pass
    for key in IDENTITY_ALIASES: state[key]=c
    # Bind existing PowerBI outputs to this generation. Never synthesize a path.
    bundle=state.get("powerbi_calibrated_bundle_20260617")
    if isinstance(bundle, Mapping):
        b=dict(bundle); summary=_m(b.get("summary"))
        for target in (b,summary):
            target["run_id"]=run_id; target["generation_id"]=generation_label; target["calculation_generation"]=generation_number
            target["snapshot_hash"]=c.get("snapshot_hash"); target["source_snapshot_hash"]=c.get("source_snapshot_hash"); target["source_signature"]=c.get("source_signature"); target["symbol"]=c.get("symbol"); target["timeframe"]=c.get("timeframe"); target["completed_broker_candle"]=candle; target["broker_candle_time"]=candle; target["latest_completed_candle_time"]=candle
        b["summary"]=summary; state["powerbi_calibrated_bundle_20260617"]=b
    # Publish current confirmation from current canonical facts when archive is empty.
    payload=_m(state.get("one_hour_direction_confirmation_20260626"))
    payload["current"]=_current_confirmation(c)
    payload.setdefault("history",pd.DataFrame())
    payload.setdefault("score_scales",{})
    payload["run_id"]=run_id; payload["generation_id"]=generation_label; payload["calculation_generation"]=generation_number; payload["broker_candle_time"]=candle
    state["one_hour_direction_confirmation_20260626"]=payload
    state["successful_calculation_generation_20260617"] = generation_number
    state["canonical_calculation_generation_20260617"] = generation_number
    result={"ok":True,"run_id":run_id,"generation_id":generation_label,"calculation_generation":generation_number,"broker_candle_time":str(candle),"powerbi_bound":isinstance(bundle,Mapping)}
    if isinstance(status,MutableMapping):
        status["post_run_consistency_20260626"]=result
        state["settings_run_status_20260617"]=status
    return result

__all__=["enforce_post_run_consistency"]

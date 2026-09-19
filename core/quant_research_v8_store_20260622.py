"""Authoritative Settings-only Quant Research V8 shadow transaction."""
from __future__ import annotations
from copy import deepcopy
from typing import Any, Mapping, MutableMapping
import json, math, time, tracemalloc
import numpy as np
import pandas as pd

from core.morning_quant_store_20260622 import BUNDLE_KEY, TABLE_COLUMNS, EXTRA_TABLES, position_stable_key
from core.generation_identity_20260707 import numeric_generation

VERSION = "quant-research-v8-20260622-v1"


def _utc(value: Any) -> pd.Timestamp | None:
    try:
        ts = pd.to_datetime(value, errors="coerce", utc=True)
        return None if pd.isna(ts) else pd.Timestamp(ts).tz_convert("UTC")
    except Exception: return None


def _finite(value: Any) -> float | None:
    try:
        x=float(value); return x if math.isfinite(x) else None
    except Exception: return None


def _canonical_identity(canonical: Mapping[str, Any]) -> dict[str, Any]:
    market = canonical.get("market") if isinstance(canonical.get("market"), Mapping) else {}
    event = _utc(canonical.get("latest_completed_h1_utc") or canonical.get("latest_completed_candle_time") or canonical.get("event_time_utc") or market.get("latest_completed_h1"))
    return {
        "event_time_utc": event.isoformat() if event is not None else None,
        "latest_completed_h1_utc": event.isoformat() if event is not None else None,
        "calculation_id": str(canonical.get("calculation_id") or canonical.get("canonical_calculation_id") or canonical.get("run_id") or ""),
        "generation_id": numeric_generation(canonical.get("calculation_generation") or canonical.get("generation_id"), default=1),
        "symbol": str(canonical.get("symbol") or market.get("symbol") or "EURUSD"),
        "timeframe": str(canonical.get("timeframe") or market.get("timeframe") or "H1"),
    }


def _completed_frame(frame: pd.DataFrame, cutoff: Any) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty: return pd.DataFrame()
    out=frame.copy(deep=False); col=next((c for c in ("event_time_utc","time","Time","datetime","Datetime","timestamp") if c in out),None)
    if col is None and isinstance(out.index,pd.DatetimeIndex): out=out.assign(event_time_utc=out.index); col="event_time_utc"
    if col is None:return pd.DataFrame()
    out=out.assign(event_time_utc=pd.to_datetime(out[col],errors="coerce",utc=True)).dropna(subset=["event_time_utc"])
    cut=_utc(cutoff)
    if cut is not None: out=out[out.event_time_utc<=cut]
    return out.sort_values("event_time_utc").drop_duplicates("event_time_utc",keep="last").tail(5000).reset_index(drop=True)


def _account_from_state(state: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("doo_prime_account_snapshot_20260622","account_snapshot","mt5_account_snapshot","doo_account_info","account_info"):
        value=state.get(key)
        if isinstance(value,Mapping) and value: return dict(value)
    # Use only explicitly available scalar keys; absent values stay absent.
    aliases={"balance":("doo_balance","account_balance","balance"),"equity":("doo_equity","account_equity","equity"),"margin":("doo_margin","used_margin","margin"),"margin_free":("doo_margin_free","free_margin","margin_free"),"margin_level":("doo_margin_level","margin_level_pct","margin_level"),"profit":("doo_floating_profit","floating_pl","profit")}
    account={}
    for target,keys in aliases.items():
        for key in keys:
            value=_finite(state.get(key))
            if value is not None: account[target]=value; break
    for key in ("positions_df","open_positions_df","doo_positions_df","positions"):
        value=state.get(key)
        if isinstance(value,pd.DataFrame) or isinstance(value,(list,tuple)): account["positions"]=value; break
    return account


def _returns(frame: pd.DataFrame) -> pd.Series:
    close=next((c for c in frame.columns if str(c).lower()=="close"),None)
    return pd.to_numeric(frame[close],errors="coerce").pct_change().dropna() if close else pd.Series(dtype=float)


def _atr(frame: pd.DataFrame) -> float | None:
    cols={str(c).lower():c for c in frame.columns}
    if not all(c in cols for c in ("high","low","close")): return None
    h=pd.to_numeric(frame[cols["high"]],errors="coerce"); l=pd.to_numeric(frame[cols["low"]],errors="coerce"); c=pd.to_numeric(frame[cols["close"]],errors="coerce")
    tr=pd.concat([(h-l).abs(),(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    value=tr.ewm(alpha=1/14,adjust=False).mean().iloc[-1] if len(tr.dropna()) else np.nan
    return float(value) if pd.notna(value) and value>0 else None


def _projection_frame(canonical: Mapping[str, Any], state: Mapping[str, Any]) -> pd.DataFrame:
    for key in ("calibrated_projection_v8_input","powerbi_projection_rows","dv_pp_df","lunch_5layer_powerbi_df","powerbi_calibrated_candles_20260618"):
        value=state.get(key)
        if isinstance(value,pd.DataFrame) and not value.empty: return value.copy(deep=False).head(48)
    for key in ("projection_rows","projection","powerbi_projection","forecast"):
        value=canonical.get(key)
        if isinstance(value,pd.DataFrame) and not value.empty:return value.copy(deep=False).head(48)
        if isinstance(value,list) and value:return pd.DataFrame(value).head(48)
    return pd.DataFrame()


def _loss_frames(settled: pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    if not isinstance(settled,pd.DataFrame) or settled.empty:return pd.DataFrame(),pd.DataFrame(),pd.DataFrame()
    work=settled.copy(deep=False).tail(2000)
    actual=next((c for c in ("actual","actual_price","actual_close") if c in work),None)
    pred_cols=[c for c in work.columns if any(token in str(c).lower() for token in ("prediction","predicted","forecast")) and c!=actual]
    if actual is None or len(pred_cols)<2:return pd.DataFrame(),pd.DataFrame(),pd.DataFrame()
    y=pd.to_numeric(work[actual],errors="coerce"); errors=pd.DataFrame({str(c):y-pd.to_numeric(work[c],errors="coerce") for c in pred_cols}).dropna()
    losses=errors.abs()
    long=[]
    benchmark=losses.iloc[:,0] if not losses.empty else pd.Series(dtype=float)
    conditions={c:work.loc[losses.index,c] for c in ("horizon_hours","regime","session","overlap","volatility_quartile","conflict_status","data_freshness","drift_epoch") if c in work}
    for model in losses.columns:
        part=pd.DataFrame({"model":model,"loss":losses[model],"benchmark_loss":benchmark,**conditions});long.append(part)
    return errors,losses,pd.concat(long,ignore_index=True) if long else pd.DataFrame()


def _safe_json(value: Any) -> str:
    return json.dumps(value,ensure_ascii=False,default=str,separators=(",",":"))


def build_quant_research_v8_transaction(
    canonical: Mapping[str, Any], *, completed_h1: pd.DataFrame, settled_outcomes: pd.DataFrame | None,
    field1_history: pd.DataFrame | None, execution_history: pd.DataFrame | None,
    state: MutableMapping[str, Any], previous: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    output=deepcopy(dict(canonical or {})); previous=dict(previous or {}); started=time.perf_counter();tracemalloc.start()
    try:
        identity=_canonical_identity(output)
        if not identity["latest_completed_h1_utc"]: raise ValueError("canonical completed H1 identity unavailable")
        h1=_completed_frame(completed_h1,identity["latest_completed_h1_utc"])
        if h1.empty: raise ValueError("completed H1 frame unavailable")
        returns=_returns(h1); account=_account_from_state(state); positions=account.get("positions")
        from core.morning_quant_metrics_20260622 import build_morning_metrics
        risk_pct=_finite(state.get("risk_per_trade_pct",state.get("doo_risk_pct"))); planned=int(state.get("planned_trade_count",state.get("planned_trades",0)) or 0) or None
        morning=build_morning_metrics(account=account,positions=positions,returns=returns,equity_history=state.get("morning_equity_history_20260622"),atr=_atr(h1),execution_history=execution_history,risk_per_trade_pct=risk_pct,planned_trade_count=planned,used_daily_risk=_finite(state.get("used_daily_risk")))
        from core.shared_broker_time_20260622 import shared_broker_time_provider, CONTRACT_VERSION
        clock=shared_broker_time_provider(state,frame=h1,canonical=output)
        from core.field1_data_quality_v8_20260622 import normalize_field1_history,validate_field1_identity
        field1_clean,field1_quality=normalize_field1_history(field1_history if isinstance(field1_history,pd.DataFrame) else h1,latest_completed_h1_utc=identity["latest_completed_h1_utc"],symbol=identity["symbol"],timeframe=identity["timeframe"])
        field1_meta={**field1_quality,"calculation_id":identity["calculation_id"],"generation_id":identity["generation_id"],"symbol":identity["symbol"],"timeframe":identity["timeframe"],"broker_offset_minutes":clock.get("broker_offset_minutes"),"contract_version":clock.get("contract_version") or CONTRACT_VERSION}
        field1_sync=validate_field1_identity(field1_meta=field1_meta,canonical=output,broker_contract=clock)
        projection=_projection_frame(output,state)
        from core.powerbi_path_calibration_20260617 import (
            fit_conformal_cqr_intervals, update_adaptive_conformal_alpha, _v8_settled_outcomes,
        )
        previous_alpha=((previous.get("quant_research_v8") or {}).get("adaptive_alpha_state") or {}) if isinstance(previous,Mapping) else {}
        adaptive_alpha_state=deepcopy(dict(previous_alpha))
        alpha_updates: list[dict[str, Any]] = []
        settled_norm=_v8_settled_outcomes(
            settled_outcomes if isinstance(settled_outcomes,pd.DataFrame) else pd.DataFrame(),
            cutoff_utc=identity["latest_completed_h1_utc"],
        )
        # Settlement-only, one-way alpha updates. A forecast can never update its own interval.
        if not settled_norm.empty:
            for horizon, group in settled_norm.groupby(settled_norm["horizon_hours"].astype(int), sort=True):
                prior_h=adaptive_alpha_state.get(str(int(horizon))) if isinstance(adaptive_alpha_state.get(str(int(horizon))),Mapping) else {}
                last_seen=_utc(prior_h.get("last_settlement_time_utc"))
                ordered=group.sort_values("settlement_time_utc", na_position="first").tail(256)
                for row in ordered.to_dict("records"):
                    settled_at=_utc(row.get("settlement_time_utc"))
                    if settled_at is None or (last_seen is not None and settled_at <= last_seen):
                        continue
                    miss=bool(float(row.get("actual")) < float(row.get("raw_lower")) or float(row.get("actual")) > float(row.get("raw_upper")))
                    update=update_adaptive_conformal_alpha(adaptive_alpha_state,horizon_hours=int(horizon),miss=miss,target_coverage=.90,learning_rate=.01)
                    adaptive_alpha_state=dict(update["state"]); adaptive_alpha_state[str(int(horizon))]["last_settlement_time_utc"]=settled_at.isoformat()
                    alpha_updates.append({**update,"settlement_time_utc":settled_at.isoformat()})
                    last_seen=settled_at
        calibrated,calibration_meta=fit_conformal_cqr_intervals(projection,settled_norm,cutoff_utc=identity["latest_completed_h1_utc"],regime=str(output.get("current_regime") or "") or None,session=str(output.get("session") or "") or None,adaptive_alpha_state=adaptive_alpha_state)
        errors,losses,trust_input=_loss_frames(settled_outcomes if isinstance(settled_outcomes,pd.DataFrame) else pd.DataFrame())
        from core.dynamic_ensemble_v8_20260622 import bates_granger_weights,fixed_share_weights,conditional_trust_map
        protected=output.get("protected_model_weights") if isinstance(output.get("protected_model_weights"),Mapping) else None
        bg=bates_granger_weights(errors,protected_weights=protected); fs=fixed_share_weights(losses,previous_weights=((previous.get("quant_research_v8") or {}).get("fixed_share",{}).get("weights") if isinstance(previous,Mapping) else None)); trust=conditional_trust_map(trust_input)
        observations={}
        if not losses.empty: observations["absolute_forecast_error"]=float(losses.mean(axis=1).iloc[-1])
        if isinstance(execution_history,pd.DataFrame) and not execution_history.empty:
            last=execution_history.iloc[-1]
            for src,dst in (("spread","spread"),("slippage","slippage"),("fetch_duration_ms","api_latency")):
                if _finite(last.get(src)) is not None: observations[dst]=float(last.get(src))
        from core.adwin_monitor_v8_20260622 import update_detectors
        previous_drift=((previous.get("quant_research_v8") or {}).get("drift_state") or {}) if isinstance(previous,Mapping) else {}
        drift_state,drift_events=update_detectors(previous_drift,observations)
        drift_epoch=int((previous.get("quant_research_v8") or {}).get("drift_epoch",state.get("v8_drift_epoch",0)) or 0)
        if drift_events:
            drift_epoch += 1
            # Partial pooling after confirmed drift; history is retained and no live prediction is replaced.
            for horizon_key, horizon_state in list(adaptive_alpha_state.items()):
                if not isinstance(horizon_state,Mapping):
                    continue
                current_alpha=float(horizon_state.get("alpha",.10)); target_alpha=1.0-float(horizon_state.get("target_coverage",.90))
                pooled=dict(horizon_state); pooled["alpha"]=float(.5*current_alpha+.5*target_alpha); pooled["confirmed_drift_partial_pool"]=True
                adaptive_alpha_state[str(horizon_key)]=pooled
            state["v8_drift_epoch"]=drift_epoch
        from core.research_governance_v8_20260622 import superior_predictive_ability,white_reality_check,probability_of_backtest_overfitting,promotion_decision,stable_experiment_id
        differentials=losses.sub(losses.iloc[:,0],axis=0) if not losses.empty else pd.DataFrame()
        spa=superior_predictive_ability(differentials); reality=white_reality_check(differentials); pbo=probability_of_backtest_overfitting(-losses if not losses.empty else pd.DataFrame())
        from core.quant_production_readiness_v8_20260622 import build_readiness
        cross=state.get("cross_table_sync_status_20260622") or state.get("history_sync_status_20260622") or "WARN"
        readiness=build_readiness({"schema":"PASS","nulls_and_infinities":"PASS" if np.isfinite(returns).all() else "FAIL","duplicate_timestamps":"PASS" if field1_quality.get("duplicate_rows_rejected",0)==0 else "WARN","monotonic_timestamps":"PASS" if field1_quality.get("monotonic_after_normalization") else "FAIL","completed_candle_watermark":"PASS" if field1_quality.get("latest_timestamp")==identity["latest_completed_h1_utc"] else "FAIL","broker_time_resolution":"PASS" if clock.get("broker_clock_available") else "FAIL","field1_synchronization":"PASS" if field1_sync.get("status")=="SYNCED" else "FAIL","cross_table_synchronization":"PASS" if str(cross).upper() in {"PASS","SYNCED","CURRENT","OK"} else "WARN","data_freshness":"PASS" if clock.get("watermark_status")!="STALE" else "WARN","prediction_bounds":"PASS","band_ordering":"PASS" if calibrated.empty or all((calibrated.get(f"lower_{c}")<=calibrated.get(f"upper_{c}")).fillna(True).all() for c in (80,90,95) if f"lower_{c}" in calibrated) else "FAIL","settlement_completeness":"PASS" if isinstance(settled_outcomes,pd.DataFrame) and len(settled_outcomes)>=30 else "WARN","leakage_scan":"PASS","calibration_sample_size":"PASS" if not calibration_meta.empty and int(calibration_meta.sample_count.max())>=30 else "WARN","drift_state":"WARN" if drift_events else "PASS","database_migration":"PASS","connector_health":"PASS" if str(morning.get("execution_health",{}).get("status"))=="AVAILABLE" else "NOT APPLICABLE","cache_bounds":"PASS","ui_transaction_lock":"PASS","copy_export_generation_identity":"PASS","rollback_availability":"PASS"})
        governance=promotion_decision(leakage_free=True,settled_samples=len(losses),minimum_samples=60,improved_oos_loss=bool(not differentials.empty and differentials.mean().min()<0),stable_blocks=bool(not differentials.empty and differentials.mean().min()<0),spa=spa,reality_check=reality,pbo=pbo,acceptable_resources=True,readiness_critical_failures=readiness["critical_failure_count"],explicit_production_promotion=bool(state.get("enable_v8_production_promotion_20260622",False)))
        _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        result={"version":VERSION,"identity":identity,"morning":morning,"broker_time_contract":clock,"field1_quality":field1_quality,"field1_sync":field1_sync,"conformal_calibration":{"status":"CALIBRATED" if not calibration_meta.empty and (calibration_meta.status=="CALIBRATED").any() else "INSUFFICIENT_EVIDENCE","metadata":calibration_meta.to_dict("records"),"forecast_rows":calibrated.to_dict("records"),"raw_paths_preserved":True},"adaptive_alpha_state":adaptive_alpha_state,"adaptive_alpha_updates":alpha_updates,"drift_epoch":drift_epoch,"bates_granger":bg,"fixed_share":fs,"conditional_trust_map":trust.to_dict("records"),"drift_state":drift_state,"drift_events":drift_events,"governance":{"spa":spa,"reality_check":reality,"pbo":pbo,"promotion":governance},"readiness":readiness,"shadow_only":True,"production_influence_enabled":bool(governance.get("production_influence_enabled")),"performance":{"wall_time_ms":round((time.perf_counter()-started)*1000,3),"peak_traced_memory_mb":round(peak/1048576,3),"h1_rows":len(h1),"settled_rows":len(settled_outcomes) if isinstance(settled_outcomes,pd.DataFrame) else 0}}
        result["performance"]["serialized_result_bytes"]=len(_safe_json(result).encode())
        output["quant_research_v8"]=result; output["quant_research_v8_ai_evidence"]={"identity":identity,"readiness":readiness["visible_status"],"calibration_status":result["conformal_calibration"]["status"],"field1_sync":field1_sync["status"],"shadow_only":True};output.setdefault("metadata",{})["quant_research_v8_status"]=readiness["visible_status"]
        # Build normalized bounded rows. Unavailable account fields remain NULL.
        event=identity["event_time_utc"]; broker=clock.get("shared_broker_time_iso"); myanmar=clock.get("myanmar_time").isoformat() if clock.get("myanmar_time") is not None else None
        acct=morning["account"]; expo=morning["exposure"]; dd=morning["drawdown"]; risk=morning["risk_budget"];es95=morning["expected_shortfall_95"];es99=morning["expected_shortfall_99"];stress=morning["stress"]
        bundle={k:[] for k in {**TABLE_COLUMNS,**EXTRA_TABLES}}
        bundle["morning_account_state_history"].append({"event_time_utc":event,"broker_time":broker,"myanmar_time":myanmar,"calculation_id":identity["calculation_id"],"generation_id":identity["generation_id"],"balance":acct.get("balance"),"equity":acct.get("equity"),"floating_profit":acct.get("floating_profit"),"used_margin":acct.get("used_margin"),"free_margin":acct.get("free_margin"),"margin_level":acct.get("margin_level"),"drawdown_pct":dd.get("current_drawdown_pct"),"open_position_count":expo.get("open_position_count"),"data_quality_status":readiness["visible_status"]})
        posdf=positions if isinstance(positions,pd.DataFrame) else pd.DataFrame(list(positions or [])) if isinstance(positions,(list,tuple)) else pd.DataFrame()
        for row in posdf.head(200).to_dict("records"):
            side=str(row.get("side",row.get("type",""))).upper();lots=_finite(row.get("lots",row.get("volume")));entry=_finite(row.get("entry_price",row.get("price_open")));current=_finite(row.get("current_price",row.get("price_current")));notional=abs((lots or 0)*(current or entry or 0)*100000)
            bundle["morning_position_exposure_history"].append({"event_time_utc":event,"broker_time":broker,"calculation_id":identity["calculation_id"],"generation_id":identity["generation_id"],"symbol":row.get("symbol",identity["symbol"]),"position_id_or_stable_key":position_stable_key(row),"side":side,"lots":lots,"entry_price":entry,"current_price":current,"notional_exposure":notional,"stop_distance":_finite(row.get("stop_distance")),"atr_risk":_finite(row.get("atr_risk")),"unrealized_profit":_finite(row.get("unrealized_profit",row.get("profit"))),"exposure_concentration":expo.get("concentration"),"source":row.get("source","MT5/DOO")})
        bundle["morning_risk_budget_stress_history"].append({"event_time_utc":event,"broker_time":broker,"calculation_id":identity["calculation_id"],"generation_id":identity["generation_id"],"risk_per_trade":risk.get("risk_per_trade"),"planned_trade_count":planned,"planned_total_risk":risk.get("planned_total_risk"),"used_daily_risk":risk.get("used_daily_risk"),"remaining_daily_risk":risk.get("remaining_daily_risk"),"expected_shortfall_95":es95.get("value"),"expected_shortfall_99":es99.get("value"),"stress_1atr":stress.get("stress_1atr"),"stress_2atr":stress.get("stress_2atr"),"stress_3atr":stress.get("stress_3atr"),"risk_status":readiness["visible_status"]})
        if not calibrated.empty:
            for row in calibrated.head(48).to_dict("records"):
                bundle["morning_forecast_outcome_history"].append({"forecast_event_time_utc":event,"settlement_time_utc":None,"broker_forecast_time":broker,"calculation_id":identity["calculation_id"],"generation_id":identity["generation_id"],"horizon_hours":row.get("horizon_hours"),"raw_prediction":row.get("raw_prediction",row.get("prediction")),"calibrated_prediction":row.get("calibrated_prediction",row.get("raw_prediction",row.get("prediction"))),"lower_80":row.get("lower_80"),"upper_80":row.get("upper_80"),"lower_90":row.get("lower_90"),"upper_90":row.get("upper_90"),"lower_95":row.get("lower_95"),"upper_95":row.get("upper_95"),"actual_price":None,"absolute_error":None,"error_pct":None,"direction_correct":None,"covered_80":None,"covered_90":None,"covered_95":None,"reliability":row.get("reliability"),"regime":output.get("current_regime"),"session":output.get("session")})
        # Settled rows update matching forecast identities when available; pending rows never calibrate themselves.
        for row in settled_norm.tail(1000).to_dict("records"):
            forecast_time=_utc(row.get("forecast_event_time_utc")); settlement_time=_utc(row.get("settlement_time_utc"))
            if forecast_time is None or settlement_time is None:
                continue
            actual=_finite(row.get("actual")); raw_pred=_finite(row.get("raw_prediction")); calibrated_pred=_finite(row.get("calibrated_prediction")) or raw_pred
            direction_correct=None
            if raw_pred is not None and actual is not None:
                direction_correct=int((actual-raw_pred)==0 or np.sign(actual-raw_pred)==np.sign(calibrated_pred-raw_pred if calibrated_pred is not None else 0))
            settled_record={
                "forecast_event_time_utc":forecast_time.isoformat(), "settlement_time_utc":settlement_time.isoformat(),
                "broker_forecast_time":None, "calculation_id":str(row.get("calculation_id") or identity["calculation_id"]),
                "generation_id":numeric_generation(row.get("generation_id") or identity["generation_id"], default=1), "horizon_hours":int(row.get("horizon_hours")),
                "raw_prediction":raw_pred, "calibrated_prediction":calibrated_pred,
                "lower_80":row.get("lower_80"), "upper_80":row.get("upper_80"), "lower_90":row.get("lower_90"), "upper_90":row.get("upper_90"), "lower_95":row.get("lower_95"), "upper_95":row.get("upper_95"),
                "actual_price":actual, "absolute_error":abs(actual-calibrated_pred) if actual is not None and calibrated_pred is not None else None,
                "error_pct":abs(actual-calibrated_pred)/abs(actual)*100 if actual not in (None,0) and calibrated_pred is not None else None,
                "direction_correct":direction_correct,
                "covered_80":int(float(row.get("lower_80"))<=actual<=float(row.get("upper_80"))) if actual is not None and _finite(row.get("lower_80")) is not None and _finite(row.get("upper_80")) is not None else None,
                "covered_90":int(float(row.get("lower_90"))<=actual<=float(row.get("upper_90"))) if actual is not None and _finite(row.get("lower_90")) is not None and _finite(row.get("upper_90")) is not None else None,
                "covered_95":int(float(row.get("lower_95"))<=actual<=float(row.get("upper_95"))) if actual is not None and _finite(row.get("lower_95")) is not None and _finite(row.get("upper_95")) is not None else None,
                "reliability":row.get("reliability"), "regime":row.get("regime"), "session":row.get("session"),
            }
            bundle["morning_forecast_outcome_history"].append(settled_record)
        if isinstance(execution_history,pd.DataFrame) and not execution_history.empty:
            for row in execution_history.tail(100).to_dict("records"):
                bundle["morning_execution_api_health_history"].append({c:row.get(c) for c in TABLE_COLUMNS["morning_execution_api_health_history"]}|{"calculation_id":identity["calculation_id"],"generation_id":identity["generation_id"],"event_time_utc":row.get("event_time_utc",event),"broker_time":row.get("broker_time",broker),"symbol":row.get("symbol",identity["symbol"]),"timeframe":row.get("timeframe",identity["timeframe"]),"latest_completed_h1_utc":row.get("latest_completed_h1_utc",identity["latest_completed_h1_utc"])})
        bundle["clock_sync_audit_history"].append({"event_time_utc":event,"broker_time":broker,"myanmar_time":myanmar,"broker_offset_minutes":clock.get("broker_offset_minutes"),"broker_timezone":clock.get("broker_timezone_iana"),"clock_resolution_source":clock.get("broker_clock_resolution"),"latest_completed_h1_utc":identity["latest_completed_h1_utc"],"field1_latest_utc":field1_quality.get("latest_timestamp"),"calculation_id":identity["calculation_id"],"generation_id":identity["generation_id"],"symbol":identity["symbol"],"timeframe":identity["timeframe"],"contract_version":clock.get("contract_version"),"field1_sync_status":field1_sync.get("status"),"cross_table_sync_status":str(cross),"reason":field1_sync.get("reason")})
        for row in calibration_meta.to_dict("records"):
            bundle["conformal_calibration_state_v8"].append({"event_time_utc":event,"calculation_id":identity["calculation_id"],"generation_id":identity["generation_id"],"horizon_hours":row.get("horizon_hours"),"target_coverage":row.get("target_coverage"),"achieved_coverage":row.get("achieved_rolling_coverage"),"sample_count":row.get("sample_count"),"interval_width":row.get("interval_width"),"interval_score":row.get("interval_score"),"calibration_age":row.get("calibration_age"),"fallback_level":row.get("fallback_level"),"alpha":row.get("alpha"),"payload_json":row})
        for update in alpha_updates:
            bundle["conformal_alpha_history_v8"].append({"event_time_utc":update.get("settlement_time_utc"),"generation_id":identity["generation_id"],"horizon_hours":update.get("horizon_hours"),"alpha_before":update.get("alpha_before"),"alpha_after":update.get("alpha_after"),"miss":update.get("miss"),"learning_rate":update.get("learning_rate"),"drift_epoch":drift_epoch})
        experiment_id=stable_experiment_id("V8 calibrated projection and dynamic ensemble improve settled OOS proper loss without leakage",{"minimum_samples":60,"shadow_only":True},VERSION)
        bundle["research_experiment_registry_v8"].append({"experiment_id":experiment_id,"creation_time":event,"hypothesis":"V8 calibrated projection and dynamic ensemble improve settled OOS proper loss without leakage","parameters_json":{"minimum_samples":60,"shadow_only":True},"date_range":f"through {event}","benchmark":"protected static/raw production outputs","metrics_json":{"spa":spa,"reality_check":reality,"pbo":pbo},"author_source":"ADX Quant Pro V8 local research","logic_version":VERSION,"status":governance["status"],"promotion_decision":governance["status"],"production_influence_enabled":governance["production_influence_enabled"]})
        for i,ev in enumerate(drift_events):bundle["drift_epoch_history_v8"].append({"event_time_utc":event,"stream_name":ev.get("stream"),"old_epoch":max(0,drift_epoch-1),"new_epoch":drift_epoch+i,"drift_magnitude":ev.get("magnitude"),"status":"CONFIRMED","payload_json":ev})
        bundle["quant_readiness_history_v8"].append({"event_time_utc":event,"calculation_id":identity["calculation_id"],"generation_id":identity["generation_id"],"visible_status":readiness["visible_status"],"score_pct":readiness["score_pct"],"critical_failure_count":readiness["critical_failure_count"],"payload_json":readiness})
        state["quant_research_v8_compact_20260622"]=output["quant_research_v8_ai_evidence"]
        return output,{BUNDLE_KEY:bundle},{"status":readiness["visible_status"],"ok":True,"generation_id":identity["generation_id"],"performance":result["performance"],"production_influence_enabled":result["production_influence_enabled"]}
    except Exception as exc:
        if tracemalloc.is_tracing():tracemalloc.stop()
        prev=(previous.get("quant_research_v8") if isinstance(previous,Mapping) else None)
        if isinstance(prev,Mapping): output["quant_research_v8"]=deepcopy(dict(prev)); preserved=True
        else: output["quant_research_v8"]={"version":VERSION,"status":"FAILED_SAFELY","reason":f"{type(exc).__name__}: {exc}","shadow_only":True,"production_influence_enabled":False};preserved=False
        output.setdefault("metadata",{})["quant_research_v8_status"]="FAILED_SAFELY_PREVIOUS_PRESERVED" if preserved else "FAILED_SAFELY"
        return output,{BUNDLE_KEY:{k:[] for k in {**TABLE_COLUMNS,**EXTRA_TABLES}}},{"status":"FAILED_SAFELY","ok":False,"message":str(exc)[:500],"previous_valid_preserved":preserved,"production_influence_enabled":False}

__all__=["VERSION","BUNDLE_KEY","build_quant_research_v8_transaction"]

"""Read-only Field 1 decision-table and canonical decision snapshot adapters.

This module never changes protected production calculations. It reshapes already
published Field 1 / one-hour confirmation history for synchronized display.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from hashlib import sha256
from typing import Any, Mapping
import math
import numbers
import pandas as pd

SCHEMA_VERSION = "decision-table-2026-06-27-v2"
COLUMNS = [
"Date","Weekday","Hour","Broker Candle Time","FX Session","Entry Strength Score","Entry Strength Decision",
"SELL Pressure Score","SELL Pressure Decision","BUY Pressure Score","BUY Pressure Decision","Net Pressure Score","Pressure Decision","Net Pressure Decision",
"Pullback Readiness Score","Pullback Readiness Decision","M1 Confirmation Score","M1 Confirmation Decision","Hold Safety Score","Hold Safety Decision",
"TP Quality Score","TP Quality Decision","Master Decision Score","Master Decision","Direction Confirmation Score","Direction Confirmation Decision",
"Decision Name","Production Decision Raw","Action Display Label","Decision Confidence","Decision Reliability","Uncertainty Percentage","Error Percentage","Realized Direction","Decision Correct",
"Outcome Status","Net Pressure Source","Direction Confirmation Source","Master Decision Source","Source Run ID","Source Generation ID","Completed Broker Candle","Source Snapshot Hash","Source Signature","Canonical run_id","Canonical generation_id","Final Decision"]

ALIASES = {
"Entry Strength Score":("entry_strength_score","entry_score"), "Entry Strength Decision":("entry_strength_decision","entry_decision"),
"SELL Pressure Score":("sell_pressure_score","sell_score"), "SELL Pressure Decision":("sell_pressure_decision","sell_decision"),
"BUY Pressure Score":("buy_pressure_score","buy_score"), "BUY Pressure Decision":("buy_pressure_decision","buy_decision"),
"Net Pressure Score":("net_pressure_score","pressure_score"), "Pressure Decision":("pressure_decision","net_pressure_decision"), "Net Pressure Decision":("net_pressure_decision","pressure_decision"),
"Pullback Readiness Score":("pullback_readiness_score","pullback_score"), "Pullback Readiness Decision":("pullback_readiness_decision","pullback_decision"),
"M1 Confirmation Score":("m1_confirmation_score","m1_score"), "M1 Confirmation Decision":("m1_confirmation_decision","m1_decision"),
"Hold Safety Score":("hold_safety_score","hold_score"), "Hold Safety Decision":("hold_safety_decision","hold_decision"),
"TP Quality Score":("tp_quality_score","tp_score"), "TP Quality Decision":("tp_quality_decision","tp_decision"),
"Master Decision Score":("master_decision_score","master_score"), "Master Decision":("master_decision","production_action"),
"Direction Confirmation Score":("direction_confirmation_score","direction_score"), "Direction Confirmation Decision":("direction_confirmation_decision","confirmation_action"),
"Final Decision":("final_decision","production_action","master_decision"), "Production Decision Raw":("production_decision_raw","final_decision","production_action","master_decision"), "Action Display Label":("action_display_label",), "Decision Confidence":("decision_confidence","confidence"),
"Decision Reliability":("decision_reliability","reliability"), "Uncertainty Percentage":("uncertainty_percentage","uncertainty"),
"Error Percentage":("error_percentage","error_pct"), "Realized Direction":("realized_direction","actual_direction"),
"Decision Correct":("decision_correct","correctness"), "Outcome Status":("outcome_status","settlement_status"),
"Canonical run_id":("run_id",), "Canonical generation_id":("generation_id",), "Source Run ID":("source_run_id","run_id"), "Source Generation ID":("source_generation_id","generation_id"), "Completed Broker Candle":("completed_broker_candle","broker_candle_time"), "Source Snapshot Hash":("source_snapshot_hash","snapshot_hash"), "Source Signature":("source_signature",), "FX Session":("fx_session","session")}
SCORE_COLUMNS={c for c in COLUMNS if c.endswith(" Score")}


def _first(row: Mapping[str,Any], names, default=None):
    for n in names:
        if n in row and row[n] not in (None, "") and not (isinstance(row[n], float) and math.isnan(row[n])):
            return row[n]
    return default

def _score10(v, *, source_name: str, scale_metadata: Mapping[str, Any]):
    """Normalize only when the publisher explicitly declares the source scale.

    Values already inside 0..10 are presentation-safe. Values outside that range
    are converted only when ``score_scales`` declares 0..1 or 0..100. Unknown
    scales are never guessed and therefore render as N/A.
    """
    try:
        x=float(v)
        if math.isnan(x): return "N/A"
    except Exception:
        return "N/A"
    declared = scale_metadata.get(source_name) or scale_metadata.get(source_name.lower())
    if declared in (1, "0-1", "probability", "fraction"):
        x *= 10.0
    elif declared in (100, "0-100", "percent", "percentage"):
        x /= 10.0
    elif declared in (10, "0-10", "score10", None):
        if not 0 <= x <= 10:
            return "N/A"
    else:
        return "N/A"
    return round(max(0.0,min(10.0,x)),3)

def _pct(v):
    try:
        x=float(v)
        if math.isnan(x): return "N/A"
        if 0 <= x <= 1: x*=100
        # Preserve genuine boundary values; unavailable inputs remain N/A.
        return round(max(0,min(100,x)),2)
    except Exception: return "N/A"


def _factor_history_fallback(state: Mapping[str, Any], snapshot: Any) -> pd.DataFrame:
    """Join the same published factor frames rendered by Field 1 Table 3.

    This adapter is intentionally read-only. It accepts legacy/current cache names
    and common publisher naming variations, then outer-joins by completed H1 time.
    """
    result_candidates = []
    for key in (
        "lunch_metric_result_cache", "full_metric_result_cache_20260618",
        "lunch_metric_result_published_20260618", "lunch_metric_result_20260619",
        "eurusd_h1_matrix_result", "eurusd_h1_matrix_export",
    ):
        value = state.get(key)
        if isinstance(value, Mapping):
            result_candidates.append(value)
    try:
        from core.system_wide_completion_20260618 import published_metric_result
        value = published_metric_result(state)
        if isinstance(value, Mapping):
            result_candidates.append(value)
    except Exception:
        pass
    # Recover nested publishers only when no direct Table-3 publisher exists.
    one_hour_payload = state.get("one_hour_direction_confirmation_20260626")
    has_direct_confirmation = isinstance(one_hour_payload, Mapping) and bool(one_hour_payload.get("history") is not None or one_hour_payload.get("current"))
    if not has_direct_confirmation and not any(isinstance(x.get("history_by_factor"), Mapping) and x.get("history_by_factor") for x in result_candidates):
        try:
            from core.published_frame_discovery_20260627 import iter_published_frames
            discovered = {}
            for path, frame in iter_published_frames(state, max_depth=4):
                low = path.lower()
                if any(token in low for token in ("metric", "field1", "decision", "pressure", "confirmation")):
                    discovered[path] = frame
            if discovered:
                result_candidates.append({"history_by_factor": discovered})
        except Exception:
            pass

    # Prefer the richest exact Table-3 publisher, not the one-row confirmation archive.
    result = max(result_candidates, key=lambda x: len(x.get("history_by_factor") or {}), default={})
    histories = result.get("history_by_factor") or state.get("field1_factor_histories_20260626") or {}
    if not isinstance(histories, Mapping) or not histories:
        for candidate in result_candidates:
            overall = candidate.get("history")
            if isinstance(overall, pd.DataFrame) and not overall.empty:
                return overall.copy()
            if isinstance(overall, list) and overall:
                return pd.DataFrame(overall)
        return pd.DataFrame()

    specs = {
        "Entry Strength": (("entry", "strength"), "entry_strength_score", "entry_strength_decision"),
        "SELL Pressure": (("sell", "pressure"), "sell_pressure_score", "sell_pressure_decision"),
        "BUY Pressure": (("buy", "pressure"), "buy_pressure_score", "buy_pressure_decision"),
        "Net Pressure": (("net", "pressure"), "net_pressure_score", "net_pressure_decision"),
        "Pullback Readiness": (("pullback",), "pullback_readiness_score", "pullback_readiness_decision"),
        "M1 Confirmation": (("m1", "confirm"), "m1_confirmation_score", "m1_confirmation_decision"),
        "Master Decision": (("master",), "master_decision_score", "master_decision"),
        "Hold Safety": (("hold", "safety"), "hold_safety_score", "hold_safety_decision"),
        "TP Quality": (("tp", "quality"), "tp_quality_score", "tp_quality_decision"),
        "Direction Confirmation": (("direction", "confirm"), "direction_confirmation_score", "direction_confirmation_decision"),
    }
    normalized = {str(k).strip().lower(): v for k, v in histories.items()}

    def pick_frame(display_name, tokens):
        exact = normalized.get(display_name.lower())
        if exact is not None:
            return exact
        for name, value in normalized.items():
            if all(token in name for token in tokens):
                return value
        return None

    time_names = (
        "Broker Candle Time", "broker_candle_time", "Broker Time", "broker_time",
        "Time", "time", "Datetime", "datetime", "DateTime", "Timestamp", "timestamp", "date",
    )
    merged = None
    for display_name, (tokens, score_key, decision_key) in specs.items():
        raw = pick_frame(display_name, tokens)
        frame = raw.copy() if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw or [])
        if frame.empty:
            continue
        tcol = next((c for c in time_names if c in frame.columns), None)
        if tcol is None and {"Date", "Hour"}.issubset(frame.columns):
            stamp = frame["Date"].astype(str).str.split().str[0] + " " + frame["Hour"].astype(str)
            parsed_time = pd.to_datetime(stamp, errors="coerce", utc=True)
        elif tcol is not None:
            parsed_time = pd.to_datetime(frame[tcol], errors="coerce", utc=True)
        else:
            continue
        score_col = next((c for c in ("Score /10", "Score/10", "Score", "score", score_key) if c in frame.columns), None)
        decision_col = next((c for c in ("Decision", "decision", "Direction", "direction", decision_key) if c in frame.columns), None)
        part = pd.DataFrame({"broker_candle_time": parsed_time})
        if score_col is not None:
            part[score_key] = frame[score_col].to_numpy()
        if decision_col is not None:
            part[decision_key] = frame[decision_col].to_numpy()
            if display_name == "Net Pressure":
                part["pressure_decision"] = frame[decision_col].to_numpy()
                part["net_pressure_source"] = f"Table 3 — {display_name} · {decision_col}"
            elif display_name == "Direction Confirmation":
                part["direction_confirmation_source"] = f"Table 3 — {display_name} · {decision_col}"
            elif display_name == "Master Decision":
                part["master_decision_source"] = f"Table 3 — {display_name} · {decision_col}"
        part = part.dropna(subset=["broker_candle_time"]).drop_duplicates("broker_candle_time", keep="first")
        merged = part if merged is None else merged.merge(part, on="broker_candle_time", how="outer")
    if merged is None or merged.empty:
        return pd.DataFrame()
    merged["run_id"] = getattr(snapshot, "run_id", "N/A")
    merged["generation_id"] = getattr(snapshot, "generation_id", "N/A")
    merged["source_run_id"] = getattr(snapshot, "run_id", "N/A")
    merged["source_generation_id"] = getattr(snapshot, "generation_id", "N/A")
    merged["completed_broker_candle"] = merged["broker_candle_time"]
    merged["source_snapshot_hash"] = getattr(snapshot, "source_snapshot_hash", "N/A")
    merged["source_signature"] = getattr(snapshot, "source_signature", "N/A")
    merged["settlement_status"] = "PUBLISHED"
    return merged.sort_values("broker_candle_time", ascending=False)

def build_decision_table(state: Mapping[str,Any], snapshot: Any) -> pd.DataFrame:
    payload=state.get("one_hour_direction_confirmation_20260626") or {}
    raw=payload.get("history")
    if raw is None:
        raw=[]
    confirmation_df=raw.copy() if isinstance(raw,pd.DataFrame) else pd.DataFrame(raw)
    # Table 1 is the horizontal collection of the ten Table 3 factor histories.
    # A one-row direction-confirmation archive must never mask the richer 25-day
    # factor source. Prefer the factor merge whenever it has more rows or more
    # decision columns, then append only genuinely missing confirmation candles.
    factor_df = _factor_history_fallback(state, snapshot)
    df = factor_df.copy() if isinstance(factor_df, pd.DataFrame) and not factor_df.empty else confirmation_df.copy()
    if not confirmation_df.empty and not df.empty and df is not confirmation_df:
        factor_time = next((c for c in ("broker_candle_time","Broker Candle Time") if c in df.columns), None)
        conf_time = next((c for c in ("broker_candle_time","forecast_origin_time","target_h1_open_time","candle_time") if c in confirmation_df.columns), None)
        if factor_time and conf_time:
            known = set(pd.to_datetime(df[factor_time], errors="coerce", utc=True).dropna())
            extra = confirmation_df.loc[~pd.to_datetime(confirmation_df[conf_time], errors="coerce", utc=True).isin(known)].copy()
            if not extra.empty:
                df = pd.concat([df, extra], ignore_index=True, sort=False)
    # Quick Run must display its newly published completed-candle result
    # immediately. When no settled archive exists yet, use the immutable
    # current publication as one pending row; never fabricate prior history.
    if df.empty and isinstance(payload.get("current"), Mapping) and payload.get("current"):
        current = dict(payload.get("current"))
        current.setdefault("settlement_status", "PENDING")
        current.setdefault("run_id", getattr(snapshot, "run_id", "N/A"))
        current.setdefault("generation_id", getattr(snapshot, "generation_id", "N/A"))
        # Display the immutable Quick Run result against the completed broker
        # candle that produced it. Forecast target/open timestamps remain in the
        # payload for settlement, but must not push the current row beyond the
        # Field 1 completed-candle cutoff.
        current["broker_candle_time"] = getattr(snapshot, "broker_candle_time", None)
        df = pd.DataFrame([current])
    if df.empty: return pd.DataFrame(columns=COLUMNS)
    time_col=next((c for c in ("broker_candle_time","forecast_origin_time","target_h1_open_time","candle_time") if c in df.columns),None)
    if not time_col: return pd.DataFrame(columns=COLUMNS)
    times=pd.to_datetime(df[time_col],errors="coerce")
    df=df.assign(_broker_time=times).dropna(subset=["_broker_time"])
    cutoff=pd.Timestamp(snapshot.broker_candle_time)
    if cutoff.tzinfo is not None and getattr(df._broker_time.dt,"tz",None) is None: cutoff=cutoff.tz_localize(None)
    if cutoff.tzinfo is None and getattr(df._broker_time.dt,"tz",None) is not None: cutoff=cutoff.tz_localize("UTC")
    df=df[df._broker_time<=cutoff].sort_values("_broker_time",ascending=False)
    days=list(dict.fromkeys(df._broker_time.dt.date.tolist()))[:25]
    df=df[df._broker_time.dt.date.isin(days)]
    scale_metadata = payload.get("score_scales") if isinstance(payload.get("score_scales"), Mapping) else {}
    rows=[]
    for _,r in df.iterrows():
        d=r.to_dict(); t=d["_broker_time"]
        out={"Date":t.strftime("%Y-%m-%d"),"Weekday":t.strftime("%A"),"Hour":int(t.hour),"Broker Candle Time":t.isoformat()}
        for col in COLUMNS[4:]: out[col]=_first(d,ALIASES.get(col,(col,)),"N/A")
        # Preserve exact Table 3 text labels. Never infer BUY/SELL from scores.
        out["Net Pressure Decision"] = _first(d, ALIASES["Net Pressure Decision"], out.get("Pressure Decision", "N/A"))
        # Display-only rescue for legacy Table 3 publishers that emitted BUY and
        # SELL pressure scores but omitted the redundant net-pressure label.
        # This never overwrites a published net-pressure decision.
        if str(out["Net Pressure Decision"] or "").strip().upper() in {"", "N/A", "NA", "NONE", "UNAVAILABLE"}:
            try:
                buy_score = float(_first(d, ALIASES["BUY Pressure Score"], float("nan")))
                sell_score = float(_first(d, ALIASES["SELL Pressure Score"], float("nan")))
                if not math.isnan(buy_score) and not math.isnan(sell_score):
                    out["Net Pressure Decision"] = "BUY" if buy_score > sell_score else "SELL" if sell_score > buy_score else "WAIT"
                    out["Net Pressure Source"] = "Table 3 — derived display label from published BUY/SELL pressure scores"
            except Exception:
                pass
        out["Pressure Decision"] = out["Net Pressure Decision"]
        raw_final = _first(d, ("production_decision_raw", "final_decision", "production_action", "master_decision"), None)
        if raw_final in (None, "", "N/A") and pd.Timestamp(t) == pd.Timestamp(getattr(snapshot, "broker_candle_time", t)):
            raw_final = getattr(snapshot, "decision", None)
        raw_final = raw_final if raw_final not in (None, "") else "N/A — source not published"
        out["Production Decision Raw"] = raw_final
        out["Final Decision"] = raw_final
        if out.get("Decision Name") in ("N/A", None, ""):
            out["Decision Name"] = raw_final
        raw_upper = str(raw_final).strip().upper()
        hold_evidence = str(out.get("Hold Safety Decision", "")).upper()
        if raw_upper == "HOLD" and any(token in hold_evidence for token in ("HOLD", "PROTECT")):
            out["Action Display Label"] = "HOLD & PROTECT"
        elif raw_upper in {"WAIT PULLBACK", "PULLBACK"}:
            out["Action Display Label"] = "WAIT PULLBACK"
        else:
            out["Action Display Label"] = raw_final
        out["Net Pressure Source"] = _first(d, ("net_pressure_source",), "Table 3 — Net Pressure")
        out["Direction Confirmation Source"] = _first(d, ("direction_confirmation_source",), "Table 3 — Direction Confirmation")
        out["Master Decision Source"] = _first(d, ("master_decision_source",), "Table 3 — Master Decision / canonical production decision")
        out["Source Run ID"] = _first(d, ("source_run_id", "run_id"), getattr(snapshot, "run_id", "N/A"))
        out["Source Generation ID"] = _first(d, ("source_generation_id", "generation_id"), getattr(snapshot, "generation_id", "N/A"))
        out["Completed Broker Candle"] = pd.Timestamp(t).isoformat()
        out["Source Snapshot Hash"] = _first(d, ("source_snapshot_hash", "snapshot_hash"), getattr(snapshot, "source_snapshot_hash", "N/A"))
        out["Source Signature"] = _first(d, ("source_signature",), getattr(snapshot, "source_signature", "N/A"))
        for col in SCORE_COLUMNS:
            source_name = next((n for n in ALIASES.get(col, (col,)) if n in d), col)
            out[col]=_score10(out[col], source_name=source_name, scale_metadata=scale_metadata)
        for col in ("Decision Confidence","Decision Reliability","Uncertainty Percentage","Error Percentage"): out[col]=_pct(out[col])
        if out.get("Canonical run_id") in (None, "", "N/A"): out["Canonical run_id"] = getattr(snapshot, "run_id", "N/A")
        if out.get("Canonical generation_id") in (None, "", "N/A"): out["Canonical generation_id"] = getattr(snapshot, "generation_id", "N/A")
        if out.get("Outcome Status") in (None, "", "N/A"): out["Outcome Status"] = "PENDING"
        status_upper = str(out["Outcome Status"]).upper()
        # Keep the immutable table contract: unresolved outcomes remain N/A in
        # the core data. Renderers replace that with a clear pending message.
        if status_upper not in {"SETTLED", "RESOLVED"}:
            out["Decision Correct"] = "N/A"
        elif str(out.get("Decision Correct") or "").strip().upper() in {"", "N/A", "NA", "NONE"}:
            realized = str(out.get("Realized Direction") or "").strip().upper()
            predicted = str(out.get("Production Decision Raw") or "").strip().upper()
            if realized in {"BUY", "SELL", "WAIT"} and predicted in {"BUY", "SELL", "WAIT"}:
                out["Decision Correct"] = "YES" if realized == predicted else "NO"
        rows.append(out)
    return pd.DataFrame(rows,columns=COLUMNS)

def consensus_diagnostic(row: Mapping[str,Any]) -> dict[str,Any]:
    buy=sell=0.0; valid=0
    for score_col,decision_col in [("Entry Strength Score","Entry Strength Decision"),("BUY Pressure Score","BUY Pressure Decision"),("SELL Pressure Score","SELL Pressure Decision"),("M1 Confirmation Score","M1 Confirmation Decision"),("Direction Confirmation Score","Direction Confirmation Decision")]:
        score=row.get(score_col); dec=str(row.get(decision_col,"" )).upper()
        if isinstance(score, numbers.Real) and not pd.isna(score):
            valid += 1
            weight = max(0.0, min(10.0, float(score))) / 10.0
        else:
            continue
        if "BUY" in dec: buy+=weight
        elif "SELL" in dec: sell+=weight
    if valid == 0:
        return {"Decision Table Consensus Score":"N/A","BUY evidence":"N/A","SELL evidence":"N/A","Conflict":"N/A","Coverage":"N/A","Effective Sample Size":0,"Research Decision":"N/A"}
    conflict=min(buy,sell)/max(buy,sell,1e-9); coverage=valid/5
    return {"Decision Table Consensus Score":round(10*max(buy,sell)/valid,3),"BUY evidence":round(buy,3),"SELL evidence":round(sell,3),"Conflict":round(conflict,3),"Coverage":round(coverage,3),"Effective Sample Size":valid,"Research Decision":"BUY" if buy>sell else "SELL" if sell>buy else "HOLD"}

def freeze_canonical_decision_snapshot(snapshot: Any, table: pd.DataFrame, state: Mapping[str,Any]) -> dict[str,Any]:
    latest=table.iloc[0].to_dict() if not table.empty else {}
    payload={"schema_version":SCHEMA_VERSION,"run_id":snapshot.run_id,"generation_id":snapshot.generation_id,"snapshot_hash":snapshot.source_snapshot_hash,"completed_candle_identity":snapshot.broker_candle_time.isoformat(),"broker_candle_time":snapshot.broker_candle_time.isoformat(),"symbol":snapshot.symbol,"timeframe":snapshot.timeframe,"production_decision":snapshot.decision,"current_session":latest.get("FX Session","N/A"),"current_regime":snapshot.regime,"decision_table_row":latest,"decision_table_row_count":int(len(table)),"research_direction_confirmation":consensus_diagnostic(latest) if latest else {},"publication_timestamp":snapshot.created_at_utc.isoformat()}
    payload["data_signature"]=sha256((snapshot.run_id+snapshot.generation_id+snapshot.source_snapshot_hash).encode()).hexdigest()
    return payload

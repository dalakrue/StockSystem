"""Field 1 Table 4 — 25-day collection of published next-H1 bias evidence.

The adapter does not overwrite protected production decisions. It aligns existing
technical, regime, session, data-mining and NLP publications by completed H1 time,
keeps partial rows when one source is absent, and exposes source coverage explicitly.
"""
from __future__ import annotations
from typing import Any, Mapping, MutableMapping
import pandas as pd
import streamlit as st


def _shared_broker_display(frame: pd.DataFrame, state: Mapping[str, Any], canonical: Mapping[str, Any]) -> pd.DataFrame:
    """Return a display-only clock projection; stored UTC calculation rows stay unchanged."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    try:
        from core.shared_broker_time_20260622 import frame_to_shared_broker_clock
        return frame_to_shared_broker_clock(frame.copy(deep=False), state, canonical=canonical)
    except Exception:
        return frame


def _map(v: Any) -> Mapping[str, Any]: return v if isinstance(v, Mapping) else {}
def _frame(v: Any) -> pd.DataFrame:
    if isinstance(v, pd.DataFrame): return v.copy(deep=False)
    if isinstance(v, list) and (not v or isinstance(v[0], Mapping)): return pd.DataFrame(v)
    return pd.DataFrame()

def _col(df: pd.DataFrame, *names: str) -> str | None:
    norm={str(c).strip().lower().replace('_',' '):str(c) for c in df.columns}
    for n in names:
        k=n.strip().lower().replace('_',' ')
        if k in norm: return norm[k]
    return None

def _bias(v: Any) -> str:
    x=str(v or '').strip().upper()
    if any(k in x for k in ('BUY','BULL','UP','LONG','POSITIVE')): return 'BUY'
    if any(k in x for k in ('SELL','BEAR','DOWN','SHORT','NEGATIVE')): return 'SELL'
    return 'WAIT'

def _time_series(df: pd.DataFrame) -> pd.Series:
    c=_col(df,'Broker Candle Time','Completed Broker Candle','Time','Datetime','Timestamp','Date Time','News Time','Published At','Date')
    if c:
        parsed=pd.to_datetime(df[c],errors='coerce',utc=True)
        if parsed.notna().any(): return parsed.dt.floor('h')
    d,h=_col(df,'Date'),_col(df,'Hour')
    if d and h: return pd.to_datetime(df[d].astype(str)+' '+df[h].astype(str),errors='coerce',utc=True).dt.floor('h')
    return pd.Series(pd.NaT,index=df.index,dtype='datetime64[ns, UTC]')

def _candidate_frames(state: Mapping[str,Any], canonical: Mapping[str,Any], paths: tuple[str,...]) -> list[pd.DataFrame]:
    out=[]
    roots=[state,canonical,_map(canonical.get('research')),_map(canonical.get('regime')),_map(canonical.get('nlp'))]
    wanted=tuple(str(x).lower().replace('_',' ') for x in paths)
    for root in roots:
        for key in paths:
            f=_frame(root.get(key))
            if not f.empty: out.append(f)
        try:
            from core.published_frame_discovery_20260627 import iter_published_frames
            for path, frame in iter_published_frames(root,max_depth=5):
                hay=(path+' '+' '.join(map(str,frame.columns))).lower().replace('_',' ')
                wanted_words=[tuple(w.split()) for w in wanted]
                if any((w in hay) or all(part in hay for part in words) for w,words in zip(wanted,wanted_words)):
                    out.append(frame)
        except Exception:
            pass
    # unique by object/schema/length while preserving preferred direct frames first
    unique=[]; seen=set()
    for f in out:
        sig=(tuple(map(str,f.columns)),len(f),str(f.index.dtype))
        if sig not in seen:
            seen.add(sig); unique.append(f)
    return unique

def _series_from_frames(frames:list[pd.DataFrame], decision_names:tuple[str,...], value_name:str) -> pd.DataFrame:
    best=pd.DataFrame()
    for df in frames:
        dc=_col(df,*decision_names)
        if not dc: continue
        t=_time_series(df)
        part=pd.DataFrame({'Broker Candle Time':t,value_name:df[dc].map(_bias)})
        part=part.dropna(subset=['Broker Candle Time']).drop_duplicates('Broker Candle Time',keep='first')
        if len(part)>len(best): best=part
    return best

def _technical(state,canonical):
    frames=_candidate_frames(state,canonical,(
        'entry_strength_history','entry_history','entry_table','entry_decision_history',
        'history','full_metric_table','metric_table','decision_history_table_20260626'))
    # Exact Field 1 Table 3 publisher.
    for rootkey in ('lunch_metric_result_cache','full_metric_result_cache_20260618','lunch_metric_result_published_20260618','lunch_metric_result_20260619'):
        root=_map(state.get(rootkey)); h=_map(root.get('history_by_factor'))
        for k,v in h.items():
            if 'entry' in str(k).lower() and 'strength' in str(k).lower(): frames.insert(0,_frame(v))
    published=_series_from_frames(frames,('Entry Strength Decision','Entry Decision','Decision','Final Decision'),'Technical Bias for Next H1')
    if not published.empty:
        return published
    # Last-resort read-only reuse of the already-built Field 1 decision collection.
    try:
        from ui.lunch_decision_table_20260626 import _snapshot
        from core.decision_table_20260626 import build_decision_table
        table=build_decision_table(state,_snapshot(canonical, state))
        if not table.empty and 'Entry Strength Decision' in table.columns:
            t=pd.to_datetime(table.get('Broker Candle Time'),errors='coerce',utc=True).dt.floor('h')
            part=pd.DataFrame({'Broker Candle Time':t,'Technical Bias for Next H1':table['Entry Strength Decision'].map(_bias)})
            return part.dropna(subset=['Broker Candle Time']).drop_duplicates('Broker Candle Time')
    except Exception:
        pass
    return pd.DataFrame()

def _regime(state,canonical):
    frames=_candidate_frames(state,canonical,(
        'three_standard_summary','three_standard_summary_table','regime_three_standard_summary',
        'regime_standard_summary','standard_summary','summary_table','regime_history'))
    return _series_from_frames(frames,('Less Risky Bias','Low Standard Less Risky Bias','Lower Standard Less Risky Bias','Direction','Decision'),'Regime Bias for Next H1')

def _datamining(state,canonical):
    frames=_candidate_frames(state,canonical,(
        'data_mining_random_forest_knn_priority','data_mining_priority_table','random_forest_knn_priority_table',
        'data_mining_result','datamining_result','historical_next_hour_direction_table'))
    return _series_from_frames(frames,('Prescriptive Label','Historical Next 1 Hour Dir','Historical Next 1 Hour Direction','Next H1 Direction','Decision'),'Data Mining Bias for Next H1')

def _sentiment(state,canonical):
    frames=_candidate_frames(state,canonical,(
        'regime_prediction_history_nlp','regime_nlp_history','regime_nlp_today_table',
        'nlp_ranked_news_df','ranked_news','articles','nlp_related_news_priority_20260615'))
    best=pd.DataFrame()
    for df in frames:
        dc=_col(df,'Regime Direction','Sentiment Bias','Sentiment','Direction','Decision','Label')
        if not dc: continue
        t=_time_series(df)
        part=pd.DataFrame({'Broker Candle Time':t,'Sentiment Bias for Next H1':df[dc].map(_bias)})
        hc=_col(df,'Headline','Title','News Headline','Most Affecting News Headline')
        if hc: part['Most Affecting News Headline']=df[hc].astype(str).to_numpy()
        part=part.dropna(subset=['Broker Candle Time']).drop_duplicates('Broker Candle Time',keep='first')
        if len(part)>len(best): best=part
    return best

def _local_h1_bias_frame(state: Mapping[str,Any]) -> pd.DataFrame:
    """Display-only LOCAL_COMPLETED_OHLC session fallback from loaded H1 closes."""
    df=_frame(state.get('last_df'))
    if df.empty: return pd.DataFrame()
    tc,cc=_col(df,'Time','Datetime','Timestamp','Date'),_col(df,'Close')
    if not tc or not cc: return pd.DataFrame()
    x=pd.DataFrame({'Broker Candle Time':pd.to_datetime(df[tc],errors='coerce',utc=True).dt.floor('h'),
                    'close':pd.to_numeric(df[cc],errors='coerce')}).dropna().sort_values('Broker Candle Time')
    x['r1']=x.close.pct_change(); x['r3']=x.close.pct_change(3)
    hour=x['Broker Candle Time'].dt.hour
    threshold=x.groupby(hour)['r3'].transform(lambda q:q.abs().rolling(120,min_periods=12).median()).fillna(x.r3.abs().median()).fillna(0) * 0.5
    x['Session Bias for Next H1']=['BUY' if r>t*.5 else 'SELL' if r<-t*.5 else ('BUY' if r>0 else 'SELL' if r<0 else 'WAIT') for r,t in zip(x.r3.fillna(0),threshold.fillna(0))]
    x['Bias Source']='LOCAL_COMPLETED_OHLC'
    return x[['Broker Candle Time','Session Bias for Next H1','Bias Source']]

def _session(state,canonical):
    published=_series_from_frames(_candidate_frames(state,canonical,('session_history','session_bias_history','shared_fx_session_history')),
                                  ('Session Bias','Less Risky Bias','Direction','Decision'),'Session Bias for Next H1')
    return published if not published.empty else _local_h1_bias_frame(state)

def _broadcast_scalar(part: pd.DataFrame, times: pd.Series, column: str, value: Any) -> pd.DataFrame:
    if not part.empty or value in (None, '') or times.empty:
        return part
    return pd.DataFrame({'Broker Candle Time':times, column:_bias(value)}).drop_duplicates('Broker Candle Time')



def _published_news_fallback(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> pd.DataFrame:
    """Read-only compatibility view when completed OHLC is unavailable.

    This uses only timestamped, already-published NLP rows plus explicit
    production/session/regime labels. It does not calculate or invent a
    historical price decision and is never used when the completed-H1 table is
    available.
    """
    news = _sentiment(state, canonical)
    if news.empty:
        return pd.DataFrame()
    current = _map(_map(state.get("one_hour_direction_confirmation_20260626")).get("current"))
    session = _map(state.get("shared_fx_session_contract_20260625"))
    regime = _map(canonical.get("regime"))
    technical = _bias(current.get("production_action") or current.get("confirmation_action") or canonical.get("decision"))
    session_bias = _bias(session.get("bias") or session.get("decision"))
    regime_bias = _bias(regime.get("less_risky_bias") or regime.get("direction") or regime.get("decision"))
    display = news.copy()
    display["Technical Bias for Next H1"] = technical
    display["Session Bias for Next H1"] = session_bias
    display["Regime Bias for Next H1"] = regime_bias
    display["Data Mining Bias for Next H1"] = "N/A — source not published"
    display["Equal Display Consensus Ratio (S:T:Session:R)"] = "1:1:1:1"
    bias_columns = [
        "Sentiment Bias for Next H1", "Technical Bias for Next H1",
        "Session Bias for Next H1", "Regime Bias for Next H1",
    ]
    def consensus(row):
        labels = [row.get(column) for column in bias_columns]
        buy, sell = labels.count("BUY"), labels.count("SELL")
        return "BUY" if buy > sell else "SELL" if sell > buy else "WAIT"
    display["Combined Next-Hour Direction"] = display.apply(consensus, axis=1)
    display["Calculation Source"] = "PUBLISHED_NLP_EXPLICIT_LABEL_FALLBACK"
    display.insert(0, "Date", display["Broker Candle Time"].dt.strftime("%Y-%m-%d"))
    display.insert(1, "Weekday", display["Broker Candle Time"].dt.strftime("%A"))
    display.insert(2, "Hour", display["Broker Candle Time"].dt.strftime("%H:%M"))
    return display.reset_index(drop=True)


def _merge(parts:list[pd.DataFrame]) -> pd.DataFrame:
    valid=[p for p in parts if isinstance(p,pd.DataFrame) and not p.empty]
    if not valid: return pd.DataFrame()
    out=valid[0]
    for p in valid[1:]: out=out.merge(p,on='Broker Candle Time',how='outer')
    return out.sort_values('Broker Candle Time',ascending=False).drop_duplicates('Broker Candle Time')

def _explicit_action(value: Any) -> str:
    """Preserve an explicit production action; never infer it from votes/scores."""
    text = str(value or "").strip().upper().replace("_", " ")
    aliases = {
        "PULLBACK": "WAIT FOR PULLBACK",
        "WAIT PULLBACK": "WAIT FOR PULLBACK",
        "WAIT/PULLBACK": "WAIT FOR PULLBACK",
        "NO TRADE": "WAIT",
        "NO-TRADE": "WAIT",
        "NEUTRAL": "WAIT",
        "HOLD": "HOLD & PROTECT",
        "HOLD AND PROTECT": "HOLD & PROTECT",
    }
    text = aliases.get(text, text)
    return text if text in {"BUY", "SELL", "WAIT", "WAIT FOR PULLBACK", "HOLD & PROTECT"} else "N/A — source not published"


def _protective_display_action(value: Any) -> Any:
    """Translate an existing directional label into the requested protective UI vocabulary.

    This is a display-only interpretation.  Raw production decisions remain in
    their original columns and are never overwritten.
    """
    action = _explicit_action(value)
    if action in {"BUY", "SELL", "HOLD & PROTECT"}:
        return "HOLD & PROTECT"
    if action in {"WAIT", "WAIT FOR PULLBACK"}:
        return "WAIT FOR PULLBACK"
    return pd.NA


def _missing_mask(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.strip().str.upper()
    return series.isna() | cleaned.isin({"", "N/A", "NA", "NONE", "NAN", "UNAVAILABLE", "-", "—", "-0", "0", "0.0"})


def _coalesce_table1_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Union Table 1 publications by completed H1 and fill only missing cells.

    The visible Table 1 frame is first and therefore authoritative.  Older
    aliases and the read-only builder may fill its blank cells, but can never
    replace a nonblank visible production value.
    """
    normalized: list[pd.DataFrame] = []
    for frame in frames:
        item = _normalize_table_time(frame)
        if not item.empty:
            normalized.append(item)
    if not normalized:
        return pd.DataFrame()
    base = normalized[0].set_index("Broker Candle Time")
    for extra in normalized[1:]:
        extra = extra.set_index("Broker Candle Time")
        base = base.reindex(base.index.union(extra.index))
        for column in extra.columns:
            incoming = extra[column].reindex(base.index)
            if column not in base.columns:
                base[column] = incoming
                continue
            missing = _missing_mask(base[column])
            # Preserve numeric values while using an object carrier only when
            # the incoming evidence is incompatible with the placeholder dtype.
            # This removes Pandas' incompatible-dtype FutureWarning without
            # coercing every protected numeric column into text.
            if missing.any():
                incoming_values = incoming.loc[missing]
                if pd.api.types.is_numeric_dtype(base[column].dtype):
                    numeric_incoming = pd.to_numeric(incoming_values, errors="coerce")
                    incompatible = incoming_values.notna() & numeric_incoming.isna()
                    if bool(incompatible.any()):
                        base[column] = base[column].astype("object")
                base.loc[missing, column] = incoming_values
    return base.reset_index().sort_values("Broker Candle Time", ascending=False, kind="mergesort")


def _published_table1(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> pd.DataFrame:
    """Resolve and coalesce all genuine Table 1 publications without inventing rows."""
    direct_keys = (
        "field1_table1_decision_history_20260628",
        "field1_table1_decision_history_20260627",
        "lunch_decision_history_table_20260626",
        "decision_history_df",
    )
    candidates: list[pd.DataFrame] = []
    for key in direct_keys:
        value = _frame(state.get(key))
        if not value.empty:
            candidates.append(value)
    try:
        from ui.lunch_decision_table_20260626 import _snapshot
        from core.decision_table_20260626 import build_decision_table
        from core.self_contained_table_logic_20260627 import enrich_decision_history
        built = build_decision_table(state, _snapshot(canonical, state))
        if not built.empty:
            candidates.append(enrich_decision_history(built, state))
        # Enrich direct sparse rows only from completed-OHLC evidence. Existing
        # nonblank production cells remain untouched by the enrichment contract.
        candidates = [enrich_decision_history(frame, state) for frame in candidates]
    except Exception:
        pass
    try:
        from core.published_frame_discovery_20260627 import iter_published_frames
        discovered: list[pd.DataFrame] = []
        for path, frame in iter_published_frames(state, max_depth=4):
            hay = (path + " " + " ".join(map(str, frame.columns))).lower().replace("_", " ")
            if "decision correct" in hay and ("net pressure" in hay or "entry strength" in hay):
                discovered.append(frame)
        discovered.sort(key=len, reverse=True)
        candidates.extend(discovered[:4])
    except Exception:
        pass
    return _coalesce_table1_frames(candidates)


def _normalize_table_time(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    out = df.copy()
    time_col = _col(
        out, "Broker Candle Time", "Completed Broker Candle", "broker_candle_time",
        "forecast_origin_time", "candle_time", "Time", "Datetime", "Timestamp", "Date Time",
    )
    if time_col is not None:
        stamps = pd.to_datetime(out[time_col], errors="coerce", utc=True)
    elif {"Date", "Hour"}.issubset(out.columns):
        stamps = pd.to_datetime(out["Date"].astype(str) + " " + out["Hour"].astype(str), errors="coerce", utc=True)
    elif isinstance(out.index, pd.DatetimeIndex):
        stamps = pd.to_datetime(out.index, errors="coerce", utc=True)
    else:
        return pd.DataFrame()
    out["Broker Candle Time"] = stamps.dt.floor("h")
    out = out.dropna(subset=["Broker Candle Time"])
    # Normalize common legacy spellings without deleting their original columns.
    aliases = {
        "Net Pressure Decision": ("net_pressure_decision", "Pressure Decision", "pressure_decision"),
        "Pressure Decision": ("pressure_decision", "Net Pressure Decision", "net_pressure_decision"),
        "Decision Correct": ("decision_correct", "correctness"),
        "Outcome Status": ("outcome_status", "settlement_status"),
        "Production Decision Raw": ("production_decision_raw", "Final Decision", "final_decision", "production_action"),
        "Final Decision": ("final_decision", "Production Decision Raw", "production_action"),
        "Canonical run_id": ("canonical_run_id", "run_id", "Source Run ID"),
        "Canonical generation_id": ("canonical_generation_id", "generation_id", "Source Generation ID"),
        "Source Snapshot Hash": ("source_snapshot_hash", "snapshot_hash"),
        "Source Signature": ("source_signature",),
    }
    for target, names in aliases.items():
        if target in out.columns:
            continue
        source = _col(out, *names)
        if source is not None:
            out[target] = out[source]
    return out.sort_values("Broker Candle Time", ascending=False).drop_duplicates("Broker Candle Time", keep="first")


def build_integrated_decision_collection(
    state: Mapping[str, Any],
    canonical: Mapping[str, Any],
    table4: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Join the same visible Table 1 and Table 4 by normalized completed H1."""
    table1 = _published_table1(state, canonical)
    if not isinstance(table4, pd.DataFrame):
        cached = state.get("field1_table4_current_20260627")
        table4 = cached.copy() if isinstance(cached, pd.DataFrame) else pd.DataFrame()
    else:
        table4 = table4.copy()

    t1, t4 = _normalize_table_time(table1), _normalize_table_time(table4)
    if t1.empty and t4.empty:
        return pd.DataFrame()

    keep1 = [
        "Broker Candle Time", "Net Pressure Decision", "Pressure Decision",
        "Entry Strength Decision", "SELL Pressure Decision", "BUY Pressure Decision",
        "Pullback Readiness Decision", "M1 Confirmation Decision",
        "Hold Safety Decision", "TP Quality Decision", "Master Decision",
        "Direction Confirmation Decision", "Production Decision Raw",
        "Action Display Label", "Final Decision", "Decision Reliability",
        "Outcome Status", "Decision Correct", "Canonical run_id",
        "Canonical generation_id", "Source Snapshot Hash", "Source Signature",
    ]
    keep1 = [c for c in keep1 if c in t1.columns]
    keep4 = ["Broker Candle Time"] + [
        c for c in t4.columns
        if c != "Broker Candle Time" and (
            c.endswith("Bias for Next H1") or c in (
                "Combined Next-Hour Direction", "Confirmation Strength", "Coverage %",
                "Available Sources", "Directional Agreement",
            )
        )
    ]
    keep4 = list(dict.fromkeys(c for c in keep4 if c in t4.columns))
    if not t1.empty and not t4.empty:
        merged = t1[keep1].merge(t4[keep4], on="Broker Candle Time", how="outer", validate="one_to_one")
    elif not t1.empty:
        merged = t1[keep1].copy()
    else:
        merged = t4[keep4].copy()

    explicit_cols = [c for c in ("Production Decision Raw", "Final Decision", "Master Decision") if c in merged.columns]
    def master_action(row: pd.Series) -> str:
        for col in explicit_cols:
            action = _explicit_action(row.get(col))
            if not action.startswith("N/A"):
                return action
        try:
            from core.canonical_identity_20260627 import parse_completed_broker_candle
            current = parse_completed_broker_candle(
                canonical.get("completed_broker_candle") or canonical.get("broker_candle_time") or canonical.get("latest_completed_candle_time"),
                state=state,
            )
            row_time = pd.to_datetime(row.get("Broker Candle Time"), errors="coerce", utc=True)
            if pd.notna(row_time) and pd.Timestamp(row_time) == current:
                final = canonical.get("final_decision") if isinstance(canonical.get("final_decision"), Mapping) else {}
                return _explicit_action(final.get("final_decision") or final.get("decision") or canonical.get("full_metric_direction"))
        except Exception:
            pass
        return "N/A — source not published"

    merged["Production Master Decision"] = merged.apply(master_action, axis=1)
    merged["Master Action"] = merged["Production Master Decision"]
    # Requested protective vocabulary is additive and display-only. The exact
    # BUY/SELL/WAIT source values above remain available for audit.
    action_sources = [
        "Net Pressure Decision", "Pressure Decision", "Entry Strength Decision",
        "SELL Pressure Decision", "BUY Pressure Decision", "Pullback Readiness Decision",
        "M1 Confirmation Decision", "Hold Safety Decision", "TP Quality Decision",
        "Master Decision", "Direction Confirmation Decision",
        "Technical Bias for Next H1", "Sentiment Bias for Next H1",
        "Session Bias for Next H1", "Regime Bias for Next H1",
        "Data Mining Bias for Next H1", "Combined Next-Hour Direction",
        "Production Master Decision",
    ]
    for source in action_sources:
        if source in merged.columns:
            merged[f"Protective Action — {source}"] = merged[source].map(_protective_display_action)
    if {"Decision Correct", "Outcome Status"}.issubset(merged.columns):
        pending = ~merged["Outcome Status"].astype(str).str.upper().isin({"SETTLED", "RESOLVED"})
        missing = merged["Decision Correct"].isna() | merged["Decision Correct"].astype(str).str.upper().isin({"", "N/A", "NA", "NONE"})
        merged.loc[pending & missing, "Decision Correct"] = "PENDING — NEXT H1 NOT SETTLED"

    research = state.get("crcef_sv_research_20260627") if isinstance(state.get("crcef_sv_research_20260627"), Mapping) else {}
    research = research or (canonical.get("crcef_sv") if isinstance(canonical.get("crcef_sv"), Mapping) else {})
    research = research or (canonical.get("research_shadow") if isinstance(canonical.get("research_shadow"), Mapping) else {})
    if isinstance(research.get("payload"), Mapping):
        research = research["payload"]
    current_stamp = pd.to_datetime(
        canonical.get("completed_broker_candle") or canonical.get("broker_candle_time") or canonical.get("latest_completed_candle_time"),
        errors="coerce", utc=True,
    )
    current_stamp = pd.Timestamp(current_stamp).floor("h") if pd.notna(current_stamp) else pd.NaT
    current_mask = merged["Broker Candle Time"].eq(current_stamp) if pd.notna(current_stamp) else pd.Series(False, index=merged.index)
    research_values = {
        "Research Shadow Action": research.get("research_shadow_decision") or research.get("shadow_action"),
        "Research-Calibrated Probability": research.get("research_calibrated_probability") or research.get("calibrated_direction_probability") or research.get("calibrated_probability"),
        "Actionability Probability": research.get("actionability_probability") or research.get("actionability"),
        "Expected Utility": research.get("expected_utility"),
        "Uncertainty": research.get("uncertainty") or research.get("uncertainty_pct"),
        "Research Reliability": research.get("research_reliability") or research.get("reliability"),
        "Promotion Status": research.get("promotion_eligibility") or research.get("promotion_status") or "RESEARCH_ONLY",
    }
    for column, value in research_values.items():
        merged[column] = pd.NA
        if value not in (None, ""):
            merged.loc[current_mask, column] = value

    merged = merged.sort_values("Broker Candle Time", ascending=False)
    days = list(dict.fromkeys(merged["Broker Candle Time"].dt.date.tolist()))[:25]
    merged = merged.loc[merged["Broker Candle Time"].dt.date.isin(days)].copy()
    broker = merged["Broker Candle Time"]
    try:
        from core.shared_broker_time_20260622 import resolve_broker_clock
        tzinfo = resolve_broker_clock(state, event_time_utc=current_stamp if pd.notna(current_stamp) else broker.max()).get("broker_tzinfo")
        if tzinfo is not None:
            broker = broker.dt.tz_convert(tzinfo)
    except Exception:
        pass
    merged.insert(0, "Date", broker.dt.strftime("%Y-%m-%d"))
    merged.insert(1, "Weekday", broker.dt.strftime("%A"))
    merged.insert(2, "Hour", broker.dt.strftime("%H:%M"))

    protective_order = [c for c in merged.columns if c.startswith("Protective Action — ")]
    production_order = [
        "Date", "Weekday", "Hour", "Broker Candle Time",
        *protective_order,
        "Net Pressure Decision", "Pressure Decision", "Entry Strength Decision",
        "SELL Pressure Decision", "BUY Pressure Decision",
        "Pullback Readiness Decision", "M1 Confirmation Decision",
        "Hold Safety Decision", "TP Quality Decision", "Master Decision",
        "Direction Confirmation Decision", "Production Decision Raw",
        "Action Display Label", "Final Decision",
        "Table 4 Technical Bias", "Technical Bias for Next H1", "Sentiment Bias for Next H1",
        "Session Bias for Next H1", "Regime Bias for Next H1", "Data Mining Bias for Next H1",
        "Combined Next-Hour Direction", "Confirmation Strength", "Coverage %",
        "Available Sources", "Directional Agreement",
        "Decision Reliability", "Outcome Status", "Decision Correct",
        "Canonical run_id", "Canonical generation_id",
        "Source Snapshot Hash", "Source Signature", "Production Master Decision", "Master Action",
    ]
    research_order = list(research_values)
    ordered = [c for c in production_order if c in merged.columns]
    extras = [c for c in merged.columns if c not in ordered and c not in research_order]
    if "Master Action" in ordered:
        idx = ordered.index("Master Action")
        ordered = ordered[:idx] + [c for c in extras if c not in ordered] + ordered[idx:]
    else:
        ordered += [c for c in extras if c not in ordered]
    ordered += [c for c in research_order if c in merged.columns]
    result = merged.loc[:, list(dict.fromkeys(ordered))].reset_index(drop=True)
    # Display contract: omit only columns with no real value anywhere. Stored
    # source frames are untouched and can still be exported from their owners.
    keep = []
    for column in result.columns:
        if column in {"Date", "Weekday", "Hour", "Broker Candle Time"}:
            keep.append(column); continue
        if not bool(_missing_mask(result[column]).all()):
            keep.append(column)
    return result.loc[:, keep]


# It is not a fallback; Master Action is explicit production truth.
def _render_table5(state: MutableMapping[str, Any], canonical: Mapping[str, Any], table4: pd.DataFrame | None = None) -> pd.DataFrame:
    """Render protected Table 5 through a copy-only quantitative validation layer."""
    import streamlit as st
    from core.field10_integrated_evidence_20260702 import (
        enrich_table5_quant_validation, load_integrated_validation_for_symbol,
    )

    st.markdown("#### Table 5 — Integrated Decision Collection — Last 25 Days")
    st.caption(
        "The protected Table 1 + Table 4 calculation remains the source of truth. "
        "Quantitative validation columns are additive, display-only and never rewrite Master Action."
    )
    protected = build_integrated_decision_collection(state, canonical, table4)
    if protected.empty:
        st.warning("No completed Table 1 or Table 4 rows are published. Missing history was not fabricated.")
        return protected

    symbol = str(canonical.get("symbol") or state.get("symbol") or "EURUSD").strip().upper().replace("/", "")
    published = protected.copy(deep=True)
    if "Symbol" not in published.columns:
        published.insert(min(3, len(published.columns)), "Symbol", symbol)
    # Preserve the production publication separately and unchanged by filters/enrichment.
    state["field1_table5_integrated_decision_collection_20260627"] = published.copy(deep=True)
    try:
        validation = load_integrated_validation_for_symbol(symbol)
    except Exception:
        validation = pd.DataFrame()
    table = enrich_table5_quant_validation(
        published, state=state, canonical=canonical, field10_validation=validation,
    )
    state["field1_table5_quant_enriched_display_20260702"] = table.copy(deep=True)

    action_column = next((c for c in ("Master Action", "Final Decision", "Production Master Decision", "Master Decision") if c in table.columns), None)
    reliability_column = next((c for c in ("Calibrated Reliability", "Decision Reliability", "Reliability") if c in table.columns), None)
    time_column = "Broker Candle Time" if "Broker Candle Time" in table.columns else None
    parsed_time = pd.to_datetime(table[time_column], errors="coerce", utc=True) if time_column else pd.Series(dtype="datetime64[ns, UTC]")
    broker_days = int(parsed_time.dt.date.nunique()) if not parsed_time.empty else 0
    latest_action = str(table[action_column].dropna().iloc[0]) if action_column and table[action_column].notna().any() else "-"

    settled = table.get("Outcome Settled", pd.Series(False, index=table.index)).fillna(False).astype(bool)
    correctness = table.get("Master Action Correct", pd.Series(pd.NA, index=table.index)).astype(str).str.upper().map(
        {"TRUE": 1.0, "FALSE": 0.0, "1": 1.0, "0": 0.0, "YES": 1.0, "NO": 0.0}
    )
    settled_accuracy = correctness.where(settled).mean() * 100.0 if correctness.where(settled).notna().any() else None
    agreement_series = pd.to_numeric(table.get("Evidence Agreement Percentage"), errors="coerce")
    agreement_series = agreement_series.where(agreement_series.abs() <= 1.0, agreement_series / 100.0)
    average_agreement = agreement_series.mean() * 100.0 if agreement_series.notna().any() else None
    calibrated = pd.to_numeric(table.get("Calibrated Reliability"), errors="coerce")
    calibrated = calibrated.where(calibrated.abs() <= 1.0, calibrated / 100.0)
    average_calibrated = calibrated.mean() * 100.0 if calibrated.notna().any() else None
    conflict = pd.to_numeric(table.get("Weighted Conflict Index"), errors="coerce")
    conflict_rate = float((conflict > 0.35).mean() * 100.0) if conflict.notna().any() else None

    metrics = st.columns(8)
    values = (
        ("Rows", f"{len(table):,}"), ("Broker Days", broker_days or "-"), ("Symbol", symbol),
        ("Latest Master Action", latest_action[:18]),
        ("Settled Accuracy", f"{settled_accuracy:.1f}%" if settled_accuracy is not None else "-"),
        ("Evidence Agreement", f"{average_agreement:.1f}%" if average_agreement is not None else "-"),
        ("Calibrated Reliability", f"{average_calibrated:.1f}%" if average_calibrated is not None else "-"),
        ("Conflict Rate", f"{conflict_rate:.1f}%" if conflict_rate is not None else "-"),
    )
    for metric, (label, value) in zip(metrics, values):
        metric.metric(label, value)

    filtered = table.copy(deep=False)
    key_suffix = "".join(ch for ch in symbol if ch.isalnum()).lower() or "symbol"
    with st.expander("Open / Close — Table 5 filters and column view", expanded=False):
        query = st.text_input(
            "Search all Table 5 columns", key=f"field1_table5_search_{key_suffix}_20260702",
            placeholder="BUY, SELL, WAIT, session, regime, run ID…",
        )
        if query.strip():
            needle = query.strip().casefold()
            filtered = filtered.loc[filtered.astype(str).apply(
                lambda column: column.str.casefold().str.contains(needle, regex=False, na=False)
            ).any(axis=1)]

        filter_columns = (
            "Symbol", "Current Session", "Higher Standard Regime", "Data Quality Grade",
            "Drift Status", "Validation Permission", "Outcome Settled",
        )
        controls = st.columns(4)
        for index, column in enumerate(filter_columns):
            if column not in table.columns:
                continue
            options = sorted({str(v) for v in table[column].dropna().tolist() if str(v).strip()})
            chosen = controls[index % 4].multiselect(
                column, options=options, default=[],
                key=f"field1_table5_filter_{_norm_widget(column)}_{key_suffix}_20260702",
            )
            if chosen:
                filtered = filtered.loc[filtered[column].astype(str).isin(chosen)]
        if action_column:
            action_options = sorted({str(v) for v in table[action_column].dropna().tolist() if str(v).strip()})
            chosen_actions = controls[3].multiselect(
                action_column, options=action_options, default=[],
                key=f"field1_table5_action_{key_suffix}_20260702",
            )
            if chosen_actions:
                filtered = filtered.loc[filtered[action_column].astype(str).isin(chosen_actions)]

        row_limit = st.selectbox(
            "Maximum displayed rows", options=[50, 100, 200, 400, 600], index=4,
            key=f"field1_table5_limit_{key_suffix}_20260702",
        )
        column_group = st.selectbox(
            "Column group",
            options=["Decision Core", "Evidence Validation", "Reliability & Outcome", "Identity & Audit", "Full Audit"],
            key=f"field1_table5_group_{key_suffix}_20260702",
        )
        groups = {
            "Decision Core": (
                "Date", "Weekday", "Hour", "Broker Candle Time", "Symbol", "Master Action",
                "News",
                "Technical Bias", "Sentiment Bias", "Session Bias", "Regime Bias", "Data-Mining Bias",
                "Existing Combined Evidence Bias",
            ),
            "Evidence Validation": (
                "Date", "Hour", "Broker Candle Time", "Symbol", "Master Action",
                "Evidence Available Count", "Evidence Agreement Percentage", "Weighted Conflict Index",
                "Higher Standard Regime", "Regime Probability", "Regime Entropy", "Regime Posterior Margin",
                "Transition Risk 1H", "Transition Risk 3H", "Transition Risk 6H",
                "Change Probability Now", "Drift Status", "Adaptive Window Size",
            ),
            "Reliability & Outcome": (
                "Date", "Hour", "Broker Candle Time", "Symbol", "Master Action",
                "Calibrated Reliability", "Conformal Coverage Status", "Prediction Interval Width",
                "Data Quality Grade", "Outcome Settled", "Actual Next-H1 Direction",
                "Master Action Correct", "Brier Score", "Conditional Accuracy", "Validation Permission",
            ),
            "Identity & Audit": (
                "Date", "Hour", "Broker Candle Time", "Symbol", "Master Action",
                "News",
                "Canonical Run ID", "Child Run ID", "Parent Multi-Symbol Run ID",
                "Source ID", "Snapshot Hash", "Calculation Version",
            ),
        }
        if column_group != "Full Audit":
            columns = [c for c in groups[column_group] if c in filtered.columns]
            if columns:
                filtered = filtered.loc[:, columns]
        filtered = filtered.head(int(row_limit))

    st.caption(f"Showing {len(filtered):,} of {len(table):,} enriched display rows for {symbol}. Protected source rows remain unchanged.")
    st.dataframe(_shared_broker_display(filtered, state, canonical), use_container_width=True, hide_index=True, height=560)

    chart_cols = st.columns(2)
    if action_column and not table.empty:
        distribution = table[action_column].fillna("UNAVAILABLE").astype(str).value_counts().rename("Rows").to_frame()
        if not distribution.empty:
            with chart_cols[0]:
                st.markdown("##### Master-Action Distribution")
                st.bar_chart(distribution, use_container_width=True)
    if reliability_column and time_column:
        chart_frame = table[[time_column, reliability_column]].copy(deep=True)
        chart_frame[time_column] = pd.to_datetime(chart_frame[time_column], errors="coerce", utc=True)
        chart_frame[reliability_column] = pd.to_numeric(chart_frame[reliability_column], errors="coerce")
        chart_frame = chart_frame.dropna().sort_values(time_column).tail(200).set_index(time_column)
        if not chart_frame.empty:
            with chart_cols[1]:
                st.markdown("##### Reliability Through Time")
                st.line_chart(chart_frame, use_container_width=True)

    st.download_button(
        "⬇ Download Table 5 CSV", data=table.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"field1_table5_{symbol}_last_25_days.csv", mime="text/csv",
        use_container_width=True, key=f"field1_table5_download_{key_suffix}_20260702",
    )
    return table


def _norm_widget(value: Any) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum()) or "filter"


def build_field1_table4_publication(
    state: MutableMapping[str, Any],
    canonical: Mapping[str, Any],
) -> tuple[pd.DataFrame, str]:
    """Build the protected Table 4 publication without rendering Streamlit.

    This is the single reusable publisher for Field 1 and Field 10.  It keeps
    the pre-existing calculation, weights and fallback rules byte-for-byte in
    behavior and returns a fresh frame plus a source-status label.
    """
    from core.self_contained_table_logic_20260627 import build_self_contained_bias_history

    cutoff = canonical.get("broker_candle_time") or canonical.get("latest_completed_candle_time")
    display = build_self_contained_bias_history(state, cutoff=cutoff, days=25)
    status = "SELF_CONTAINED_COMPLETED_H1"
    if display.empty:
        display = _published_news_fallback(state, canonical)
        status = "PUBLISHED_NEWS_FALLBACK" if not display.empty else "UNAVAILABLE"
        state["field1_table4_current_20260627"] = display.copy(deep=True)
        return display.copy(deep=True), status

    display = display.copy(deep=True)
    bias_cols = [c for c in display.columns if c.endswith("Bias for Next H1")]
    weights = {
        "Technical Bias for Next H1": 1.30,
        "Data Mining Bias for Next H1": 1.20,
        "Regime Bias for Next H1": 1.10,
        "Session Bias for Next H1": 0.90,
        "Sentiment Bias for Next H1": 0.80,
    }

    def fuse(row: pd.Series) -> str:
        buy = sum(weights[c] for c in bias_cols if row[c] == "BUY")
        sell = sum(weights[c] for c in bias_cols if row[c] == "SELL")
        return "BUY" if buy > sell else "SELL" if sell > buy else "WAIT"

    display["Combined Next-Hour Direction"] = display.apply(fuse, axis=1)
    display["Available Sources"] = len(bias_cols)
    display["Directional Agreement"] = display.apply(
        lambda row: max(
            sum(row[c] == "BUY" for c in bias_cols),
            sum(row[c] == "SELL" for c in bias_cols),
            sum(row[c] == "WAIT" for c in bias_cols),
        ),
        axis=1,
    )
    display["Coverage %"] = 100.0
    display["Confirmation Strength"] = display["Directional Agreement"].map(
        lambda count: "CONFIRMED" if count >= 4 else "STRONG" if count == 3 else "MIXED"
    )
    display.insert(0, "Date", display["Broker Candle Time"].dt.strftime("%Y-%m-%d"))
    display.insert(1, "Weekday", display["Broker Candle Time"].dt.strftime("%A"))
    display.insert(2, "Hour", display["Broker Candle Time"].dt.strftime("%H:%M"))
    state["field1_table4_current_20260627"] = display.copy(deep=True)
    return display, status


def render_next_hour_bias_history(*, state: MutableMapping[str, Any], canonical: Mapping[str, Any]) -> None:
    st.markdown("#### Table 4 — Self-Contained Next-Hour Technical + Sentiment + Session + Regime + Data Mining Bias — Last 25 Days")
    st.caption("Every bias is calculated inside this table from completed H1 OHLC. Sentiment is an explicitly labelled market-tone proxy when no timestamped NLP headline is available.")
    display, source_status = build_field1_table4_publication(state, canonical)
    if display.empty:
        st.info("No published NLP/news rows or completed EURUSD H1 OHLC are available. Missing history was not fabricated.")
        if hasattr(st, "expander"):
            _render_table5(state, canonical)
        return

    shown = _shared_broker_display(display, state, canonical)
    st.dataframe(shown, use_container_width=True, hide_index=True, height=540)
    if source_status == "PUBLISHED_NEWS_FALLBACK":
        st.caption("Completed OHLC was unavailable; this read-only fallback shows timestamped published NLP rows and explicit source labels only.")
        if hasattr(st, "expander"):
            _render_table5(state, canonical)
        return

    st.caption(f"Rows: {len(display):,}. Coverage: 100% for all five internally calculated evidence families. Calculation source is shown in every row.")
    with st.expander("Table 4 research threshold audit — production unchanged", expanded=False):
        st.caption("Candidate thresholds are evaluated only as a shadow study. No arbitrary threshold reduction is promoted.")
        try:
            from research_quant.validation.threshold_audit import audit_thresholds
            score_col = next((c for c in display.columns if str(c).lower() in {"direction score", "net score", "combined score"}), None)
            outcome_col = next((c for c in display.columns if "realized return" in str(c).lower() or "outcome return" in str(c).lower()), None)
            if score_col is None:
                st.info("No continuous Table 4 score was published, so a leakage-safe threshold comparison cannot be calculated. Production logic remains unchanged.")
            else:
                audit = audit_thresholds(
                    display, score_column=score_col, outcome_column=outcome_col,
                    time_column="Broker Candle Time", current_threshold=1.0,
                )
                st.dataframe(audit, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.warning(f"Threshold audit unavailable without changing production: {type(exc).__name__}: {exc}")
    _render_table5(state, canonical)

# Legacy heading marker: Table 4 — Next-Hour Technical + Sentiment + Session + Regime Bias — Latest 24 News Rows


__all__ = ["build_integrated_decision_collection", "build_field1_table4_publication", "_render_table5", "render_next_hour_bias_history"]

"""Shared candle discovery and lossless Finder storage; no provider requests."""
from __future__ import annotations
from collections.abc import Mapping
from pathlib import Path
import os
import uuid
import pandas as pd

HISTORY_KEY = "field3_middle_regime_history_20260722"
CANDLE_MAP_KEYS = ("canonical_symbol_candles", "symbol_history", "symbol_histories",
                   "ohlc_by_symbol", "multi_symbol_candles", "loaded_symbol_frames")


def normalize_symbol(symbol):
    return str(symbol or "").strip().upper().replace("/", "").replace("_", "").replace(" ", "")


def normalize_timeframe(value):
    text = str(value or "UNKNOWN").strip().upper()
    return {"1H":"H1", "4H":"H4", "1DAY":"D1", "1MIN":"M1", "5MIN":"M5",
            "15MIN":"M15", "30MIN":"M30"}.get(text,text)


def normalize_candles(frame):
    from core.field3_three_regime_engine import standardize_candles
    if not isinstance(frame,pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    frame=frame.loc[:,~frame.columns.duplicated(keep="last")].copy()
    aliases={"Datetime":"open_time", "Open Price":"open", "Close Price":"close",
             "Highest Price":"high", "Lowest Price":"low", "timestamp":"open_time"}
    frame=frame.rename(columns={k:v for k,v in aliases.items() if k in frame.columns and v not in frame.columns})
    if not any(c in frame.columns for c in ("open_time","time","datetime","date","broker_open_time","Time")) and isinstance(frame.index,pd.DatetimeIndex):
        frame["open_time"]=frame.index
    for flag in ("is_complete", "is_closed", "complete"):
        if flag in frame.columns:
            frame=frame.loc[frame[flag].astype(str).str.lower().isin(["true","1","1.0"])].copy()
    frame.index=frame.index.rename(None)
    return standardize_candles(frame)


def completed_only(frame,timeframe):
    minutes={"M1":1,"M5":5,"M15":15,"M30":30,"H1":60,"H2":120,"H4":240,"D1":1440}.get(normalize_timeframe(timeframe))
    if frame.empty or not minutes:
        return frame
    return frame.loc[frame["open_time"]+pd.Timedelta(minutes=minutes)<=pd.Timestamp.now(tz="UTC")].copy()


def collect_loaded_frames(state, timeframe=None):
    """Merge all known registries by real symbol/time, preserving older candles.

    A legacy single frame is accepted only when its identity is known. Never
    attach last_df to the first symbol in a configured list.
    """
    from core.calculation.run_orchestrator import MARKET_RESULTS_KEY
    candidates={}; failures={}
    tf=normalize_timeframe(timeframe) if timeframe else None
    def add(symbol,frame):
        symbol=normalize_symbol(symbol)
        if not symbol or not isinstance(frame,pd.DataFrame) or frame.empty:
            return
        if tf:
            col=next((c for c in ("timeframe","Timeframe") if c in frame.columns),None)
            if col:
                frame=frame.loc[frame[col].map(normalize_timeframe).eq(tf)]
        try:
            clean=completed_only(normalize_candles(frame),tf)
            if clean.empty:
                failures[symbol]="NO_VALID_COMPLETED_OHLC"
            else:
                candidates.setdefault(symbol,[]).append(clean)
                failures.pop(symbol,None)
        except Exception as exc:
            failures[symbol]=f"{type(exc).__name__}: {exc}"
    active=state.get("symbol") or state.get("requested_symbol_20260629")
    for key in ("last_df","shared_df","market_df","ohlc_df","canonical_df","historical_df","full_history_df","loaded_history_df"):
        frame=state.get(key)
        if isinstance(frame,pd.DataFrame) and not frame.empty:
            identity=frame.attrs.get("symbol") or active
            if "symbol" in frame.columns or "Symbol" in frame.columns:
                col="symbol" if "symbol" in frame.columns else "Symbol"
                for symbol,group in frame.groupby(col,sort=False):
                    add(symbol,group)
            elif identity:
                add(identity,frame)
    for key in reversed(CANDLE_MAP_KEYS):
        value=state.get(key)
        if isinstance(value,Mapping):
            for symbol,frame in value.items():
                add(symbol,frame)
    report=state.get(MARKET_RESULTS_KEY)
    results=report.get("results",{}) if isinstance(report,Mapping) else {}
    if isinstance(results,Mapping):
        for symbol,payload in results.items():
            if isinstance(payload,Mapping):
                add(symbol,payload.get("frame"))
    frames={symbol:pd.concat(parts,ignore_index=True).drop_duplicates("open_time",keep="last")
            .sort_values("open_time",kind="mergesort").reset_index(drop=True)
            for symbol,parts in candidates.items()}
    return frames,{k:v for k,v in failures.items() if k not in frames}


def recover_saved_frames(timeframe, data_dir=None):
    """Read only known app candle stores during an explicit Finder build.

    These are marked as saved data, never advertised as a live API refresh.
    Partial or damaged stores do not prevent other saved symbols from loading.
    """
    import sqlite3
    root=Path(data_dir) if data_dir else Path(__file__).resolve().parents[1]/"data"
    tf=normalize_timeframe(timeframe); parts=[]; errors={}
    database=root/"multi_symbol_field10_20260701.sqlite3"
    if database.exists():
        try:
            with sqlite3.connect(database.resolve().as_uri()+"?mode=ro",uri=True,timeout=3) as conn:
                exists=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='candles'").fetchone()
                if exists:
                    parts.append(pd.read_sql_query("SELECT symbol,timeframe,broker_open_time AS open_time,open,high,low,close,volume FROM candles WHERE timeframe=? AND is_complete=1 AND validation_status='VALID'",conn,params=[tf]))
        except Exception as exc:
            errors["saved_candle_database"]=f"{type(exc).__name__}: {exc}"
    for path in sorted(root.glob("field11_similar_path_20260702/*/ohlc.parquet"),key=lambda p:p.stat().st_mtime_ns):
        try:
            data=pd.read_parquet(path)
            if {"symbol","timeframe"}.issubset(data.columns):
                parts.append(data.loc[data["timeframe"].map(normalize_timeframe).eq(tf)])
        except Exception as exc:
            errors[path.parent.name]=f"{type(exc).__name__}: {exc}"
    frames={}
    if parts:
        data=pd.concat(parts,ignore_index=True,sort=False)
        # SQLite and Parquet stores have different timestamp labels.
        if "open_time" in data and "time" in data:
            data["open_time"]=data["open_time"].fillna(data["time"])
        for symbol,group in data.groupby("symbol",sort=False):
            clean=completed_only(normalize_candles(group),tf)
            if not clean.empty:
                clean["data_source"]="SAVED_OHLC_CACHE"
                frames[normalize_symbol(symbol)]=clean
    return frames,errors


def normalize_history(frame):
    if not isinstance(frame,pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    out=frame.loc[:,~frame.columns.duplicated(keep="last")].copy().reset_index(drop=True)
    if "Datetime" not in out:
        column=next((c for c in ("Completed Candle","open_time","datetime","time") if c in out),None)
        if column is None:
            return pd.DataFrame()
        out["Datetime"]=out[column]
    if "Symbol" not in out:
        return pd.DataFrame()
    out["Datetime"]=pd.to_datetime(out["Datetime"],errors="coerce",utc=True).dt.tz_localize(None)
    out["Symbol"]=out["Symbol"].map(normalize_symbol)
    if "Timeframe" not in out:
        out["Timeframe"]="UNKNOWN"
    out["Timeframe"]=out["Timeframe"].fillna("UNKNOWN").map(normalize_timeframe)
    # Repeating audit text is dictionary encoded to keep large histories usable.
    for column in out:
        if column.endswith(" Reason"):
            out[column]=out[column].fillna("No calculation").astype("category")
            if "No calculation" not in out[column].cat.categories:
                out[column]=out[column].cat.add_categories(["No calculation"])
        elif column.endswith(" Signal"):
            out[column]=pd.Categorical(out[column].fillna("NO DATA"),categories=["BUY","SELL","NO ENTRY","NO DATA"])
    keys=["Datetime","Symbol","Timeframe"]
    return out.dropna(subset=["Datetime"]).loc[lambda d:d.Symbol.ne("")].drop_duplicates(keys,keep="last").sort_values(keys,kind="mergesort").reset_index(drop=True)


def read_history(parquet_path, csv_path):
    errors=[]
    paths=sorted((Path(p) for p in (parquet_path,csv_path) if Path(p).exists()),key=lambda p:p.stat().st_mtime_ns,reverse=True)
    for path in paths:
        try:
            data=pd.read_parquet(path) if path.suffix==".parquet" else pd.read_csv(path,low_memory=False)
            data=normalize_history(data)
            if not data.empty:
                return data,errors
        except Exception as exc:
            errors.append(f"{path.name}: {type(exc).__name__}: {exc}")
    return pd.DataFrame(),errors


def write_history(frame,parquet_path,csv_path):
    """Atomic replace, CSV fallback even when Parquet support is unavailable."""
    errors=[]
    for target in (Path(parquet_path),Path(csv_path)):
        temp=target.with_name(target.name+"."+uuid.uuid4().hex+".tmp")
        try:
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.suffix==".parquet":
                frame.to_parquet(temp,index=False)
            else:
                frame.to_csv(temp,index=False,encoding="utf-8")
            os.replace(temp,target)
            return {"persisted":True,"format":target.suffix.lstrip("."),"warnings":errors}
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            temp.unlink(missing_ok=True)
    return {"persisted":False,"warnings":errors}


def merge_history(existing,generated):
    parts=[x for x in (existing,generated) if isinstance(x,pd.DataFrame) and not x.empty]
    return normalize_history(pd.concat(parts,ignore_index=True,sort=False)) if parts else pd.DataFrame()

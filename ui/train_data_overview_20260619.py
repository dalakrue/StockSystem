"""Canonical metadata-first Train Data overview with bounded preview."""
from __future__ import annotations

import hashlib
from typing import Any, Mapping, MutableMapping
import pandas as pd
import streamlit as st

from core.canonical_runtime_20260617 import get_canonical


def _frame(state: Mapping[str, Any]) -> pd.DataFrame:
    for key in ("training_df","train_df","canonical_completed_ohlc_df_20260617","last_df"):
        value=state.get(key)
        if isinstance(value,pd.DataFrame) and not value.empty: return value
    return pd.DataFrame()


def _time_col(frame: pd.DataFrame) -> str | None:
    return next((c for c in ("time","Time","datetime","Datetime","timestamp","Date") if c in frame.columns),None)


def _checksum(frame: pd.DataFrame) -> str:
    raw="|".join(f"{c}:{frame[c].dtype}" for c in frame.columns)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def render_train_data_overview(*, state: MutableMapping[str, Any] | None=None) -> None:
    state=state if state is not None else st.session_state; canonical=get_canonical(state); frame=_frame(state)
    run_id=canonical.get("run_id","-") if canonical else "-"; generation=canonical.get("calculation_generation","-") if canonical else "-"
    tcol=_time_col(frame); times=pd.to_datetime(frame[tcol],errors="coerce",utc=True) if tcol else pd.Series(dtype="datetime64[ns, UTC]")
    n=len(frame); features=[c for c in frame.columns if not str(c).lower().startswith("target")]
    targets=[c for c in frame.columns if str(c).lower().startswith("target") or str(c).lower() in {"future_close","future_move","future_move_pct","future_move_atr"}]
    missing=float(frame.isna().sum().sum()/max(1,frame.size)*100) if n else 0.0
    duplicates=int(frame.duplicated().sum()) if n else 0
    leakage="PASS" if (not tcol or times.is_monotonic_increasing) and not any(c in features for c in targets) else "CHECK"
    train_end=int(n*.70); val_end=int(n*.85)
    st.markdown("#### Train Data — canonical dataset identity")
    rows=[
      (("Dataset version",f"EURUSD-H1-G{generation}","display metadata"),("Run ID",str(run_id)[:18],"canonical"),("Generation",str(generation),"same as Lunch/Finder"),("Last completed H1",str(canonical.get("latest_completed_candle_time","-"))[-22:] if canonical else "-","completed candle only")),
      (("Row count",f"{n:,}","bounded preview below"),("Feature count",str(len(features)),f"targets {len(targets)}"),("Date range",f"{times.min()} → {times.max()}" if not times.dropna().empty else "-","UTC"),("Missing data",f"{missing:.2f}%",f"duplicates {duplicates}")),
      (("Training range",f"0–{max(0,train_end-1)}",f"{train_end:,} rows"),("Validation range",f"{train_end}–{max(train_end,val_end-1)}",f"{max(0,val_end-train_end):,} rows"),("Test range",f"{val_end}–{max(val_end,n-1)}",f"{max(0,n-val_end):,} rows"),("Leakage check",leakage,_checksum(frame) if n else "no dataset")),
    ]
    for row in rows:
        cols=st.columns(4)
        for col,(label,value,delta) in zip(cols,row): col.metric(label,value,delta=delta)
    st.caption(f"Target horizon: {state.get('train_horizon',state.get('horizon',12))} · Current source table: {state.get('source','canonical/shared')} · Feature-schema checksum: {_checksum(frame) if n else '-'}")
    if frame.empty:
        st.info("No prepared training dataset is currently cached. Opening Train Data does not retrain automatically."); return
    page_size=st.selectbox("Preview rows",[25,50,100],index=1,key="train_preview_size_20260619")
    max_page=max(0,(n-1)//int(page_size)); page=st.number_input("Preview page",min_value=1,max_value=max_page+1,value=min(int(state.get("train_preview_page_20260619",1)),max_page+1),step=1,key="train_preview_page_20260619")
    start=(int(page)-1)*int(page_size); preview=frame.iloc[start:start+int(page_size)]
    st.dataframe(preview,use_container_width=True,hide_index=True,height=340)
    if st.button("Prepare complete Train Data export",use_container_width=True,key="train_export_prepare_20260619"):
        state["train_export_bytes_20260619"]=frame.to_csv(index=False).encode("utf-8")
    if isinstance(state.get("train_export_bytes_20260619"),(bytes,bytearray)):
        st.download_button("Download complete Train Data CSV",state["train_export_bytes_20260619"],file_name=f"eurusd_h1_train_generation_{generation}.csv",mime="text/csv",use_container_width=True,key="train_export_download_20260619")

__all__=["render_train_data_overview"]

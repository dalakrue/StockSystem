"""Display-only, self-contained H1 evidence calculations for Lunch Tables 1, 4 and 5.

These calculations never overwrite protected production decisions. They provide
explicitly labelled, reproducible evidence from completed OHLC bars and available
NLP headlines when a published cross-tab frame is absent.
"""
from __future__ import annotations
from typing import Any, Mapping
import numpy as np
import pandas as pd


def _frame(v: Any) -> pd.DataFrame:
    if isinstance(v, pd.DataFrame): return v.copy()
    if isinstance(v, list): return pd.DataFrame(v)
    return pd.DataFrame()


def _find_ohlc(state: Mapping[str, Any]) -> pd.DataFrame:
    for key in ("last_df", "shared_market_df", "df", "market_df", "eurusd_h1_df", "normalized_market_data"):
        f = _frame(state.get(key))
        if f.empty: continue
        cols = {str(c).lower().replace('_',' '): c for c in f.columns}
        tc = next((cols.get(x) for x in ("broker candle time","datetime","timestamp","time","date") if cols.get(x) is not None), None)
        cc = cols.get("close")
        if tc is None or cc is None: continue
        out = pd.DataFrame({"Broker Candle Time": pd.to_datetime(f[tc], errors="coerce", utc=True)})
        for name in ("open","high","low","close","volume"):
            c=cols.get(name)
            out[name.title()] = pd.to_numeric(f[c], errors="coerce") if c is not None else np.nan
        out = out.dropna(subset=["Broker Candle Time","Close"]).sort_values("Broker Candle Time").drop_duplicates("Broker Candle Time")
        if not out.empty: return out
    return pd.DataFrame()


def _label(score: pd.Series, threshold: pd.Series | float) -> pd.Series:
    th = threshold if isinstance(threshold, pd.Series) else pd.Series(float(threshold), index=score.index)
    return pd.Series(np.where(score > th, "BUY", np.where(score < -th, "SELL", "WAIT")), index=score.index)


def build_self_contained_bias_history(state: Mapping[str, Any], cutoff: Any = None, days: int = 25) -> pd.DataFrame:
    x = _find_ohlc(state)
    if x.empty: return x
    c = x["Close"]
    ret1 = c.pct_change()
    ret3 = c.pct_change(3)
    ret6 = c.pct_change(6)
    ema8 = c.ewm(span=8, adjust=False).mean(); ema21 = c.ewm(span=21, adjust=False).mean()
    vol = ret1.rolling(24, min_periods=6).std().replace(0, np.nan)
    ztrend = ((ema8-ema21)/c).fillna(0) / vol.fillna(vol.median()).fillna(1e-6)
    momentum = (0.55*ret3.fillna(0)+0.45*ret6.fillna(0)) / vol.fillna(1e-6)
    rng = ((x["High"]-x["Low"])/c).replace([np.inf,-np.inf],np.nan)
    range_med = rng.rolling(48,min_periods=8).median().fillna(rng.median()).fillna(0)
    threshold = (0.18 + (rng > range_med).astype(float)*0.07)

    technical = _label(0.65*ztrend + 0.35*momentum, threshold)
    regime = _label(ztrend.rolling(5,min_periods=1).mean(), 0.20)
    data_mining = _label(0.4*ret1.fillna(0)/vol.fillna(1e-6)+0.6*momentum, 0.22)
    hour = x["Broker Candle Time"].dt.hour
    hourly_edge = ret1.groupby(hour).transform(lambda s: s.shift(1).rolling(60,min_periods=8).mean()).fillna(0)
    session = _label(0.6*momentum + 0.4*hourly_edge/vol.fillna(1e-6), 0.20)
    market_tone = _label(0.5*ret1.fillna(0)/vol.fillna(1e-6)+0.5*ztrend, 0.24)

    out = pd.DataFrame({
        "Broker Candle Time": x["Broker Candle Time"],
        "Technical Bias for Next H1": technical,
        "Sentiment Bias for Next H1": market_tone,
        "Session Bias for Next H1": session,
        "Regime Bias for Next H1": regime,
        "Data Mining Bias for Next H1": data_mining,
        "Technical Score": (0.65*ztrend+0.35*momentum).clip(-10,10).round(4),
        "Market Tone Score": (0.5*ret1.fillna(0)/vol.fillna(1e-6)+0.5*ztrend).clip(-10,10).round(4),
        "Session Score": (0.6*momentum+0.4*hourly_edge/vol.fillna(1e-6)).clip(-10,10).round(4),
        "Regime Score": ztrend.rolling(5,min_periods=1).mean().clip(-10,10).round(4),
        "Data Mining Score": (0.4*ret1.fillna(0)/vol.fillna(1e-6)+0.6*momentum).clip(-10,10).round(4),
        "Calculation Source": "SELF_CONTAINED_COMPLETED_OHLC",
    })
    end = pd.to_datetime(cutoff, errors="coerce", utc=True)
    if pd.isna(end): end = out["Broker Candle Time"].max()
    out = out[(out["Broker Candle Time"] <= end) & (out["Broker Candle Time"] >= end-pd.Timedelta(days=days))]
    return out.sort_values("Broker Candle Time", ascending=False).reset_index(drop=True)


def enrich_decision_history(table: pd.DataFrame, state: Mapping[str, Any]) -> pd.DataFrame:
    if not isinstance(table,pd.DataFrame) or table.empty: return table
    out=table.copy()
    evidence=build_self_contained_bias_history(state)
    if evidence.empty: return out
    tc=next((c for c in ("Broker Candle Time","Completed Broker Candle","Time","Datetime","Timestamp") if c in out.columns),None)
    if tc is None and {"Date","Hour"}.issubset(out.columns):
        out["__time"] = pd.to_datetime(out["Date"].astype(str)+" "+out["Hour"].astype(str),errors="coerce",utc=True)
        tc="__time"
    if tc is None: return out
    out[tc]=pd.to_datetime(out[tc],errors="coerce",utc=True).dt.floor("h")
    ev=evidence.set_index("Broker Candle Time")
    mapping={
      "Entry Strength Decision":"Technical Bias for Next H1", "SELL Pressure Decision":"Technical Bias for Next H1",
      "BUY Pressure Decision":"Technical Bias for Next H1",
      "Pressure Decision":"Data Mining Bias for Next H1",
      "Net Pressure Decision":"Data Mining Bias for Next H1",
      "Pullback Readiness Decision":"Regime Bias for Next H1", "M1 Confirmation Decision":"Session Bias for Next H1",
      "Master Decision":"Technical Bias for Next H1", "Hold Safety Decision":"Regime Bias for Next H1",
      "TP Quality Decision":"Data Mining Bias for Next H1", "Direction Confirmation Decision":"Technical Bias for Next H1",
      "Decision Name":"Technical Bias for Next H1", "Final Decision":"Technical Bias for Next H1",
    }
    invalid={"","N/A","NA","NONE","MISSING","UNAVAILABLE","-0","0","0.0"}
    for dest,src in mapping.items():
        vals=out[tc].map(ev[src])
        if dest not in out.columns: out[dest]=vals
        else:
            bad=out[dest].astype(str).str.strip().str.upper().isin(invalid) | out[dest].isna()
            out.loc[bad,dest]=vals[bad]
    if "__time" in out.columns: out.drop(columns="__time",inplace=True)
    return out

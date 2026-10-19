
"""Advanced Middle Standard Regime upgrade layer - 2026-09-26.

Additive migration module:
- H4 confirmation
- ADX regime filter
- currency strength score
- entry quality score
- ATR based TP/SL
- ATR trailing exit helper
- meta quality probability scaffold

This layer is designed to attach to the existing finder/engine dataframe without
breaking existing S1-S110 strategy logic.
"""
from __future__ import annotations
from typing import Any
import math
import pandas as pd
import numpy as np

VERSION="ADV-MIDDLE-20260926"

def _num(s, default=0.0):
    return pd.to_numeric(s, errors="coerce").fillna(default)

def add_adx(df, period=14):
    out=df.copy()
    h,l,c=_num(out["high"]),_num(out["low"]),_num(out["close"])
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    up=h.diff(); down=-l.diff()
    plus=np.where((up>down)&(up>0),up,0)
    minus=np.where((down>up)&(down>0),down,0)
    atr=pd.Series(tr).rolling(period).mean()
    pdi=100*pd.Series(plus).rolling(period).mean()/atr.replace(0,np.nan)
    mdi=100*pd.Series(minus).rolling(period).mean()/atr.replace(0,np.nan)
    dx=((pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan))*100
    out["ADX"]=dx.rolling(period).mean().fillna(0)
    return out

def currency_strength_score(base, quote, strength):
    b=strength.get(base,0); q=strength.get(quote,0)
    return float(b-q)

def entry_quality(row):
    score=0
    if str(row.get("H4_Bias","")).upper()==str(row.get("H1_Bias","")).upper():
        score+=30
    if str(row.get("H1_Bias","")).upper() in ("BUY","SELL"):
        score+=25
    adx=float(row.get("ADX",0) or 0)
    score+=15 if adx>=25 else (10 if adx>=20 else 0)
    score+=min(15,abs(float(row.get("Currency_Strength_Diff",0) or 0))*3)
    if float(row.get("ATR_Position",0) or 0)>0: score+=10
    if float(row.get("Price_Position",0) or 0)>0: score+=5
    return min(100,round(score,2))

def dynamic_tp_sl(row):
    """Backward-compatible row helper returning price distances when possible."""
    try:
        from core.hourly_four_symbol_selector_20260928 import add_dynamic_24h_targets
        mini = pd.DataFrame([{
            "open": row.get("open", np.nan),
            "high": row.get("high", np.nan),
            "low": row.get("low", np.nan),
            "close": row.get("close", np.nan),
            "ADX": row.get("ADX", np.nan),
            "ATR": row.get("ATR", np.nan),
        }])
        bias = str(row.get("Middle_Regime_Bias", row.get("Middle Bias", row.get("H1_Bias", row.get("Bias", "NEUTRAL")))) or "NEUTRAL")
        result = add_dynamic_24h_targets(mini, bias, timeframe="H1", symbol=row.get("Symbol", ""))
        return float(result.iloc[0]["24H TP Distance"]), float(result.iloc[0]["24H SL Distance"])
    except Exception:
        return np.nan, np.nan

def enrich_signals(df):
    out = add_adx(df)
    out["Entry_Score"] = out.apply(entry_quality, axis=1)
    try:
        from core.hourly_four_symbol_selector_20260928 import add_dynamic_24h_targets
        bias = out.get("Middle_Regime_Bias", out.get("Middle Bias", out.get("H1_Bias", out.get("Bias", pd.Series("NEUTRAL", index=out.index)))))
        targets = add_dynamic_24h_targets(out, bias, timeframe="H1", symbol=out.get("Symbol", ""))
        out["Suggested_TP"] = targets["Suggested TP"]
        out["Suggested_SL"] = targets["Suggested SL"]
        out["Suggested_TP_Price"] = targets["Suggested TP Price"]
        out["Suggested_SL_Price"] = targets["Suggested SL Price"]
        out["Risk_Reward"] = targets["TP:SL Price Ratio"]
        out["24H_TP_Upper_Envelope"] = targets["24H TP Upper Envelope"]
        out["TP_Target_Horizon_Hours"] = targets["TP Target Horizon Hours"]
        out["24H_TP_Confidence"] = targets["24H TP Confidence"]
        out["Max_Hold_Hours"] = 24
        out["Time_Exit_Hours"] = 24
        out["Exit_Scenario"] = "Dynamic TP + Middle Bias Exit"
        out["TP_Estimate_Basis"] = targets["TP Estimate Basis"]
    except Exception:
        out["Suggested_TP"] = np.nan
        out["Suggested_SL"] = np.nan
        out["Suggested_TP_Price"] = np.nan
        out["Suggested_SL_Price"] = np.nan
        out["Risk_Reward"] = np.nan
        out["24H_TP_Upper_Envelope"] = np.nan
        out["TP_Estimate_Basis"] = "Unavailable"
    out["Quality_Level"] = pd.cut(out["Entry_Score"], [-1,65,70,85,101],
        labels=["Reject", "Low Frequency", "Normal", "Premium"])
    out["Quality_Probability"] = out["Entry_Score"]
    out["Exit_Method"] = "Dynamic TP + Middle Bias Exit | hard 24h cap"
    return out


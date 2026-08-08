"""Metric inner tab for EURUSD H1 decision engine.

V23 non-destructive upgrade:
- H1 remains the main decision timeframe.
- M1 is confirmation / pullback timing only.
- Adds 10/10 scale tables, hour search, and true 25-day hour-by-hour history.
- Heavy calculation is lazy/button-triggered and exports compact data only.
"""

import json
import math
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import streamlit as st

try:
    from core.global_upgrade import render_page_shell, render_tab_footer
except Exception:
    def render_page_shell(title, subtitle='', icon=''):
        st.markdown(f"# {icon} {title}")
        if subtitle:
            st.caption(subtitle)
    def render_tab_footer(title):
        return None


def _num(v, default=0.0):
    try:
        v = float(v)
        if math.isfinite(v):
            return v
    except Exception:
        pass
    return float(default)


def _clip(v, lo=0.0, hi=100.0):
    return float(max(lo, min(hi, _num(v))))


def _scale10(v):
    return round(_clip(v) / 10.0, 2)


def _decision(score):
    score = _clip(score)
    if score >= 80:
        return "STRONG"
    if score >= 70:
        return "ALLOWED"
    if score >= 55:
        return "WAIT PULLBACK"
    if score >= 45:
        return "HOLD / PROTECT"
    return "NO TRADE"


def _normalize_ohlc(df):
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    d = df.copy()
    ren = {"datetime": "time", "date": "time", "timestamp": "time", "tick_volume": "volume"}
    for a, b in ren.items():
        if a in d.columns and b not in d.columns:
            d = d.rename(columns={a: b})
    need = ["time", "open", "high", "low", "close"]
    if not all(c in d.columns for c in need):
        return pd.DataFrame()
    d["time"] = pd.to_datetime(d["time"], errors="coerce")
    for c in ["open", "high", "low", "close", "volume"]:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time").drop_duplicates("time")
    return d.reset_index(drop=True)


def _resample(df, tf):
    d = _normalize_ohlc(df)
    if d.empty:
        return d
    rule = {"M1": "1min", "H1": "1h"}.get(str(tf).upper(), "1h")
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in d.columns:
        agg["volume"] = "sum"
    out = d.set_index("time").resample(rule).agg(agg).dropna().reset_index()
    return _normalize_ohlc(out)


def _get_frames() -> Tuple[pd.DataFrame, pd.DataFrame]:
    custom_h1 = _normalize_ohlc(st.session_state.get("custom_h1_df"))
    custom_m1 = _normalize_ohlc(st.session_state.get("custom_m1_df"))
    staging = st.session_state.get("calculation_staging_ohlc_df_20260617") if st.session_state.get("settings_calculation_lock_20260617") else None
    shared = _normalize_ohlc(staging if isinstance(staging, pd.DataFrame) and not staging.empty else st.session_state.get("last_df"))
    tf = str(st.session_state.get("timeframe", "H1")).upper()
    h1 = custom_h1 if not custom_h1.empty else (shared if tf == "H1" else _resample(shared, "H1"))
    m1 = custom_m1 if not custom_m1.empty else (shared if tf == "M1" else pd.DataFrame())
    return _normalize_ohlc(h1), _normalize_ohlc(m1)


def _indicators(df):
    d = _normalize_ohlc(df)
    if d.empty:
        return d
    high, low, close = d["high"], d["low"], d["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high-low).abs(), (high-prev_close).abs(), (low-prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False, min_periods=3).mean()
    up = high.diff(); down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    plus_di = 100 * pd.Series(plus_dm, index=d.index).ewm(alpha=1/14, adjust=False, min_periods=3).mean() / atr.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=d.index).ewm(alpha=1/14, adjust=False, min_periods=3).mean() / atr.replace(0, np.nan)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx = dx.ewm(alpha=1/14, adjust=False, min_periods=3).mean()
    d["atr"] = atr.fillna(0)
    d["plus_di"] = plus_di.fillna(0)
    d["minus_di"] = minus_di.fillna(0)
    d["adx"] = adx.fillna(0)
    d["pressure"] = d["plus_di"] - d["minus_di"]
    d["adx_slope"] = d["adx"].diff(3).fillna(0)
    d["pressure_accel"] = d["pressure"].diff().diff().fillna(0)
    rng = (d["high"] - d["low"]).replace(0, np.nan)
    d["body_ratio"] = ((d["close"]-d["open"]).abs() / rng).fillna(0).clip(0, 1)
    d["ret"] = d["close"].pct_change().fillna(0)
    return d


def _row_features(h: pd.DataFrame, idx: int, m1: pd.DataFrame | None = None) -> Dict[str, float]:
    row = h.iloc[idx]
    start = max(0, idx - 23)
    recent = h.iloc[start: idx + 1]
    close = _num(row["close"])
    atr = max(_num(row.get("atr")), abs(close) * 0.0005, 1e-9)
    rng = max(_num(recent["high"].max() - recent["low"].min()), atr)
    pos = _clip((close - _num(recent["low"].min())) / rng * 100)
    pressure = _num(row.get("pressure"))
    trend_capacity_used = pos if pressure >= 0 else 100 - pos
    pullback_h1 = _clip(100 - abs(pos - 50) * 2)
    m1_confirm = 50.0
    if isinstance(m1, pd.DataFrame) and not m1.empty:
        mt = m1[m1["time"] <= row["time"]].tail(60)
        if not mt.empty and "pressure" in mt.columns:
            m1_confirm = 60 + np.sign(pressure) * np.sign(_num(mt.iloc[-1].get("pressure"))) * 25
    pullback_readiness = _clip((pullback_h1 * 0.65) + (_clip(m1_confirm) * 0.35))
    vol_noise = _num(h["ret"].iloc[max(0, idx-11):idx+1].std() * 10000)
    hold_quality = _clip((100 - trend_capacity_used) * 0.35 + min(_num(row.get("adx")) / 35, 1) * 35 + max(0, 100 - vol_noise * 8) * 0.30)
    position_survival = _clip(hold_quality * 0.7 + (100 - abs(pressure) * 1.2) * 0.3)
    expected_remaining_move = max(atr * 0.8, rng * max(0.08, (100 - trend_capacity_used) / 100) * 0.35)
    return {
        "close": close, "atr": atr, "adx": _num(row.get("adx")), "plus_di": _num(row.get("plus_di")), "minus_di": _num(row.get("minus_di")),
        "pressure": pressure, "adx_slope": _num(row.get("adx_slope")), "pressure_acceleration": _num(row.get("pressure_accel")),
        "body_ratio": _num(row.get("body_ratio")), "trend_capacity_used": trend_capacity_used,
        "pullback_readiness": pullback_readiness, "expected_remaining_move": expected_remaining_move,
        "position_survival": position_survival, "hold_quality": hold_quality, "m1_confirm": _clip(m1_confirm),
    }


def _score_pack(x: Dict[str, float]) -> Dict[str, float | str]:
    buy_pressure = _clip(50 + x["pressure"] * 1.4)
    sell_pressure = _clip(50 - x["pressure"] * 1.4)
    entry_values = [max(buy_pressure, sell_pressure), _clip(x["adx"]/35*100), _clip(x["body_ratio"]*100), 65,
                    x["pullback_readiness"], x["m1_confirm"], _clip(100-x["trend_capacity_used"]),
                    _clip(50+abs(x["pressure_acceleration"])*12), x["position_survival"], max(58, x["pullback_readiness"])]
    weights = [1.25,1.10,0.85,0.75,1.10,0.70,1.00,0.85,0.90,0.80]
    entry_score = _clip(np.average(entry_values, weights=weights))
    buy_direction_items = [buy_pressure,
        x["trend_capacity_used"] if x["pressure"]>=0 else 100-x["trend_capacity_used"],
        _clip(x["adx"]/35*100) if x["pressure"]>=0 else 45,
        _clip(50+x["pressure_acceleration"]*15),
        x["m1_confirm"] if x["pressure"]>=0 else 100-x["m1_confirm"],
        x["hold_quality"] if x["pressure"]>=0 else 45,
        x["pullback_readiness"], _clip((x["expected_remaining_move"]/x["atr"])*55),
        _clip(x["body_ratio"]*100) if x["pressure"]>=0 else 45, 62]
    sell_direction_items = [sell_pressure,
        100-x["trend_capacity_used"] if x["pressure"]>=0 else x["trend_capacity_used"],
        _clip(x["adx"]/35*100) if x["pressure"]<0 else 45,
        _clip(50-x["pressure_acceleration"]*15),
        100-x["m1_confirm"] if x["pressure"]>=0 else x["m1_confirm"],
        x["hold_quality"] if x["pressure"]<0 else 45,
        x["pullback_readiness"], _clip((x["expected_remaining_move"]/x["atr"])*55),
        _clip(x["body_ratio"]*100) if x["pressure"]<0 else 45, 62]
    buy_score = _clip(np.mean(buy_direction_items)); sell_score = _clip(np.mean(sell_direction_items))
    direction_score = max(buy_score, sell_score)
    direction = "BUY" if buy_score >= 65 and buy_score > sell_score else "SELL" if sell_score >= 65 and sell_score > buy_score else "WAIT"
    exit_risk = _clip(x["trend_capacity_used"]*0.45 + max(0,-x["adx_slope"])*8 + max(0,100-x["position_survival"])*0.35)
    hold_safety = _clip((100-exit_risk)*0.45 + x["hold_quality"]*0.35 + x["position_survival"]*0.20)
    tp_quality = _clip((100-x["trend_capacity_used"])*0.45 + x["hold_quality"]*0.35 + x["pullback_readiness"]*0.20)
    master = _clip(entry_score*0.25 + direction_score*0.30 + hold_safety*0.25 + tp_quality*0.20)
    return {"Entry Score": entry_score, "Entry /10": _scale10(entry_score), "BUY Score": buy_score, "SELL Score": sell_score,
            "Direction Score": direction_score, "Direction": direction, "Exit Risk": exit_risk, "Exit Risk /10": _scale10(exit_risk),
            "Hold Safety Score": hold_safety, "Hold /10": _scale10(hold_safety), "TP Quality Score": tp_quality,
            "TP /10": _scale10(tp_quality), "Master EURUSD H1 Score": master, "Master /10": _scale10(master),
            "Decision": _decision(master)}


def _metrics(h1, m1):
    h = _indicators(h1)
    m = _indicators(m1)
    if h.empty:
        return {}
    x = _row_features(h, len(h)-1, m)
    x["h1"] = h; x["m1"] = m
    return x


def _history_table(h: pd.DataFrame, m: pd.DataFrame, days=25):
    if h.empty:
        return pd.DataFrame()
    hist = h.tail(int(days) * 24).copy()
    rows = []
    start_idx = max(0, len(h) - len(hist))
    for idx in range(start_idx, len(h)):
        r = h.iloc[idx]
        x = _row_features(h, idx, m)
        s = _score_pack(x)
        rows.append({
            "Date": r["time"].strftime("%Y-%m-%d"), "Weekday": r["time"].strftime("%A"), "Hour": r["time"].strftime("%H:00"),
            "Open": round(_num(r["open"]), 5), "High": round(_num(r["high"]), 5), "Low": round(_num(r["low"]), 5), "Close": round(_num(r["close"]), 5),
            "Entry /10": s["Entry /10"], "Direction": s["Direction"], "BUY /10": _scale10(s["BUY Score"]), "SELL /10": _scale10(s["SELL Score"]),
            "Exit Risk /10": s["Exit Risk /10"], "Hold /10": s["Hold /10"], "TP /10": s["TP /10"], "Master /10": s["Master /10"],
            "Score": round(_num(s["Master EURUSD H1 Score"]), 2), "Decision": s["Decision"],
            "ADX": round(x["adx"], 2), "Pressure": round(x["pressure"], 2), "M1 Confirm /10": _scale10(x["m1_confirm"]),
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out["_sort_time"] = pd.to_datetime(out["Date"].astype(str) + " " + out["Hour"].astype(str), errors="coerce")
        out = out.sort_values("_sort_time", ascending=False, na_position="last").drop(columns=["_sort_time"]).reset_index(drop=True)
    return out



def _history_by_factor_tables(h: pd.DataFrame, m: pd.DataFrame, days=25) -> Dict[str, pd.DataFrame]:
    """Build 10 separate 25-day history tables.

    Each table is independent (not mixed/combined) and sorted newest first.
    The value shown first is Scale /10, matching the user's requested decision
    scale format.
    """
    tables: Dict[str, list] = {}
    if h.empty:
        return {}
    hist = h.tail(int(days) * 24).copy()
    start_idx = max(0, len(h) - len(hist))
    for idx in range(start_idx, len(h)):
        r = h.iloc[idx]
        x = _row_features(h, idx, m)
        scores = _score_pack(x)
        factor_df = _reverse_scale_table(x, scores)
        for _, factor in factor_df.iterrows():
            name = str(factor.get("10 Reverse-Style Factor", "Decision"))
            tables.setdefault(name, []).append({
                "Date": r["time"].strftime("%Y-%m-%d"),
                "Weekday": r["time"].strftime("%A"),
                "Hour": r["time"].strftime("%H:00"),
                "Scale /10": factor.get("Scale /10"),
                "Score /100": round(_num(factor.get("Score /100")), 2),
                "Decision": factor.get("Decision", ""),
                "Open": round(_num(r["open"]), 5),
                "Close": round(_num(r["close"]), 5),
                "ADX": round(_num(x.get("adx")), 2),
                "Pressure": round(_num(x.get("pressure")), 2),
                "M1 Confirm /10": _scale10(x.get("m1_confirm", 50)),
                "Meaning": factor.get("Meaning", ""),
            })
    out: Dict[str, pd.DataFrame] = {}
    for name, rows in tables.items():
        df = pd.DataFrame(rows)
        if not df.empty:
            df["_sort_time"] = pd.to_datetime(df["Date"].astype(str) + " " + df["Hour"].astype(str), errors="coerce")
            df = df.sort_values("_sort_time", ascending=False, na_position="last").drop(columns=["_sort_time"])
        out[name] = df
    return out


def _reverse_scale_table(x: Dict[str, float], scores: Dict[str, object]):
    rows = [
        (1, "Entry Strength", scores["Entry /10"], scores["Entry Score"], "Can enter only if H1 + M1 timing align"),
        (2, "BUY Pressure", _scale10(scores["BUY Score"]), scores["BUY Score"], "+DI pressure and H1 bullish structure"),
        (3, "SELL Pressure", _scale10(scores["SELL Score"]), scores["SELL Score"], "-DI pressure and H1 bearish structure"),
        (4, "Hold Safety", scores["Hold /10"], scores["Hold Safety Score"], "Safe to hold through next H1 candles"),
        (5, "Exit Risk", scores["Exit Risk /10"], scores["Exit Risk"], "Higher means protect/reduce/exit risk"),
        (6, "TP Quality", scores["TP /10"], scores["TP Quality Score"], "Remaining room before trend capacity used"),
        (7, "Pullback Readiness", _scale10(x["pullback_readiness"]), x["pullback_readiness"], "H1 pullback + M1 timing"),
        (8, "Trend Capacity Remaining", _scale10(100-x["trend_capacity_used"]), 100-x["trend_capacity_used"], "Avoid late one-way entries"),
        (9, "M1 Confirmation", _scale10(x["m1_confirm"]), x["m1_confirm"], "Confirmation only, never main bias"),
        (10, "Master Decision", scores["Master /10"], scores["Master EURUSD H1 Score"], "Final combined EURUSD H1 decision"),
    ]
    df = pd.DataFrame(rows, columns=["No", "10 Reverse-Style Factor", "Scale /10", "Score /100", "Meaning"])
    df["Decision"] = df["Score /100"].apply(_decision)
    return df


def build_tables(h1=None, m1=None) -> Dict[str, object]:
    if h1 is None or m1 is None:
        h1, m1 = _get_frames()
    x = _metrics(h1, m1)
    if not x:
        return {"ok": False, "message": "No valid H1 OHLC data. Connect EURUSD H1 or Custom first."}
    h, m = x["h1"], x["m1"]
    scores = _score_pack(x)
    buy_pressure = _clip(50 + x["pressure"] * 1.4)
    sell_pressure = _clip(50 - x["pressure"] * 1.4)

    entry_rows = [(1,"H1 trend pressure",x["pressure"],max(buy_pressure,sell_pressure),1.25,"abs(+DI--DI) pressure"),(2,"ADX strength",x["adx"],_clip(x["adx"]/35*100),1.10,"min(adx/35,1)*100"),(3,"Candle conviction",x["body_ratio"],_clip(x["body_ratio"]*100),0.85,"abs(close-open)/(high-low)"),(4,"ATR activity",x["atr"],65,0.75,"ATR confirms tradable activity"),(5,"Pullback readiness",x["pullback_readiness"],x["pullback_readiness"],1.10,"H1 pullback + M1 timing"),(6,"M1 confirmation only",x["m1_confirm"],x["m1_confirm"],0.70,"M1 confirms timing, not direction"),(7,"Trend capacity remaining",100-x["trend_capacity_used"],_clip(100-x["trend_capacity_used"]),1.00,"100 - trend_capacity_used"),(8,"Pressure acceleration",x["pressure_acceleration"],_clip(50+abs(x["pressure_acceleration"])*12),0.85,"pressure.diff().diff()"),(9,"Position survival",x["position_survival"],x["position_survival"],0.90,"margin/hold quality proxy"),(10,"NY-prep session rule",x["pullback_readiness"],max(58,x["pullback_readiness"]),0.80,"at least one candidate before NY session")]
    entry_df = pd.DataFrame(entry_rows, columns=["No","Entry Factor","Value","Score","Weight","Equation"])
    entry_df["Weighted Score"] = entry_df["Score"] * entry_df["Weight"]
    entry_df["Scale /10"] = entry_df["Score"].apply(_scale10)
    entry_df["Decision"] = "Entry Allowed" if scores["Entry Score"] >= 70 else "Wait Pullback" if scores["Entry Score"] >= 55 else "No Entry"

    direction_factors = [("DI pressure",buy_pressure,sell_pressure,100-max(buy_pressure,sell_pressure),"+DI - -DI"),("Close vs 24H range",x["trend_capacity_used"] if x["pressure"]>=0 else 100-x["trend_capacity_used"],100-x["trend_capacity_used"] if x["pressure"]>=0 else x["trend_capacity_used"],35,"position in H1 24-bar range"),("ADX trend quality",_clip(x["adx"]/35*100) if x["pressure"]>=0 else 45,_clip(x["adx"]/35*100) if x["pressure"]<0 else 45,35,"ADX follows pressure side"),("Pressure acceleration",_clip(50+x["pressure_acceleration"]*15),_clip(50-x["pressure_acceleration"]*15),35,"pressure acceleration"),("M1 timing confirm",x["m1_confirm"] if x["pressure"]>=0 else 100-x["m1_confirm"],100-x["m1_confirm"] if x["pressure"]>=0 else x["m1_confirm"],40,"M1 confirmation only"),("Hold quality",x["hold_quality"] if x["pressure"]>=0 else 45,x["hold_quality"] if x["pressure"]<0 else 45,35,"hold quality score"),("Pullback readiness",x["pullback_readiness"],x["pullback_readiness"],45,"both sides wait if pullback not ready"),("Expected move room",_clip((x["expected_remaining_move"]/x["atr"])*55),_clip((x["expected_remaining_move"]/x["atr"])*55),35,"remaining move / ATR"),("Candle conviction",_clip(x["body_ratio"]*100) if x["pressure"]>=0 else 45,_clip(x["body_ratio"]*100) if x["pressure"]<0 else 45,35,"body ratio by pressure side"),("EURUSD H1 stability",62,62,38,"H1 main timeframe stability filter")]
    direction_df = pd.DataFrame([(i,n,_clip(b),_clip(s),_clip(ne),"BUY Bias" if _clip(b)>=65 and b>s else "SELL Bias" if _clip(s)>=65 and s>b else "WAIT",e) for i,(n,b,s,ne,e) in enumerate(direction_factors,1)], columns=["No","Direction Factor","BUY Score","SELL Score","Neutral Score","Final Bias","Equation"])
    direction_df["BUY /10"] = direction_df["BUY Score"].apply(_scale10); direction_df["SELL /10"] = direction_df["SELL Score"].apply(_scale10)

    exit_rows = [(1,"Trend capacity used",x["trend_capacity_used"],x["trend_capacity_used"],100-x["trend_capacity_used"],"capacity_used"),(2,"ADX fatigue",x["adx_slope"],_clip(50-x["adx_slope"]*10),_clip(50+x["adx_slope"]*10),"adx slope"),(3,"Pressure acceleration risk",x["pressure_acceleration"],_clip(abs(x["pressure_acceleration"])*15),_clip(100-abs(x["pressure_acceleration"])*15),"abs pressure accel"),(4,"Pullback danger",100-x["pullback_readiness"],_clip(100-x["pullback_readiness"]),x["pullback_readiness"],"100-pullback readiness"),(5,"Position survival",x["position_survival"],100-x["position_survival"],x["position_survival"],"survival proxy"),(6,"Hold quality",x["hold_quality"],100-x["hold_quality"],x["hold_quality"],"hold quality"),(7,"ATR shock risk",x["atr"],45,55,"ATR proxy"),(8,"One-way limit risk",x["trend_capacity_used"],_clip(x["trend_capacity_used"]*1.1),_clip(100-x["trend_capacity_used"]),"trend limit"),(9,"M1 opposite noise",x["m1_confirm"],_clip(100-x["m1_confirm"]),x["m1_confirm"],"M1 only"),(10,"Profit protection",scores["Exit Risk"],scores["Exit Risk"],100-scores["Exit Risk"],"weighted risk")]
    exit_df = pd.DataFrame(exit_rows, columns=["No","Exit Factor","Current Value","Exit Score","Hold Score","Equation"])
    exit_df["Exit /10"] = exit_df["Exit Score"].apply(_scale10); exit_df["Hold /10"] = exit_df["Hold Score"].apply(_scale10)
    exit_df["Decision"] = "Exit" if scores["Exit Risk"]>=75 else "Reduce 50%" if scores["Exit Risk"]>=60 else "Protect Profit" if scores["Exit Risk"]>=45 else "Hold"

    buy_tp = x["close"] + x["expected_remaining_move"]; sell_tp = x["close"] - x["expected_remaining_move"]
    tp_items = [("Expected remaining move",scores["TP Quality Score"],"Medium","close +/- expected_remaining_move"),("ATR expansion room",_clip(x["expected_remaining_move"]/x["atr"]*50),"Low/Med","remaining / ATR"),("Trend capacity",_clip(100-x["trend_capacity_used"]),"Medium","100-capacity used"),("Pullback readiness",x["pullback_readiness"],"Low if >70","pullback timing"),("Hold quality",x["hold_quality"],"Medium","hold score"),("Position survival",x["position_survival"],"Risk filter","survival score"),("Pressure acceleration",_clip(50+abs(x["pressure_acceleration"])*12),"Acceleration","pressure accel"),("ADX support",_clip(x["adx"]/35*100),"Trend risk","ADX"),("M1 confirm timing",x["m1_confirm"],"Noise risk","M1 confirm"),("EURUSD H1 TP quality",scores["TP Quality Score"],"Final","weighted TP quality")]
    tp_df = pd.DataFrame([(i,n,buy_tp,sell_tp,p,_scale10(p),r,e) for i,(n,p,r,e) in enumerate(tp_items,1)], columns=["No","TP Factor","BUY TP","SELL TP","Probability","Scale /10","Risk","Equation"])
    tp_df["Decision"] = np.where(tp_df["Probability"]>=70,"TP Good",np.where(tp_df["Probability"]>=55,"Partial TP / Trail","Weak TP"))

    sess_rows = []
    for name,a,b in [("Asia",1,7),("London",8,12),("Before NY",12,15)]:
        sc = scores["Entry Score"]; dec = entry_df["Decision"].iloc[0]
        if name == "Before NY" and sc < 70:
            dec = "Required Pre-NY Candidate: Wait Pullback" if sc >= 55 else "Required Pre-NY Candidate: Micro confirmation only"
            sc = max(sc, 55)
        sess_rows.append({"Session":name,"Hours":f"{a:02d}:00-{b:02d}:00","Best Entry Score":round(sc,2),"Scale /10":_scale10(sc),"Decision":dec,"Rule":"At least one candidate before NY; M1 confirms timing only"})
    session_df = pd.DataFrame(sess_rows)
    history = _history_table(h, m, 25)
    reverse10 = _reverse_scale_table(x, scores)
    history_by_factor = _history_by_factor_tables(h, m, 25)
    return {"ok": True, "metrics": x, "entry": entry_df, "direction": direction_df, "exit": exit_df, "tp": tp_df, "session": session_df, "history": history, "reverse10": reverse10, "history_by_factor": history_by_factor, "scores": scores}




def _short_necessary_metric_text(result=None):
    """Compact copy: key decision only, no huge tables."""
    src = result or st.session_state.get("eurusd_h1_matrix_export", {}) or {}
    scores = src.get("scores", {}) if isinstance(src, dict) else {}
    reverse10 = src.get("reverse10", []) if isinstance(src, dict) else []
    # Live result uses DataFrame for reverse10; exported result uses list.
    if hasattr(reverse10, "to_dict"):
        reverse10 = reverse10.to_dict("records")
    lines = [
        "NECESSARY SHORT METRIC COPY",
        f"Symbol: {st.session_state.get('symbol','EURUSD')}",
        f"Timeframe: {st.session_state.get('timeframe','H1')}",
        f"Source: {st.session_state.get('source','DISCONNECTED')}",
    ]
    if isinstance(scores, dict) and scores:
        for k in ["Decision", "Direction", "Master /10", "Entry /10", "Hold /10", "TP /10", "Exit Risk /10"]:
            if k in scores:
                lines.append(f"{k}: {scores.get(k)}")
    if isinstance(reverse10, list) and reverse10:
        lines.append("10 reverse-style factors:")
        for r in reverse10[:10]:
            if isinstance(r, dict):
                lines.append(f"- {r.get('No','')}. {r.get('10 Reverse-Style Factor','Factor')}: {r.get('Scale /10','?')}/10 | {r.get('Decision','')}")
    return "\n".join(lines)


def _render_short_necessary_metric_copy(result=None, key="metric_short_copy"):
    try:
        from core.pro_terminal_uiux import render_mobile_copy_button
        txt = _short_necessary_metric_text(result)
        render_mobile_copy_button("Copy Necessary Short Only", txt, key)
        with st.expander("Fallback text — Necessary Short Copy", expanded=False):
            st.text_area("Long-press / select all if phone browser blocks copy", txt, height=180, key=f"{key}_fallback")
    except Exception:
        st.text_area("Necessary Short Copy", _short_necessary_metric_text(result), height=180, key=f"{key}_plain")


def _save_to_session(result):
    def _pack(v):
        if isinstance(v, pd.DataFrame):
            return v.tail(300).to_dict("records")
        if isinstance(v, dict):
            return {str(k): _pack(val) for k, val in v.items()}
        return v
    try:
        compact = {k: _pack(v) for k, v in result.items() if k not in ["metrics"]}
        st.session_state["eurusd_h1_matrix_export"] = compact
    except Exception:
        pass


def render_compact_panel(location="home"):
    h1, m1 = _get_frames()
    result = build_tables(h1, m1)
    if not result.get("ok"):
        with st.expander("📂 Open / Close — Metric", expanded=False):
            st.info(result.get("message"))
        return
    _save_to_session(result)
    s = result["scores"]
    with st.expander("📂 Open / Close — Metric + Reverse 10/10 + 25D Hour Search", expanded=True if location in ["tab", "metric"] else False):
        c = st.columns(5)
        c[0].metric("Master", f"{s['Master /10']:.2f}/10", s["Decision"])
        c[1].metric("Entry", f"{s['Entry /10']:.2f}/10")
        c[2].metric("Direction", s["Direction"], f"B {s['BUY Score']:.0f} / S {s['SELL Score']:.0f}")
        c[3].metric("Hold", f"{s['Hold /10']:.2f}/10")
        c[4].metric("TP", f"{s['TP /10']:.2f}/10")
        st.dataframe(result["session"], use_container_width=True, hide_index=True)
        st.markdown("#### 📋 Short necessary copy")
        _render_short_necessary_metric_copy(result, key=f"metric_short_copy_{location}")

        history_by_factor = result.get("history_by_factor", {}) or {}
        open_history = st.checkbox(
            "📂 Open / Close — 25D Separate History For All 10 Metric Decisions",
            value=True,
            key=f"metric_25d_factor_history_open_{location}",
        )
        if open_history:
            st.caption("Each decision factor is separate, not mixed or combined. Newest/current H1 rows are shown first. Weekday shows Monday/Tuesday/etc. Scale /10 is placed first for every table.")
            if not history_by_factor:
                st.info("No separate 25-day decision history available yet.")
            else:
                factor_names = list(history_by_factor.keys())
                factor_tabs = st.tabs([str(i + 1) for i in range(len(factor_names))])
                for tab_obj, factor_name in zip(factor_tabs, factor_names):
                    with tab_obj:
                        st.markdown(f"#### {factor_name}")
                        factor_df = history_by_factor.get(factor_name)
                        if isinstance(factor_df, pd.DataFrame) and not factor_df.empty:
                            cols = [c for c in ["Scale /10", "Date", "Weekday", "Hour", "Decision", "Score /100", "Open", "Close", "ADX", "Pressure", "M1 Confirm /10", "Meaning"] if c in factor_df.columns]
                            st.dataframe(factor_df[cols], use_container_width=True, hide_index=True)
                        else:
                            st.info("No rows for this decision factor yet.")

        hist = result["history"].copy()
        hour_options = ["ALL"] + sorted(hist["Hour"].dropna().unique().tolist()) if not hist.empty else ["ALL"]
        pick_hour = st.selectbox("Search each hour score in last 25 days", hour_options, key="eurusd_h1_hour_search")
        min_score = st.slider("Minimum Master /10", 0.0, 10.0, 0.0, 0.25, key="eurusd_h1_min_score")
        search_hist = hist if pick_hour == "ALL" else hist[hist["Hour"] == pick_hour]
        if not search_hist.empty:
            search_hist = search_hist[pd.to_numeric(search_hist["Master /10"], errors="coerce") >= float(min_score)]

        tabs = st.tabs(["Reverse 10/10", "10 Entry", "10 Direction", "10 Exit", "10 TP", "25D Hour History"])
        for tab, key in zip(tabs, ["reverse10","entry","direction","exit","tp",None]):
            with tab:
                if key:
                    st.dataframe(result[key], use_container_width=True, hide_index=True)
                else:
                    st.caption("True hour-by-hour score from the last 25 H1 days. Filter by hour and score above.")
                    st.dataframe(search_hist, use_container_width=True, hide_index=True)

        if str(st.session_state.get("timeframe", "H1")).upper() == "CUSTOM":
            st.markdown("#### CUSTOM timeframe: H1 main table + M1 confirmation table")
            h1_show = _normalize_ohlc(st.session_state.get("custom_h1_df")).tail(25*24)
            m1_show = _normalize_ohlc(st.session_state.get("custom_m1_df")).tail(1000)
            htab, mtab = st.tabs(["H1 Main Open/Close", "M1 Confirmation Open/Close"])
            with htab:
                st.caption("H1 is the main data for bias, entry, exit, and TP.")
                st.dataframe(h1_show, use_container_width=True, hide_index=True) if not h1_show.empty else st.info("No H1 Custom data loaded yet.")
            with mtab:
                st.caption("M1 confirms timing only. It is not mixed into H1 direction.")
                st.dataframe(m1_show, use_container_width=True, hide_index=True) if not m1_show.empty else st.info("No M1 Custom data loaded yet.")


def show():
    render_page_shell("Metric", "EURUSD H1 main bias/entry/exit/TP. M1 confirms timing only. Separate 25-day 10-decision history added.", "📊")
    h1, m1 = _get_frames()
    if h1.empty:
        st.warning("Connect EURUSD H1 or choose CUSTOM timeframe to load H1+M1 first.")
        render_tab_footer("Metric")
        return
    if str(st.session_state.get("symbol", "EURUSD")).upper() != "EURUSD":
        st.info("This matrix is tuned for EURUSD H1. Current symbol is not EURUSD, so treat output as structural test only.")
    if st.button("Calculate / Refresh Metric", use_container_width=True, key="eurusd_h1_calc_button"):
        st.session_state["eurusd_h1_run_calc"] = True
    st.markdown("#### 📋 Short necessary copy")
    _render_short_necessary_metric_copy(key="metric_short_copy_tab_top")
    if st.session_state.get("eurusd_h1_run_calc", False):
        render_compact_panel("tab")
    else:
        st.info("Press Calculate to keep RAM lower. Metric will not calculate heavy 25-day history until clicked.")
    with st.expander("📋 Open / Close — Copy Metric JSON", expanded=False):
        payload = json.dumps(st.session_state.get("eurusd_h1_matrix_export", {}), default=str, indent=2)
        st.text_area("Copy this matrix data", payload, height=260)
    render_tab_footer("Metric")

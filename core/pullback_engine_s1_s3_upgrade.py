"""Independent Middle Standard Regime pullback engines with 24h dynamic targets."""
from __future__ import annotations
from typing import Any, Mapping
import numpy as np
import pandas as pd

STRATEGY_NAMES = {
    "S1": "Middle Regime Trend Continuation Pullback",
    "S2": "Middle Regime Volatility Compression Pullback",
    "S3": "Middle Regime RSI Reset Pullback",
    "S4": "RAS (Higher Regime Bias)",
    "S5": "Middle Regime Pullback",
    "S6": "Middle Regime Pullback Composite",
    "S7": "Middle Regime MACD Recovery Pullback",
    "S8": "Middle Regime Stochastic Reset Pullback",
    "S9": "Middle Regime Volume Dry-Up Pullback",
    "S10": "Middle Regime HMM State Pullback",
    "S11": "Middle Standard VWAP Reclaim Pullback",
    "S12": "Middle Standard Fibonacci Retracement Pullback",
    "S13": "Middle Standard ADX-DMI Strength Pullback",
    "S14": "Middle Standard Donchian Midline Reclaim Pullback",
    "S15": "Middle Standard Wick Rejection Pullback",
    "S16": "Middle Standard Keltner Midline Reclaim Pullback",
    "S17": "Middle Standard RSI-2 Reset Pullback",
    "S18": "Middle Standard Pivot Reclaim Pullback",
    "S19": "Middle Standard Ichimoku Kijun Pullback",
    "S20": "Middle Standard OBV Momentum Pullback",
    "S21": "EMA trend pullback continuation",
    "S22": "ADX strong trend retracement",
    "S23": "VWAP reclaim pullback",
    "S24": "Fibonacci 50-61.8 pullback",
    "S25": "RSI reset trend pullback",
    "S26": "Bollinger mean pullback continuation",
    "S27": "Keltner channel pullback",
    "S28": "Support resistance rejection pullback",
    "S29": "Volume confirmed pullback",
    "S30": "Multi-filter measured quality pullback",
    "S31": "EMA20/50 deep pullback continuation",
    "S32": "EMA200 trend reload pullback",
    "S33": "ADX + DI pullback recovery",
    "S34": "MACD histogram pullback reset",
    "S35": "RSI directional reset in trend",
    "S36": "ATR controlled volatility pullback",
    "S37": "VWAP deviation recovery",
    "S38": "Liquidity sweep rejection pullback",
    "S39": "Previous high/low breakout retest",
    "S40": "Multi timeframe trend pullback",
    "S41": "Order block style pullback",
    "S42": "Volume dry-up then expansion",
    "S43": "Bollinger squeeze release pullback",
    "S44": "Keltner trend continuation pullback",
    "S45": "Fibonacci golden zone confirmation",
    "S46": "Market structure higher-low pullback",
    "S47": "Candle confirmation pullback",
    "S48": "Trend exhaustion recovery",
    "S49": "Weighted quality pullback",
    "S50": "Ultimate multi-filter pullback",
}

# S51-S92 are retained as the previously added Middle Standard opportunity
# families. Their common gate is deliberately relaxed by 30% in the shared
# audit so these models can surface more opportunities without removing the
# higher/middle direction-alignment safety rule.
for _i,_name in {
51:"Breakout Continuation",52:"Breakout Momentum Confirmation",53:"Support Resistance Break",54:"Volatility Filtered Breakout",
55:"Momentum Ignition",56:"ATR Expansion",57:"Candle Strength Expansion",58:"Momentum Regime Alignment",
59:"Mean Reversion Regime",60:"RSI Extreme Recovery",61:"Bollinger Deviation Return",62:"EMA Deviation Recovery",
63:"Breakout Retest",64:"Retest Rejection",65:"Level Quality Retest",66:"Trend Retest Confirmation",
67:"Volatility Compression Expansion",68:"Squeeze Release",69:"Range Expansion",70:"ATR Regime Expansion",
71:"Regime Transition",72:"Bias Flip Confirmation",73:"Early Trend Formation",74:"Transition Momentum",
75:"Momentum Expansion Continuation",76:"Strong Body Continuation",77:"Institutional Momentum Proxy",78:"Acceleration Continuation",
79:"Deep Retracement Recovery",80:"Extreme Pullback Recovery",81:"Trend Fair Value Return",82:"Controlled Mean Return",
83:"Range Break",84:"Range Quality Break",85:"Consolidation Release",86:"Channel Escape",
87:"Reversal Exhaustion",88:"Divergence Reversal",89:"Structure Reversal",90:"Momentum Exhaustion",
91:"Adaptive Hybrid Quality",92:"Adaptive Multi Filter"}.items():
    STRATEGY_NAMES[f"S{_i}"]=f"Middle Standard {_name} Strategy"

for _i,_name in {
93:"EMA34 Envelope Reclaim Pullback",
94:"EMA100 Reload Pullback",
95:"EMA10/20 Ribbon Reset Pullback",
96:"VWAP and EMA Confluence Pullback",
97:"48-Bar Value Midline Reclaim Pullback",
98:"Fibonacci Shallow 23.6-38.2 Reclaim",
99:"Fibonacci Deep 61.8-78.6 Recovery",
100:"12-Bar Liquidity Sweep Recovery Pullback",
101:"30-Bar Level Rejection Pullback",
102:"Classic Pivot S1-R1 Reclaim Pullback",
103:"Stochastic 50-Line Reset Pullback",
104:"MACD Zero-Line Retest Pullback",
105:"Williams Percent-R Reset Pullback",
106:"Money Flow Index Reset Pullback",
107:"ADX Contraction Recovery Pullback",
108:"ATR Envelope Re-entry Pullback",
109:"Two-Candle Reversal at EMA50 Pullback",
110:"Multi-Zone Confluence Pullback",
}.items():
    STRATEGY_NAMES[f"S{_i}"]=f"Middle Standard {_name}"

# S111-S120 are rescue-only structures.  Their formulas live in the shared
# causal audit, while this ordered registry is the single contract consumed by
# live ranking, Finder, the worker, exports and tests.
for _i, _name in {
111: "Micro Pullback Resumption",
112: "Impulse Pause Resume Flag",
113: "Inside-Bar Trend Break",
114: "NR7 Narrow-Range Expansion",
115: "Failed Countertrend Break Trap Reclaim",
116: "Multi-Wick Absorption",
117: "Fair Value Gap Imbalance Reclaim",
118: "Structure Break First Clean Retest",
119: "Contraction To Re-Acceleration",
120: "Independent Evidence Consensus Rescue",
}.items():
    STRATEGY_NAMES[f"S{_i}"] = f"Middle Standard {_name}"


def _series(df, name):
    if not isinstance(df, pd.DataFrame) or name not in df.columns: return pd.Series(dtype=float)
    return pd.to_numeric(df[name], errors="coerce")

def _ema(values, span):
    return values.ewm(span=span, adjust=False, min_periods=max(3, span // 3)).mean()

def _rsi(close, period=14):
    change = close.diff(); gain = change.clip(lower=0).ewm(alpha=1/period, adjust=False, min_periods=period).mean(); loss = (-change.clip(upper=0)).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    return (100 - 100/(1 + gain/loss.replace(0, np.nan))).fillna(50.0)

def _atr(df, period=14):
    high, low, close = _series(df, "high"), _series(df, "low"), _series(df, "close")
    if any(x.empty for x in (high, low, close)): return pd.Series(dtype=float)
    tr = pd.concat(((high-low).abs(), (high-close.shift()).abs(), (low-close.shift()).abs()), axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()

def _hmm_regime(df, lookback=160):
    close = _series(df, "close").dropna().to_numpy(dtype=float)
    if len(close) < 35: return {"ready": False, "trend_prob": 0., "high_vol_prob": 1., "transition_prob": 1., "cooling": False}
    ret = np.diff(np.log(np.maximum(close[-lookback:], 1e-12)))
    if len(ret) < 30 or not np.isfinite(ret).all(): return {"ready": False, "trend_prob": 0., "high_vol_prob": 1., "transition_prob": 1., "cooling": False}
    feat = np.column_stack((ret, np.abs(ret))); half = len(feat)//2
    mu = np.array((feat[:half].mean(0), feat[half:].mean(0))); var = np.array((feat[:half].var(0), feat[half:].var(0))) + 1e-12
    trans = np.array(((.92,.08),(.18,.82))); pi = np.array((.65,.35))
    for _ in range(8):
        ll = np.empty((len(feat),2))
        for s in range(2): ll[:,s] = -.5*np.sum(np.log(2*np.pi*var[s]) + (feat-mu[s])**2/var[s], axis=1)
        a = np.zeros_like(ll); a[0] = np.log(pi)+ll[0]
        for t in range(1,len(feat)): a[t] = ll[t] + np.logaddexp.reduce(a[t-1][:,None] + np.log(trans), axis=0)
        b = np.zeros_like(ll)
        for t in range(len(feat)-2,-1,-1): b[t] = np.logaddexp.reduce(np.log(trans)+ll[t+1][None,:]+b[t+1][None,:], axis=1)
        g = np.exp(a+b-np.logaddexp.reduce(a[-1])); g /= np.maximum(g.sum(1,keepdims=True),1e-12)
        w = g.sum(0); mu = (g.T@feat)/np.maximum(w[:,None],1e-12); var = np.array([(g[:,s,None]*(feat-mu[s])**2).sum(0)/max(w[s],1e-12) for s in range(2)])+1e-12
    low, high = (int(v) for v in np.argsort(var[:,1])); trend, highp = float(g[-1,low]), float(g[-1,high])
    transition = float(np.clip(highp*trans[high,low]+trend*trans[low,high],0,1))
    return {"ready": True, "trend_prob": trend, "high_vol_prob": highp, "transition_prob": transition, "cooling": highp < float(g[-2,high])}

def _clip(v): return int(np.clip(round(float(v)),0,100)) if np.isfinite(v) else 0
def _empty(reason): return {s:{"entry_condition":False,"signal":"NO ENTRY","reason":reason,"score":0,"eligible":False} for s in STRATEGY_NAMES}
def _row(entry, direction, reason, score, eligible=True): return {"entry_condition":bool(entry),"signal":direction if entry and direction in {"BUY","SELL"} else "NO ENTRY","reason":reason,"score":_clip(score),"eligible":bool(eligible)}

def evaluate_pullback_strategies(df: pd.DataFrame, higher_bias: str, middle_bias: str, timeframe: str = "H1"):
    """Return the same S1–S120 decision used by live ranking and historical prefix replay."""
    if not isinstance(df,pd.DataFrame) or len(df)<55:
        return _empty("Rejected: at least 55 completed candles are required")
    from core.strategy_audit_20260924 import build_strategy_audit
    audit=build_strategy_audit(df,higher_bias,middle_bias,timeframe=timeframe)
    if audit.empty:
        return _empty("Rejected: OHLC data is incomplete")
    latest=audit.iloc[-1]
    out={}
    for label in STRATEGY_NAMES:
        score=int(latest[f"{label} Score"])
        target=(70 if score>=92 else 60 if score>=82 else 50) if int(label[1:])>20 else 40
        out[label]={
            "entry_condition":bool(latest[f"{label} Entry Condition"]),
            "signal":str(latest[f"{label} Signal"]),
            "reason":str(latest[f"{label} Reason"]),
            "score":score,"eligible":bool(latest["Entry Quality Passed"]),
            "tp":target,"sl":20,"rr":target/20,
            "entry_price":float(latest.get("close")) if pd.notna(latest.get("close")) else np.nan,
            "tp_price":float(latest.get("Suggested TP")) if pd.notna(latest.get("Suggested TP")) else np.nan,
            "sl_price":float(latest.get("Suggested SL")) if pd.notna(latest.get("Suggested SL")) else np.nan,
            "tp_pips":float(latest.get("Suggested TP Pips")) if pd.notna(latest.get("Suggested TP Pips")) else np.nan,
            "sl_pips":float(latest.get("Suggested SL Pips")) if pd.notna(latest.get("Suggested SL Pips")) else np.nan,
            "tp_price_display":str(latest.get("TP Price Display", "—")),
            "sl_price_display":str(latest.get("SL Price Display", "—")),
            "tp_horizon_hours":float(latest.get("TP Target Horizon Hours")) if pd.notna(latest.get("TP Target Horizon Hours")) else 24.0,
            "tp_confidence":float(latest.get("24H TP Confidence")) if pd.notna(latest.get("24H TP Confidence")) else 0.0,
            "max_hold_hours":24.0,
            "exit_scenario":"Dynamic TP + Middle Bias Exit",
            "near_entry_score":float(latest.get("Near Entry Score", 0) or 0),
            "strategy_hit_count":int(latest.get("Strategy Hit Count", 0) or 0),
            "noise_ratio":float(latest["Entry Noise Ratio"]) if pd.notna(latest["Entry Noise Ratio"]) else 1.0,
        }
    return out


def strategy_decision(results: Mapping[str, Mapping[str, Any]]) -> str:
    """Publish the dominant strategy side using the dynamic 24h TP/SL.

    The public text stays compatible with older callers (for example
    ``BUY-4 TP40 SL20``) when dynamic target fields are absent. New live rows
    use price-derived TP/SL distances instead of the old static ladder.
    """
    grouped = {"BUY": [], "SELL": []}
    for label in STRATEGY_NAMES:
        row = results.get(label) or {}
        signal = str(row.get("signal", "NO ENTRY")).upper().strip()
        if signal in grouped and bool(row.get("entry_condition", False)):
            grouped[signal].append(row)

    if grouped["BUY"] and grouped["SELL"]:
        buy_strength = sum(max(float(r.get("score", 1) or 1), 1) for r in grouped["BUY"])
        sell_strength = sum(max(float(r.get("score", 1) or 1), 1) for r in grouped["SELL"])
        if buy_strength >= sell_strength:
            grouped["SELL"] = []
        else:
            grouped["BUY"] = []

    parts = []
    for direction, rows in grouped.items():
        if not rows:
            continue
        count = len(rows)
        weights = [max(float(r.get("score", 1) or 1), 1.0) for r in rows]
        total_weight = sum(weights)

        dynamic_tp_pairs = [
            (float(row.get("tp_pips")), weight)
            for row, weight in zip(rows, weights)
            if np.isfinite(float(row.get("tp_pips", np.nan))) and float(row.get("tp_pips")) > 0
        ]
        dynamic_sl_pairs = [
            (float(row.get("sl_pips")), weight)
            for row, weight in zip(rows, weights)
            if np.isfinite(float(row.get("sl_pips", np.nan))) and float(row.get("sl_pips")) > 0
        ]

        if dynamic_tp_pairs:
            avg_tp = sum(value * weight for value, weight in dynamic_tp_pairs) / max(sum(weight for _, weight in dynamic_tp_pairs), 1.0)
            tp = int(max(10, round(avg_tp / 10.0) * 10))
        else:
            avg_tp = sum(float(r.get("tp", 40) or 40) * w for r, w in zip(rows, weights)) / total_weight
            tp = int(max(30, min(90, round(avg_tp / 10.0) * 10)))

        if dynamic_sl_pairs:
            avg_sl = sum(value * weight for value, weight in dynamic_sl_pairs) / max(sum(weight for _, weight in dynamic_sl_pairs), 1.0)
            sl = int(max(10, round(avg_sl / 10.0) * 10))
        else:
            sl = 20

        # Compact live display: direction + hit count + price targets only.
        # Detailed strategy audit remains available in the audit columns.
        if not any(r.get("tp_price_display") or r.get("tp_price") for r in rows):
            parts.append(f"{direction}-{count} TP{tp} SL{sl}")
            continue
        price_tp = rows[0].get("tp_price_display") or rows[0].get("tp_price") or "—"
        price_sl = rows[0].get("sl_price_display") or rows[0].get("sl_price") or "—"
        try:
            price_tp = f"{float(price_tp):.5f}"
        except Exception:
            price_tp = str(price_tp)
        try:
            price_sl = f"{float(price_sl):.5f}"
        except Exception:
            price_sl = str(price_sl)
        parts.append(f"{direction}-{count} TP {price_tp} SL {price_sl}")

    return " | ".join(parts) or "None"


def middle_bias_exit(position_side: str, current_middle_bias: str, position_age_hours: float | int | None = None):
    from core.hourly_four_symbol_selector_20260928 import middle_bias_exit_decision
    return middle_bias_exit_decision(position_side, current_middle_bias, position_age_hours=position_age_hours)

def ranked_pullback_scores(df, higher_bias, middle_bias=None):
    middle=middle_bias if middle_bias in {"BUY","SELL"} else higher_bias
    return {s:int(v["score"]) for s,v in evaluate_pullback_strategies(df,higher_bias,middle).items()}

def run_pullback_models(df, higher_bias, middle_bias=None, symbol="UNKNOWN"):
    del symbol; middle=middle_bias if middle_bias in {"BUY","SELL"} else higher_bias
    return strategy_decision(evaluate_pullback_strategies(df,higher_bias,middle))

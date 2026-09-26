"""Independent Middle Standard Regime pullback engines (S1-S110)."""
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

def evaluate_pullback_strategies(df: pd.DataFrame, higher_bias: str, middle_bias: str, symbol='UNKNOWN', timeframe='H1'):
    """Return the same S1–S110 decision used by live ranking and historical prefix replay."""
    if not isinstance(df,pd.DataFrame) or len(df)<55:
        return _empty("Rejected: at least 55 completed candles are required")
    from core.strategy_audit_20260924 import build_strategy_audit
    audit=build_strategy_audit(df,higher_bias,middle_bias,symbol=symbol,timeframe=timeframe)
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
            "tp":float(latest["Suggested TP"]) if pd.notna(latest["Suggested TP"]) else target,
            "sl":float(latest["Suggested SL"]) if pd.notna(latest["Suggested SL"]) else 20,
            "rr":float(latest["Expected Reward Risk"]) if pd.notna(latest["Expected Reward Risk"]) else 0,
            "_v4_decision":str(latest["Adaptive Decision"]),
            "noise_ratio":float(latest["Entry Noise Ratio"]) if pd.notna(latest["Entry Noise Ratio"]) else 1.0,
        }
    return out


def strategy_decision(results: Mapping[str, Mapping[str, Any]]) -> str:
    """
    Short public decision display.

    Instead of printing every strategy TP/SL:
        BUY-4 S1(TP=40,SL=20),S21(TP=50,SL=20)

    publish one optimized TP/SL for the symbol:
        BUY-4 TP40 SL20

    The selected TP/SL is calculated only from strategies that actually meet
    entry conditions. Higher score strategies have more influence, while the
    final risk profile avoids selecting an aggressive TP when quality is weak.
    """
    for row in results.values():
        if "_v4_decision" in row:
            return str(row["_v4_decision"])
    grouped = {"BUY": [], "SELL": []}

    for label in STRATEGY_NAMES:
        row = results.get(label) or {}
        signal = str(row.get("signal", "NO ENTRY")).upper().strip()
        if signal in grouped and bool(row.get("entry_condition", False)):
            grouped[signal].append(row)

    # Only publish the dominant bias. If BUY and SELL strategies appear
    # together, keep the side with stronger agreement instead of showing
    # conflicting directions in the Strategy Decision column.
    if grouped["BUY"] and grouped["SELL"]:
        buy_strength = sum(max(float(r.get("score", 1) or 1), 1) for r in grouped["BUY"])
        sell_strength = sum(max(float(r.get("score", 1) or 1), 1) for r in grouped["SELL"])
        grouped["SELL" if buy_strength > sell_strength else "BUY"] = []

    parts = []
    for direction, rows in grouped.items():
        if not rows:
            continue

        count = len(rows)

        # Score weighted TP/SL selection
        total_weight = sum(max(float(r.get("score", 1) or 1), 1) for r in rows)
        avg_tp = sum(float(r.get("tp", 40) or 40) * max(float(r.get("score", 1) or 1), 1)
                     for r in rows) / total_weight

        # Noise-aware TP selection:
        # SL is fixed at 20 pips. TP is not simply the largest strategy target.
        # It is reduced when historical candle noise/volatility risk is high.
        noise_values = []
        for r in rows:
            for key in ("noise", "noise_ratio", "adverse_noise", "max_noise"):
                try:
                    if r.get(key) is not None:
                        noise_values.append(float(r.get(key)))
                        break
                except Exception:
                    pass
        noise_factor = 1.0
        if noise_values:
            avg_noise = sum(noise_values) / len(noise_values)
            if avg_noise > 1:
                noise_factor = max(0.55, 1.0 - ((avg_noise - 1) * 0.15))

        # Favor TP that survives normal market noise before SL20.
        tp = int(round((avg_tp * noise_factor) / 10) * 10)
        sl = 20

        # Low-risk safety limits
        tp = max(30, min(tp, 90))

        parts.append(f"{direction}-{count} TP{tp} SL{sl}")

    return " | ".join(parts) or "None"

def ranked_pullback_scores(df, higher_bias, middle_bias=None):
    middle=middle_bias if middle_bias in {"BUY","SELL"} else higher_bias
    return {s:int(v["score"]) for s,v in evaluate_pullback_strategies(df,higher_bias,middle).items()}

def run_pullback_models(df, higher_bias, middle_bias=None, symbol="UNKNOWN"):
    middle=middle_bias if middle_bias in {"BUY","SELL"} else higher_bias
    return strategy_decision(evaluate_pullback_strategies(df,higher_bias,middle,symbol=symbol))

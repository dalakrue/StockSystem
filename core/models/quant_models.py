"""
Math + ML algorithm core for the quant app.

Upgrade goals:
- Keep the original public functions: add_indicators, regime_label, ml_bias,
  history_match, quant_stack, pre_manual_decision.
- Make indicator math more robust against bad candles, zeros, NaN, inf, duplicate time,
  and tiny datasets.
- Reduce ML leakage by using walk-forward chronological split and excluding unfinished
  future-label tail.
- Add probability calibration, 3-class BUY/SELL/WAIT support, risk-adjusted scoring,
  and deterministic Monte Carlo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    from core.common import safe_float
except Exception:
    def safe_float(x, default=0.0):
        try:
            v = float(x)
            return v if math.isfinite(v) else default
        except Exception:
            return default

try:
    from ta.trend import ADXIndicator
    from ta.volatility import AverageTrueRange
except Exception:
    ADXIndicator = None
    AverageTrueRange = None

try:
    from sklearn.ensemble import ExtraTreesClassifier, GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, log_loss
    from sklearn.preprocessing import RobustScaler
except Exception:
    ExtraTreesClassifier = None
    GradientBoostingClassifier = None
    RandomForestClassifier = None
    LogisticRegression = None
    accuracy_score = None
    log_loss = None
    RobustScaler = None

EPS = 1e-12
DEFAULT_HORIZON = 12
RNG_SEED = 42

FEATURE_COLS = [
    "adx", "plus_di", "minus_di", "atr", "pressure", "adx_slope", "atr_slope",
    "ret", "log_ret", "momentum", "momentum_velocity", "volatility", "realized_volatility",
    "vol_decay", "fat_tail", "robust_tail_z", "mean_dist", "mean_dist_atr", "wick_ratio",
    "range_expansion", "directional_efficiency", "trend_power", "trend_age", "exhaustion_risk",
    "start_impulse_score", "pullback_risk", "breakout_quality", "noise_ratio", "micro_structure_score",
]


def _finite_float(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        return v if np.isfinite(v) else default
    except Exception:
        return default


def _clean_ohlc(df: Any) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or len(df) == 0:
        return pd.DataFrame()
    out = df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]
    if "datetime" in out.columns and "time" not in out.columns:
        out = out.rename(columns={"datetime": "time"})
    if "timestamp" in out.columns and "time" not in out.columns:
        out = out.rename(columns={"timestamp": "time"})
    for c in ["open", "high", "low", "close"]:
        if c not in out.columns:
            raise ValueError(f"Missing column: {c}")
        out[c] = pd.to_numeric(out[c], errors="coerce")
    if "volume" not in out.columns:
        out["volume"] = 0.0
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(0)
    if "time" in out.columns:
        out["time"] = pd.to_datetime(out["time"], errors="coerce")
        out = out.dropna(subset=["time"]).sort_values("time")
        out = out.drop_duplicates("time", keep="last")
    out = out.replace([np.inf, -np.inf], np.nan)
    out = out.dropna(subset=["open", "high", "low", "close"])
    # Repair impossible high/low relationships without deleting usable rows.
    hi = out[["open", "high", "low", "close"]].max(axis=1)
    lo = out[["open", "high", "low", "close"]].min(axis=1)
    out["high"] = np.maximum(out["high"], hi)
    out["low"] = np.minimum(out["low"], lo)
    return out.reset_index(drop=True)


def _safe_div(num: Any, den: Any, default: float = 0.0) -> Any:
    return pd.Series(num).astype(float).div(pd.Series(den).replace(0, np.nan).astype(float)).replace([np.inf, -np.inf], np.nan).fillna(default)


def _ema(s: pd.Series, span: int) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").ewm(span=span, adjust=False, min_periods=1).mean()


def _robust_zscore(s: pd.Series, window: int = 120) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    med = x.rolling(window, min_periods=max(10, window // 5)).median()
    mad = (x - med).abs().rolling(window, min_periods=max(10, window // 5)).median()
    return ((x - med) / (1.4826 * mad.replace(0, np.nan))).replace([np.inf, -np.inf], np.nan).fillna(0)


def _fallback_indicators(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    out = df.copy()
    prev_close = out["close"].shift(1)
    tr = pd.concat([
        out["high"] - out["low"],
        (out["high"] - prev_close).abs(),
        (out["low"] - prev_close).abs(),
    ], axis=1).max(axis=1).fillna(0)
    atr = _ema(tr, window)
    up_move = out["high"].diff().fillna(0)
    down_move = -out["low"].diff().fillna(0)
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=out.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=out.index)
    plus_di = 100 * _ema(plus_dm, window) / atr.replace(0, np.nan)
    minus_di = 100 * _ema(minus_dm, window) / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    out["adx"] = _ema(dx.fillna(0), window).fillna(0)
    out["plus_di"] = plus_di.replace([np.inf, -np.inf], np.nan).fillna(0)
    out["minus_di"] = minus_di.replace([np.inf, -np.inf], np.nan).fillna(0)
    out["atr"] = atr.fillna(0)
    return out


def add_indicators(df: Any) -> pd.DataFrame:
    try:
        out = _clean_ohlc(df)
    except Exception:
        return pd.DataFrame()
    if len(out) < 5:
        return out
    try:
        if ADXIndicator is not None and AverageTrueRange is not None and len(out) >= 30:
            adx_obj = ADXIndicator(out["high"], out["low"], out["close"], window=14)
            atr_obj = AverageTrueRange(out["high"], out["low"], out["close"], window=14)
            out["adx"] = adx_obj.adx()
            out["plus_di"] = adx_obj.adx_pos()
            out["minus_di"] = adx_obj.adx_neg()
            out["atr"] = atr_obj.average_true_range()
        else:
            out = _fallback_indicators(out)
    except Exception:
        out = _fallback_indicators(out)

    out["ret"] = out["close"].pct_change().replace([np.inf, -np.inf], np.nan).fillna(0)
    out["log_ret"] = np.log(out["close"].replace(0, np.nan) / out["close"].shift(1).replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0)
    out["momentum"] = out["close"].diff().fillna(0)
    out["pressure"] = out["plus_di"].fillna(0) - out["minus_di"].fillna(0)
    out["adx_slope"] = out["adx"].diff().fillna(0)
    out["atr_slope"] = out["atr"].diff().fillna(0)
    out["range"] = (out["high"] - out["low"]).clip(lower=0).replace(0, np.nan)
    out["body"] = (out["close"] - out["open"]).abs()
    out["upper_wick"] = (out["high"] - out[["open", "close"]].max(axis=1)).clip(lower=0)
    out["lower_wick"] = (out[["open", "close"]].min(axis=1) - out["low"]).clip(lower=0)
    out["wick_ratio"] = ((out["range"] - out["body"]) / out["range"]).replace([np.inf, -np.inf], np.nan).fillna(0)
    out["volatility"] = out["ret"].rolling(30, min_periods=5).std().fillna(0)
    out["realized_volatility"] = out["log_ret"].rolling(60, min_periods=10).std().fillna(0) * np.sqrt(60)
    out["vol_decay"] = out["volatility"].diff().fillna(0)
    out["fat_tail"] = out["ret"].rolling(90, min_periods=20).kurt().replace([np.inf, -np.inf], np.nan).fillna(0)
    out["robust_tail_z"] = _robust_zscore(out["ret"], 120).abs()
    out["ma20"] = out["close"].rolling(20, min_periods=1).mean()
    out["ma50"] = out["close"].rolling(50, min_periods=1).mean()
    out["ma200"] = out["close"].rolling(200, min_periods=1).mean()
    out["mean_dist"] = (out["close"] - out["ma50"]).fillna(0)
    out["mean_dist_atr"] = (out["mean_dist"] / out["atr"].replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0)
    out["trend_power"] = out["adx"].fillna(0) * out["pressure"].abs().fillna(0)
    out["momentum_velocity"] = _ema(out["momentum"], 5).fillna(0)
    avg_range = out["range"].rolling(30, min_periods=5).mean().replace(0, np.nan)
    out["range_expansion"] = (out["range"] / avg_range).replace([np.inf, -np.inf], np.nan).fillna(1)
    path = out["close"].diff().abs().rolling(30, min_periods=5).sum().replace(0, np.nan)
    direct = (out["close"] - out["close"].shift(30)).abs()
    out["directional_efficiency"] = (direct / path).replace([np.inf, -np.inf], np.nan).fillna(0).clip(0, 1)
    side = np.sign(out["pressure"].fillna(0))
    out["trend_age"] = (side == side.shift(1)).astype(int).rolling(30, min_periods=1).sum()
    out["noise_ratio"] = (1 - out["directional_efficiency"]).clip(0, 1)
    out["pullback_risk"] = np.clip((out["mean_dist_atr"].abs() / 4) * 35 + out["wick_ratio"] * 35 + out["robust_tail_z"].clip(0, 4) * 7.5, 0, 100)
    out["breakout_quality"] = np.clip(out["directional_efficiency"] * 45 + out["range_expansion"].clip(0, 3) * 18 + out["adx_slope"].clip(lower=0) * 6 + out["pressure"].abs() / 2, 0, 100)
    out["micro_structure_score"] = np.clip((1 - out["noise_ratio"]) * 40 + out["breakout_quality"] * 0.35 + (100 - out["pullback_risk"]) * 0.25, 0, 100)
    out["exhaustion_risk"] = np.clip(
        out["wick_ratio"].clip(0, 1) * 30
        + out["fat_tail"].clip(lower=0, upper=10) * 4
        + out["trend_age"].clip(0, 30) / 30 * 20
        + out["mean_dist_atr"].abs().clip(0, 5) * 6
        - out["directional_efficiency"].clip(0, 1) * 15,
        0, 100,
    )
    out["start_impulse_score"] = np.clip(
        out["adx_slope"].clip(lower=0) * 7
        + out["range_expansion"].clip(0, 3) * 16
        + out["directional_efficiency"].clip(0, 1) * 34
        + out["pressure"].abs().clip(0, 80) / 2
        + out["momentum_velocity"].abs() / out["atr"].replace(0, np.nan) * 8,
        0, 100,
    ).replace([np.inf, -np.inf], np.nan).fillna(0)
    return out.replace([np.inf, -np.inf], np.nan).ffill().fillna(0).reset_index(drop=True)


def _feature_frame(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    features = [c for c in FEATURE_COLS if c in df.columns]
    X = df[features].replace([np.inf, -np.inf], np.nan).fillna(0) if features else pd.DataFrame(index=df.index)
    return X, features


def _fallback_bias(df: pd.DataFrame, mode: str = "fallback") -> Tuple[str, float, Dict[str, Any]]:
    last = df.iloc[-1] if isinstance(df, pd.DataFrame) and not df.empty else {}
    pressure = _finite_float(getattr(last, "get", lambda *_: 0)("pressure", 0)) if len(df) else 0
    eff = _finite_float(getattr(last, "get", lambda *_: 0)("directional_efficiency", 0)) if len(df) else 0
    start = _finite_float(getattr(last, "get", lambda *_: 0)("start_impulse_score", 0)) if len(df) else 0
    raw = 0.50 + np.tanh(pressure / 35.0) * 0.16 + (eff - 0.35) * 0.08 + (start - 50) / 600
    raw = float(np.clip(raw, 0.32, 0.68))
    bias = "BUY" if raw >= 0.53 else "SELL" if raw <= 0.47 else "WAIT"
    return bias, float(max(raw, 1 - raw)), {"mode": mode, "fallback_buy_probability": round(raw, 4)}


def _future_target(df: pd.DataFrame, horizon: int = DEFAULT_HORIZON, min_move_atr: float = 0.08) -> pd.Series:
    close = pd.to_numeric(df["close"], errors="coerce")
    future_close = pd.Series(np.nan, index=df.index, dtype=float)
    if len(close) > horizon:
        future_close.iloc[:-horizon] = close.iloc[horizon:].to_numpy()
    future = future_close - close
    atr = df.get("atr", pd.Series(0, index=df.index)).replace(0, np.nan)
    future_atr = (future / atr).replace([np.inf, -np.inf], np.nan)
    return pd.Series(np.where(future_atr > min_move_atr, 1, np.where(future_atr < -min_move_atr, 0, np.nan)), index=df.index)


def ml_bias(df: Any, horizon: int = DEFAULT_HORIZON) -> Tuple[str, float, Dict[str, Any]]:
    df = add_indicators(df)
    if df.empty:
        return "WAIT", 0.50, {"mode": "empty_data"}
    if len(df) < 120 or RandomForestClassifier is None or GradientBoostingClassifier is None:
        return _fallback_bias(df, "fallback_not_enough_rows_or_sklearn")
    work = df.copy()
    work["target"] = _future_target(work, horizon=horizon, min_move_atr=0.08)
    # Remove unfinished future labels and neutral micro-noise rows for cleaner directional training.
    work = work.dropna(subset=["target"]).copy()
    X, features = _feature_frame(work)
    if len(features) < 8 or len(work) < 100 or work["target"].nunique() < 2:
        return _fallback_bias(df, "fallback_low_label_variation")
    try:
        split = int(len(work) * 0.78)
        if split < 60 or len(work) - split < 20:
            return _fallback_bias(df, "fallback_split_too_small")
        X_train, y_train = X.iloc[:split], work["target"].iloc[:split].astype(int)
        X_val, y_val = X.iloc[split:], work["target"].iloc[split:].astype(int)
        models = []
        rf = RandomForestClassifier(n_estimators=260, max_depth=9, min_samples_leaf=4, random_state=7, n_jobs=1, class_weight="balanced_subsample")
        gb = GradientBoostingClassifier(random_state=11, n_estimators=120, max_depth=3, learning_rate=0.045)
        rf.fit(X_train, y_train); gb.fit(X_train, y_train)
        models.extend([("rf", rf, 0.55), ("gb", gb, 0.45)])
        if ExtraTreesClassifier is not None and len(X_train) >= 250:
            et = ExtraTreesClassifier(n_estimators=220, max_depth=10, min_samples_leaf=4, random_state=13, n_jobs=1, class_weight="balanced")
            et.fit(X_train, y_train)
            models.append(("et", et, 0.25))
        weight_sum = sum(w for _, _, w in models) or 1
        x_last = df[features].tail(1).replace([np.inf, -np.inf], np.nan).fillna(0)
        model_probs = {}
        raw_buy = 0.0
        for name, model, weight in models:
            p = float(model.predict_proba(x_last)[0][1])
            model_probs[f"{name}_buy"] = round(p, 4)
            raw_buy += p * weight / weight_sum
        val_probs = np.zeros(len(X_val))
        for _, model, weight in models:
            val_probs += model.predict_proba(X_val)[:, 1] * weight / weight_sum
        val_acc = float(accuracy_score(y_val, val_probs >= 0.5)) if accuracy_score is not None else 0.0
        # Conservative calibration: low validation accuracy pulls probability toward 0.50.
        shrink = float(np.clip((val_acc - 0.50) / 0.20, 0.25, 1.0))
        buy_prob = 0.50 + (raw_buy - 0.50) * shrink
        bias = "BUY" if buy_prob >= 0.54 else "SELL" if buy_prob <= 0.46 else "WAIT"
        conf = float(max(buy_prob, 1 - buy_prob))
        meta = {
            "mode": "walk_forward_ml_ensemble",
            "buy_probability": round(float(buy_prob), 4),
            "raw_buy_probability": round(float(raw_buy), 4),
            "validation_accuracy": round(val_acc, 4),
            "calibration_shrink": round(shrink, 4),
            "train_rows": int(len(X_train)),
            "validation_rows": int(len(X_val)),
            "features": len(features),
        }
        meta.update(model_probs)
        return bias, conf, meta
    except Exception as exc:
        bias, conf, meta = _fallback_bias(df, "ml_error_fallback")
        meta["error"] = str(exc)[:180]
        return bias, conf, meta


def regime_label(df: Any) -> Tuple[str, Dict[str, Any]]:
    df = add_indicators(df)
    if df.empty:
        return "UNKNOWN", {}
    last = df.iloc[-1]
    adx = _finite_float(last.get("adx", 0)); slope = _finite_float(last.get("adx_slope", 0))
    eff = _finite_float(last.get("directional_efficiency", 0)); expansion = _finite_float(last.get("range_expansion", 1))
    exhaustion = _finite_float(last.get("exhaustion_risk", 0)); start = _finite_float(last.get("start_impulse_score", 0))
    pressure = _finite_float(last.get("pressure", 0)); noise = _finite_float(last.get("noise_ratio", 1))
    if start >= 68 and slope > 0 and eff >= 0.34 and expansion >= 1.05:
        regime = "IMPULSE_START"
    elif adx >= 25 and eff >= 0.25 and exhaustion < 62 and noise < 0.78:
        regime = "TREND_CONTINUATION"
    elif exhaustion >= 72 or _finite_float(last.get("pullback_risk", 0)) >= 78:
        regime = "EXHAUSTION_OR_REVERSAL_RISK"
    elif expansion < 0.85 and adx < 20:
        regime = "ACCUMULATION_OR_RANGE"
    elif adx < 18 and abs(pressure) < 8:
        regime = "DISTRIBUTION_OR_CHOP"
    else:
        regime = "WAIT_CONFIRMATION"
    return regime, {
        "adx": round(adx, 2), "adx_slope": round(slope, 4), "directional_efficiency": round(eff, 3),
        "range_expansion": round(expansion, 3), "exhaustion_risk": round(exhaustion, 1),
        "start_impulse_score": round(start, 1), "pressure": round(pressure, 2), "noise_ratio": round(noise, 3),
    }


def history_match(df: Any, trade_history: Optional[Sequence[Dict[str, Any]]] = None) -> Tuple[float, int]:
    df = add_indicators(df)
    if df.empty:
        return 0.50, 0
    latest = df.iloc[-1]
    try:
        hist = pd.DataFrame(trade_history or [])
        if not hist.empty and {"pressure", "adx", "result"}.issubset(hist.columns):
            hist = hist.copy()
            for c in ["pressure", "adx"]:
                hist[c] = pd.to_numeric(hist[c], errors="coerce")
            if "directional_efficiency" not in hist.columns:
                hist["directional_efficiency"] = 0.0
            hist["directional_efficiency"] = pd.to_numeric(hist["directional_efficiency"], errors="coerce").fillna(0)
            hist = hist.dropna(subset=["pressure", "adx"])
            if not hist.empty:
                hist["dist"] = (
                    (hist["pressure"] - _finite_float(latest.get("pressure", 0))).abs() / 20
                    + (hist["adx"] - _finite_float(latest.get("adx", 0))).abs() / 25
                    + (hist["directional_efficiency"] - _finite_float(latest.get("directional_efficiency", 0))).abs() * 2
                )
                m = hist.sort_values("dist").head(40)
                wins = m["result"].astype(str).str.upper().isin(["WIN", "PROFIT", "TP", "TAKE_PROFIT"]).mean()
                if np.isfinite(wins):
                    return float(np.clip(wins, 0.25, 0.85)), int(len(m))
    except Exception:
        pass
    score = 0.50 + np.tanh(abs(_finite_float(latest.get("pressure", 0))) / 30 + _finite_float(latest.get("adx", 0)) / 100) / 4
    return float(np.clip(score, 0.35, 0.75)), 0


def _monte_carlo_direction(df: pd.DataFrame, bias: str, horizon: int = 720) -> float:
    try:
        ret = pd.to_numeric(df["log_ret"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna().tail(500)
        if len(ret) < 30:
            return 0.50
        mu = float(ret.mean()); sigma = float(ret.std() + EPS)
        # Bootstrap + normal mixture gives more robust fat-tail behavior than normal-only.
        rng = np.random.default_rng(RNG_SEED)
        boot = rng.choice(ret.values, size=(400, min(horizon, 720)), replace=True).sum(axis=1)
        norm = rng.normal(mu, sigma, size=(400, min(horizon, 720))).sum(axis=1)
        sim = 0.65 * boot + 0.35 * norm
        return float((sim > 0).mean()) if bias == "BUY" else float((sim < 0).mean()) if bias == "SELL" else 0.50
    except Exception:
        return 0.50


def _account_risk_adjustment(account: Optional[Dict[str, Any]]) -> float:
    if not isinstance(account, dict) or not account:
        return 0.0
    margin_level = _finite_float(account.get("margin_level", account.get("margin_level_pct", 999)), 999)
    drawdown = _finite_float(account.get("drawdown_pct", account.get("drawdown", 0)), 0)
    open_positions = _finite_float(account.get("open_positions", account.get("positions", 0)), 0)
    penalty = 0.0
    if margin_level < 120: penalty += 7
    if margin_level < 80: penalty += 8
    if margin_level < 60: penalty += 10
    if drawdown > 35: penalty += 5
    if drawdown > 55: penalty += 6
    if open_positions > 50: penalty += 4
    return float(np.clip(penalty, 0, 28))


def quant_stack(df: Any, trade_history: Optional[Sequence[Dict[str, Any]]] = None, account: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    df = add_indicators(df)
    if df.empty or len(df) < 5:
        return {"bias": "WAIT", "safe_pct": 1, "scale10": 0.1, "history_samples": 0, "error": "not_enough_data"}
    last = df.iloc[-1]
    bias, conf, meta = ml_bias(df)
    hm, hm_n = history_match(df, trade_history)
    regime, regime_meta = regime_label(df)
    vol = _finite_float(last.get("volatility", 0)); atr = max(_finite_float(last.get("atr", 0)), EPS)
    mean_revert_risk = float(np.clip(abs(_finite_float(last.get("mean_dist", 0))) / (atr * 3 + EPS), 0, 1))
    decay = max(0.0, -_finite_float(last.get("vol_decay", 0)) * 10000)
    fat_tail = float(np.clip(max(0, _finite_float(last.get("fat_tail", 0))) / 10 + _finite_float(last.get("robust_tail_z", 0)) / 8, 0, 1))
    exhaustion = float(np.clip(_finite_float(last.get("exhaustion_risk", 0)) / 100, 0, 1))
    impulse = float(np.clip(_finite_float(last.get("start_impulse_score", 0)) / 100, 0, 1))
    breakout = float(np.clip(_finite_float(last.get("breakout_quality", 0)) / 100, 0, 1))
    noise = float(np.clip(_finite_float(last.get("noise_ratio", 1)), 0, 1))
    bayes = conf * 0.33 + hm * 0.20 + (1 - mean_revert_risk) * 0.10 + (1 - fat_tail) * 0.10 + impulse * 0.10 + breakout * 0.08 + (1 - exhaustion) * 0.06 + (1 - noise) * 0.03
    safe_pct = float(np.clip(bayes * 100, 1, 99))
    mc_positive = _monte_carlo_direction(df, bias)
    spoofing_risk = float(np.clip(abs(_finite_float(last.get("pressure", 0))) / (_finite_float(last.get("adx", 0)) + 1) / 3, 0, 1))
    ergodicity = float(np.clip(1 - fat_tail * 0.50 - mean_revert_risk * 0.22 - exhaustion * 0.20 - noise * 0.08, 0, 1))
    account_penalty = _account_risk_adjustment(account)
    final_pct = float(np.clip((safe_pct * 0.55 + mc_positive * 100 * 0.18 + ergodicity * 100 * 0.12 + impulse * 100 * 0.08 + breakout * 100 * 0.07) - spoofing_risk * 7 - account_penalty, 1, 99))
    if regime in ["EXHAUSTION_OR_REVERSAL_RISK", "DISTRIBUTION_OR_CHOP"]:
        final_pct *= 0.82
    final_bias = "WAIT" if final_pct < 45 or bias == "WAIT" else bias
    return {
        "bias": final_bias, "safe_pct": round(final_pct, 1), "scale10": round(final_pct / 10, 1),
        "regime": regime, "regime_meta": regime_meta,
        "ml_conf_pct": round(conf * 100, 1), "history_match_pct": round(hm * 100, 1), "history_samples": hm_n,
        "volatility": round(vol, 8), "vol_decay": round(decay, 2), "mean_revert_risk_pct": round(mean_revert_risk * 100, 1),
        "fat_tail_risk_pct": round(fat_tail * 100, 1), "exhaustion_risk_pct": round(exhaustion * 100, 1),
        "impulse_start_pct": round(impulse * 100, 1), "breakout_quality_pct": round(breakout * 100, 1), "noise_risk_pct": round(noise * 100, 1),
        "bayes_pct": round(bayes * 100, 1), "kelly_fraction": round(max(0, min(0.25, (bayes * 2 - 1) / 2)), 3),
        "monte_carlo_pct": round(mc_positive * 100, 1), "ergodicity_pct": round(ergodicity * 100, 1), "spoofing_risk_pct": round(spoofing_risk * 100, 1),
        "account_risk_penalty_pct": round(account_penalty, 1), "meta": meta,
        "adx": round(_finite_float(last.get("adx", 0)), 2), "pressure": round(_finite_float(last.get("pressure", 0)), 2), "atr": round(float(atr), 4),
        "directional_efficiency": round(_finite_float(last.get("directional_efficiency", 0)), 3), "range_expansion": round(_finite_float(last.get("range_expansion", 0)), 3),
    }


def trend_math_snapshot(df: Any) -> Dict[str, Any]:
    """Small safe summary usable by any tab for diagnostics."""
    dfi = add_indicators(df)
    if dfi.empty:
        return {"status": "NO_DATA"}
    last = dfi.iloc[-1]
    q = quant_stack(dfi.tail(3000))
    return {
        "status": "OK", "rows": int(len(dfi)), "bias": q.get("bias", "WAIT"), "safe_pct": q.get("safe_pct", 0),
        "regime": q.get("regime", "UNKNOWN"), "adx": round(_finite_float(last.get("adx", 0)), 2),
        "pressure": round(_finite_float(last.get("pressure", 0)), 2), "atr": round(_finite_float(last.get("atr", 0)), 4),
        "efficiency": round(_finite_float(last.get("directional_efficiency", 0)) * 100, 2),
        "fat_tail": round(_finite_float(last.get("fat_tail", 0)), 3),
        "exhaustion_risk_pct": q.get("exhaustion_risk_pct", 0), "impulse_start_pct": q.get("impulse_start_pct", 0),
    }


def pre_manual_decision(plus_now, minus_now, plus_prev, minus_prev, selected_decision="WAIT") -> Dict[str, Any]:
    plus_now = safe_float(plus_now); minus_now = safe_float(minus_now)
    plus_prev = safe_float(plus_prev); minus_prev = safe_float(minus_prev)
    selected_decision = str(selected_decision or "WAIT").upper()
    pressure = plus_now - minus_now
    prev = plus_prev - minus_prev
    accel = pressure - prev
    agreement = 1.0 if (selected_decision == "BUY" and pressure > 0) or (selected_decision == "SELL" and pressure < 0) else 0.0
    raw = 50 + np.tanh(pressure / 20) * 20 + np.tanh(accel / 10) * 15
    if selected_decision in ["BUY", "SELL"]:
        raw += 8 * agreement - 14 * (1 - agreement)
    else:
        raw = 100 - abs(raw - 50)
    pct = float(np.clip(raw, 0, 100))
    bias = "BUY" if pressure > 0 else "SELL" if pressure < 0 else "WAIT"
    return {
        "manual_bias": bias, "decision_quality_pct": round(pct, 1), "scale10": round(pct / 10, 1),
        "pressure": round(pressure, 2), "acceleration": round(accel, 2),
        "comment": "Robust manual emergency model; DI pressure, acceleration, and selected-side agreement are checked without API dependency.",
    }

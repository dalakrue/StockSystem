"""Institutional-quality additive Field 3 regime lifecycle monitor.

This module is a Settings-owned, shadow-only sidecar.  It never overwrites the
protected Lower/Middle/Higher regime calculations, production decisions,
priority values, historical tables, canonical snapshot, or broker-time rules.

The implementation deliberately separates:
* the preserved production regime outputs;
* causal filtered latent-state probabilities;
* retrospective smoothed/PELT audit evidence;
* explicit-duration and survival estimates;
* cost-adjusted directional bias probabilities;
* calibration, data-quality, drift, trust and action gates.

Expensive work is performed only by the Settings transaction.  Lunch rendering
reads the saved payload and never fits a model.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass
from hashlib import sha256
from math import exp, log
from typing import Any, Iterable, Mapping, MutableMapping, Sequence
import json
import math
import time

import numpy as np
import pandas as pd

VERSION = "field3-regime-lifecycle-monitor-20260701-v1"
STATE_KEY = "field3_regime_lifecycle_monitor_20260701"
EPS = 1e-12
REGIMES = (
    "BULL_TREND", "BEAR_TREND", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION",
)
HORIZONS = (1, 3, 6)
FIRST_14_COLUMNS = [
    "Broker Candle Time", "Existing Lower Regime", "Existing Middle Regime",
    "Existing Higher Regime", "Canonical Combined Regime", "Regime Bias",
    "Selected-Regime Posterior", "Second-Best Regime", "Second-Best Probability",
    "Probability Margin", "Regime Age in Completed H1 Candles",
    "Expected Total Regime Duration", "Median Remaining Duration",
    "Remaining-Duration 50% Interval",
]
ACTION_THRESHOLDS = {
    "trade": {
        "trust": 80.0, "bias_reliability": 75.0, "posterior": 0.75,
        "margin": 0.20, "max_change_point": 0.45,
        "max_horizon_switch_risk": 0.40, "data_quality": 90.0,
    },
    "reduce": {"trust_min": 70.0, "trust_max": 79.999},
    "trust_labels": {"strong": 85, "usable": 70, "weak": 55, "unreliable": 40},
}
TRUST_WEIGHTS = {
    "calibrated_regime_confidence": 1.0,
    "calibration_quality": 1.0,
    "data_quality": 1.0,
    "stability": 1.0,
    "one_minus_drift": 1.0,
    "critical_component_cap": 0.15,
}


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "to_dict"):
        try:
            out = value.to_dict()
            return dict(out) if isinstance(out, Mapping) else {}
        except Exception:
            return {}
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if np.isfinite(out) else default
    except Exception:
        return default


def _clip01(value: Any) -> float:
    return float(np.clip(_float(value), 0.0, 1.0))


def _jsonable(value: Any) -> Any:
    if isinstance(value, (np.integer,)): return int(value)
    if isinstance(value, (np.floating,)): return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)): return bool(value)
    if isinstance(value, pd.Timestamp): return value.isoformat()
    if isinstance(value, pd.Timedelta): return value.total_seconds()
    if isinstance(value, np.ndarray): return [_jsonable(x) for x in value.tolist()]
    if isinstance(value, pd.Series): return [_jsonable(x) for x in value.tolist()]
    if isinstance(value, pd.DataFrame): return [_jsonable(x) for x in value.to_dict("records")]
    if isinstance(value, Mapping): return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_jsonable(x) for x in value]
    return value


def _stable_hash(parts: Sequence[Any]) -> str:
    raw = json.dumps(_jsonable(list(parts)), sort_keys=True, separators=(",", ":"), default=str)
    return sha256(raw.encode("utf-8")).hexdigest()


def _snapshot_identity(snapshot: Any) -> dict[str, Any]:
    raw = _mapping(snapshot)
    return {
        "run_id": str(raw.get("run_id") or ""),
        "generation_id": str(raw.get("generation_id") or raw.get("calculation_generation") or ""),
        "snapshot_hash": str(raw.get("source_snapshot_hash") or raw.get("snapshot_hash") or ""),
        "symbol": str(raw.get("symbol") or "EURUSD").upper(),
        "timeframe": str(raw.get("timeframe") or "H1").upper(),
        "broker_candle_time": raw.get("broker_candle_time") or raw.get("latest_completed_candle_time"),
        "protected_regime": str(raw.get("regime") or "UNKNOWN"),
        "protected_bias": str(raw.get("less_risky_decision") or raw.get("decision") or "WAIT").upper(),
    }


def _column(frame: pd.DataFrame, *aliases: str) -> str | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    normalized = {str(c).strip().lower().replace("_", " "): str(c) for c in frame.columns}
    for alias in aliases:
        hit = normalized.get(str(alias).strip().lower().replace("_", " "))
        if hit is not None:
            return hit
    return None


def _source_frame(state: Mapping[str, Any], identity: Mapping[str, Any], maximum_rows: int = 5000) -> tuple[pd.DataFrame, dict[str, Any]]:
    from core.lunch_h1_data_quality_v13 import cached_completed_ohlc, combined_h1_time

    source = cached_completed_ohlc(state)
    if source.empty:
        return pd.DataFrame(), {"status": "FAIL", "reasons": ["missing_completed_h1_source"]}
    work = source.copy(deep=False)
    work = work.rename(columns={c: str(c).strip().lower() for c in work.columns})
    if "time" not in work.columns:
        parsed = combined_h1_time(source)
        if parsed.notna().any():
            work = work.copy()
            work["time"] = parsed
    aliases = {"o": "open", "h": "high", "l": "low", "c": "close", "tick_volume": "volume"}
    for src, dst in aliases.items():
        if dst not in work.columns and src in work.columns:
            work = work.rename(columns={src: dst})
    required = ["time", "open", "high", "low", "close"]
    missing = [c for c in required if c not in work.columns]
    if missing:
        return pd.DataFrame(), {"status": "FAIL", "reasons": [f"missing_{c}" for c in missing]}
    work["time"] = pd.to_datetime(work["time"], errors="coerce", utc=True)
    for c in ["open", "high", "low", "close", "spread", "volume"]:
        if c in work.columns:
            work[c] = pd.to_numeric(work[c], errors="coerce")
    raw_rows = len(work)
    work = work.dropna(subset=required).sort_values("time", kind="mergesort")
    duplicates = int(work.duplicated("time", keep=False).sum())
    work = work.drop_duplicates("time", keep="last")
    cutoff = None
    try:
        from core.shared_broker_time_20260622 import shared_broker_time_provider
        contract = shared_broker_time_provider(state)
        cutoff = pd.to_datetime(contract.get("latest_completed_h1_utc"), errors="coerce", utc=True)
    except Exception:
        contract = {}
    if pd.isna(cutoff):
        cutoff = pd.to_datetime(identity.get("broker_candle_time"), errors="coerce", utc=True)
    if pd.isna(cutoff):
        cutoff = work["time"].max()
    work = work.loc[work["time"].le(cutoff)].tail(max(720, int(maximum_rows))).reset_index(drop=True)
    return work, {
        "raw_rows": raw_rows, "deduplicated_rows": len(work), "duplicate_rows": duplicates,
        "cutoff_utc": cutoff.isoformat() if pd.notna(cutoff) else None,
        "broker_clock_available": bool(contract.get("broker_clock_available")) if isinstance(contract, Mapping) else False,
        "broker_clock": _jsonable(contract) if isinstance(contract, Mapping) else {},
    }


def _frame_signature(frame: pd.DataFrame) -> str:
    if frame.empty: return ""
    columns = [c for c in ("time", "open", "high", "low", "close", "spread", "volume") if c in frame]
    raw = pd.util.hash_pandas_object(frame[columns], index=False).values.tobytes()
    return sha256(raw).hexdigest()


def _data_quality(frame: pd.DataFrame, source_meta: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    critical: list[str] = []
    if frame.empty:
        return {"score": 0.0, "status": "INVALID", "critical": True, "reasons": ["no_completed_h1_rows"]}
    score = 100.0
    times = pd.to_datetime(frame["time"], errors="coerce", utc=True)
    invalid_ts = int(times.isna().sum())
    if invalid_ts:
        score -= min(30, invalid_ts * 3); reasons.append(f"invalid_timestamps:{invalid_ts}")
    if not times.dropna().is_monotonic_increasing:
        score -= 20; critical.append("non_monotonic_timestamps")
    duplicate_rows = int(source_meta.get("duplicate_rows") or 0)
    if duplicate_rows:
        score -= min(12, 100 * duplicate_rows / max(1, int(source_meta.get("raw_rows") or len(frame))))
        reasons.append(f"duplicate_candles:{duplicate_rows}")
    gaps = times.diff().dt.total_seconds().div(3600)
    # Ignore normal weekend closures; penalize suspicious gaps inside the trading week.
    suspicious = gaps[(gaps > 1.5) & (gaps < 47.0)]
    missing_candles = int(np.maximum(np.rint(suspicious).astype(int) - 1, 0).sum()) if len(suspicious) else 0
    if missing_candles:
        score -= min(20, missing_candles * 0.6); reasons.append(f"missing_h1_candles:{missing_candles}")
    ohlc_bad = ((frame["high"] < frame[["open", "close", "low"]].max(axis=1)) |
                (frame["low"] > frame[["open", "close", "high"]].min(axis=1))).sum()
    if int(ohlc_bad):
        score -= min(40, int(ohlc_bad) * 5); critical.append(f"invalid_ohlc:{int(ohlc_bad)}")
    last = times.max()
    cutoff = pd.to_datetime(source_meta.get("cutoff_utc"), errors="coerce", utc=True)
    stale_hours = float((cutoff - last).total_seconds() / 3600.0) if pd.notna(cutoff) and pd.notna(last) else None
    if stale_hours is None or stale_hours > 1.1:
        score -= 25; critical.append(f"stale_latest_candle:{stale_hours}")
    if len(frame) < 480:
        score -= 25; reasons.append(f"insufficient_feature_history:{len(frame)}<480")
    elif len(frame) < 1000:
        score -= 8; reasons.append(f"limited_model_history:{len(frame)}<1000")
    spread = pd.to_numeric(frame.get("spread"), errors="coerce") if "spread" in frame else pd.Series(dtype=float)
    abnormal_spread = False
    if not spread.empty and spread.notna().sum() >= 30:
        recent = float(spread.iloc[-1])
        q99 = float(spread.iloc[:-1].quantile(.99)) if spread.iloc[:-1].notna().sum() else recent
        abnormal_spread = bool(np.isfinite(recent) and np.isfinite(q99) and recent > max(q99, EPS) * 1.25)
        if abnormal_spread:
            score -= 12; reasons.append("abnormal_spread")
    provider_disagreement = False
    for c in frame.columns:
        if "provider" in c and "disagreement" in c:
            value = _float(frame[c].iloc[-1])
            provider_disagreement = value > 0.25 if value <= 1 else value > 25
    if provider_disagreement:
        score -= 15; reasons.append("provider_disagreement")
    if not bool(source_meta.get("broker_clock_available")):
        score -= 5; reasons.append("broker_clock_projection_unavailable")
    score = float(np.clip(score, 0, 100))
    if critical or score < 60:
        status = "INVALID" if critical or score < 40 else "POOR"
    elif score < 80: status = "CAUTION"
    elif score < 90: status = "GOOD"
    else: status = "STRONG"
    return {
        "score": round(score, 2), "status": status, "critical": bool(critical or score < 40),
        "reasons": critical + reasons, "missing_candles": missing_candles,
        "duplicate_rows": duplicate_rows, "stale_hours": stale_hours,
        "abnormal_spread": abnormal_spread, "provider_disagreement": provider_disagreement,
        "sample_count": len(frame),
    }


def _rolling_percentile(series: pd.Series, window: int, minimum: int) -> pd.Series:
    return series.rolling(window, min_periods=minimum).rank(pct=True)


def _feature_engine(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    close = frame["close"].astype(float).clip(lower=EPS)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    open_ = frame["open"].astype(float)
    logret = np.log(close).diff()
    prev = close.shift(1)
    tr = pd.concat([(high-low).abs(), (high-prev).abs(), (low-prev).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    up = high.diff(); down = -low.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    plus_di = 100 * plus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean() / (atr + EPS)
    minus_di = 100 * minus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean() / (atr + EPS)
    dx = 100 * (plus_di-minus_di).abs() / (plus_di+minus_di+EPS)
    adx = dx.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    mid = close.rolling(20, min_periods=10).mean()
    std20 = close.rolling(20, min_periods=10).std(ddof=0)
    bandwidth = 4.0 * std20 / (mid + EPS)
    rolling_high = high.rolling(24, min_periods=8).max()
    rolling_low = low.rolling(24, min_periods=8).min()
    range_width = (rolling_high-rolling_low)/(close+EPS)
    rv = logret.rolling(24, min_periods=8).std(ddof=0)
    directional_persistence = logret.rolling(12, min_periods=6).apply(
        lambda x: abs(float(np.sign(x).sum())) / max(1, len(x)), raw=True
    )
    equilibrium = close.rolling(48, min_periods=16).median()
    iqr_price = close.rolling(48, min_periods=16).quantile(.75) - close.rolling(48, min_periods=16).quantile(.25)
    body = (close-open_).abs() / ((high-low).abs()+EPS)
    upper_wick = high - pd.concat([open_, close], axis=1).max(axis=1)
    lower_wick = pd.concat([open_, close], axis=1).min(axis=1) - low
    wick_asym = (upper_wick-lower_wick)/((high-low).abs()+EPS)
    raw = pd.DataFrame(index=frame.index)
    raw["log_return"] = logret
    raw["return_3h"] = logret.rolling(3).sum()
    raw["return_6h"] = logret.rolling(6).sum()
    raw["realized_volatility"] = rv
    raw["atr_level"] = atr / close
    raw["atr_percentile"] = _rolling_percentile(raw["atr_level"], 720, 72)
    raw["adx_level"] = adx / 100.0
    raw["adx_slope"] = adx.diff(3) / 100.0
    raw["di_difference"] = (plus_di-minus_di)/100.0
    raw["directional_persistence"] = directional_persistence
    raw["rolling_range_width"] = range_width
    raw["compression_percentile"] = _rolling_percentile(bandwidth, 720, 72)
    raw["bollinger_bandwidth"] = bandwidth
    raw["volatility_of_volatility"] = rv.rolling(24, min_periods=8).std(ddof=0)
    raw["return_autocorrelation"] = logret.rolling(48, min_periods=16).apply(
        lambda x: pd.Series(x).autocorr(1), raw=False
    )
    raw["distance_from_equilibrium"] = (close-equilibrium)/(iqr_price+EPS)
    raw["body_to_range"] = body
    raw["wick_asymmetry"] = wick_asym
    if "volume" in frame:
        volume = pd.to_numeric(frame["volume"], errors="coerce")
        raw["tick_volume_change"] = np.log(volume.clip(lower=1)).diff()
    else:
        raw["tick_volume_change"] = np.nan
    if "spread" in frame:
        spread = pd.to_numeric(frame["spread"], errors="coerce")
        raw["spread"] = spread
        raw["spread_percentile"] = _rolling_percentile(spread, 720, 72)
    else:
        raw["spread"] = np.nan; raw["spread_percentile"] = np.nan
    hour = pd.to_datetime(frame["time"], utc=True).dt.hour
    raw["session_asia"] = ((hour < 7) | (hour >= 21)).astype(float)
    raw["session_london"] = hour.between(7, 11).astype(float)
    raw["session_overlap"] = hour.between(12, 16).astype(float)
    raw["session_new_york"] = hour.between(17, 20).astype(float)
    event_col = next((c for c in frame.columns if "event" in c and "risk" in c), None)
    raw["scheduled_macro_event_risk"] = pd.to_numeric(frame[event_col], errors="coerce") if event_col else 0.0
    cross_col = next((c for c in frame.columns if "cross" in c and "agreement" in c), None)
    raw["cross_market_agreement"] = pd.to_numeric(frame[cross_col], errors="coerce") if cross_col else np.nan
    raw["downside_tail_score"] = logret.clip(upper=0).pow(2).rolling(48, min_periods=16).mean()
    raw["upside_tail_score"] = logret.clip(lower=0).pow(2).rolling(48, min_periods=16).mean()
    raw["rolling_skewness"] = logret.rolling(72, min_periods=24).skew()
    raw["rolling_excess_kurtosis"] = logret.rolling(72, min_periods=24).kurt()

    # Causal robust normalization: statistics at t use only rows through t-1.
    med = raw.rolling(720, min_periods=96).median().shift(1)
    q75 = raw.rolling(720, min_periods=96).quantile(.75).shift(1)
    q25 = raw.rolling(720, min_periods=96).quantile(.25).shift(1)
    scale = (q75-q25).replace(0, np.nan)
    z = ((raw-med)/(scale+EPS)).clip(-10, 10)
    z = z.replace([np.inf, -np.inf], np.nan)
    return raw, z, {
        "feature_names": list(raw.columns), "normalization": "rolling median/IQR, shifted one completed H1 candle",
        "window": 720, "minimum_history": 96, "lookahead_allowed": False,
    }


def _canonicalize_regime(value: Any) -> str:
    text = str(value or "").upper().replace("-", "_").replace(" ", "_")
    if "TRANS" in text or "UNKNOWN" in text: return "TRANSITION"
    if "COMPRESS" in text or "SQUEEZE" in text: return "COMPRESSION"
    if "EXPANS" in text or "HIGH_VOL" in text or "BREAKOUT" in text: return "EXPANSION"
    if "BULL" in text or "UPTREND" in text or text == "BUY": return "BULL_TREND"
    if "BEAR" in text or "DOWNTREND" in text or text == "SELL": return "BEAR_TREND"
    if "RANGE" in text or "NEUTRAL" in text or "SIDE" in text or text == "WAIT": return "RANGE"
    return "TRANSITION"


def _extract_standard_frame(value: Any, label: str) -> pd.DataFrame:
    if not isinstance(value, pd.DataFrame) or value.empty:
        return pd.DataFrame(columns=["time", f"Existing {label} Regime"])
    work = value.copy(deep=False)
    try:
        from core.lunch_h1_data_quality_v13 import combined_h1_time
        times = combined_h1_time(work)
    except Exception:
        times = pd.Series(pd.NaT, index=work.index)
    regime_col = next((str(c) for c in work.columns if "regime" in str(c).lower() and "reliab" not in str(c).lower()), None)
    if regime_col is None:
        regime_col = next((str(c) for c in work.columns if any(t in str(c).lower() for t in ("state", "bias", "decision"))), None)
    out = pd.DataFrame({"time": pd.to_datetime(times, errors="coerce", utc=True)})
    out[f"Existing {label} Regime"] = work[regime_col].astype(str) if regime_col else "UNAVAILABLE"
    for target, tokens in (
        (f"{label} KNN Priority", ("knn", "priority")),
        (f"{label} Greedy Priority", ("greedy", "priority")),
        (f"{label} Score Out of 10", ("score", "/10")),
        (f"{label} Reliability", ("reliab",)),
    ):
        col = next((str(c) for c in work.columns if all(t in str(c).lower() for t in tokens)), None)
        if col: out[target] = work[col].values
    return out.dropna(subset=["time"]).sort_values("time").drop_duplicates("time", keep="last")


def _production_standards(state: Mapping[str, Any], frame: pd.DataFrame, identity: Mapping[str, Any]) -> pd.DataFrame:
    details = None
    for key in ("regime_standard_detail_tables_published_20260618", "regime_standard_detail_tables_20260617"):
        value = state.get(key)
        if isinstance(value, Mapping) and value:
            details = value; break
    out = pd.DataFrame({"time": frame["time"]})
    if isinstance(details, Mapping):
        aliases = {
            "Lower": ("lower", "low"), "Middle": ("medium", "middle", "mid"), "Higher": ("higher", "high"),
        }
        for label, keys in aliases.items():
            value = next((details.get(k) for k in keys if isinstance(details.get(k), pd.DataFrame)), None)
            extracted = _extract_standard_frame(value, label)
            out = out.merge(extracted, on="time", how="left")
    # Exact production values are preferred. The completed-H1 matrix is only a
    # transparent read-only fallback when a stored standard table is absent.
    needed = [f"Existing {x} Regime" for x in ("Lower", "Middle", "Higher")]
    if any(c not in out or out[c].notna().sum() == 0 for c in needed):
        try:
            from core.lunch_h1_data_quality_v13 import build_regime_decision_matrix
            matrix = build_regime_decision_matrix(state, None, limit=min(600, len(frame)))
            if not matrix.empty:
                mtime = pd.to_datetime(matrix.get("event_time_utc"), errors="coerce", utc=True)
                fallback = pd.DataFrame({"time": mtime})
                fmap = {
                    "Existing Lower Regime": "Lower 1-Day Regime",
                    "Existing Middle Regime": "Middle 5-Day Regime",
                    "Existing Higher Regime": "Higher 25-Day Regime",
                }
                for target, source in fmap.items():
                    if source in matrix: fallback[target] = matrix[source].values
                out = out.merge(fallback.dropna(subset=["time"]).drop_duplicates("time", keep="last"), on="time", how="left", suffixes=("", "__fallback"))
                for c in needed:
                    fb = f"{c}__fallback"
                    if fb in out:
                        out[c] = out[c].where(out[c].notna(), out[fb]) if c in out else out[fb]
                        out = out.drop(columns=[fb])
        except Exception:
            pass
    for c in needed:
        if c not in out: out[c] = "UNAVAILABLE"
        out[c] = out[c].fillna("UNAVAILABLE").astype(str)
    mapped = out[needed].apply(lambda col: col.map(_canonicalize_regime))
    def consensus(row: pd.Series) -> str:
        counts = Counter(row.tolist())
        best = counts.most_common()
        if not best: return _canonicalize_regime(identity.get("protected_regime"))
        if len(best) > 1 and best[0][1] == best[1][1]: return "TRANSITION"
        return best[0][0]
    out["Canonical Combined Regime"] = mapped.apply(consensus, axis=1)
    out["Lower/Middle/Higher Agreement"] = mapped.apply(lambda r: 100.0 * max(Counter(r).values()) / 3.0, axis=1)

    # Preserve every standard-specific value and expose stable aggregate aliases
    # required by the institutional history contract.  Priority is ascending,
    # therefore the best available preserved priority is the minimum.  The
    # aggregate score is the mean of available existing standard scores.  No
    # protected source column is overwritten or synthesized when all sources are
    # unavailable: missing evidence remains explicit NaN.
    knn_cols = [c for c in out.columns if c.endswith(" KNN Priority")]
    greedy_cols = [c for c in out.columns if c.endswith(" Greedy Priority")]
    score_cols = [c for c in out.columns if c.endswith(" Score Out of 10")]
    out["Existing KNN Priority"] = (
        out[knn_cols].apply(pd.to_numeric, errors="coerce").min(axis=1)
        if knn_cols else np.nan
    )
    out["Existing Greedy Priority"] = (
        out[greedy_cols].apply(pd.to_numeric, errors="coerce").min(axis=1)
        if greedy_cols else np.nan
    )
    out["Existing Score Out of 10"] = (
        out[score_cols].apply(pd.to_numeric, errors="coerce").mean(axis=1)
        if score_cols else np.nan
    )
    return out


def _softmax(scores: np.ndarray) -> np.ndarray:
    values = np.asarray(scores, dtype=float)
    values = values - np.nanmax(values, axis=1, keepdims=True)
    ex = np.exp(np.clip(values, -60, 60))
    ex[~np.isfinite(ex)] = 0.0
    denom = ex.sum(axis=1, keepdims=True)
    denom[denom <= 0] = 1.0
    return ex / denom


def _latent_filter(z: pd.DataFrame, production: pd.DataFrame) -> dict[str, Any]:
    f = z.fillna(0.0)
    def c(name: str) -> np.ndarray:
        return pd.to_numeric(f.get(name, 0.0), errors="coerce").fillna(0.0).to_numpy(float)
    r3, r6, vol = c("return_3h"), c("return_6h"), c("realized_volatility")
    atr, adx, adx_slope, di = c("atr_percentile"), c("adx_level"), c("adx_slope"), c("di_difference")
    persist, bw, comp = c("directional_persistence"), c("bollinger_bandwidth"), c("compression_percentile")
    vov, autocorr, eq = c("volatility_of_volatility"), c("return_autocorrelation"), c("distance_from_equilibrium")
    spread = c("spread_percentile")
    score = np.column_stack([
        1.15*r3 + 1.0*r6 + .75*di + .55*adx + .35*adx_slope + .45*persist + .20*eq - .10*vol,
        -1.15*r3 - 1.0*r6 - .75*di + .55*adx + .35*adx_slope + .45*persist - .20*eq - .10*vol,
        -.75*np.abs(r3) - .55*np.abs(r6) - .45*adx - .35*persist - .30*np.abs(eq) - .15*np.abs(autocorr),
        -1.0*atr - .95*bw - .70*vol - .35*vov - .20*np.abs(r3),
        1.0*atr + .80*bw + .75*vol + .55*np.abs(r3) + .40*vov,
        .85*vov + .55*np.abs(adx_slope) + .45*spread + .35*np.abs(eq) - .35*adx,
    ])
    emission = _softmax(score)
    warmup = min(max(120, len(emission)//5), max(120, len(emission)-1)) if len(emission) > 121 else max(1, len(emission)//2)
    preliminary = np.argmax(emission[:warmup], axis=1)
    counts = np.ones((len(REGIMES), len(REGIMES)), dtype=float)
    counts += np.eye(len(REGIMES))*20.0
    for a, b in zip(preliminary[:-1], preliminary[1:]): counts[a, b] += 1.0
    trans = counts / counts.sum(axis=1, keepdims=True)
    filtered = np.zeros_like(emission)
    prior = np.full(len(REGIMES), 1.0/len(REGIMES))
    for i in range(len(emission)):
        pred = prior @ trans
        post = pred * emission[i]
        post = post / max(post.sum(), EPS)
        filtered[i] = post
        prior = post
    # Retrospective smoothed probabilities are audit-only and never used in the
    # current action gate.
    smoothed = filtered.copy()
    for i in range(len(filtered)-2, -1, -1):
        ratio = smoothed[i+1] / np.clip(filtered[i] @ trans, EPS, None)
        smoothed[i] = filtered[i] * (trans @ ratio)
        smoothed[i] /= max(smoothed[i].sum(), EPS)
    order = np.argsort(filtered, axis=1)
    winner = order[:, -1]
    runner = order[:, -2]
    posterior = filtered[np.arange(len(filtered)), winner]
    second = filtered[np.arange(len(filtered)), runner]
    entropy = -np.sum(filtered*np.log(np.clip(filtered, EPS, 1)), axis=1)/math.log(len(REGIMES))
    return {
        "emission": emission, "filtered": filtered, "smoothed": smoothed, "transition": trans,
        "winner_index": winner, "runner_index": runner, "posterior": posterior, "second": second,
        "margin": posterior-second, "entropy": entropy,
        "selected": np.array([REGIMES[i] for i in winner], dtype=object),
        "runner": np.array([REGIMES[i] for i in runner], dtype=object),
        "smoothed_selected": np.array([REGIMES[i] for i in np.argmax(smoothed, axis=1)], dtype=object),
        "warmup": warmup,
    }


def _bocpd_multivariate(z: pd.DataFrame, maximum_run: int = 240, hazard: float = 1/96) -> dict[str, Any]:
    columns = [c for c in (
        "return_3h", "realized_volatility", "atr_percentile", "adx_level",
        "di_difference", "bollinger_bandwidth", "volatility_of_volatility", "distance_from_equilibrium",
    ) if c in z]
    x = z[columns].fillna(0.0).clip(-8, 8).to_numpy(float)
    n, d = x.shape
    if n < 60:
        zeros = np.zeros(n)
        return {"probability": zeros, "mode_run_length": zeros.astype(int), "run_length_entropy": zeros,
                "severity": zeros, "confirmation": np.array(["INSUFFICIENT_EVIDENCE"]*n, dtype=object),
                "current": {"status": "INSUFFICIENT_EVIDENCE"}}
    try:
        from scipy.special import gammaln
    except Exception:
        gammaln = np.vectorize(math.lgamma)
    R = np.array([1.0])
    mu = np.zeros((1, d)); kappa = np.ones(1); alpha = np.full(1, 2.0); beta = np.full((1, d), 2.0)
    probs = np.zeros(n); modes = np.zeros(n, dtype=int); ent = np.zeros(n); severity = np.zeros(n)
    for t, obs in enumerate(x):
        df = 2.0*alpha[:, None]
        scale2 = beta*(kappa[:, None]+1.0)/(alpha[:, None]*kappa[:, None]+EPS)
        q = (obs[None, :]-mu)**2/(df*scale2+EPS)
        logp_dim = (gammaln((df+1)/2)-gammaln(df/2)-.5*np.log(df*np.pi*scale2+EPS)
                    -((df+1)/2)*np.log1p(q))
        logp = np.sum(logp_dim, axis=1)
        logp -= np.max(logp)
        pred = np.exp(np.clip(logp, -700, 50))
        growth = R*pred*(1-hazard)
        cp = float(np.sum(R*pred*hazard))
        new_R = np.r_[cp, growth]
        new_R /= max(new_R.sum(), EPS)
        new_R = new_R[:maximum_run+1]
        new_R /= max(new_R.sum(), EPS)
        # robust surprise severity against the most probable run length
        rstar = int(np.argmax(R))
        denom = np.sqrt(np.maximum(scale2[min(rstar, len(scale2)-1)], EPS))
        sev = float(np.sqrt(np.mean(((obs-mu[min(rstar, len(mu)-1)])/denom)**2)))
        raw_cp = float(new_R[0])
        calibrated_cp = float(np.clip(.55*raw_cp + .45/(1+np.exp(-(sev-2.2))), 0, 1))
        probs[t] = calibrated_cp; modes[t] = int(np.argmax(new_R))
        ent[t] = float(-np.sum(new_R*np.log(np.clip(new_R, EPS, 1)))/max(log(len(new_R)), EPS))
        severity[t] = sev
        # Posterior hyperparameter update for run lengths r+1; r=0 is prior.
        keep = min(len(R), maximum_run)
        old_mu = mu[:keep]; old_k = kappa[:keep]; old_a = alpha[:keep]; old_b = beta[:keep]
        new_k = old_k+1.0
        delta = obs[None, :]-old_mu
        updated_mu = old_mu + delta/new_k[:, None]
        updated_a = old_a+.5
        updated_b = old_b + .5*(old_k[:, None]*delta**2/new_k[:, None])
        mu = np.vstack([np.zeros((1, d)), updated_mu])[:len(new_R)]
        kappa = np.r_[1.0, new_k][:len(new_R)]
        alpha = np.r_[2.0, updated_a][:len(new_R)]
        beta = np.vstack([np.full((1, d), 2.0), updated_b])[:len(new_R)]
        R = new_R
    rolling = pd.Series(probs).rolling(3, min_periods=1)
    confirmed = (rolling.apply(lambda s: float(np.sum(s >= .45)), raw=True) >= 2).to_numpy()
    candidate = (pd.Series(probs).rolling(3, min_periods=1).max() >= .30).to_numpy()
    confirmation = np.where(confirmed, "CONFIRMED_CHANGE", np.where(candidate, "TRANSITION_CANDIDATE", "NO_CHANGE"))
    return {
        "probability": probs, "mode_run_length": modes, "run_length_entropy": ent,
        "severity": severity, "confirmation": confirmation,
        "current": {
            "status": "AVAILABLE", "changepoint_probability": float(probs[-1]),
            "most_likely_run_length": int(modes[-1]), "run_length_entropy": float(ent[-1]),
            "structural_break_severity": float(severity[-1]), "change_confirmation_state": str(confirmation[-1]),
            "feature_vector": columns, "hazard_prior": hazard,
            "method": "multivariate diagonal Student-t BOCPD adaptation",
        },
    }


def _pelt_audit(raw: pd.DataFrame, selected: np.ndarray, maximum_rows: int = 1200, tolerance: int = 3) -> dict[str, Any]:
    from core.regime_intelligence_stack_20260624 import pelt_breaks
    start = max(0, len(raw)-maximum_rows)
    local = raw.iloc[start:].reset_index(drop=True)
    candidates: dict[str, list[int]] = {}
    series_map = {
        "mean_return": local["log_return"],
        "variance": local["log_return"].pow(2),
        "mean_and_variance": local["log_return"] + .5*local["log_return"].abs(),
        "directional_strength": local["adx_level"],
        "volatility_structure": local["realized_volatility"],
    }
    for name, series in series_map.items():
        result = pelt_breaks(series.fillna(0.0), min_segment=12)
        candidates[name] = [start+int(i) for i in result.get("breaks", [])]
    votes: Counter[int] = Counter()
    all_breaks = sorted({b for values in candidates.values() for b in values})
    for b in all_breaks:
        votes[b] = sum(any(abs(b-x) <= tolerance for x in values) for values in candidates.values())
    confirmed = [b for b in all_breaks if votes[b] >= 2]
    live = list(np.flatnonzero(pd.Series(selected).ne(pd.Series(selected).shift(1)).to_numpy()))
    matched_live: set[int] = set(); matched_pelt: set[int] = set(); delays: list[int] = []
    for j, pb in enumerate(confirmed):
        options = [(i, lb) for i, lb in enumerate(live) if i not in matched_live and abs(lb-pb) <= tolerance]
        if options:
            i, lb = min(options, key=lambda x: abs(x[1]-pb)); matched_live.add(i); matched_pelt.add(j); delays.append(lb-pb)
    precision = len(matched_live)/max(1, len(live)); recall = len(matched_pelt)/max(1, len(confirmed))
    f1 = 2*precision*recall/max(precision+recall, EPS)
    return {
        "method_break_indices": candidates, "confirmed_break_indices": confirmed,
        "live_boundary_indices": live,
        "matched_live_boundary_indices": [live[i] for i in sorted(matched_live)],
        "matched_pelt_boundary_indices": [confirmed[i] for i in sorted(matched_pelt)],
        "matched_boundaries": len(matched_live),
        "false_regime_switches": max(0, len(live)-len(matched_live)),
        "missed_structural_breaks": max(0, len(confirmed)-len(matched_pelt)),
        "average_detection_delay_hours": float(np.mean(delays)) if delays else None,
        "boundary_precision": float(precision), "boundary_recall": float(recall), "boundary_f1": float(f1),
        "tolerance_hours": tolerance, "retrospective_only": True,
    }


def _episodes(states: Sequence[str]) -> list[tuple[int, int, str]]:
    if not states: return []
    rows: list[tuple[int, int, str]] = []
    start = 0; current = str(states[0])
    for i in range(1, len(states)):
        if str(states[i]) != current:
            rows.append((start, i-1, current)); start=i; current=str(states[i])
    rows.append((start, len(states)-1, current))
    return rows


def _duration_estimate(state: str, age: int, by_state: Mapping[str, list[int]], pooled: Sequence[int]) -> dict[str, Any]:
    state_d = list(by_state.get(state, [])); pool = list(pooled)
    effective = list(state_d)
    low_sample = len(state_d) < 8
    if low_sample and pool:
        qs = np.quantile(pool, [.20, .35, .50, .65, .80])
        effective.extend(max(1, int(round(x))) for x in qs)
    # Remaining time is measured to the first candle of the next regime.  At
    # the final candle of a completed episode the exit is therefore 1H away,
    # not zero hours away.
    survivors = np.array([d-age+1 for d in effective if d >= age], dtype=float)
    if len(survivors) == 0:
        base = float(np.median(effective)) if effective else max(12.0, age*1.35)
        hazard = float(np.clip(1.0/max(base, 1.0), .005, .50))
        grid = np.arange(1, 241, dtype=float)
        pmf = hazard*np.power(1-hazard, grid-1); pmf /= pmf.sum()
    else:
        grid = np.arange(1, max(241, int(survivors.max())+2), dtype=float)
        pmf = np.zeros(len(grid), dtype=float)
        for remaining in survivors:
            idx = min(len(grid)-1, max(0, int(round(remaining))-1)); pmf[idx] += 1.0
        # Beta/geometric shrinkage keeps sparse tails from becoming false certainty.
        mean_total = float(np.mean(effective)) if effective else age+12
        h = float(np.clip(1/max(mean_total, 1), .005, .50))
        geo = h*np.power(1-h, grid-1); geo /= geo.sum()
        weight = len(state_d)/(len(state_d)+5.0)
        pmf = weight*(pmf/max(pmf.sum(), EPS)) + (1-weight)*geo
        pmf /= max(pmf.sum(), EPS)
    cdf = np.cumsum(pmf)
    def q(prob: float) -> float: return float(grid[min(len(grid)-1, int(np.searchsorted(cdf, prob)))])
    def sw(h: int) -> float: return float(cdf[min(len(cdf)-1, h-1)])
    mean_remaining = float(np.sum(grid*pmf))
    return {
        "expected_total": float(age+mean_remaining), "median_remaining": q(.50),
        "remaining_50_low": q(.25), "remaining_50_high": q(.75),
        "remaining_80_low": q(.10), "remaining_80_high": q(.90),
        "switch_1h": sw(1), "switch_3h": sw(3), "switch_6h": sw(6),
        "duration_confidence": float(np.clip(len(state_d)/12.0, 0.20, 1.0)),
        "sample_count": len(state_d), "low_sample": low_sample,
    }


def _duration_path(states: Sequence[str]) -> dict[str, Any]:
    n = len(states); age = np.ones(n, dtype=int)
    expected = np.zeros(n); median = np.zeros(n); q25=np.zeros(n); q75=np.zeros(n); q10=np.zeros(n); q90=np.zeros(n)
    sw1=np.zeros(n); sw3=np.zeros(n); sw6=np.zeros(n); conf=np.zeros(n); samples=np.zeros(n, dtype=int); low=np.zeros(n, dtype=bool)
    by_state: defaultdict[str, list[int]] = defaultdict(list); pooled: list[int] = []
    eps = _episodes(list(states))
    for episode_i, (start, end, state) in enumerate(eps):
        for idx in range(start, end+1):
            a = idx-start+1; age[idx]=a
            est = _duration_estimate(state, a, by_state, pooled)
            expected[idx]=est["expected_total"]; median[idx]=est["median_remaining"]
            q25[idx]=est["remaining_50_low"]; q75[idx]=est["remaining_50_high"]
            q10[idx]=est["remaining_80_low"]; q90[idx]=est["remaining_80_high"]
            sw1[idx]=est["switch_1h"]; sw3[idx]=est["switch_3h"]; sw6[idx]=est["switch_6h"]
            conf[idx]=est["duration_confidence"]; samples[idx]=est["sample_count"]; low[idx]=est["low_sample"]
        # The final episode is right-censored and is not treated as a completed duration.
        if episode_i < len(eps)-1:
            duration=end-start+1; by_state[state].append(duration); pooled.append(duration)
    return {
        "age": age, "expected_total": expected, "median_remaining": median,
        "q25":q25,"q75":q75,"q10":q10,"q90":q90,"switch1":sw1,"switch3":sw3,"switch6":sw6,
        "confidence":conf,"samples":samples,"low_sample":low,"episodes":eps,
        "completed_durations_by_state": dict(by_state), "pooled_completed_durations": pooled,
    }


def _regime_volatility(raw: pd.DataFrame, states: Sequence[str]) -> dict[str, np.ndarray]:
    ret = pd.to_numeric(raw["log_return"], errors="coerce").fillna(0.0).to_numpy(float)
    n=len(ret); variance=np.zeros(n); persistence=np.zeros(n); shock=np.zeros(n); vol1=np.zeros(n); vol3=np.zeros(n)
    skew=np.zeros(n); kurt=np.zeros(n); downside=np.zeros(n); upside=np.zeros(n); es=np.zeros(n)
    history: defaultdict[str, list[float]] = defaultdict(list)
    v = float(np.nanvar(ret[:min(48,n)])) if n else 0.0
    for i in range(n):
        state=str(states[i]); sample=np.asarray(history[state][-480:], dtype=float)
        target=float(np.var(sample, ddof=0)) if len(sample)>=20 else float(np.var(ret[max(0,i-120):i], ddof=0)) if i>=20 else max(v,1e-10)
        sq = sample*sample
        ac = float(pd.Series(sq).autocorr(1)) if len(sample)>=30 else .85
        beta=float(np.clip(ac if np.isfinite(ac) else .85, .70, .94)); alpha=float(np.clip(.12*(1-beta)/.15, .04, .16))
        omega=max(target*(1-alpha-beta), EPS)
        previous = ret[i-1] if i else 0.0
        v=omega+alpha*previous*previous+beta*max(v,EPS)
        variance[i]=v; persistence[i]=alpha+beta; vol1[i]=math.sqrt(max(v,0)); vol3[i]=math.sqrt(max(3*v,0))
        if len(sample)>=20:
            sd=max(float(np.std(sample,ddof=0)),EPS); shock[i]=float(np.clip(abs(previous)/(3*sd),0,1))
            skew[i]=float(pd.Series(sample).skew()); kurt[i]=float(pd.Series(sample).kurt())
            downside[i]=float(np.mean(sample < -1.645*sd)); upside[i]=float(np.mean(sample > 1.645*sd))
            tail=sample[sample <= np.quantile(sample,.05)]; es[i]=float(tail.mean()) if len(tail) else float(np.min(sample))
        history[state].append(ret[i])
    labels=np.where(vol1 >= pd.Series(vol1).rolling(720,min_periods=72).quantile(.75).fillna(np.nanmedian(vol1)),"HIGH",
             np.where(vol1 <= pd.Series(vol1).rolling(720,min_periods=72).quantile(.25).fillna(np.nanmedian(vol1)),"LOW","NORMAL"))
    return {"conditional_variance":variance,"persistence":persistence,"shock_probability":shock,"volatility_regime":labels,
            "forecast_1h":vol1,"forecast_3h":vol3,"skewness":skew,"excess_kurtosis":kurt,
            "downside_tail_probability":downside,"upside_tail_probability":upside,"expected_shortfall":es,
            "method":np.array(["REGIME_CONDITIONED_GARCH_APPROXIMATION"]*n,dtype=object)}


def _spread_cost_return(frame: pd.DataFrame) -> np.ndarray:
    close=frame["close"].to_numpy(float)
    if "spread" not in frame:
        return np.full(len(frame), 0.00008/np.maximum(close,EPS))
    s=pd.to_numeric(frame["spread"],errors="coerce").ffill().fillna(0.8).to_numpy(float)
    median=float(np.nanmedian(s)) if len(s) else .8
    price_cost = s*0.0001 if median > .01 else s
    return np.maximum(price_cost/np.maximum(close,EPS), 0.0)


def _ece(probability: np.ndarray, outcome: np.ndarray, bins: int = 10) -> float | None:
    p=np.asarray(probability,float); y=np.asarray(outcome,float); mask=np.isfinite(p)&np.isfinite(y)
    if mask.sum()<20:return None
    p=p[mask];y=y[mask]; total=len(p); e=0.0
    edges=np.linspace(0,1,bins+1)
    for a,b in zip(edges[:-1],edges[1:]):
        m=(p>=a)&(p<(b if b<1 else b+EPS))
        if m.any():e+=m.mean()*abs(float(p[m].mean()-y[m].mean()))
    return float(e)


def _bias_walk_forward(raw: pd.DataFrame, frame: pd.DataFrame, states: Sequence[str], block: int = 48) -> dict[str, Any]:
    n=len(frame); close=frame["close"].to_numpy(float); cost=_spread_cost_return(frame)
    feature_names=[c for c in (
        "return_3h","return_6h","realized_volatility","atr_percentile","adx_level","adx_slope",
        "di_difference","directional_persistence","bollinger_bandwidth","volatility_of_volatility",
        "return_autocorrelation","distance_from_equilibrium","body_to_range","wick_asymmetry",
        "spread_percentile","rolling_skewness","rolling_excess_kurtosis",
    ) if c in raw]
    X=raw[feature_names].replace([np.inf,-np.inf],np.nan)
    outputs: dict[int,dict[str,Any]]={}
    for h in HORIZONS:
        p=np.full((n,3),np.nan); ev_buy=np.full(n,np.nan);ev_sell=np.full(n,np.nan);efe=np.full(n,np.nan);eae=np.full(n,np.nan)
        future=np.full(n,np.nan); target=np.full(n,-1,dtype=int); mfe=np.full(n,np.nan); mae=np.full(n,np.nan)
        if n>h:
            future[:-h]=close[h:]/close[:-h]-1.0
            for i in range(n-h):
                path_high=float(frame["high"].iloc[i+1:i+h+1].max()/close[i]-1.0)
                path_low=float(frame["low"].iloc[i+1:i+h+1].min()/close[i]-1.0)
                mfe[i]=path_high;mae[i]=path_low
            target=np.where(future>cost,0,np.where(future<-cost,1,2)).astype(int)
            target[~np.isfinite(future)]=-1
        first=max(360, int(X.notna().all(axis=1).idxmax()) if X.notna().all(axis=1).any() else 360)
        for origin in range(first,n,block):
            train_end=origin-h
            if train_end<300:continue
            idx=np.arange(max(0,train_end-3000),train_end)
            valid=X.iloc[idx].notna().all(axis=1).to_numpy()&(target[idx]>=0)
            idx=idx[valid]
            if len(idx)<300 or min(Counter(target[idx]).values(),default=0)<8:continue
            split=max(220,int(len(idx)*.72)); fit_idx=idx[:split]; cal_idx=idx[split:]
            if len(cal_idx)<50:continue
            try:
                from sklearn.preprocessing import RobustScaler
                from sklearn.linear_model import LogisticRegression
                from sklearn.isotonic import IsotonicRegression
                scaler=RobustScaler().fit(X.iloc[fit_idx])
                model=LogisticRegression(max_iter=250,class_weight="balanced",random_state=20260701).fit(scaler.transform(X.iloc[fit_idx]),target[fit_idx])
                cal_raw=model.predict_proba(scaler.transform(X.iloc[cal_idx]))
                calibrators=[]
                for cls in range(3):
                    y=(target[cal_idx]==cls).astype(int)
                    if y.sum()>=8 and (1-y).sum()>=8:
                        calibrators.append(IsotonicRegression(out_of_bounds="clip").fit(cal_raw[:,list(model.classes_).index(cls)],y))
                    else: calibrators.append(None)
                end=min(n,origin+block); pred_idx=np.arange(origin,end)
                valid_pred=X.iloc[pred_idx].notna().all(axis=1).to_numpy(); use=pred_idx[valid_pred]
                if not len(use):continue
                rawp=model.predict_proba(scaler.transform(X.iloc[use])); calibrated=np.zeros((len(use),3))
                for cls in range(3):
                    pos=list(model.classes_).index(cls)
                    calibrated[:,cls]=calibrators[cls].predict(rawp[:,pos]) if calibrators[cls] is not None else rawp[:,pos]
                calibrated=np.clip(calibrated,1e-6,None);calibrated/=calibrated.sum(axis=1,keepdims=True);p[use]=calibrated
                means=np.array([np.nanmean(future[fit_idx][target[fit_idx]==cls]) if np.any(target[fit_idx]==cls) else 0 for cls in range(3)])
                mfe_means=np.array([np.nanmean(mfe[fit_idx][target[fit_idx]==cls]) if np.any(target[fit_idx]==cls) else 0 for cls in range(3)])
                mae_means=np.array([np.nanmean(mae[fit_idx][target[fit_idx]==cls]) if np.any(target[fit_idx]==cls) else 0 for cls in range(3)])
                expected=calibrated@means
                ev_buy[use]=expected-cost[use]; ev_sell[use]=-expected-cost[use]
                efe[use]=calibrated@mfe_means;eae[use]=calibrated@mae_means
            except Exception:
                continue
        # Causal empirical fallback remains WAIT-grade and never creates false precision.
        for i in range(max(240,first),n):
            if np.isfinite(p[i]).all():continue
            end=i-h; start=max(0,end-720)
            hist=np.arange(start,end)
            hist=hist[target[hist]>=0] if len(hist) else hist
            same=np.array([str(states[j])==str(states[i]) for j in hist]) if len(hist) else np.array([],dtype=bool)
            use=hist[same] if same.sum()>=30 else hist
            if len(use)>=60:
                counts=np.bincount(target[use],minlength=3)+2.0;p[i]=counts/counts.sum()
                means=np.array([np.nanmean(future[use][target[use]==cls]) if np.any(target[use]==cls) else 0 for cls in range(3)])
                expected=float(p[i]@means);ev_buy[i]=expected-cost[i];ev_sell[i]=-expected-cost[i]
                efe[i]=np.nanmean(mfe[use]);eae[i]=np.nanmean(mae[use])
        actual=target
        mask=np.isfinite(p).all(axis=1)&(actual>=0)
        brier=float(np.mean(np.sum((p[mask]-np.eye(3)[actual[mask]])**2,axis=1))) if mask.sum() else None
        ll=float(-np.mean(np.log(np.clip(p[mask,actual[mask]],1e-9,1)))) if mask.sum() else None
        eces=[_ece(p[:,cls],(actual==cls).astype(float)) for cls in range(3)]
        ece=float(np.nanmean([x for x in eces if x is not None])) if any(x is not None for x in eces) else None
        outputs[h]={"probabilities":p,"ev_buy":ev_buy,"ev_sell":ev_sell,"efe":efe,"eae":eae,"future_return":future,
                    "actual_class":actual,"brier":brier,"log_loss":ll,"ece":ece,"sample_count":int(mask.sum()),
                    "feature_names":feature_names,"calibration":"chronological isotonic; empirical fallback when insufficient"}
    return outputs


def _calibrate_regime_probability(filtered: np.ndarray, smoothed: np.ndarray) -> tuple[np.ndarray,float,dict[str,Any]]:
    """Causally calibrate selected-state confidence in chronological blocks.

    The calibration label is deliberately maturity-aware: a selected state is
    counted as confirmed when at least two of the following three completed H1
    states persist.  A label is eligible for fitting only after that three-hour
    window has completed.  Retrospective smoothed probabilities remain an audit
    output and are never used to fit the live calibration map.
    """
    selected=np.argmax(filtered,axis=1); confidence=np.max(filtered,axis=1); n=len(confidence)
    horizon=3; block=48
    target=np.full(n,np.nan)
    for i in range(max(0,n-horizon)):
        target[i]=float(np.mean(selected[i+1:i+1+horizon]==selected[i]) >= (2/3))
    calibrated=confidence.copy(); oos=np.zeros(n,dtype=bool); methods=[]
    if n>=300:
        try:
            from sklearn.isotonic import IsotonicRegression
            for origin in range(240,n,block):
                train_end=origin-horizon
                idx=np.arange(0,max(0,train_end)); idx=idx[np.isfinite(target[idx])]
                if len(idx)<180: continue
                y=target[idx].astype(int)
                if y.sum()<12 or (1-y).sum()<12: continue
                iso=IsotonicRegression(out_of_bounds="clip").fit(confidence[idx],y)
                use=np.arange(origin,min(n,origin+block))
                calibrated[use]=iso.predict(confidence[use]);oos[use]=True;methods.append("isotonic")
        except Exception:
            pass
    eval_mask=oos&np.isfinite(target)
    e=_ece(calibrated[eval_mask],target[eval_mask]) if eval_mask.any() else None
    quality=float(np.clip(1-(e if e is not None else .25)*2,0,1))
    calibrated=np.clip(calibrated,0.01,0.99)
    return calibrated,quality,{
        "method":"anchored_walk_forward_isotonic" if methods else "identity_insufficient_mature_labels",
        "target":"selected state persists in at least 2 of the next 3 completed H1 states",
        "label_maturity_hours":horizon,"same_fit_sample":False,
        "out_of_sample_rows":int(oos.sum()),"expected_calibration_error":e,
        "smoothed_probabilities_used_for_fit":False,
    }


def _calibrate_switch_probabilities(duration: MutableMapping[str,Any], states: Sequence[str]) -> dict[str,Any]:
    """Chronologically calibrate 1H/3H/6H exit probabilities.

    Raw survival probabilities are retained.  Each horizon is calibrated only
    with labels whose full future window had completed before the prediction
    block, preventing overlapping future labels from leaking into the fit.
    """
    n=len(states); selected=np.asarray(states,dtype=object); report={}
    for h,key in ((1,"switch1"),(3,"switch3"),(6,"switch6")):
        raw=np.asarray(duration[key],dtype=float).copy(); calibrated=raw.copy()
        target=np.full(n,np.nan);oos=np.zeros(n,dtype=bool);block=48
        for i in range(max(0,n-h)):
            target[i]=float(np.any(selected[i+1:i+1+h] != selected[i]))
        try:
            from sklearn.isotonic import IsotonicRegression
            for origin in range(240,n,block):
                train_end=origin-h
                idx=np.arange(0,max(0,train_end));idx=idx[np.isfinite(target[idx])&np.isfinite(raw[idx])]
                if len(idx)<180:continue
                y=target[idx].astype(int)
                if y.sum()<10 or (1-y).sum()<10:continue
                iso=IsotonicRegression(out_of_bounds="clip").fit(raw[idx],y)
                use=np.arange(origin,min(n,origin+block));calibrated[use]=iso.predict(raw[use]);oos[use]=True
        except Exception:
            pass
        duration[f"raw_{key}"]=raw
        duration[key]=np.clip(calibrated,0,1)
        mask=oos&np.isfinite(target)
        brier=float(np.mean((calibrated[mask]-target[mask])**2)) if mask.any() else None
        ece=_ece(calibrated[mask],target[mask]) if mask.any() else None
        report[f"H{h}"]={
            "method":"anchored_walk_forward_isotonic" if oos.any() else "raw_empirical_survival_insufficient_mature_labels",
            "label_maturity_hours":h,"same_fit_sample":False,"out_of_sample_rows":int(oos.sum()),
            "brier_score":brier,"expected_calibration_error":ece,
        }
    return report


def _drift_path(z: pd.DataFrame, step: int = 12) -> np.ndarray:
    cols=[c for c in ("return_3h","realized_volatility","atr_percentile","adx_level","di_difference","bollinger_bandwidth","volatility_of_volatility","distance_from_equilibrium") if c in z]
    x=z[cols].replace([np.inf,-np.inf],np.nan); n=len(x); out=np.zeros(n)
    for i in range(240,n,step):
        recent=x.iloc[max(0,i-72):i].dropna(); reference=x.iloc[max(0,i-720):max(0,i-72)].dropna()
        if len(recent)<30 or len(reference)<100:score=.5
        else:
            med_shift=(recent.median()-reference.median()).abs()/(reference.apply(lambda s:s.quantile(.75)-s.quantile(.25))+EPS)
            iqr_recent=recent.apply(lambda s:s.quantile(.75)-s.quantile(.25));iqr_ref=reference.apply(lambda s:s.quantile(.75)-s.quantile(.25))
            scale_shift=np.abs(np.log((iqr_recent+EPS)/(iqr_ref+EPS)))
            score=float(np.clip(np.nanmean(med_shift)*.22+np.nanmean(scale_shift)*.18,0,1))
        out[i:min(n,i+step)]=score
    if n: out[:240]=out[240] if n>240 else .5
    return out


def _next_regime(filtered: np.ndarray, transition: np.ndarray, winner: np.ndarray) -> tuple[np.ndarray,np.ndarray]:
    names=np.empty(len(filtered),dtype=object); probs=np.zeros(len(filtered))
    for i in range(len(filtered)):
        forecast=filtered[i]@transition; current=int(winner[i]); forecast[current]=0
        idx=int(np.argmax(forecast));names[i]=REGIMES[idx];probs[i]=float(forecast[idx])
    return names,probs


def _trust_label(score: float) -> str:
    if score>=85:return "Strong"
    if score>=70:return "Usable with caution"
    if score>=55:return "Weak; confirmation required"
    if score>=40:return "Unreliable"
    return "Invalid"


def _build_history(frame: pd.DataFrame, production: pd.DataFrame, latent: Mapping[str,Any], bocpd: Mapping[str,Any],
                   duration: Mapping[str,Any], volatility: Mapping[str,Any], bias_models: Mapping[int,Mapping[str,Any]],
                   data_quality: Mapping[str,Any], drift: np.ndarray, identity: Mapping[str,Any],
                   pelt: Mapping[str,Any], calibration_quality: float, hamilton: Mapping[str,Any]) -> tuple[pd.DataFrame,dict[str,Any]]:
    n=len(frame); selected=np.asarray(latent["selected"],dtype=object);posterior=np.asarray(latent["posterior"],float)
    calibrated=np.asarray(latent["calibrated_posterior"],float);margin=np.asarray(latent["margin"],float);entropy=np.asarray(latent["entropy"],float)
    next_names,next_prob=_next_regime(latent["filtered"],latent["transition"],latent["winner_index"])
    hamilton_probs=_mapping(hamilton.get("state_probabilities")); hamilton_state=str(hamilton.get("most_likely_shadow_state") or "UNAVAILABLE")
    hamilton_mapped=_canonicalize_regime(hamilton_state)
    agreement=np.zeros(n); model_agreement=np.zeros(n)
    existing_mapped=production[["Existing Lower Regime","Existing Middle Regime","Existing Higher Regime"]].apply(lambda col: col.map(_canonicalize_regime))
    for i in range(n):
        agreement[i]=float((existing_mapped.iloc[i]==selected[i]).mean())
        audit_agree=float(latent["smoothed_selected"][i]==selected[i])
        ham_agree=float(hamilton_mapped==selected[i]) if hamilton_state!="UNAVAILABLE" else .5
        model_agreement[i]=.55*agreement[i]+.25*audit_agree+.20*ham_agree
    b3=bias_models[3]; p3=np.asarray(b3["probabilities"],float)
    pbuy=np.nan_to_num(p3[:,0],nan=1/3);psell=np.nan_to_num(p3[:,1],nan=1/3);pwait=np.nan_to_num(p3[:,2],nan=1/3)
    evb=np.nan_to_num(b3["ev_buy"],nan=-1e-9);evs=np.nan_to_num(b3["ev_sell"],nan=-1e-9)
    calibration_bias=float(np.clip(1-(b3.get("ece") if b3.get("ece") is not None else .25)*2,0,1))
    bias=np.where((pbuy>=.58)&(evb>0),"BUY",np.where((psell>=.58)&(evs>0),"SELL","WAIT"))
    high_transition=(np.asarray(duration["switch3"])>.40)|(np.asarray(bocpd["probability"])>=.45)
    bias=np.where(high_transition,"WAIT",bias)
    bias_reliability=100*np.maximum.reduce([pbuy,psell,pwait])*calibration_bias*(1-.45*np.asarray(duration["switch3"]))
    dq=float(data_quality.get("score") or 0)/100
    stability=np.clip(1-np.asarray(duration["switch3"]),0,1)
    entropy_quality=1-entropy
    base=np.power(np.clip(calibrated,EPS,1)*max(calibration_quality,.05)*max(dq,.01)*np.clip(stability,EPS,1)*np.clip(1-drift,EPS,1),1/5)
    penalties=(.18*np.clip(.20-margin,0,.20)/.20 + .16*entropy + .22*np.asarray(bocpd["probability"]) +
               .16*(1-model_agreement)+.10*(1-agreement)+.08*np.asarray(duration["low_sample"],float)+
               .10*float(bool(data_quality.get("abnormal_spread"))))
    trust=100*np.clip(base*(1-penalties),0,1)
    critical_components=np.column_stack([calibrated,np.full(n,calibration_quality),np.full(n,dq),stability,1-drift,model_agreement])
    cap=100*(np.min(critical_components,axis=1)+TRUST_WEIGHTS["critical_component_cap"])
    trust=np.minimum(trust,cap)
    uncertainty=100*np.clip(.30*entropy+.20*(1-margin)+.20*np.asarray(duration["switch3"])+.15*np.asarray(bocpd["probability"])+.15*drift,0,1)
    try:
        from core.session_context_20260625 import detect_session_from_utc
        sessions = [detect_session_from_utc(pd.Timestamp(ts).to_pydatetime())[0] for ts in pd.to_datetime(frame["time"], utc=True)]
    except Exception:
        sessions = ["UNAVAILABLE"] * n
    rows=pd.DataFrame({
        "event_time_utc":frame["time"],"Close":frame["close"],
        "Existing Lower Regime":production["Existing Lower Regime"],"Existing Middle Regime":production["Existing Middle Regime"],
        "Existing Higher Regime":production["Existing Higher Regime"],"Canonical Combined Regime":selected,
        "Regime Bias":bias,"Selected-Regime Posterior":calibrated,"Second-Best Regime":latent["runner"],
        "Second-Best Probability":latent["second"],"Probability Margin":margin,
        "Regime Age in Completed H1 Candles":duration["age"],"Expected Total Regime Duration":duration["expected_total"],
        "Median Remaining Duration":duration["median_remaining"],
        "Remaining-Duration 50% Interval":[f"{a:.0f}–{b:.0f}H" for a,b in zip(duration["q25"],duration["q75"])],
        "Remaining-Duration 80% Interval":[f"{a:.0f}–{b:.0f}H" for a,b in zip(duration["q10"],duration["q90"])],
        "Switch Probability Within 1H":duration["switch1"],"Switch Probability Within 3H":duration["switch3"],
        "Switch Probability Within 6H":duration["switch6"],"Most Likely Next Regime":next_names,"Next-Regime Probability":next_prob,
        "Raw Switch Probability Within 1H":duration.get("raw_switch1",duration["switch1"]),
        "Raw Switch Probability Within 3H":duration.get("raw_switch3",duration["switch3"]),
        "Raw Switch Probability Within 6H":duration.get("raw_switch6",duration["switch6"]),
        "BOCPD Change-Point Probability":bocpd["probability"],"BOCPD Most Likely Run Length":bocpd["mode_run_length"],
        "BOCPD Run-Length Entropy":bocpd["run_length_entropy"],"Structural-Break Severity":bocpd["severity"],
        "Change Confirmation State":bocpd["confirmation"],"Volatility Regime":volatility["volatility_regime"],
        "Conditional Variance":volatility["conditional_variance"],"Volatility Persistence":volatility["persistence"],
        "Volatility Forecast 1H":volatility["forecast_1h"],"Volatility Forecast 3H":volatility["forecast_3h"],
        "Downside-Tail Probability":volatility["downside_tail_probability"],"Upside-Tail Probability":volatility["upside_tail_probability"],
        "Regime-Conditioned Skewness":volatility["skewness"],"Regime-Conditioned Excess Kurtosis":volatility["excess_kurtosis"],
        "Expected Shortfall":volatility["expected_shortfall"],"Regime Stability Score":100*stability,
        "Bias Reliability Score":bias_reliability,"Model Agreement Score":100*model_agreement,
        "Lower/Middle/Higher Agreement":production["Lower/Middle/Higher Agreement"],
        "Data Quality Score":float(data_quality.get("score") or 0),"Drift or Distribution-Shift Score":100*drift,
        "Calibrated Trust Score":trust,"Trust Interpretation":[_trust_label(x) for x in trust],"Uncertainty Score":uncertainty,
        "Calibration Quality Score":100*calibration_quality,"Model Disagreement Score":100*(1-model_agreement),
        "Probability Entropy":entropy,"Filtered Posterior (Uncalibrated)":posterior,
        "Smoothed Audit Regime":latent["smoothed_selected"],"Duration Confidence":100*np.asarray(duration["confidence"]),
        "Duration Sample Count":duration["samples"],"Duration Low-Sample Flag":duration["low_sample"],
        "P(Net Positive 3H)":pbuy,"P(Net Negative 3H)":psell,"P(WAIT/Cost Zone 3H)":pwait,
        "Expected Favourable Excursion":b3["efe"],"Expected Adverse Excursion":b3["eae"],
        "Cost-Adjusted Expected Value BUY":evb,"Cost-Adjusted Expected Value SELL":evs,
        "Cost-Adjusted Expected Value":np.maximum(evb,evs),
        "Session":sessions,
        "Run ID":identity["run_id"],"Generation ID":identity["generation_id"],"Snapshot Hash":identity["snapshot_hash"],
        "Symbol":identity["symbol"],"Timeframe":identity["timeframe"],
    })
    for horizon,item in bias_models.items():
        probs=np.asarray(item["probabilities"],float)
        rows[f"P(Net Positive {horizon}H)"]=probs[:,0]
        rows[f"P(Net Negative {horizon}H)"]=probs[:,1]
        rows[f"P(WAIT/Cost Zone {horizon}H)"]=probs[:,2]
        rows[f"Expected Favourable Excursion {horizon}H"]=item["efe"]
        rows[f"Expected Adverse Excursion {horizon}H"]=item["eae"]
        rows[f"Cost-Adjusted Expected Value BUY {horizon}H"]=item["ev_buy"]
        rows[f"Cost-Adjusted Expected Value SELL {horizon}H"]=item["ev_sell"]
    for idx,name in enumerate(REGIMES): rows[f"P({name})"]=latent["filtered"][:,idx]
    for c in production.columns:
        if c not in rows.columns and c!="time":rows[c]=production[c].values
    invalid=[]; actions=[]
    for i,row in rows.iterrows():
        reasons=[]
        if data_quality.get("critical"):reasons.extend(data_quality.get("reasons") or ["critical_data_quality"])
        if row["Selected-Regime Posterior"]<.75:reasons.append("posterior_below_0.75")
        if row["Probability Margin"]<.20:reasons.append("probability_margin_below_0.20")
        if row["BOCPD Change-Point Probability"]>=.45:reasons.append("change_point_probability_at_or_above_0.45")
        if row["Switch Probability Within 3H"]>=.40:reasons.append("switch_risk_exceeds_holding_horizon_gate")
        if row["Model Agreement Score"]<60:reasons.append("regime_model_disagreement")
        if row["Duration Low-Sample Flag"]:reasons.append("low_duration_episode_sample")
        positive_ev=row["Cost-Adjusted Expected Value"]>0
        trade=(row["Calibrated Trust Score"]>=80 and row["Bias Reliability Score"]>=75 and row["Selected-Regime Posterior"]>=.75 and
               row["Probability Margin"]>=.20 and row["BOCPD Change-Point Probability"]<.45 and row["Switch Probability Within 3H"]<.40 and
               row["Data Quality Score"]>=90 and positive_ev and row["Regime Bias"] in {"BUY","SELL"})
        if data_quality.get("critical") or row["Calibrated Trust Score"]<40: action="BLOCK"
        elif trade:action="TRADE"
        elif row["Calibrated Trust Score"]>=70 and positive_ev and row["Regime Bias"] in {"BUY","SELL"}:action="REDUCE"
        else:action="WAIT"
        actions.append(action);invalid.append("; ".join(reasons[:5]) if reasons else "NONE")
    rows["Final Action"]=actions;rows["Invalidation Reason"]=invalid
    pelt_set=set(pelt.get("confirmed_break_indices") or [])
    matched_live=set(pelt.get("matched_live_boundary_indices") or [])
    matched_pelt=set(pelt.get("matched_pelt_boundary_indices") or [])
    live_set=set(pelt.get("live_boundary_indices") or [])
    rows["PELT Confirmed Boundary"]=[i in pelt_set for i in range(n)]
    rows["Matched Regime Boundary"]=[i in matched_live for i in range(n)]
    rows["False Regime Switch"]=[i in live_set and i not in matched_live for i in range(n)]
    rows["Missed PELT Boundary"]=[i in pelt_set and i not in matched_pelt for i in range(n)]
    # Shared broker-time projection is the only visible candle-time source.
    try:
        from core.shared_broker_time_20260622 import frame_to_shared_broker_clock
        display=frame_to_shared_broker_clock(rows,state={},canonical=None,include_myanmar=False,hide_raw_utc=False)
        broker_col=next((c for c in display.columns if str(c).startswith("Broker Time")),None)
        if broker_col: rows["Broker Candle Time"]=display[broker_col].values
        else: rows["Broker Candle Time"]="BROKER TIME UNAVAILABLE — CONFIGURE SETTINGS"
    except Exception:
        rows["Broker Candle Time"]="BROKER TIME UNAVAILABLE — CONFIGURE SETTINGS"
    # Caller replaces broker time with state-aware projection; this placeholder
    # keeps the stable schema during offline tests.
    components={"agreement":agreement,"model_agreement":model_agreement,"bias_reliability":bias_reliability,
                "trust":trust,"uncertainty":uncertainty,"bias":bias}
    return rows,components


def _apply_broker_time(rows: pd.DataFrame, state: Mapping[str,Any]) -> pd.DataFrame:
    try:
        from core.shared_broker_time_20260622 import frame_to_shared_broker_clock
        temp=rows.drop(columns=["Broker Candle Time"],errors="ignore")
        projected=frame_to_shared_broker_clock(temp,state,include_myanmar=False,hide_raw_utc=False)
        broker=next((c for c in projected.columns if str(c).startswith("Broker Time")),None)
        if broker:
            rows=rows.copy();rows["Broker Candle Time"]=projected[broker].values
    except Exception:pass
    return rows


def _daily_summary(history: pd.DataFrame, bias_models: Mapping[int,Mapping[str,Any]], pelt: Mapping[str,Any], duration: Mapping[str,Any]) -> pd.DataFrame:
    work=history.copy()
    broker=pd.to_datetime(work["Broker Candle Time"],errors="coerce")
    fallback=pd.to_datetime(work["event_time_utc"],errors="coerce",utc=True).dt.tz_localize(None)
    work["broker_date"]=broker.fillna(fallback).dt.date
    state_change=work["Canonical Combined Regime"].ne(work["Canonical Combined Regime"].shift(1))
    work["confirmed_switch"]=(state_change & work["Change Confirmation State"].eq("CONFIRMED_CHANGE")).astype(int)
    work["candidate_switch"]=(state_change | work["Change Confirmation State"].eq("TRANSITION_CANDIDATE")).astype(int)
    work["transition_hour"]=work["Canonical Combined Regime"].eq("TRANSITION").astype(int)
    p1=np.asarray(bias_models[1]["probabilities"],float);actual=np.asarray(bias_models[1]["actual_class"],int)
    pred=np.where(np.isfinite(p1).all(axis=1),np.argmax(p1,axis=1),-1)
    work["bias_correct_1h"]=(pred==actual).astype(float);work.loc[(pred<0)|(actual<0),"bias_correct_1h"]=np.nan
    work["buy_correct"] = np.where(pred==0,(actual==0).astype(float),np.nan)
    work["sell_correct"] = np.where(pred==1,(actual==1).astype(float),np.nan)
    work["wait_correct"] = np.where(pred==2,(actual==2).astype(float),np.nan)
    realized_remaining=np.full(len(work),np.nan);completed_duration=np.full(len(work),np.nan)
    for start,end,_state in duration.get("episodes") or []:
        if end>=len(work)-1:continue  # right-censored current episode
        for idx in range(start,end+1):realized_remaining[idx]=end-idx+1
        completed_duration[end]=end-start+1
    predicted_remaining=pd.to_numeric(work["Median Remaining Duration"],errors="coerce").to_numpy(float)
    work["duration_abs_error"]=np.abs(predicted_remaining-realized_remaining)
    work["completed_episode_duration"]=completed_duration
    def interval_coverage(text: Any, actual_remaining: float) -> float:
        if not np.isfinite(actual_remaining):return np.nan
        try:
            a,b=str(text).replace("H","").split("–");return float(float(a)<=actual_remaining<=float(b))
        except Exception:return np.nan
    work["duration_50_covered"]=[interval_coverage(text,actual_remaining) for text,actual_remaining in zip(work["Remaining-Duration 50% Interval"],realized_remaining)]
    work["duration_80_covered"]=[interval_coverage(text,actual_remaining) for text,actual_remaining in zip(work["Remaining-Duration 80% Interval"],realized_remaining)]
    rows=[]
    for date,g in work.groupby("broker_date",sort=False):
        if pd.isna(date):continue
        dom_reg=g["Canonical Combined Regime"].mode();dom_bias=g["Regime Bias"].mode()
        session_col="Session" if "Session" in g.columns else next((c for c in g.columns if "Session" in c),None)
        session_perf = g.groupby(session_col)["bias_correct_1h"].mean().dropna() if session_col else pd.Series(dtype=float)
        loc=np.asarray(g.index,dtype=int);valid=(pred[loc]>=0)&(actual[loc]>=0)&np.isfinite(p1[loc]).all(axis=1)
        daily_brier=float(np.mean(np.sum((p1[loc][valid]-np.eye(3)[actual[loc][valid]])**2,axis=1))) if valid.any() else None
        daily_log_loss=float(-np.mean(np.log(np.clip(p1[loc][valid,actual[loc][valid]],1e-9,1)))) if valid.any() else None
        daily_eces=[_ece(p1[loc,cls],(actual[loc]==cls).astype(float),bins=5) for cls in range(3)]
        daily_ece=float(np.nanmean([x for x in daily_eces if x is not None])) if any(x is not None for x in daily_eces) else None
        row={
            "Broker Date":str(date),"Dominant Regime":dom_reg.iloc[0] if len(dom_reg) else "N/A",
            "Dominant Bias":dom_bias.iloc[0] if len(dom_bias) else "WAIT",
            "Confirmed Switches":int(g["confirmed_switch"].sum()),"Candidate Switches":int(g["candidate_switch"].sum()),
            "Transition Hours":int(g["transition_hour"].sum()),"Mean Regime Posterior":float(g["Selected-Regime Posterior"].mean()),
            "Mean Probability Margin":float(g["Probability Margin"].mean()),"Mean Bias Reliability":float(g["Bias Reliability Score"].mean()),
            "Mean Trust Score":float(g["Calibrated Trust Score"].mean()),"Maximum 1H Switch Probability":float(g["Switch Probability Within 1H"].max()),
            "Maximum 3H Switch Probability":float(g["Switch Probability Within 3H"].max()),
            "Average Completed-Regime Duration":float(g["completed_episode_duration"].mean()) if g["completed_episode_duration"].notna().any() else None,
            "False Switches":int(g["False Regime Switch"].sum()) if "False Regime Switch" in g else 0,
            "Missed PELT Boundaries":int(g["Missed PELT Boundary"].sum()) if "Missed PELT Boundary" in g else 0,
            "Average Transition Detection Delay":pelt.get("average_detection_delay_hours"),
            "Regime Directional Accuracy":float(g["bias_correct_1h"].mean()) if g["bias_correct_1h"].notna().any() else None,
            "BUY Accuracy":float(g["buy_correct"].mean()) if g["buy_correct"].notna().any() else None,
            "SELL Accuracy":float(g["sell_correct"].mean()) if g["sell_correct"].notna().any() else None,
            "WAIT Protection Accuracy":float(g["wait_correct"].mean()) if g["wait_correct"].notna().any() else None,
            "Brier Score":daily_brier,"Multiclass Log Loss":daily_log_loss,
            "Expected Calibration Error":daily_ece,
            "Duration Prediction MAE":float(g["duration_abs_error"].mean()) if g["duration_abs_error"].notna().any() else None,
            "50% Interval Coverage":float(g["duration_50_covered"].mean()) if g["duration_50_covered"].notna().any() else None,
            "80% Interval Coverage":float(g["duration_80_covered"].mean()) if g["duration_80_covered"].notna().any() else None,
            "Best Session":str(session_perf.idxmax()) if not session_perf.empty else "N/A",
            "Worst Session":str(session_perf.idxmin()) if not session_perf.empty else "N/A",
            "Data-Quality Warning Count":int((g["Data Quality Score"]<90).sum()),
        }
        rows.append(row)
    return pd.DataFrame(rows).sort_values("Broker Date",ascending=False).head(25).reset_index(drop=True)


def _validation(history: pd.DataFrame, bias_models: Mapping[int,Mapping[str,Any]], pelt: Mapping[str,Any], duration: Mapping[str,Any]) -> dict[str,Any]:
    report={"walk_forward":{"method":"anchored/rolling chronological blocks with horizon purge; calibration subset separate from model-fit subset","embargo_hours":6,"overlapping_forecasts_counted_as_independent":False},
            "bias":{},"regime_boundaries":{k:pelt.get(k) for k in ("boundary_precision","boundary_recall","boundary_f1","average_detection_delay_hours","false_regime_switches","missed_structural_breaks")}}
    try:
        from sklearn.metrics import balanced_accuracy_score,f1_score
    except Exception:
        balanced_accuracy_score=f1_score=None
    for h,item in bias_models.items():
        p=np.asarray(item["probabilities"],float);y=np.asarray(item["actual_class"],int);mask=np.isfinite(p).all(axis=1)&(y>=0);pred=np.argmax(p[mask],axis=1) if mask.any() else np.array([])
        report["bias"][f"H{h}"]={
            "sample_count":int(mask.sum()),"balanced_accuracy":float(balanced_accuracy_score(y[mask],pred)) if balanced_accuracy_score and mask.any() else None,
            "macro_f1":float(f1_score(y[mask],pred,average="macro")) if f1_score and mask.any() else None,
            "brier_score":item.get("brier"),"multiclass_log_loss":item.get("log_loss"),"expected_calibration_error":item.get("ece"),
            "cost_adjusted_expected_value_mean":float(np.nanmean(np.maximum(item["ev_buy"],item["ev_sell"]))) if np.isfinite(np.maximum(item["ev_buy"],item["ev_sell"])).any() else None,
        }
    # Duration interval validation on completed episodes, using origin-time estimates in the stored history.
    errors=[];cov50=[];cov80=[]
    for start,end,state in duration.get("episodes") or []:
        if end>=len(history)-1:continue
        actual=end-start+1
        pred=float(history.iloc[start]["Median Remaining Duration"])
        errors.append(abs(pred-actual))
        text50=str(history.iloc[start]["Remaining-Duration 50% Interval"]);text80=str(history.iloc[start]["Remaining-Duration 80% Interval"])
        def parse(text):
            try:a,b=text.replace("H","").split("–");return float(a),float(b)
            except Exception:return np.nan,np.nan
        a,b=parse(text50);c,d=parse(text80);cov50.append(float(a<=actual<=b) if np.isfinite(a+b) else np.nan);cov80.append(float(c<=actual<=d) if np.isfinite(c+d) else np.nan)
    report["duration"]={"mae_hours":float(np.nanmean(errors)) if errors else None,"interval_50_coverage":float(np.nanmean(cov50)) if cov50 else None,
                        "interval_80_coverage":float(np.nanmean(cov80)) if cov80 else None,"completed_episode_count":len(errors)}
    if "Session" in history.columns:
        h1=bias_models[1]; p=np.asarray(h1["probabilities"],float); y=np.asarray(h1["actual_class"],int)
        pred=np.where(np.isfinite(p).all(axis=1),np.argmax(np.nan_to_num(p,nan=0.0),axis=1),-1)
        session_rows={}
        for session, idx in history.groupby("Session").groups.items():
            loc=np.asarray(list(idx),dtype=int); mask=(pred[loc]>=0)&(y[loc]>=0)
            session_rows[str(session)]={"sample_count":int(mask.sum()),"bias_accuracy":float(np.mean(pred[loc][mask]==y[loc][mask])) if mask.any() else None}
        report["performance_by_session"]=session_rows
    report["baselines"]={
        "no_change_regime_baseline":"reported as persistence baseline; no superiority claim without mature external labels",
        "existing_field3_regime_logic":"preserved and displayed side-by-side",
        "simple_adx_atr_threshold":"audit baseline hook",
        "markov_transition_only":"transition matrix baseline hook",
    }
    report["improvement_claimed"]=False
    report["claim_reason"]="No production accuracy improvement is claimed until the shadow monitor beats preserved baselines out of sample on mature labels and costs."
    return report


def _current_summary(history: pd.DataFrame, data_quality: Mapping[str,Any]) -> dict[str,Any]:
    row=history.iloc[-1]
    return {
        "current_canonical_regime":row["Canonical Combined Regime"],"current_bias":row["Regime Bias"],
        "selected_regime_posterior":row["Selected-Regime Posterior"],"probability_margin":row["Probability Margin"],
        "regime_age":row["Regime Age in Completed H1 Candles"],"expected_total_duration":row["Expected Total Regime Duration"],
        "median_remaining_duration":row["Median Remaining Duration"],"remaining_duration_50_interval":row["Remaining-Duration 50% Interval"],
        "remaining_duration_80_interval":row["Remaining-Duration 80% Interval"],"switch_probability_1h":row["Switch Probability Within 1H"],
        "switch_probability_3h":row["Switch Probability Within 3H"],"switch_probability_6h":row["Switch Probability Within 6H"],
        "most_likely_next_regime":row["Most Likely Next Regime"],"next_regime_probability":row["Next-Regime Probability"],
        "change_point_probability":row["BOCPD Change-Point Probability"],"volatility_regime":row["Volatility Regime"],
        "stability":row["Regime Stability Score"],"bias_reliability":row["Bias Reliability Score"],
        "model_agreement":row["Model Agreement Score"],"calibration_quality":row["Calibration Quality Score"],
        "duration_confidence":row["Duration Confidence"],"drift_risk":row["Drift or Distribution-Shift Score"],
        "calibrated_trust":row["Calibrated Trust Score"],"trust_interpretation":row["Trust Interpretation"],
        "uncertainty":row["Uncertainty Score"],"data_quality":row["Data Quality Score"],"data_quality_status":data_quality.get("status"),
        "final_action":row["Final Action"],"primary_invalidation_condition":str(row["Invalidation Reason"]).split("; ")[0],
        "broker_candle_time":row["Broker Candle Time"],"cost_adjusted_expected_value":row["Cost-Adjusted Expected Value"],
    }


def _order_history_columns(frame: pd.DataFrame) -> pd.DataFrame:
    remaining=[c for c in frame.columns if c not in FIRST_14_COLUMNS]
    return frame.loc[:,[c for c in FIRST_14_COLUMNS if c in frame]+remaining]


def build_field3_regime_lifecycle_monitor(snapshot: Any, state: MutableMapping[str,Any], *, force: bool=False) -> dict[str,Any]:
    """Build one immutable, cached, additive Field 3 monitor payload."""
    started=time.perf_counter();identity=_snapshot_identity(snapshot)
    frame,source_meta=_source_frame(state,identity,maximum_rows=5000);signature=_frame_signature(frame)
    cache_key=_stable_hash([VERSION,identity,signature])
    existing=state.get(STATE_KEY)
    if not force and isinstance(existing,Mapping) and str(existing.get("cache_key"))==cache_key:
        return dict(existing)
    base={"version":VERSION,"cache_key":cache_key,**identity,"data_signature":signature,"shadow_only":True,
          "production_decision_changed":False,"protected_regime_calculations_changed":False,
          "ordinary_lunch_rerun_training":False,"settings_owned_heavy_run":True}
    dq=_data_quality(frame,source_meta,state)
    if frame.empty:
        payload={**base,"status":"DATA_NOT_READY","data_quality":dq,"current":{"final_action":"BLOCK","primary_invalidation_condition":"missing_completed_h1_source"},
                 "history_25d":[],"daily_25d":[],"performance":{"runtime_ms":round((time.perf_counter()-started)*1000,3)}}
        state[STATE_KEY]=payload;return payload
    raw,z,feature_meta=_feature_engine(frame);production=_production_standards(state,frame,identity);latent=_latent_filter(z,production)
    calibrated,cal_quality,cal_meta=_calibrate_regime_probability(latent["filtered"],latent["smoothed"]);latent["calibrated_posterior"]=calibrated
    bocpd=_bocpd_multivariate(z);pelt=_pelt_audit(raw,latent["selected"]);duration=_duration_path(list(latent["selected"]))
    switch_calibration=_calibrate_switch_probabilities(duration,list(latent["selected"]))
    volatility=_regime_volatility(raw,latent["selected"]);bias=_bias_walk_forward(raw,frame,latent["selected"]);drift=_drift_path(z)
    try:
        from core.hamilton_regime_research_v4_20260622 import run_hamilton_regime_model
        hamilton=run_hamilton_regime_model(frame,identity,protected_regime=identity.get("protected_regime"))
    except Exception as exc:
        hamilton={"status":"FAILED_SAFELY","error":f"{type(exc).__name__}: {exc}"}
    history,components=_build_history(frame,production,latent,bocpd,duration,volatility,bias,dq,drift,identity,pelt,cal_quality,hamilton)
    history=_apply_broker_time(history,state)
    display=history.tail(600).copy().iloc[::-1].reset_index(drop=True);display=_order_history_columns(display)
    daily=_daily_summary(history,bias,pelt,duration)
    validation=_validation(history,bias,pelt,duration)
    current=_current_summary(history,dq)
    chart_cols=["event_time_utc","Broker Candle Time","Close","Canonical Combined Regime","Selected-Regime Posterior","Probability Margin",
                "Probability Entropy","Switch Probability Within 3H","BOCPD Change-Point Probability","PELT Confirmed Boundary","Regime Bias",
                "Calibrated Trust Score","Regime Age in Completed H1 Candles"]
    chart=history.tail(600)[chart_cols].copy()
    last_time=pd.to_datetime(frame["time"].iloc[-1],utc=True)
    median=float(history.iloc[-1]["Median Remaining Duration"]);q25=float(duration["q25"][-1]);q75=float(duration["q75"][-1]);q10=float(duration["q10"][-1]);q90=float(duration["q90"][-1])
    lifecycle_window={"current_regime_start_utc":pd.to_datetime(frame["time"].iloc[-int(duration["age"][-1])],utc=True).isoformat(),
                      "median_exit_utc":(last_time+pd.Timedelta(hours=median)).isoformat(),
                      "remaining_50_start_utc":(last_time+pd.Timedelta(hours=q25)).isoformat(),"remaining_50_end_utc":(last_time+pd.Timedelta(hours=q75)).isoformat(),
                      "remaining_80_start_utc":(last_time+pd.Timedelta(hours=q10)).isoformat(),"remaining_80_end_utc":(last_time+pd.Timedelta(hours=q90)).isoformat()}
    payload={**base,"status":"AVAILABLE" if not dq.get("critical") else "INVALID_DATA_QUALITY","completed_candle_time_utc":source_meta.get("cutoff_utc"),
             "data_quality":dq,"source_metadata":source_meta,"feature_engine":feature_meta,"current":_jsonable(current),
             "full_state_probability_vector":{REGIMES[i]:float(latent["filtered"][-1,i]) for i in range(len(REGIMES))},
             "latent_state_model":{"method":"causal sticky latent-state filter with semantic emissions","regimes":list(REGIMES),
                                   "transition_matrix":latent["transition"].tolist(),"filtered_probability_only_for_action":True,
                                   "smoothed_probabilities_retrospective_only":True,"warmup_rows":latent["warmup"]},
             "hamilton_markov_switching":_jsonable(hamilton),"bocpd":_jsonable(bocpd["current"]),"pelt_audit":_jsonable(pelt),
             "duration_model":{"method":"explicit-duration empirical survival with pooled-prior shrinkage","current_sample_count":int(duration["samples"][-1]),
                               "low_sample":bool(duration["low_sample"][-1]),"completed_durations_by_state":duration["completed_durations_by_state"]},
             "volatility_model":{"method":"regime-conditioned GARCH approximation; not represented as full MS-GARCH",
                                 "current_conditional_variance":float(volatility["conditional_variance"][-1]),"current_persistence":float(volatility["persistence"][-1])},
             "calibration":{"regime_posterior":cal_meta,"regime_calibration_quality":cal_quality,
                            "switch_probability":switch_calibration,
                            "buy_sell":"chronological model-fit/calibration/test blocks for H1/H3/H6",
                            "remaining_duration_intervals":"causal empirical survival quantiles with pooled-prior shrinkage; coverage reported on completed episodes"},
             "validation":_jsonable(validation),"history_25d":_jsonable(display),"daily_25d":_jsonable(daily),
             "chart_timeline":_jsonable(chart),"lifecycle_window":lifecycle_window,
             "trust_definition":{"formula":"100 × geometric mean(calibrated confidence, calibration quality, data quality, stability, 1-drift), then conservative penalties and critical-component cap",
                                 "weights":TRUST_WEIGHTS,"penalties":["low margin","high entropy","high change-point probability","Lower/Middle/Higher disagreement","model disagreement","low duration samples","stale data","abnormal spread"]},
             "action_thresholds":ACTION_THRESHOLDS,
             "method_disclosures":["Protected production regime and decisions remain unchanged.","TRANSITION is evidence-driven by uncertainty/change risk and is not forced to persist like an ordinary state.",
                                   "PELT and smoothed probabilities are retrospective auditors only.","No accuracy or profitability improvement is claimed."],
             "performance":{"runtime_ms":round((time.perf_counter()-started)*1000,3),"training_rows":len(frame),"display_rows":len(display),
                            "cache_key":cache_key,"incremental_update_supported":True}}
    state[STATE_KEY]=payload
    return payload


__all__=["VERSION","STATE_KEY","REGIMES","FIRST_14_COLUMNS","ACTION_THRESHOLDS","TRUST_WEIGHTS","build_field3_regime_lifecycle_monitor"]

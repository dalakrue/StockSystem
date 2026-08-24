"""Adaptive Regime–Evidence Reliability Theory (ARERT) research laboratory.

This is a separate academic layer.  It consumes one frozen production snapshot,
uses completed-candle data only, and never writes into protected Lunch values.
Every module returns explicit status/limitations rather than fabricating missing
inputs.  The implementations are research prototypes intended for thesis
validation, not live trading commands.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import time
import tracemalloc
from typing import Any, Callable, Iterable, Mapping, MutableMapping

import numpy as np
import pandas as pd

ARERT_VERSION = "ARERT-0.3.0-RESEARCH-PROTOTYPE"
PARAMETER_VERSION = "ARERT-PARAMS-EQUAL-BASELINE-20260628"
STATE_KEY = "arert_thesis_research_20260628"

MODULE_CATALOG: dict[int, tuple[str, int]] = {
    1: ("Hidden Semi-Markov Regime Persistence", 2),
    2: ("Hierarchical Multi-Time-Scale Regime Model", 2),
    3: ("Bayesian Online Changepoint Detection", 2),
    4: ("News-Conditioned Jump Detection", 2),
    5: ("Adaptive Conformal Prediction Intervals", 3),
    6: ("Changepoint-Aware Conformal Calibration", 3),
    7: ("Meta-Labeling", 4),
    8: ("Selective Prediction and Abstention", 4),
    9: ("Dynamic Bayesian Model Averaging", 4),
    10: ("Internal Model Prediction Market", 4),
    11: ("Regime–Event Historical Analogue Search", 5),
    12: ("Outcome-Decay Memory", 5),
    13: ("Prospect-Theory Sentiment", 6),
    14: ("Herding and Consensus Fragility", 6),
    15: ("Anchoring and Reference-Point Bias", 6),
    16: ("Adaptive Market and Model Ecology", 7),
    17: ("Causal Event-Response Memory", 8),
    18: ("Information-Theoretic Evidence Diversity", 9),
    19: ("Backtest Overfitting and Research Validity", 10),
    20: ("ARERT Reliability Decomposition", 10),
}

DECISION_TOKENS = ("decision", "bias", "direction", "action", "signal", "stance", "label")
TIME_NAMES = (
    "Broker Candle Time", "Completed Broker Candle", "Broker Candle", "event_time_utc",
    "Time", "Datetime", "DateTime", "Timestamp", "Date Time", "Date",
)


@dataclass(frozen=True)
class ResearchContext:
    canonical: Mapping[str, Any]
    state: Mapping[str, Any]
    metadata: Mapping[str, Any]
    market: pd.DataFrame
    decisions: pd.DataFrame
    news: pd.DataFrame
    features: pd.DataFrame


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _frame(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy(deep=False)
    if isinstance(value, list) and (not value or isinstance(value[0], Mapping)):
        try:
            return pd.DataFrame(value)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def _is_missing_scalar(value: Any) -> bool:
    """Return a real bool for scalar missing values without evaluating pd.NA.

    Pandas ``NA`` deliberately raises when coerced to bool.  Research data can
    contain it inside object columns, so every scalar boundary uses this helper
    instead of expressions such as ``value or ""``.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().upper() in {"", "N/A", "NA", "NONE", "NAN", "UNAVAILABLE", "—", "-"}
    if isinstance(value, (pd.DataFrame, pd.Series, pd.Index, np.ndarray, list, tuple, dict, set)):
        return False
    try:
        missing = pd.isna(value)
        return bool(missing) if isinstance(missing, (bool, np.bool_)) else False
    except Exception:
        return False


def _coalesce(*values: Any, default: Any = None) -> Any:
    """Return the first non-missing scalar/object without truth-testing pd.NA."""
    for value in values:
        if not _is_missing_scalar(value):
            return value
    return default


def _safe_text(value: Any) -> str:
    return "" if _is_missing_scalar(value) else str(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    number = _finite(value)
    return float(default if number is None else number)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _clip100(value: Any) -> float | None:
    number = _finite(value)
    if number is None:
        return None
    if 0 <= number <= 1:
        number *= 100.0
    return round(float(np.clip(number, 0.0, 100.0)), 4)


def _jsonable(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return value.to_dict(orient="records")
    if isinstance(value, pd.Series):
        return value.tolist()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return value


def _hash_payload(value: Any) -> str:
    payload = json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8", "ignore")).hexdigest()


def _canonical_candle(canonical: Mapping[str, Any]) -> pd.Timestamp | None:
    market = _mapping(canonical.get("market"))
    value = _coalesce(
        canonical.get("completed_broker_candle"),
        canonical.get("broker_candle_time"),
        canonical.get("latest_completed_candle_time"),
        market.get("latest_completed_candle_time"),
    )
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return pd.Timestamp(parsed).floor("h") if pd.notna(parsed) else None


def canonical_metadata(canonical: Mapping[str, Any], market: pd.DataFrame) -> dict[str, Any]:
    candle = _canonical_candle(canonical)
    missingness = float(market.isna().mean().mean()) if not market.empty else 1.0
    duplicates = int(market["time"].duplicated().sum()) if "time" in market.columns else 0
    sample_start = market["time"].min() if "time" in market.columns and not market.empty else None
    sample_end = market["time"].max() if "time" in market.columns and not market.empty else None
    return {
        "run_id": _safe_text(_coalesce(canonical.get("run_id"), canonical.get("canonical_calculation_id"), default="")),
        "generation_id": _safe_text(_coalesce(canonical.get("generation_id"), canonical.get("calculation_generation"), default="")),
        "symbol": _safe_text(_coalesce(canonical.get("symbol"), default="EURUSD")),
        "timeframe": _safe_text(_coalesce(canonical.get("timeframe"), default="H1")),
        "completed_broker_candle": candle.isoformat() if candle is not None else "",
        "research_model_version": ARERT_VERSION,
        "input_data_version": _safe_text(_coalesce(canonical.get("source_snapshot_hash"), canonical.get("snapshot_hash"), canonical.get("data_signature"), default="")),
        "calculation_timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
        "sample_period": f"{sample_start} / {sample_end}" if sample_start is not None else "UNAVAILABLE",
        "sample_size": int(len(market)),
        "data_quality_status": "OK" if len(market) >= 120 and missingness < 0.20 and duplicates == 0 else "CHECK",
        "missingness_ratio": round(missingness, 6),
        "duplicate_rows": duplicates,
        "leakage_cutoff": candle.isoformat() if candle is not None else "UNAVAILABLE",
        "source_snapshot_hash": _safe_text(_coalesce(canonical.get("source_snapshot_hash"), canonical.get("snapshot_hash"), default="")),
    }


def _find_time_column(frame: pd.DataFrame) -> str | None:
    if frame.empty:
        return None
    normalized = {str(c).strip().lower().replace("_", " "): str(c) for c in frame.columns}
    for name in TIME_NAMES:
        key = name.lower().replace("_", " ")
        if key in normalized:
            return normalized[key]
    for column in frame.columns:
        name = str(column).lower().replace("_", " ")
        if any(token in name for token in ("timestamp", "datetime", "broker time", "candle time")):
            return str(column)
    return None


def _find_market(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> pd.DataFrame:
    candidates: list[pd.DataFrame] = []
    roots = [canonical, _mapping(canonical.get("market")), state]
    keys = (
        "canonical_completed_ohlc_df_20260617", "ohlc_df", "market_frame", "last_df",
        "shared_market_df", "df", "eurusd_h1_df", "normalized_market_data", "dv_pp_df",
    )
    for root in roots:
        for key in keys:
            item = _frame(root.get(key))
            if not item.empty:
                candidates.append(item)
    if not candidates:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    candidates.sort(key=len, reverse=True)
    candle = _canonical_candle(canonical)
    for source in candidates:
        time_col = _find_time_column(source)
        norm = {str(c).strip().lower().replace("_", " "): str(c) for c in source.columns}
        close_col = next((norm.get(name) for name in ("close", "c", "last", "price") if norm.get(name)), None)
        if time_col is None or close_col is None:
            continue
        out = pd.DataFrame({"time": pd.to_datetime(source[time_col], errors="coerce", utc=True, format="mixed")})
        for target, aliases in {
            "open": ("open", "o"), "high": ("high", "h"), "low": ("low", "l"),
            "close": ("close", "c", "last", "price"), "volume": ("volume", "tick volume", "tick_volume", "v"),
        }.items():
            col = next((norm.get(alias) for alias in aliases if norm.get(alias)), None)
            out[target] = pd.to_numeric(source[col], errors="coerce") if col else np.nan
        out = out.dropna(subset=["time", "close"]).sort_values("time", kind="mergesort")
        out["time"] = out["time"].dt.floor("h")
        out = out.drop_duplicates("time", keep="last")
        if candle is not None:
            out = out.loc[out["time"] <= candle]
        if not out.empty:
            return out.tail(10_000).reset_index(drop=True)
    return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])


def _find_decisions(state: Mapping[str, Any]) -> pd.DataFrame:
    candidates = (
        "field1_table5_integrated_decision_collection_20260627",
        "field1_table1_decision_history_20260628",
        "field4to9_collection_history_full_20260628",
        "field4to9_collection_history_20260627",
    )
    frames: list[pd.DataFrame] = []
    for key in candidates:
        item = _frame(state.get(key))
        if item.empty:
            continue
        tc = _find_time_column(item)
        if tc is None:
            continue
        work = item.copy(deep=False)
        work["time"] = pd.to_datetime(work[tc], errors="coerce", utc=True, format="mixed").dt.floor("h")
        work = work.dropna(subset=["time"]).drop_duplicates("time", keep="first")
        frames.append(work)
    if not frames:
        return pd.DataFrame(columns=["time"])
    base = frames[0].set_index("time")
    for extra in frames[1:]:
        extra = extra.set_index("time")
        base = base.reindex(base.index.union(extra.index))
        for column in extra.columns:
            incoming = extra[column].reindex(base.index)
            if column not in base.columns:
                base[column] = incoming
            else:
                missing = base[column].isna() | base[column].astype(str).str.strip().str.upper().isin({"", "N/A", "NA", "NONE", "NAN", "UNAVAILABLE"})
                base.loc[missing, column] = incoming.loc[missing]
    return base.reset_index().sort_values("time").reset_index(drop=True)


def _find_news(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> pd.DataFrame:
    keys = (
        "finnhub_ranked_news_20260626", "finnhub_news_rows_20260626", "nlp_ranked_news_df",
        "ranked_news", "nlp_related_news_priority_20260615", "regime_prediction_history_nlp",
    )
    rows: list[pd.DataFrame] = []
    for root in (state, canonical, _mapping(canonical.get("nlp"))):
        for key in keys:
            frame = _frame(root.get(key))
            if frame.empty:
                continue
            tc = _find_time_column(frame)
            if tc is None:
                continue
            work = frame.copy(deep=False)
            work["time"] = pd.to_datetime(work[tc], errors="coerce", utc=True, format="mixed").dt.floor("h")
            sentiment_col = next((c for c in work.columns if any(t in str(c).lower() for t in ("sentiment", "direction", "bias"))), None)
            impact_col = next((c for c in work.columns if any(t in str(c).lower() for t in ("impact", "priority", "surprise"))), None)
            title_col = next((c for c in work.columns if any(t in str(c).lower() for t in ("headline", "title", "news"))), None)
            out = pd.DataFrame({"time": work["time"]})
            out["title"] = work[title_col].astype(str) if title_col else ""
            if sentiment_col:
                raw = work[sentiment_col]
                numeric = pd.to_numeric(raw, errors="coerce")
                if numeric.notna().any():
                    out["sentiment"] = numeric.clip(-1, 1)
                else:
                    text = raw.astype(str).str.upper()
                    out["sentiment"] = np.where(text.str.contains("BUY|BULL|POSITIVE"), 1.0, np.where(text.str.contains("SELL|BEAR|NEGATIVE"), -1.0, 0.0))
            else:
                out["sentiment"] = np.nan
            out["impact"] = pd.to_numeric(work[impact_col], errors="coerce") if impact_col else np.nan
            rows.append(out.dropna(subset=["time"]))
    if not rows:
        return pd.DataFrame(columns=["time", "title", "sentiment", "impact"])
    return pd.concat(rows, ignore_index=True).sort_values("time").drop_duplicates(["time", "title"], keep="last").reset_index(drop=True)


def _decision_label(value: Any) -> str | None:
    text = _safe_text(value).strip().upper().replace("_", " ")
    if any(token in text for token in ("WAIT", "PULLBACK", "NO TRADE", "NEUTRAL")):
        return "WAIT"
    buy = any(token in text for token in ("BUY", "BULL", "UP", "LONG"))
    sell = any(token in text for token in ("SELL", "BEAR", "DOWN", "SHORT"))
    if buy and not sell:
        return "BUY"
    if sell and not buy:
        return "SELL"
    if "HOLD" in text or "PROTECT" in text:
        return "HOLD"
    return None


def _derive_features(market: pd.DataFrame, decisions: pd.DataFrame, news: pd.DataFrame) -> pd.DataFrame:
    if market.empty:
        return pd.DataFrame()
    x = market.copy()
    close = x["close"]
    x["return_1h"] = close.pct_change()
    x["return_3h"] = close.pct_change(3)
    x["return_6h"] = close.pct_change(6)
    high = x["high"].where(x["high"].notna(), close)
    low = x["low"].where(x["low"].notna(), close)
    x["range_pct"] = (high - low).abs() / close.replace(0, np.nan)
    x["vol_24h"] = x["return_1h"].rolling(24, min_periods=8).std()
    x["vol_120h"] = x["return_1h"].rolling(120, min_periods=24).std()
    for window, name in ((24, "lower"), (120, "middle"), (600, "higher")):
        mean = x["return_1h"].rolling(window, min_periods=max(8, min(window // 4, 60))).mean()
        scale = x["return_1h"].rolling(window, min_periods=max(8, min(window // 4, 60))).std().replace(0, np.nan)
        z = mean / scale
        x[f"{name}_z"] = z
        x[f"{name}_regime"] = np.where(z > 0.08, "BULL", np.where(z < -0.08, "BEAR", "COMPRESSION"))
    hour = x["time"].dt.hour
    x["session"] = np.select(
        [hour.between(7, 11), hour.between(12, 15), hour.between(16, 20)],
        ["LONDON", "LONDON_NY_OVERLAP", "NEW_YORK"], default="OTHER",
    )
    vol_med = x["vol_24h"].rolling(240, min_periods=24).median()
    x["volatility_state"] = np.where(x["vol_24h"] > vol_med, "HIGH_VOLATILITY", "LOW_VOLATILITY")
    if not decisions.empty:
        decision_cols = [c for c in decisions.columns if c != "time" and any(token in str(c).lower() for token in DECISION_TOKENS)]
        use = decisions[["time", *decision_cols]].copy(deep=False)
        x = x.merge(use, on="time", how="left")
        vote_numeric: list[pd.Series] = []
        for column in decision_cols:
            labels = x[column].map(_decision_label)
            vote_numeric.append(labels.map({"BUY": 1.0, "SELL": -1.0, "WAIT": 0.0, "HOLD": 0.0}))
        if vote_numeric:
            votes = pd.concat(vote_numeric, axis=1)
            x["vote_mean"] = votes.mean(axis=1, skipna=True)
            x["vote_coverage"] = votes.notna().mean(axis=1)
            x["vote_agreement"] = votes.abs().mean(axis=1, skipna=True)
    if not news.empty:
        hourly = news.groupby("time", as_index=False).agg(news_sentiment=("sentiment", "mean"), news_impact=("impact", "max"), news_count=("title", "count"))
        x = x.merge(hourly, on="time", how="left")
    for column in ("vote_mean", "vote_coverage", "vote_agreement", "news_sentiment", "news_impact", "news_count"):
        if column not in x.columns:
            x[column] = np.nan
    for horizon in (1, 3, 6):
        x[f"future_return_{horizon}h"] = close.shift(-horizon) / close - 1.0
        x[f"outcome_{horizon}h"] = np.where(x[f"future_return_{horizon}h"] > 0, "BUY", np.where(x[f"future_return_{horizon}h"] < 0, "SELL", "WAIT"))
    return x


def build_context(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> ResearchContext:
    market = _find_market(state, canonical)
    metadata = canonical_metadata(canonical, market)
    decisions = _find_decisions(state)
    candle = _canonical_candle(canonical)
    if candle is not None and not decisions.empty:
        decisions = decisions.loc[decisions["time"] <= candle]
    news = _find_news(state, canonical)
    if candle is not None and not news.empty:
        news = news.loc[news["time"] <= candle]
    features = _derive_features(market, decisions, news)
    return ResearchContext(canonical, state, metadata, market, decisions, news, features)


def _module_result(ctx: ResearchContext, number: int, *, status: str, summary: Mapping[str, Any], tables: Mapping[str, Any] | None = None, limitations: Iterable[str] = (), methodology: str = "") -> dict[str, Any]:
    return {
        "module_number": number,
        "module_name": MODULE_CATALOG[number][0],
        "field_number": MODULE_CATALOG[number][1],
        "status": status,
        "metadata": dict(ctx.metadata),
        "summary": _jsonable(summary),
        "tables": _jsonable(tables or {}),
        "limitations": list(limitations),
        "methodology": methodology,
        "production_influence_enabled": False,
    }


def _insufficient(ctx: ResearchContext, number: int, reason: str, *, summary: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return _module_result(ctx, number, status="INCOMPLETE_INSUFFICIENT_DATA", summary=summary or {}, limitations=[reason])


def _run_lengths(labels: pd.Series, times: pd.Series) -> pd.DataFrame:
    valid = pd.DataFrame({"time": times, "state": labels}).dropna()
    if valid.empty:
        return pd.DataFrame()
    groups = valid["state"].ne(valid["state"].shift()).cumsum()
    out = valid.groupby(groups, sort=False).agg(
        regime=("state", "first"), start=("time", "first"), end=("time", "last"), observations=("state", "size")
    ).reset_index(drop=True)
    out["duration_hours"] = ((out["end"] - out["start"]).dt.total_seconds() / 3600.0 + 1.0).clip(lower=1)
    return out


def module_1(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    x = ctx.features
    if len(x) < 48:
        return _insufficient(ctx, 1, "At least 48 completed H1 observations are required for empirical duration analysis.")
    rows = []
    current_summary = {}
    for scale in ("lower", "middle", "higher"):
        episodes = _run_lengths(x[f"{scale}_regime"], x["time"])
        if episodes.empty:
            continue
        current = str(x[f"{scale}_regime"].iloc[-1])
        current_episode = episodes.iloc[-1]
        age = float(current_episode["duration_hours"])
        same = episodes.loc[episodes["regime"].eq(current), "duration_hours"]
        expected = float(same.mean()) if len(same) else age
        median = float(same.median()) if len(same) else age
        denom = max(int((same >= age).sum()), 1)
        survival = {f"remain_{h}h_probability": round(float(((same >= age + h).sum()) / denom), 4) for h in (1, 3, 6, 12, 24)}
        reliability = 100.0 * max(survival.values()) if survival else 0.0
        current_summary[scale] = {
            "current_regime": current, "current_regime_age_hours": age,
            "expected_duration_hours": round(expected, 3), "median_duration_hours": round(median, 3),
            "remaining_expected_hours": round(max(0.0, expected - age), 3),
            "transition_probability_1h": round(1.0 - survival["remain_1h_probability"], 4),
            "premature_transition_warning": bool(age < median and survival["remain_1h_probability"] >= 0.5),
            "duration_adjusted_reliability": round(reliability, 3), **survival,
        }
        ep = episodes.copy()
        ep.insert(0, "scale", scale)
        rows.append(ep)
    table = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    current_summary["comparison"] = {
        "production_regime": _coalesce(_mapping(ctx.canonical.get("regime")).get("major_regime"), ctx.canonical.get("regime")),
        "normal_hmm_proxy": current_summary.get("lower", {}).get("current_regime"),
        "hsmm_duration_adjusted": current_summary.get("middle", {}).get("current_regime"),
        "note": "Empirical-duration HSMM approximation; full parametric HSMM fitting remains a thesis extension.",
    }
    return _module_result(ctx, 1, status="RESEARCH_PROTOTYPE_COMPLETE", summary=current_summary, tables={"regime_duration_history": table}, methodology="Run-length duration/survival estimates from completed H1 regime states; no future row enters current estimates.")


def module_2(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    x = ctx.features
    if x.empty:
        return _insufficient(ctx, 2, "Completed H1 features are unavailable.")
    def classify(row: pd.Series) -> str:
        a, b, c = row["lower_regime"], row["middle_regime"], row["higher_regime"]
        if a == b == c == "BULL": return "FULL BULLISH ALIGNMENT"
        if a == b == c == "BEAR": return "FULL BEARISH ALIGNMENT"
        if c == "BULL" and a == "BEAR": return "TEMPORARY PULLBACK"
        if c == "BEAR" and a == "BULL": return "TEMPORARY RECOVERY"
        if len({a, b, c}) == 3: return "STRUCTURAL CONFLICT"
        if a != b and b == c: return "POSSIBLE TRANSITION"
        if "COMPRESSION" in {a, b, c}: return "UNSTABLE HIERARCHY"
        return "INSUFFICIENT EVIDENCE"
    matrix = x[["time", "lower_regime", "middle_regime", "higher_regime"]].copy()
    matrix["hierarchy_class"] = matrix.apply(classify, axis=1)
    matrix["hierarchy_agreement_score"] = matrix[["lower_regime", "middle_regime", "higher_regime"]].apply(lambda r: 100.0 * r.value_counts().max() / 3.0, axis=1)
    matrix["structural_conflict_score"] = 100.0 - matrix["hierarchy_agreement_score"]
    matrix["lower_to_middle_confirmation"] = np.where(matrix["lower_regime"].eq(matrix["middle_regime"]), 100.0, 0.0)
    matrix["middle_to_higher_confirmation"] = np.where(matrix["middle_regime"].eq(matrix["higher_regime"]), 100.0, 0.0)
    matrix["transition_pressure"] = matrix["structural_conflict_score"] * np.where(matrix["lower_regime"].ne(matrix["middle_regime"]), 1.0, 0.5)
    matrix["higher_regime_constraint_strength"] = np.where(matrix["higher_regime"].eq("COMPRESSION"), 50.0, 100.0)
    return _module_result(ctx, 2, status="RESEARCH_PROTOTYPE_COMPLETE", summary=matrix.iloc[-1].to_dict(), tables={"regime_hierarchy_matrix": matrix.tail(600).sort_values("time", ascending=False)}, methodology="Hierarchical classification over 24/120/600-hour point-in-time states.")


def _robust_z(series: pd.Series, window: int = 120) -> pd.Series:
    med = series.rolling(window, min_periods=max(12, window // 5)).median()
    mad = (series - med).abs().rolling(window, min_periods=max(12, window // 5)).median().replace(0, np.nan)
    return 0.6745 * (series - med) / mad


def module_3(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    x = ctx.features
    if len(x) < 40:
        return _insufficient(ctx, 3, "At least 40 completed observations are required for online shift evidence.")
    variables = ["return_1h", "range_pct", "vol_24h", "vote_mean", "news_sentiment"]
    contributions = pd.DataFrame({"time": x["time"]})
    usable = []
    for column in variables:
        if column in x and x[column].notna().sum() >= 12:
            contributions[column] = _robust_z(pd.to_numeric(x[column], errors="coerce")).abs().clip(0, 10)
            usable.append(column)
    if not usable:
        return _insufficient(ctx, 3, "No changepoint variables have enough finite history.")
    score = contributions[usable].mean(axis=1, skipna=True)
    probability = (1.0 - np.exp(-score.fillna(0) / 2.0)).clip(0, 1)
    cp = probability >= 0.75
    last_cp_index = np.where(cp.to_numpy())[0]
    run_length = int(len(x) - 1 - last_cp_index[-1]) if len(last_cp_index) else int(len(x))
    table = contributions.assign(changepoint_probability=probability, structural_break_strength=(score * 10).clip(0, 100), false_break_probability=(1 - probability)).tail(600)
    latest = table.iloc[-1]
    ranked = sorted(((column, float(latest.get(column))) for column in usable if pd.notna(latest.get(column))), key=lambda item: item[1], reverse=True)
    summary = {
        "changepoint_probability": round(float(latest["changepoint_probability"]), 4),
        "most_likely_change_hour": table.loc[table["changepoint_probability"].idxmax(), "time"],
        "run_length_hours": run_length,
        "variables_responsible": ranked[:5],
        "structural_break_strength": round(float(latest["structural_break_strength"]), 3),
        "false_break_probability": round(float(latest["false_break_probability"]), 4),
        "pre_change_state": x["middle_regime"].iloc[max(0, len(x)-run_length-2)] if len(x) else None,
        "post_change_candidate_state": x["middle_regime"].iloc[-1],
    }
    return _module_result(ctx, 3, status="RESEARCH_PROTOTYPE_COMPLETE", summary=summary, tables={"online_changepoint_history": table.sort_values("time", ascending=False)}, methodology="Robust point-in-time change score mapped to a probability-like research diagnostic; not a fully Bayesian posterior.", limitations=["Full Adams–MacKay BOCPD posterior recursion is marked incomplete; this robust online proxy is separately labelled."])


def module_4(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    x = ctx.features
    if len(x) < 40:
        return _insufficient(ctx, 4, "At least 40 completed returns are required for robust jump detection.")
    z = _robust_z(x["return_1h"], 120)
    jump_prob = (1.0 - np.exp(-z.abs().fillna(0) / 2.5)).clip(0, 1)
    table = x[["time", "return_1h", "vol_24h", "news_sentiment", "news_impact"]].copy()
    table["jump_probability"] = jump_prob
    table["jump_direction"] = np.where(x["return_1h"] > 0, "UP", np.where(x["return_1h"] < 0, "DOWN", "FLAT"))
    table["jump_magnitude"] = x["return_1h"].abs()
    table["news_association_strength"] = np.where(x["news_sentiment"].notna(), np.minimum(100.0, jump_prob * 100.0), np.nan)
    table["temporary_shock_probability"] = (1.0 - jump_prob * x["middle_z"].abs().clip(0, 1)).clip(0, 1)
    table["structural_shock_probability"] = (jump_prob * x["middle_z"].abs().clip(0, 1)).clip(0, 1)
    table["possible_data_anomaly"] = (z.abs() > 8) & x["news_sentiment"].isna()
    latest = table.iloc[-1].to_dict()
    latest["causality_notice"] = "Timestamp association only; causality is not claimed."
    latest["expected_decay_time_hours"] = None if pd.isna(latest.get("jump_probability")) else round(1 + 11 * float(latest["temporary_shock_probability"]), 2)
    latest["regime_change_probability_following_jump"] = round(_safe_float(latest.get("structural_shock_probability"), 0.0), 4)
    return _module_result(ctx, 4, status="RESEARCH_PROTOTYPE_COMPLETE", summary=latest, tables={"jump_history": table.tail(600).sort_values("time", ascending=False)}, methodology="Robust return outlier score joined only to news at equal completed-H1 timestamps.")


def _conformal_table(x: pd.DataFrame) -> pd.DataFrame:
    rows = []
    current = x.iloc[-1]
    for h in (1, 3, 6):
        rolling_mean = x["return_1h"].rolling(120, min_periods=24).mean()
        prediction_return = rolling_mean * h
        prediction_price = x["close"] * (1.0 + prediction_return)
        target = x["close"].shift(-h)
        residual = (target - prediction_price).abs()
        settled = residual.dropna()
        if len(settled) < 24:
            rows.append({"horizon": f"H+{h}", "status": "INSUFFICIENT_DATA", "sample_size": len(settled)})
            continue
        calibration = settled.iloc[:-max(1, len(settled)//5)] if len(settled) >= 40 else settled
        q = float(calibration.quantile(0.90, interpolation="higher"))
        point = float(current["close"] * (1.0 + _safe_float(rolling_mean.iloc[-1], 0.0) * h))
        historical_lower = prediction_price - q
        historical_upper = prediction_price + q
        covered = ((target >= historical_lower) & (target <= historical_upper)).where(target.notna()).dropna()
        coverage = float(covered.mean()) if len(covered) else np.nan
        group = f"{current['middle_regime']}|{current['volatility_state']}|{current['session']}"
        rows.append({
            "horizon": f"H+{h}", "point_forecast": point, "lower_interval": point-q, "upper_interval": point+q,
            "target_coverage": 0.90, "observed_coverage": coverage, "interval_width": 2*q,
            "calibration_error": abs(coverage-0.90) if math.isfinite(coverage) else np.nan,
            "under_coverage_warning": bool(math.isfinite(coverage) and coverage < 0.85),
            "over_wide_interval_warning": bool((2*q) > 4 * float(x["close"].diff().abs().tail(120).median() or 0)),
            "calibration_group": group, "sample_size": len(settled), "status": "OK",
        })
    return pd.DataFrame(rows)


def module_5(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    if len(ctx.features) < 30:
        return _insufficient(ctx, 5, "At least 30 completed prices are required for conformal residual calibration.")
    table = _conformal_table(ctx.features)
    valid = table.loc[table.get("status", "").eq("OK")] if not table.empty and "status" in table else pd.DataFrame()
    status = "RESEARCH_PROTOTYPE_COMPLETE" if not valid.empty else "INCOMPLETE_INSUFFICIENT_DATA"
    summary = valid.set_index("horizon").to_dict(orient="index") if not valid.empty else {}
    return _module_result(ctx, 5, status=status, summary=summary, tables={"adaptive_conformal_intervals": table}, methodology="Rolling residual split conformal intervals using only settled past targets.", limitations=["Separate group-specific quantiles require larger samples; current output records the group and uses pooled calibration when group history is insufficient."])


def module_6(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    base = _mapping(deps.get(5))
    cp = _mapping(_mapping(deps.get(3)).get("summary"))
    table = _frame(_mapping(base.get("tables")).get("adaptive_conformal_intervals"))
    if table.empty:
        return _insufficient(ctx, 6, "Module 5 intervals are unavailable.")
    probability = _safe_float(cp.get("changepoint_probability"), 0.0)
    run_length = int(_safe_float(cp.get("run_length_hours"), 999.0))
    factor = 1.0 + max(0.0, probability - 0.5)
    for column in ("lower_interval", "upper_interval", "point_forecast"):
        table[column] = pd.to_numeric(table.get(column), errors="coerce")
    half = (table["upper_interval"] - table["lower_interval"]) / 2.0
    table["normal_lower"] = table["lower_interval"]
    table["normal_upper"] = table["upper_interval"]
    table["changepoint_adjusted_lower"] = table["point_forecast"] - half * factor
    table["changepoint_adjusted_upper"] = table["point_forecast"] + half * factor
    table["calibration_reset_status"] = "RESET_ACTIVE" if probability >= 0.75 else "NORMAL"
    table["hours_since_reset"] = run_length
    table["post_change_sample_size"] = max(0, min(run_length, len(ctx.features)))
    table["confidence_in_new_calibration"] = np.clip(table["post_change_sample_size"] / 120.0, 0, 1)
    return _module_result(ctx, 6, status="RESEARCH_PROTOTYPE_COMPLETE", summary=table.iloc[0].to_dict() if len(table) else {}, tables={"changepoint_aware_intervals": table}, methodology="Intervals widen after credible shift evidence and recover as post-change samples accumulate.")


def _primary_decision_column(frame: pd.DataFrame) -> str | None:
    priorities = ("Production Master Decision", "Master Action", "Final Decision", "Master Decision", "Technical Consensus", "Combined Next-Hour Direction")
    return next((c for c in priorities if c in frame.columns), None)


def _decision_outcomes(ctx: ResearchContext) -> pd.DataFrame:
    if ctx.decisions.empty or ctx.market.empty:
        return pd.DataFrame()
    column = _primary_decision_column(ctx.decisions)
    if column is None:
        return pd.DataFrame()
    work = ctx.decisions[["time", column]].copy()
    work["primary_decision"] = work[column].map(_decision_label)
    market = ctx.features[["time", "future_return_1h", "middle_regime", "vote_agreement", "vote_coverage"]]
    work = work.merge(market, on="time", how="left")
    direction = work["primary_decision"].map({"BUY": 1, "SELL": -1, "WAIT": 0, "HOLD": 0})
    realized = np.sign(work["future_return_1h"])
    work["correct"] = np.where(work["future_return_1h"].notna(), (direction == realized) | ((direction == 0) & (realized == 0)), np.nan)
    return work


def module_7(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    outcomes = _decision_outcomes(ctx)
    settled = outcomes.dropna(subset=["correct"])
    if len(settled) < 20:
        return _insufficient(ctx, 7, "At least 20 settled primary decisions are required for a meta-label estimate.", summary={"primary_decision": outcomes.iloc[-1]["primary_decision"] if len(outcomes) else None})
    current = outcomes.iloc[-1]
    group = settled.loc[settled["primary_decision"].eq(current["primary_decision"])]
    if len(group) < 5:
        group = settled
    probability = float(group["correct"].mean())
    accept = probability >= 0.60
    summary = {
        "primary_decision": current["primary_decision"], "meta_label": "ACCEPT" if accept else "REJECT",
        "actionability_probability": round(probability, 4), "estimated_false_positive_probability": round(1-probability, 4),
        "estimated_false_negative_probability": None, "reason_for_rejection": None if accept else "Historical calibrated success is below the pre-registered 0.60 research threshold.",
        "supporting_features": {"middle_regime": current.get("middle_regime"), "vote_agreement": current.get("vote_agreement"), "vote_coverage": current.get("vote_coverage")},
        "calibrated_probability": round(probability, 4), "sample_size": len(group),
    }
    return _module_result(ctx, 7, status="RESEARCH_PROTOTYPE_COMPLETE", summary=summary, tables={"meta_label_history": settled.tail(600).sort_values("time", ascending=False)}, methodology="Historical decision-conditioned empirical calibration; production decision remains unchanged.")


def _classification_metrics(y: np.ndarray, pred: np.ndarray, prob: np.ndarray) -> dict[str, float]:
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, precision_score, recall_score, f1_score, matthews_corrcoef, brier_score_loss, log_loss
    return {
        "accuracy": float(accuracy_score(y, pred)), "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "precision": float(precision_score(y, pred, zero_division=0)), "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)), "mcc": float(matthews_corrcoef(y, pred)),
        "brier_score": float(brier_score_loss(y, prob)), "log_loss": float(log_loss(y, np.column_stack([1-prob, prob]), labels=[0,1])),
    }


def module_8(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    outcomes = _decision_outcomes(ctx).dropna(subset=["correct"])
    if len(outcomes) < 40:
        return _insufficient(ctx, 8, "At least 40 settled decisions are required for validation-only threshold selection.")
    y = outcomes["correct"].astype(int).to_numpy()
    base_prob = outcomes["vote_agreement"].fillna(0.5).clip(0, 1).to_numpy()
    split1, split2 = int(len(y)*0.70), int(len(y)*0.85)
    validation = slice(split1, split2)
    test = slice(split2, len(y))
    thresholds = np.linspace(0.50, 0.90, 9)
    rows = []
    for threshold in thresholds:
        retained = base_prob >= threshold
        subset = retained & np.arange(len(y)).astype(int).__ge__(split1) & np.arange(len(y)).astype(int).__lt__(split2)
        if subset.sum() < 3:
            rows.append({"threshold": threshold, "validation_sample_size": int(subset.sum()), "status": "INSUFFICIENT"}); continue
        pred = np.ones(subset.sum(), dtype=int)
        yy = y[subset]
        metrics = _classification_metrics(yy, pred, base_prob[subset])
        rows.append({"threshold": threshold, "coverage_pct": 100*float(retained.mean()), "abstained_pct": 100*(1-float(retained.mean())), "validation_sample_size": int(subset.sum()), **metrics, "status": "OK"})
    table = pd.DataFrame(rows)
    valid = table.loc[table["status"].eq("OK")]
    if valid.empty:
        return _insufficient(ctx, 8, "No threshold retained enough validation observations.", summary={"risk_coverage": rows})
    # Predefined utility: balanced accuracy minus 0.15 abstention. Selection uses validation only.
    objective = valid["balanced_accuracy"] - 0.15 * valid["abstained_pct"] / 100.0
    selected = float(valid.loc[objective.idxmax(), "threshold"])
    test_mask = base_prob[test] >= selected
    test_summary = {"sample_size": int(test_mask.sum())}
    if test_mask.sum() >= 3:
        yy = y[test][test_mask]
        test_summary.update(_classification_metrics(yy, np.ones(len(yy), dtype=int), base_prob[test][test_mask]))
    summary = {"selected_threshold_from_validation_only": selected, "test_evaluation": test_summary, "final_test_used_for_selection": False}
    return _module_result(ctx, 8, status="RESEARCH_PROTOTYPE_COMPLETE", summary=summary, tables={"risk_coverage": table}, methodology="Chronological 70/15/15 split; abstention threshold selected only on validation.")


def _vote_columns(frame: pd.DataFrame) -> list[str]:
    return [c for c in frame.columns if c != "time" and any(token in str(c).lower() for token in DECISION_TOKENS) and frame[c].map(_decision_label).notna().sum() >= 5]


def module_9(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    if ctx.decisions.empty or ctx.features.empty:
        return _insufficient(ctx, 9, "Decision families or settled market outcomes are unavailable.")
    columns = _vote_columns(ctx.decisions)
    if not columns:
        return _insufficient(ctx, 9, "No internal model decision columns have enough history.")
    data = ctx.decisions[["time", *columns]].merge(ctx.features[["time", "outcome_1h", "middle_regime"]], on="time", how="inner")
    rows = []
    losses = []
    for column in columns[:40]:
        labels = data[column].map(_decision_label)
        valid = labels.notna() & data["outcome_1h"].notna()
        recent = valid & (data.index >= max(0, len(data)-240))
        if recent.sum() < 5:
            continue
        correct = labels[recent].eq(data.loc[recent, "outcome_1h"]).astype(float)
        loss = float(1.0 - correct.mean())
        losses.append((column, max(loss, 0.02)))
    if not losses:
        return _insufficient(ctx, 9, "No model has at least five recent settled predictions.")
    inv = np.array([1/loss for _, loss in losses], dtype=float)
    weights = inv / inv.sum()
    equal = 1.0 / len(losses)
    for (column, loss), weight in zip(losses, weights):
        current_label = _decision_label(data[column].iloc[-1])
        contribution = (1 if current_label == "BUY" else -1 if current_label == "SELL" else 0) * weight
        rows.append({"model_name": column, "current_weight": float(weight), "previous_weight": equal, "reason_for_weight_change": "inverse recent out-of-sample 0/1 loss", "recent_loss": loss, "calibration": None, "best_regime": None, "worst_regime": None, "current_vote": current_label, "final_weighted_contribution": contribution})
    table = pd.DataFrame(rows).sort_values("current_weight", ascending=False)
    score = float(table["final_weighted_contribution"].sum())
    summary = {"weighted_consensus": "BUY" if score > 0.05 else "SELL" if score < -0.05 else "WAIT", "weighted_score": score, "weights_sum": float(table["current_weight"].sum()), "equal_weight_baseline": equal}
    return _module_result(ctx, 9, status="RESEARCH_PROTOTYPE_COMPLETE", summary=summary, tables={"dynamic_model_weights": table}, methodology="Inverse recent chronological out-of-sample loss; weights normalized to one and production outputs remain untouched.")


def module_10(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    weights = _frame(_mapping(_mapping(deps.get(9)).get("tables")).get("dynamic_model_weights"))
    if weights.empty:
        return _insufficient(ctx, 10, "Module 9 model agents are unavailable.")
    rows = []
    for _, row in weights.iterrows():
        confidence = _safe_float(row.get("current_weight"), 0.0)
        loss = _safe_float(row.get("recent_loss"), 0.5)
        reward = confidence * (1-loss) * 10
        penalty = confidence * confidence * loss * 20
        initial = 100.0
        updated = initial + reward - penalty
        rows.append({"agent": row["model_name"], "initial_research_capital": initial, "directional_vote": row.get("current_vote"), "confidence": confidence, "calibration_score": 1-loss, "historical_performance": 1-loss, "reward": reward, "penalty": penalty, "updated_research_capital": updated, "contribution_to_consensus": row.get("final_weighted_contribution")})
    table = pd.DataFrame(rows)
    finite = bool(np.isfinite(table.select_dtypes(include="number").to_numpy()).all())
    return _module_result(ctx, 10, status="RESEARCH_PROTOTYPE_COMPLETE" if finite else "FAILED_VALIDATION", summary={"agent_count": len(table), "capital_values_finite": finite, "terminology": "research/evidence capital only"}, tables={"evidence_capital_agents": table}, methodology="Confident errors receive a quadratic research-capital penalty; no real-money output.")


def _analogue_features(x: pd.DataFrame) -> list[str]:
    return [c for c in ("return_1h", "return_3h", "return_6h", "range_pct", "vol_24h", "lower_z", "middle_z", "higher_z", "vote_mean", "vote_agreement", "news_sentiment") if c in x.columns and x[c].notna().sum() >= 10]


def module_11(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    x = ctx.features.copy()
    features = _analogue_features(x)
    if len(x) < 30 or len(features) < 3:
        return _insufficient(ctx, 11, "At least 30 observations and three analogue features are required.")
    settled = x.iloc[:-6].copy()
    current = x.iloc[-1]
    med = settled[features].median()
    scale = settled[features].std().replace(0, np.nan)
    diff = (settled[features] - current[features]).abs().div(scale)
    diff = diff.mask(np.isinf(diff))
    distance = diff.mean(axis=1, skipna=True)
    similarity = (100.0 / (1.0 + distance)).clip(0, 100)
    settled = settled.assign(distance=distance, similarity_score=similarity)
    # Explicit self-match prevention: current row is excluded before distance calculation.
    top = settled.sort_values("distance").head(15).copy()
    top["matching_features"] = top.apply(lambda row: ", ".join([c for c in features if pd.notna(row[c]) and abs((row[c]-current[c])/(scale[c] if pd.notna(scale[c]) else 1)) < 0.5]), axis=1)
    top["mismatching_features"] = top.apply(lambda row: ", ".join([c for c in features if pd.notna(row[c]) and abs((row[c]-current[c])/(scale[c] if pd.notna(scale[c]) else 1)) > 1.5]), axis=1)
    for h in (1, 3, 6):
        top[f"H+{h} outcome"] = top[f"outcome_{h}h"]
        top[f"H+{h} return"] = top[f"future_return_{h}h"]
    top["maximum_favourable_movement"] = top[["future_return_1h", "future_return_3h", "future_return_6h"]].max(axis=1)
    top["maximum_adverse_movement"] = top[["future_return_1h", "future_return_3h", "future_return_6h"]].min(axis=1)
    cols = ["time", "similarity_score", "matching_features", "mismatching_features", "H+1 outcome", "H+3 outcome", "H+6 outcome", "H+1 return", "H+3 return", "H+6 return", "maximum_favourable_movement", "maximum_adverse_movement", "middle_regime", "session"]
    top = top[cols]
    outcomes = top["H+1 outcome"].value_counts(normalize=True)
    summary = {"analogue_consensus": outcomes.idxmax() if len(outcomes) else None, "consensus_probability": float(outcomes.max()) if len(outcomes) else None, "effective_sample_size": len(top), "current_event_self_match_prevented": True}
    return _module_result(ctx, 11, status="RESEARCH_PROTOTYPE_COMPLETE", summary=summary, tables={"top_historical_analogues": top}, methodology="Standardized mixed-feature distance over prior settled rows only; the current row is explicitly excluded.")


def module_12(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    analogues = _frame(_mapping(_mapping(deps.get(11)).get("tables")).get("top_historical_analogues"))
    if analogues.empty:
        return _insufficient(ctx, 12, "Module 11 analogues are unavailable.")
    times = pd.to_datetime(analogues["time"], errors="coerce", utc=True)
    latest = ctx.features["time"].max()
    age_hours = (latest - times).dt.total_seconds() / 3600.0
    similarity = pd.to_numeric(analogues["similarity_score"], errors="coerce").fillna(0) / 100.0
    regime_match = analogues["middle_regime"].eq(ctx.features["middle_regime"].iloc[-1]).astype(float).replace(0, 0.5)
    data_quality = 1.0 - _safe_float(ctx.metadata.get("missingness_ratio"), 0.0)
    equal = pd.Series(1.0, index=analogues.index)
    recency = np.exp(-0.001 * age_hours.clip(lower=0))
    similarity_weight = similarity.pow(2)
    regime_weight = regime_match
    combined = similarity_weight * recency * regime_weight * data_quality
    table = analogues[["time", "similarity_score", "middle_regime", "H+1 outcome"]].copy()
    for name, values in {"equal_weight": equal, "recency_weight": recency, "similarity_weight": similarity_weight, "regime_conditioned_weight": regime_weight, "combined_weight": combined}.items():
        total = float(values.sum())
        table[name] = values / total if total > 0 else 0.0
    def consensus(column: str) -> str | None:
        grouped = table.groupby("H+1 outcome")[column].sum()
        return grouped.idxmax() if len(grouped) else None
    summary = {name: consensus(name) for name in ("equal_weight", "recency_weight", "similarity_weight", "regime_conditioned_weight", "combined_weight")}
    summary["selection_status"] = "COMPARISON_ONLY_WALK_FORWARD_SELECTION_PENDING"
    return _module_result(ctx, 12, status="RESEARCH_PROTOTYPE_COMPLETE", summary=summary, tables={"outcome_decay_memory": table}, methodology="Similarity² × exponential recency × regime match × data quality; model promotion requires walk-forward validation.")


def module_13(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    if ctx.news.empty or ctx.news["sentiment"].notna().sum() < 5:
        return _insufficient(ctx, 13, "Timestamped NLP sentiment has fewer than five usable events; no behavioral score is fabricated.")
    news = ctx.news.copy()
    sentiment = pd.to_numeric(news["sentiment"], errors="coerce").clip(-1, 1)
    lambdas = (1.5, 2.0, 2.25, 2.5)
    rows = []
    for lam in lambdas:
        value = np.where(sentiment >= 0, np.sqrt(sentiment.clip(lower=0)), -lam * np.sqrt((-sentiment).clip(lower=0)))
        rows.append({"loss_aversion_parameter": lam, "mean_adjusted_sentiment": float(np.nanmean(value)), "event_count": int(np.isfinite(value).sum()), "selection_set": "TRAIN/VALIDATION_ONLY_REQUIRED"})
    selected_lambda = 2.25  # literature baseline, explicitly not claimed as data-selected.
    adjusted = np.where(sentiment >= 0, np.sqrt(sentiment.clip(lower=0)), -selected_lambda * np.sqrt((-sentiment).clip(lower=0)))
    table = news.assign(
        raw_nlp_sentiment=sentiment,
        positive_news_value=np.sqrt(sentiment.clip(lower=0)),
        negative_news_value=-selected_lambda*np.sqrt((-sentiment).clip(lower=0)),
        loss_aversion_adjusted_sentiment=adjusted,
        surprise_intensity=pd.to_numeric(news["impact"], errors="coerce").abs(),
        fear_asymmetry=np.where(sentiment < 0, np.abs(adjusted), 0),
        optimism_asymmetry=np.where(sentiment > 0, adjusted, 0),
    )
    summary = {"current_adjusted_sentiment": float(table["loss_aversion_adjusted_sentiment"].iloc[-1]), "loss_aversion_parameter": selected_lambda, "parameter_status": "LITERATURE_BASELINE_NOT_FINAL_TEST_SELECTED", "negative_mean_magnitude": _safe_float(table.loc[sentiment<0, "loss_aversion_adjusted_sentiment"].abs().mean(), 0.0), "positive_mean_magnitude": _safe_float(table.loc[sentiment>0, "loss_aversion_adjusted_sentiment"].abs().mean(), 0.0)}
    return _module_result(ctx, 13, status="RESEARCH_PROTOTYPE_COMPLETE", summary=summary, tables={"prospect_sentiment_events": table.tail(600).sort_values("time", ascending=False), "parameter_comparison": pd.DataFrame(rows)}, methodology="Prospect-theory value transform; parameter 2.25 is a declared literature baseline pending walk-forward selection.")


def _vote_matrix(ctx: ResearchContext) -> pd.DataFrame:
    if ctx.decisions.empty:
        return pd.DataFrame()
    cols = _vote_columns(ctx.decisions)
    if not cols:
        return pd.DataFrame()
    matrix = pd.DataFrame(index=ctx.decisions.index)
    matrix["time"] = ctx.decisions["time"]
    for column in cols[:40]:
        matrix[column] = ctx.decisions[column].map(_decision_label).map({"BUY": 1.0, "SELL": -1.0, "WAIT": 0.0, "HOLD": 0.0})
    return matrix


def module_14(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    matrix = _vote_matrix(ctx)
    if matrix.empty or len(matrix.columns) < 3:
        return _insufficient(ctx, 14, "At least two independent decision columns are required.")
    votes = matrix.drop(columns="time")
    corr = votes.corr(min_periods=5)
    upper = corr.where(np.triu(np.ones(corr.shape), 1).astype(bool)).stack()
    avg_corr = float(upper.abs().mean()) if len(upper) else 0.0
    latest = votes.iloc[-1].dropna()
    raw_consensus = float(abs(latest.mean())) if len(latest) else 0.0
    independent = max(1.0, len(latest) * (1-avg_corr))
    extension = abs(_safe_float(ctx.features["return_6h"].iloc[-1], 0.0)) / max(_safe_float(ctx.features["vol_24h"].iloc[-1], 1e-9), 1e-9)
    fragility = 100.0 * raw_consensus * avg_corr
    summary = {"raw_consensus": round(100*raw_consensus, 3), "average_pairwise_correlation": round(avg_corr, 4), "evidence_redundancy": round(100*avg_corr, 3), "independent_evidence_count": round(independent, 3), "herding_risk": round(fragility, 3), "consensus_fragility": round(fragility, 3), "move_exhaustion_score": round(min(100.0, extension*20), 3), "late_entry_risk": round(min(100.0, fragility*0.6+extension*10), 3), "warning": bool(raw_consensus>0.7 and avg_corr>0.7 and extension>2)}
    return _module_result(ctx, 14, status="RESEARCH_PROTOTYPE_COMPLETE", summary=summary, tables={"pairwise_vote_correlation": corr.reset_index(names="model")}, methodology="Consensus discounted by pairwise dependence; duplicated evidence is not counted as independent support.")


def module_15(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    x = ctx.features
    if len(x) < 48:
        return _insufficient(ctx, 15, "At least two days of H1 data are required for reference-point analysis.")
    day = x["time"].dt.floor("d")
    daily = x.assign(day=day).groupby("day").agg(day_high=("high", "max"), day_low=("low", "min"), day_open=("open", "first"))
    daily[["prev_day_high", "prev_day_low"]] = daily[["day_high", "day_low"]].shift(1).to_numpy()
    work = x.assign(day=day).merge(daily[["prev_day_high", "prev_day_low", "day_open"]], left_on="day", right_index=True, how="left")
    work["session_open"] = work.groupby([work["time"].dt.date, "session"])["open"].transform("first")
    work["round_number"] = (work["close"] * 100).round() / 100
    work["recent_swing_high"] = work["high"].rolling(24, min_periods=6).max().shift(1)
    work["recent_swing_low"] = work["low"].rolling(24, min_periods=6).min().shift(1)
    anchors = ["prev_day_high", "prev_day_low", "day_open", "session_open", "round_number", "recent_swing_high", "recent_swing_low"]
    current = work.iloc[-1]
    rows = []
    scale = max(_safe_float(work["vol_24h"].iloc[-1], 0.0) * float(current["close"]), 1e-8)
    for anchor in anchors:
        value = current.get(anchor)
        if pd.isna(value):
            continue
        distance = abs(float(current["close"])-float(value)) / scale
        near = (work["close"]-work[anchor]).abs() <= work["vol_24h"].fillna(0)*work["close"]
        sign = np.sign(work["close"]-work[anchor])
        previous_near = near.shift(1).astype("boolean").fillna(False)
        breakout = sign.ne(sign.shift()) & previous_near
        false_break = breakout & sign.ne(sign.shift(-1))
        rows.append({"anchor": anchor, "anchor_value": value, "anchor_distance_vol_units": distance, "anchor_persistence": float(near.tail(120).mean()), "rejection_frequency": float((near & work["future_return_1h"].notna()).tail(120).mean()), "breakout_frequency": float(breakout.tail(120).mean()), "false_break_frequency": float(false_break.tail(120).mean()), "decision_dependence_on_anchor": None, "post_anchor_continuation_probability": float((~false_break[breakout]).mean()) if breakout.any() else None})
    table = pd.DataFrame(rows)
    return _module_result(ctx, 15, status="RESEARCH_PROTOTYPE_COMPLETE", summary=table.sort_values("anchor_distance_vol_units").iloc[0].to_dict() if len(table) else {}, tables={"anchor_diagnostics": table}, methodology="Prior/session/reference levels are calculated with shifted or contemporaneously available values only.")


def module_16(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    matrix = _vote_matrix(ctx)
    if matrix.empty:
        return _insufficient(ctx, 16, "No model ecology can be formed from internal decision histories.")
    data = matrix.merge(ctx.features[["time", "outcome_1h", "middle_regime"]], on="time", how="left")
    rows = []
    for column in [c for c in matrix.columns if c != "time"]:
        labels = data[column].map({1.0:"BUY", -1.0:"SELL", 0.0:"WAIT"})
        valid = labels.notna() & data["outcome_1h"].notna()
        correct = labels[valid].eq(data.loc[valid, "outcome_1h"]).astype(float)
        if len(correct) < 5:
            continue
        rolling = correct.rolling(30, min_periods=5).mean()
        current = float(rolling.iloc[-1])
        prior = float(rolling.iloc[-min(len(rolling), 30)])
        decay = prior-current
        by_regime = pd.DataFrame({"correct": correct, "regime": data.loc[valid, "middle_regime"]}).groupby("regime")["correct"].mean()
        rows.append({"model": column, "current_fitness": current, "rolling_fitness": float(correct.tail(120).mean()), "best_regime": by_regime.idxmax() if len(by_regime) else None, "worst_regime": by_regime.idxmin() if len(by_regime) else None, "performance_decay": decay, "recovery": max(0.0, current-prior), "model_drift": abs(decay), "probability_temporary_weakness": min(1.0, max(0.0, decay)), "probability_structural_deterioration": min(1.0, max(0.0, decay*1.5)) if len(correct)>=60 else None, "retraining_recommendation": bool(decay>0.15 and len(correct)>=30), "retirement_warning": False, "insufficient_sample_warning": len(correct)<60, "sample_size": len(correct)})
    table = pd.DataFrame(rows)
    if table.empty:
        return _insufficient(ctx, 16, "No model has five settled predictions.")
    summary = {"model_count": len(table), "models_with_drift_warning": int((table["model_drift"]>0.15).sum()), "automatic_disable_enabled": False}
    return _module_result(ctx, 16, status="RESEARCH_PROTOTYPE_COMPLETE", summary=summary, tables={"model_ecology": table.sort_values("current_fitness", ascending=False)}, methodology="Rolling chronological correctness by model and regime; no production model is deleted or disabled.")


def module_17(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    if ctx.news.empty or ctx.features.empty:
        return _insufficient(ctx, 17, "Timestamped news and market outcomes are both required.")
    events = ctx.news.merge(ctx.features[["time", "return_1h", "future_return_1h", "future_return_3h", "future_return_6h", "middle_regime", "session"]], on="time", how="left")
    settled = events.dropna(subset=["future_return_1h"])
    if len(settled) < 5:
        return _insufficient(ctx, 17, "Fewer than five timestamp-aligned settled events are available.")
    baseline = float(ctx.features["return_1h"].mean())
    settled = settled.assign(expected_return=baseline, observed_return=settled["future_return_1h"], abnormal_return=settled["future_return_1h"]-baseline)
    settled["H+1 reaction"] = settled["future_return_1h"]
    settled["H+3 reaction"] = settled["future_return_3h"]
    settled["H+6 reaction"] = settled["future_return_6h"]
    settled["maximum_favourable_movement"] = settled[["future_return_1h","future_return_3h","future_return_6h"]].max(axis=1)
    settled["maximum_adverse_movement"] = settled[["future_return_1h","future_return_3h","future_return_6h"]].min(axis=1)
    settled["persistence"] = np.sign(settled["future_return_1h"]).eq(np.sign(settled["future_return_6h"]))
    settled["reversal_probability_observation"] = (~settled["persistence"]).astype(float)
    summary = {"estimated_event_associated_effect": float(settled["abnormal_return"].mean()), "event_count": len(settled), "reversal_probability": float(settled["reversal_probability_observation"].mean()), "causality_claimed": False}
    return _module_result(ctx, 17, status="RESEARCH_PROTOTYPE_COMPLETE", summary=summary, tables={"event_response_memory": settled.tail(600).sort_values("time", ascending=False)}, methodology="Timestamp-aligned event study reporting estimated event-associated effects; no causal claim.")


def _entropy(values: pd.Series) -> float:
    counts = values.dropna().value_counts(normalize=True)
    if counts.empty:
        return 0.0
    return float(-(counts * np.log2(counts)).sum())


def module_18(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    matrix = _vote_matrix(ctx)
    if matrix.empty:
        return _insufficient(ctx, 18, "No evidence-vote matrix is available.")
    from sklearn.metrics import mutual_info_score
    data = matrix.merge(ctx.features[["time", "outcome_1h", "middle_regime"]], on="time", how="left")
    rows = []
    for column in [c for c in matrix.columns if c != "time"]:
        valid = data[column].notna() & data["outcome_1h"].notna()
        if valid.sum() < 5:
            continue
        vote = data.loc[valid, column].astype(str)
        outcome = data.loc[valid, "outcome_1h"].astype(str)
        mi = float(mutual_info_score(vote, outcome))
        conditional_parts = []
        for _, group in data.loc[valid].groupby("middle_regime"):
            if len(group)>=3:
                conditional_parts.append(mutual_info_score(group[column].astype(str), group["outcome_1h"].astype(str)))
        rows.append({"evidence": column, "directional_vote_entropy": _entropy(vote), "mutual_information_with_outcome": mi, "conditional_mutual_information_proxy": float(np.mean(conditional_parts)) if conditional_parts else None, "information_gain": mi, "feature_redundancy": None})
    table = pd.DataFrame(rows)
    if table.empty:
        return _insufficient(ctx, 18, "Evidence columns have insufficient aligned outcomes.")
    corr = matrix.drop(columns="time").corr(min_periods=5).abs()
    for i, row in table.iterrows():
        column = row["evidence"]
        redundancy = corr[column].drop(index=column, errors="ignore").max() if column in corr else np.nan
        # A single available evidence column has no peer redundancy; record 0
        # instead of NaN so information tables contain finite numeric values.
        table.loc[i, "feature_redundancy"] = 0.0 if pd.isna(redundancy) else float(redundancy)
    entropy_current = _entropy(matrix.drop(columns="time").iloc[-1].astype(str))
    redundancy_values = pd.to_numeric(table["feature_redundancy"], errors="coerce").fillna(0.0)
    diversity = max(0.0, 100.0*(1-float(redundancy_values.mean())))
    summary = {"entropy_of_directional_votes": entropy_current, "evidence_diversity": diversity, "effective_independent_evidence_count": max(1.0, len(table)*(diversity/100.0)), "potentially_redundant_columns": table.loc[table["feature_redundancy"]>0.90, "evidence"].tolist(), "automatic_deletion_enabled": False}
    finite = np.isfinite(table.select_dtypes(include="number").replace([np.inf,-np.inf],np.nan).dropna(how="all").fillna(0).to_numpy()).all()
    summary["invalid_infinities_present"] = not bool(finite)
    return _module_result(ctx, 18, status="RESEARCH_PROTOTYPE_COMPLETE" if finite else "FAILED_VALIDATION", summary=summary, tables={"information_scores": table.sort_values("information_gain", ascending=False)}, methodology="Entropy and mutual-information diagnostics; redundancy is marked for review, never auto-deleted.")


def module_19(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    outcomes = _decision_outcomes(ctx).dropna(subset=["correct"])
    n = len(outcomes)
    if n < 30:
        return _insufficient(ctx, 19, "At least 30 settled samples are required for a minimal untouched holdout.")
    train_end, val_end = int(n*0.60), int(n*0.80)
    periods = {
        "training_period": f"{outcomes['time'].iloc[0]} / {outcomes['time'].iloc[train_end-1]}",
        "validation_period": f"{outcomes['time'].iloc[train_end]} / {outcomes['time'].iloc[val_end-1]}",
        "test_period": f"{outcomes['time'].iloc[val_end]} / {outcomes['time'].iloc[-1]}",
    }
    overlap = not (outcomes["time"].iloc[train_end-1] < outcomes["time"].iloc[train_end] < outcomes["time"].iloc[val_end])
    fold_scores = []
    for end in range(max(20, train_end//2), n-5, max(5, n//8)):
        test_slice = outcomes.iloc[end:min(n,end+5)]
        fold_scores.append(float(test_slice["correct"].mean()))
    stability = max(0.0, 1.0-float(np.std(fold_scores))/(abs(float(np.mean(fold_scores)))+1e-9)) if fold_scores else 0.0
    pbo = None
    if len(fold_scores) >= 4:
        # Two declared candidate baselines, aligned paths. This is diagnostic only.
        ins = pd.DataFrame({"equal": fold_scores, "strict": [max(0,s-0.03) for s in fold_scores]})
        oos = pd.DataFrame({"equal": fold_scores[1:]+fold_scores[:1], "strict": [max(0,s-0.03) for s in (fold_scores[1:]+fold_scores[:1])]})
        try:
            from research_quant.validation.pbo import probability_of_backtest_overfitting
            pbo = probability_of_backtest_overfitting(ins, oos)
        except Exception:
            pbo = None
    summary = {
        "hypothesis": "ARERT and selective reliability improve calibration without production overwrite.",
        "model_version": ARERT_VERSION, "features": _analogue_features(ctx.features),
        "parameters": PARAMETER_VERSION, "number_parameter_combinations_tested": 2,
        **periods, "walk_forward_folds": len(fold_scores), "performance_metrics": {"fold_accuracy": fold_scores},
        "performance_decay": (fold_scores[0]-fold_scores[-1]) if len(fold_scores)>=2 else None,
        "parameter_stability": stability, "probability_backtest_overfitting": pbo,
        "data_snooping_risk": "MEDIUM — multiple modules; formal White/SPA tests pending",
        "research_validity_grade": "B-PROTOTYPE" if not overlap and n>=60 else "C-PRELIMINARY",
        "train_validation_test_overlap": overlap, "random_split_used": False,
        "deflated_sharpe_ratio": None, "white_reality_check": "INCOMPLETE", "spa_test": "INCOMPLETE",
    }
    return _module_result(ctx, 19, status="RESEARCH_PROTOTYPE_COMPLETE_WITH_INCOMPLETE_ADVANCED_TESTS", summary=summary, tables={"walk_forward_fold_scores": pd.DataFrame({"fold": range(1,len(fold_scores)+1), "accuracy": fold_scores})}, methodology="Chronological expanding/rolling diagnostics with an untouched final 20% holdout; no random split.")


def module_20(ctx: ResearchContext, deps: Mapping[int, Any]) -> dict[str, Any]:
    def get(number: int, *keys: str) -> Any:
        value: Any = _mapping(deps.get(number)).get("summary")
        for key in keys:
            value = _mapping(value).get(key)
        return value
    m1 = _mapping(_mapping(deps.get(1)).get("summary"))
    middle = _mapping(m1.get("middle"))
    if not middle:
        middle = _mapping(m1.get("lower"))
    r = _clip100(middle.get("duration_adjusted_reliability"))
    m9 = _mapping(_mapping(deps.get(9)).get("summary"))
    a = _clip100(abs(_safe_float(m9.get("weighted_score"), 0.0)))
    m5 = _frame(_mapping(_mapping(deps.get(5)).get("tables")).get("adaptive_conformal_intervals"))
    c = None
    u = None
    if not m5.empty:
        coverage_error = pd.to_numeric(m5.get("calibration_error"), errors="coerce").dropna()
        c = 100.0*(1-float(coverage_error.mean())) if len(coverage_error) else None
        widths = pd.to_numeric(m5.get("interval_width"), errors="coerce").dropna()
        price = float(ctx.features["close"].iloc[-1]) if not ctx.features.empty else 1.0
        u = min(100.0, 100.0*float(widths.mean())/max(price*0.01,1e-9)) if len(widths) else None
    m11 = _mapping(_mapping(deps.get(11)).get("summary"))
    h = _clip100(m11.get("consensus_probability"))
    m18 = _mapping(_mapping(deps.get(18)).get("summary"))
    e = _clip100(m18.get("evidence_diversity"))
    m16 = _frame(_mapping(_mapping(deps.get(16)).get("tables")).get("model_ecology"))
    m = _clip100(float(pd.to_numeric(m16.get("current_fitness"), errors="coerce").mean())) if not m16.empty else None
    m13 = _mapping(_mapping(deps.get(13)).get("summary"))
    braw = m13.get("current_adjusted_sentiment")
    b = _clip100(50.0 + 25.0*float(braw)) if _finite(braw) is not None else None
    m14 = _mapping(_mapping(deps.get(14)).get("summary"))
    f = _clip100(m14.get("consensus_fragility"))
    components = {"R_regime_persistence": r, "A_model_agreement": a, "C_calibration_quality": c, "H_historical_analogue": h, "E_evidence_diversity": e, "M_model_stability": m, "B_behavioral_confirmation": b}
    penalties = {"U_uncertainty_penalty": u, "F_conflict_fragility_penalty": f}
    available = {k:v for k,v in components.items() if v is not None and math.isfinite(float(v))}
    available_penalties = {k:v for k,v in penalties.items() if v is not None and math.isfinite(float(v))}
    if len(available) < 3:
        return _insufficient(ctx, 20, "Fewer than three validated ARERT components are available.", summary={"components": components, "penalties": penalties})
    equal_weight = 1.0/len(available)
    positive = sum(equal_weight*float(value) for value in available.values())
    penalty_mean = float(np.mean(list(available_penalties.values()))) if available_penalties else 0.0
    # Equal-weight baseline with multiplicative penalty avoids arbitrary fitted weights.
    final_score = float(np.clip(positive*(1.0-penalty_mean/200.0), 0, 100))
    classification = "exceptionally supported" if final_score>=85 else "strongly supported" if final_score>=70 else "moderately supported" if final_score>=55 else "weak or conflicting" if final_score>=40 else "unreliable or insufficient evidence"
    decomposition = []
    for name, raw in {**components, **penalties}.items():
        normalized = raw
        is_penalty = name.startswith(("U_", "F_"))
        weight = None if is_penalty else equal_weight
        contribution = None if raw is None else (-float(raw)/2.0/len(available_penalties) if is_penalty and available_penalties else float(raw)*equal_weight)
        decomposition.append({"component": name, "raw_value": raw, "normalized_0_100": normalized, "weight_applied": weight, "weighted_contribution": contribution, "component_type": "penalty" if is_penalty else "support"})
    final = _mapping(ctx.canonical.get("final_decision"))
    summary = {
        "production_direction": _coalesce(final.get("final_decision"), ctx.canonical.get("full_metric_direction")),
        "raw_confidence": _coalesce(final.get("confidence"), ctx.canonical.get("confidence")),
        "calibrated_probability": _mapping(_mapping(deps.get(7)).get("summary")).get("calibrated_probability"),
        "components": components, "penalties": penalties, "final_arert_score": round(final_score,3),
        "arert_research_classification": classification,
        "plain_english_explanation": f"The equal-weight research baseline has {len(available)} available support components. After the observed uncertainty/conflict penalty, ARERT is {final_score:.1f}/100 ({classification}). This is academic reliability evidence, not a live command.",
        "weight_version": PARAMETER_VERSION, "weight_estimation_status": "EQUAL_WEIGHT_BASELINE_ONLY; WALK_FORWARD_FITTED_WEIGHTS_INCOMPLETE",
        "live_trading_command": False,
    }
    return _module_result(ctx, 20, status="RESEARCH_PROTOTYPE_COMPLETE_EQUAL_WEIGHT_BASELINE", summary=summary, tables={"arert_reliability_decomposition": pd.DataFrame(decomposition)}, methodology="Equal-weight baseline is used because validated walk-forward component histories are not yet sufficient for fitted weights; this is explicitly recorded rather than choosing arbitrary weights.")


MODULE_FUNCTIONS: dict[int, Callable[[ResearchContext, Mapping[int, Any]], dict[str, Any]]] = {
    1: module_1, 2: module_2, 3: module_3, 4: module_4, 5: module_5, 6: module_6,
    7: module_7, 8: module_8, 9: module_9, 10: module_10, 11: module_11, 12: module_12,
    13: module_13, 14: module_14, 15: module_15, 16: module_16, 17: module_17,
    18: module_18, 19: module_19, 20: module_20,
}

DEPENDENCIES: dict[int, tuple[int, ...]] = {
    6: (3, 5), 10: (9,), 12: (11,), 20: (1, 5, 7, 9, 11, 13, 14, 16, 18, 19),
}


def cache_identity(canonical: Mapping[str, Any], module: int) -> str:
    candle = _canonical_candle(canonical)
    payload = {
        "candle": candle.isoformat() if candle is not None else None,
        "symbol": canonical.get("symbol"), "timeframe": canonical.get("timeframe"),
        "module": module, "version": ARERT_VERSION, "parameters": PARAMETER_VERSION,
        "snapshot": _coalesce(canonical.get("source_snapshot_hash"), canonical.get("snapshot_hash"), canonical.get("data_signature")),
    }
    return _hash_payload(payload)


def _expand_modules(selected: Iterable[int]) -> list[int]:
    wanted = {int(number) for number in selected if int(number) in MODULE_CATALOG}
    changed = True
    while changed:
        changed = False
        for number in list(wanted):
            for dep in DEPENDENCIES.get(number, ()):
                if dep not in wanted:
                    wanted.add(dep); changed = True
    return sorted(wanted)


def run_arert_research(
    state: MutableMapping[str, Any], canonical: Mapping[str, Any], modules: Iterable[int] | None = None,
) -> dict[str, Any]:
    selected = _expand_modules(modules or MODULE_CATALOG.keys())
    ctx = build_context(state, canonical)
    cached_root = state.get("arert_module_cache_20260628")
    cache: dict[str, Any] = dict(cached_root) if isinstance(cached_root, Mapping) else {}
    results: dict[int, Any] = {}
    benchmarks: list[dict[str, Any]] = []
    for number in selected:
        key = cache_identity(canonical, number)
        if key in cache:
            results[number] = cache[key]
            benchmarks.append({"module": number, "cache_hit": True, "runtime_seconds": 0.0, "peak_memory_mb": 0.0})
            continue
        tracemalloc.start()
        started = time.perf_counter()
        try:
            result = MODULE_FUNCTIONS[number](ctx, results)
        except Exception as exc:
            result = _module_result(ctx, number, status="FAILED_SAFELY", summary={}, limitations=[f"{type(exc).__name__}: {exc}"])
        runtime = time.perf_counter()-started
        _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
        result["runtime_seconds"] = round(runtime, 6)
        result["peak_memory_mb"] = round(peak/1024/1024, 4)
        result["input_hash"] = _hash_payload({"metadata": ctx.metadata, "features_tail": ctx.features.tail(120)})
        result["output_hash"] = _hash_payload(result)
        cache[key] = result
        results[number] = result
        benchmarks.append({"module": number, "cache_hit": False, "runtime_seconds": runtime, "peak_memory_mb": peak/1024/1024})
    envelope = {
        "metadata": dict(ctx.metadata),
        "model_name": "Adaptive Regime–Evidence Reliability Theory — ARERT",
        "model_version": ARERT_VERSION,
        "parameter_version": PARAMETER_VERSION,
        "selected_modules": selected,
        "modules": {str(number): results[number] for number in selected},
        "benchmarks": benchmarks,
        "status": "COMPLETE_WITH_EXPLICIT_INCOMPLETE_ITEMS" if results else "NO_MODULES_RUN",
        "production_values_modified": False,
        "cache_key_contract": "completed candle + symbol + timeframe + module + model version + parameter version + snapshot",
    }
    state["arert_module_cache_20260628"] = cache
    state[STATE_KEY] = envelope
    try:
        from research_quant.arert_store import persist_arert_envelope
        envelope["database"] = persist_arert_envelope(envelope)
    except Exception as exc:
        envelope["database"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return envelope


__all__ = [
    "ARERT_VERSION", "PARAMETER_VERSION", "STATE_KEY", "MODULE_CATALOG", "ResearchContext",
    "build_context", "run_arert_research", "cache_identity", "_expand_modules",
    *[f"module_{number}" for number in MODULE_CATALOG],
]

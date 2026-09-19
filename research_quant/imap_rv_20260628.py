"""Information Mining, Attention, Path-Memory and Research Validity (IMAP-RV).

Separate thesis-research prototype.  It reads one frozen completed-candle
canonical snapshot, preserves production direction, and never writes into Lunch
production calculations.  Methods are labelled as prototypes/approximations
unless a complete implementation is explicitly documented.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import sqlite3
import time
from typing import Any, Mapping, MutableMapping

import numpy as np
import pandas as pd

from research_quant.arert_lab import build_context, _decision_label

VERSION = "IMAP-RV-0.1.0-RESEARCH-PROTOTYPE"
STATE_KEY = "imap_rv_research_20260628"
CACHE_KEY = "imap_rv_cache_20260628"
DB_PATH = Path("data/imap_rv_research.sqlite3")
PROTECTIVE_ACTIONS = {"ALLOWED", "WAIT FOR PULLBACK", "HOLD AND PROTECT", "NO TRADE"}
COMPONENT_NAMES = (
    "Information Value", "Path-Memory Quality", "Signal Validity", "Evidence Diversity",
    "Calibration Quality", "Crowding Fragility", "Attention Instability", "Multiple-Testing Risk",
)


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().upper() in {"", "NA", "N/A", "NONE", "NAN", "UNAVAILABLE", "—", "-"}
    try:
        flag = pd.isna(value)
        return bool(flag) if isinstance(flag, (bool, np.bool_)) else False
    except Exception:
        return False


def _first(*values: Any, default: Any = None) -> Any:
    for value in values:
        if not _missing(value):
            return value
    return default


def _finite(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except Exception:
        return default
    return number if math.isfinite(number) else default


def _clip100(value: Any, default: float | None = None) -> float | None:
    number = _finite(value, default)
    if number is None:
        return None
    return round(float(np.clip(number, 0.0, 100.0)), 4)


def _jsonable(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return value.to_dict("records")
    if isinstance(value, pd.Series):
        return value.tolist()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value


def _signature(canonical: Mapping[str, Any]) -> str:
    values = [
        canonical.get("run_id"), canonical.get("canonical_calculation_id"),
        canonical.get("generation_id"), canonical.get("calculation_generation"),
        canonical.get("completed_broker_candle"), canonical.get("latest_completed_candle_time"),
        canonical.get("source_snapshot_hash"), VERSION,
    ]
    return sha256("|".join(str(value or "") for value in values).encode("utf-8", "ignore")).hexdigest()


def _metadata(canonical: Mapping[str, Any], context: Any) -> dict[str, Any]:
    base = dict(context.metadata)
    base.update({
        "framework": "Information Mining, Attention, Path-Memory and Research Validity — IMAP-RV",
        "model_version": VERSION,
        "run_id": str(_first(canonical.get("run_id"), canonical.get("canonical_calculation_id"), default="UNAVAILABLE")),
        "generation_id": str(_first(canonical.get("generation_id"), canonical.get("calculation_generation"), default="UNAVAILABLE")),
        "symbol": str(_first(canonical.get("symbol"), default="EURUSD")),
        "timeframe": str(_first(canonical.get("timeframe"), default="H1")),
        "completed_broker_candle": str(_first(canonical.get("completed_broker_candle"), canonical.get("latest_completed_candle_time"), default="UNAVAILABLE")),
        "calculation_timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
        "implementation_status": "RESEARCH PROTOTYPE / APPROXIMATION",
        "production_values_modified": False,
    })
    return base


def _token_set(text: Any) -> set[str]:
    import re
    return {token for token in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(token) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a or b else 0.0


def _news_information_value(context: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
    news = context.news.copy(deep=False)
    if news.empty:
        return pd.DataFrame(columns=[
            "publication timestamp", "first-seen timestamp", "completed broker candle", "EUR relevance",
            "USD relevance", "EURUSD relevance", "novelty", "duplicate probability", "source diversity",
            "semantic similarity to earlier news", "information surprise", "price absorption",
            "residual information value", "information age", "absorption state", "data-quality status",
        ]), {"score": None, "status": "INSUFFICIENT EVIDENCE", "limitation": "No timestamped news was available."}
    market = context.market.set_index("time").sort_index()
    returns = market["close"].pct_change() if not market.empty else pd.Series(dtype=float)
    title_col = next((column for column in news.columns if str(column).lower() in {"title", "headline", "text", "summary"}), None)
    sentiment_col = next((column for column in news.columns if "sentiment" in str(column).lower()), None)
    impact_col = next((column for column in news.columns if "impact" in str(column).lower() or "importance" in str(column).lower()), None)
    source_col = next((column for column in news.columns if "source" in str(column).lower() or "provider" in str(column).lower()), None)
    titles = news[title_col].astype(str) if title_col else pd.Series("", index=news.index)
    token_history: list[set[str]] = []
    similarities: list[float] = []
    novelty: list[float] = []
    for title in titles:
        tokens = _token_set(title)
        similarity = max((_jaccard(tokens, previous) for previous in token_history[-100:]), default=0.0)
        similarities.append(similarity)
        novelty.append(1.0 - similarity)
        token_history.append(tokens)
    lower = titles.str.lower()
    eur = lower.str.contains(r"\beur\b|euro|ecb|eurozone|lagarde", regex=True).astype(float)
    usd = lower.str.contains(r"\busd\b|dollar|fed|fomc|powell|cpi|pce|nfp|treasury", regex=True).astype(float)
    relevance = (0.45 * eur + 0.45 * usd + 0.10 * (eur * usd)).clip(0, 1)
    sentiment = pd.to_numeric(news[sentiment_col], errors="coerce").abs().clip(0, 1) if sentiment_col else pd.Series(0.35, index=news.index)
    impact = pd.to_numeric(news[impact_col], errors="coerce") if impact_col else pd.Series(np.nan, index=news.index)
    if impact.notna().any():
        impact = impact.clip(0, 100) / 100.0 if impact.max(skipna=True) > 1 else impact.clip(0, 1)
    else:
        impact = pd.Series(0.35, index=news.index)
    surprise = (0.55 * sentiment.fillna(0.35) + 0.45 * impact.fillna(0.35)).clip(0, 1)
    event_returns = []
    for timestamp in news["time"]:
        if market.empty:
            event_returns.append(np.nan)
            continue
        aligned = returns.loc[returns.index <= timestamp]
        event_returns.append(abs(float(aligned.iloc[-1])) if len(aligned) and pd.notna(aligned.iloc[-1]) else np.nan)
    event_returns = pd.Series(event_returns, index=news.index)
    return_scale = returns.abs().rolling(120, min_periods=24).quantile(0.9).median() if len(returns) else np.nan
    return_scale = float(return_scale) if pd.notna(return_scale) and return_scale > 0 else 0.001
    absorption = (event_returns / return_scale).clip(0, 1).fillna(0.5)
    non_absorption = 1.0 - absorption
    duplicate_probability = pd.Series(similarities, index=news.index).clip(0, 1)
    novelty_s = pd.Series(novelty, index=news.index).clip(0, 1)
    if source_col:
        source_diversity = news[source_col].astype(str).expanding().apply(lambda values: min(1.0, len(set(values)) / max(1.0, math.sqrt(len(values)))), raw=False)
    else:
        source_diversity = pd.Series(0.5, index=news.index)
    data_quality = pd.Series(np.where(news["time"].notna() & titles.ne(""), 1.0, 0.0), index=news.index)
    information_cost_penalty = (1.0 + duplicate_probability).clip(lower=1.0)
    residual = (novelty_s * relevance * surprise * non_absorption * data_quality / information_cost_penalty).clip(0, 1)
    latest = context.market["time"].max() if not context.market.empty else news["time"].max()
    age_hours = (latest - news["time"]).dt.total_seconds().div(3600).clip(lower=0) if latest is not None else pd.Series(np.nan, index=news.index)
    state = np.select(
        [residual >= 0.55, residual >= 0.30, residual >= 0.12, data_quality <= 0],
        ["NEW INFORMATION", "PARTIALLY ABSORBED", "MOSTLY ABSORBED", "INSUFFICIENT EVIDENCE"],
        default="FULLY ABSORBED",
    )
    table = pd.DataFrame({
        "publication timestamp": news["time"], "first-seen timestamp": news["time"],
        "completed broker candle": news["time"].dt.floor("h"), "EUR relevance": (eur * 100).round(2),
        "USD relevance": (usd * 100).round(2), "EURUSD relevance": (relevance * 100).round(2),
        "novelty": (novelty_s * 100).round(2), "duplicate probability": (duplicate_probability * 100).round(2),
        "source diversity": (source_diversity * 100).round(2),
        "semantic similarity to earlier news": (duplicate_probability * 100).round(2),
        "information surprise": (surprise * 100).round(2), "price absorption": (absorption * 100).round(2),
        "residual information value": (residual * 100).round(2), "information age": age_hours.round(2),
        "absorption state": state, "data-quality status": np.where(data_quality > 0, "VALID", "INSUFFICIENT EVIDENCE"),
    }).sort_values("publication timestamp", ascending=False)
    score = float(table["residual information value"].head(20).mean()) if len(table) else None
    return table.reset_index(drop=True), {"score": _clip100(score), "status": "PROTOTYPE", "limitation": "Price absorption uses information available at or before publication; it does not claim causal profit."}


def _path_memory(context: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
    market = context.market.copy(deep=False)
    if market.empty or len(market) < 24:
        return pd.DataFrame(), {"score": None, "status": "INSUFFICIENT EVIDENCE", "limitation": "At least 24 completed H1 candles are required."}
    returns = market["close"].pct_change().fillna(0.0)
    short_return = returns.ewm(span=6, adjust=False).mean()
    long_return = returns.ewm(span=48, adjust=False).mean()
    short_sq = returns.pow(2).ewm(span=6, adjust=False).mean()
    long_sq = returns.pow(2).ewm(span=48, adjust=False).mean()
    path_vol = np.sqrt((0.65 * short_sq + 0.35 * long_sq).clip(lower=0))
    acceleration = path_vol.diff()
    agreement = (1.0 - ((short_return - long_return).abs() / (path_vol + 1e-12)).clip(0, 1)) * 100
    table = pd.DataFrame({
        "completed broker candle": market["time"], "short trend memory": short_return,
        "long trend memory": long_return, "short activity memory": short_sq,
        "long activity memory": long_sq, "path-dependent volatility": path_vol,
        "volatility acceleration": acceleration, "volatility-memory agreement": agreement,
        "expected H+1 range": market["close"] * path_vol,
        "expected H+3 range": market["close"] * path_vol * math.sqrt(3),
        "expected H+6 range": market["close"] * path_vol * math.sqrt(6),
    }).sort_values("completed broker candle", ascending=False)
    latest_agreement = float(agreement.iloc[-1]) if pd.notna(agreement.iloc[-1]) else 0.0
    stability = float((1.0 - min(1.0, abs(acceleration.iloc[-1]) / max(float(path_vol.iloc[-1]), 1e-12))) * 100.0)
    score = 0.6 * latest_agreement + 0.4 * stability
    return table.reset_index(drop=True), {"score": _clip100(score), "status": "RECURSIVE EMA PROTOTYPE", "limitation": "EURUSD parameters require walk-forward validation; equity-index parameters were not transferred."}


def _numeric_evidence(context: Any) -> pd.DataFrame:
    features = context.features.copy(deep=False)
    if features.empty:
        return pd.DataFrame()
    numeric = features.select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan)
    numeric = numeric.loc[:, numeric.notna().sum() >= max(12, int(len(numeric) * 0.15))]
    # Constant columns cannot carry information and make correlation routines emit
    # divide-by-zero warnings. Pruning them is research-display preparation only;
    # the protected production frames are never modified.
    non_constant = numeric.nunique(dropna=True) >= 2
    numeric = numeric.loc[:, non_constant]
    return numeric.tail(600)


def _clean_covariance(numeric: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if numeric.empty or numeric.shape[1] < 2:
        return pd.DataFrame(), pd.DataFrame(), {"score": None, "status": "INSUFFICIENT EVIDENCE", "limitation": "At least two numeric evidence families are required."}
    standardized = (numeric - numeric.mean()) / numeric.std(ddof=0).replace(0, np.nan)
    standardized = standardized.dropna(axis=1, how="all").fillna(0.0)
    raw = standardized.corr().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    cov = np.cov(standardized.to_numpy(dtype=float), rowvar=False)
    diagonal = np.diag(np.diag(cov))
    shrinkage = 0.25
    cleaned = (1.0 - shrinkage) * cov + shrinkage * diagonal
    eigval, eigvec = np.linalg.eigh(cleaned)
    eigval = np.clip(eigval, 1e-9, None)
    cleaned = eigvec @ np.diag(eigval) @ eigvec.T
    std = np.sqrt(np.diag(cleaned))
    corr = cleaned / np.outer(std, std)
    clean_frame = pd.DataFrame(corr, index=standardized.columns, columns=standardized.columns)
    redundancy = raw.abs().where(~np.eye(len(raw), dtype=bool)).mean(axis=1).fillna(0.0)
    diversity = float((1.0 - redundancy.mean()) * 100.0)
    feature_table = pd.DataFrame({
        "feature": raw.columns, "redundancy score": (redundancy.values * 100).round(2),
        "marginal information": ((1.0 - redundancy.values) * 100).round(2),
        "potentially redundant flag": np.where(redundancy.values >= 0.75, "YES", "NO"),
    }).sort_values("marginal information", ascending=False)
    return raw, clean_frame, {"score": _clip100(diversity), "status": "SHRINKAGE + PSD REPAIR PROTOTYPE", "feature_table": feature_table, "limitation": "No production column is deleted from redundancy flags."}


def _crowding(numeric: pd.DataFrame, cleaned_corr: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if numeric.empty or numeric.shape[1] < 2:
        return pd.DataFrame(), {"score": None, "status": "INSUFFICIENT EVIDENCE", "limitation": "Insufficient independent evidence columns."}
    corr = cleaned_corr if not cleaned_corr.empty else numeric.corr()
    common = [column for column in corr.columns if column in numeric.columns]
    if len(common) < 2:
        return pd.DataFrame(), {"score": None, "status": "INSUFFICIENT EVIDENCE", "limitation": "Fewer than two aligned evidence columns."}
    corr = corr.loc[common, common]
    numeric = numeric.loc[:, common]
    off_diag = corr.abs().where(~np.eye(len(corr), dtype=bool))
    redundancy = off_diag.mean(axis=1).fillna(0.0)
    latest = numeric.ffill().iloc[-1]
    standardized_latest = ((latest - numeric.mean()) / numeric.std(ddof=0).replace(0, np.nan)).fillna(0.0).clip(-3, 3)
    raw_confidence = standardized_latest.abs().clip(0, 3) / 3.0
    residual_confidence = raw_confidence * (1.0 - redundancy)
    table = pd.DataFrame({
        "source model": numeric.columns, "raw confidence": (raw_confidence.values * 100).round(2),
        "pairwise residual correlation": (redundancy.values * 100).round(2),
        "evidence redundancy": (redundancy.values * 100).round(2),
        "independent contribution": (residual_confidence.values * 100).round(2),
    }).sort_values("independent contribution", ascending=False)
    crowding = float(redundancy.mean() * 100.0)
    independent_count = float(np.sum(redundancy < 0.5))
    fragility = np.clip(0.7 * crowding + 0.3 * (100.0 / max(1.0, independent_count)), 0, 100)
    return table, {"score": _clip100(100.0 - fragility), "raw_crowding": round(crowding, 3), "independent_evidence_count": int(independent_count), "status": "INTERNAL AGENT CROWDING PROTOTYPE", "limitation": "Crowding is a warning/penalty and never replaces production direction."}


def _effective_sample_size(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    n = len(values)
    if n < 3:
        return float(n)
    rho = float(values.autocorr(lag=1)) if pd.notna(values.autocorr(lag=1)) else 0.0
    rho = float(np.clip(rho, -0.99, 0.99))
    return float(np.clip(n * (1 - rho) / (1 + rho), 1, n))


def _bh_adjust(p_values: list[float]) -> list[float]:
    if not p_values:
        return []
    arr = np.asarray(p_values, dtype=float)
    order = np.argsort(arr)
    adjusted = np.empty_like(arr)
    running = 1.0
    m = len(arr)
    for rank_index in range(m - 1, -1, -1):
        index = order[rank_index]
        rank = rank_index + 1
        running = min(running, arr[index] * m / rank)
        adjusted[index] = running
    return adjusted.clip(0, 1).tolist()


def _normal_p_value_from_t(t_value: float) -> float:
    # Normal approximation avoids a hard scipy dependency.
    return float(math.erfc(abs(t_value) / math.sqrt(2.0)))


def _signal_validity(context: Any, numeric: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if numeric.empty or context.market.empty:
        return pd.DataFrame(), {"score": None, "status": "INSUFFICIENT EVIDENCE", "limitation": "Numeric features and completed market outcomes are required."}
    market = context.market.set_index("time").sort_index()
    close = market["close"]
    features = context.features.set_index("time").reindex(market.index)
    candidate_columns = [column for column in numeric.columns if column in features.columns][:24]
    rows: list[dict[str, Any]] = []
    p_values: list[float] = []
    for column in candidate_columns:
        feature = pd.to_numeric(features[column], errors="coerce")
        for horizon in (1, 3, 6):
            future = close.shift(-horizon) / close - 1.0
            pair = pd.concat([feature, future], axis=1).dropna()
            if len(pair) < 24 or pair.iloc[:, 0].nunique(dropna=True) < 2 or pair.iloc[:, 1].nunique(dropna=True) < 2:
                continue
            pearson = pair.iloc[:, 0].corr(pair.iloc[:, 1], method="pearson")
            spearman = pair.iloc[:, 0].corr(pair.iloc[:, 1], method="spearman")
            ess = _effective_sample_size(pair.iloc[:, 0])
            if pd.isna(pearson) or ess <= 3 or abs(float(pearson)) >= 1:
                t_stat = 0.0
            else:
                t_stat = float(pearson) * math.sqrt(max(1.0, (ess - 2) / max(1e-12, 1 - float(pearson) ** 2)))
            p_value = _normal_p_value_from_t(t_stat)
            p_values.append(p_value)
            rows.append({
                "feature": column, "horizon": f"H+{horizon}", "Pearson IC": pearson,
                "Spearman IC": spearman, "IC t-statistic": t_stat, "raw p-value": p_value,
                "effective sample size": ess, "raw row count": len(pair),
            })
    adjusted = _bh_adjust(p_values)
    for row, adjusted_p in zip(rows, adjusted):
        row["adjusted p-value"] = adjusted_p
        row["research validity grade"] = "SUPPORTED" if adjusted_p <= 0.05 else ("WEAK" if adjusted_p <= 0.20 else "NOT SUPPORTED")
    table = pd.DataFrame(rows)
    if table.empty:
        return table, {"score": None, "status": "INSUFFICIENT EVIDENCE", "limitation": "No feature had at least 24 matured observations."}
    supported = float((table["adjusted p-value"] <= 0.05).mean())
    mean_ic = float(table["Pearson IC"].abs().fillna(0).mean())
    score = np.clip(60 * supported + 40 * min(1.0, mean_ic / 0.10), 0, 100)
    multiple_risk = float(np.clip(100.0 * (1.0 - supported) * min(1.0, len(table) / 50.0), 0, 100))
    return table.sort_values(["adjusted p-value", "feature"]), {
        "score": _clip100(score), "multiple_testing_risk": _clip100(multiple_risk),
        "number_of_hypotheses": int(len(table)), "status": "TIME-SERIES IC + FDR PROTOTYPE",
        "limitation": "Normal/HAC-style approximation; a full thesis run should add block-bootstrap sensitivity analysis.",
    }


def _beta_fragility(context: Any, numeric: pd.DataFrame, crowding_meta: Mapping[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    beta_columns = [column for column in numeric.columns if "beta" in str(column).lower()]
    if not beta_columns:
        return pd.DataFrame([{
            "dependency": "External dependencies", "status": "UNAVAILABLE",
            "reason": "No existing Beta history or valid DXY/yield dependency inputs were published.",
        }]), {"score": None, "status": "UNAVAILABLE-DATA LIMITATION", "limitation": "The existing Beta meaning is preserved; unavailable dependencies are not invented."}
    beta = pd.to_numeric(numeric[beta_columns[0]], errors="coerce")
    instability = beta.rolling(24, min_periods=8).std()
    concentration = min(1.0, 1.0 / max(1, len(beta_columns)))
    crowding = float(crowding_meta.get("raw_crowding") or 0.0) / 100.0
    fragility = beta.abs() * instability * concentration * (1.0 + crowding)
    latest = float(fragility.dropna().iloc[-1]) if fragility.notna().any() else np.nan
    normalized = 100.0 * latest / (1.0 + latest) if math.isfinite(latest) else None
    table = pd.DataFrame({
        "completed broker candle": context.features["time"].tail(len(beta)).to_numpy(),
        "existing Beta": beta.to_numpy(), "Beta instability": instability.to_numpy(),
        "dependency concentration": concentration, "crowding adjustment": 1.0 + crowding,
        "Beta Fragility": fragility.to_numpy(),
    }).sort_values("completed broker candle", ascending=False)
    return table, {"score": _clip100(100.0 - normalized) if normalized is not None else None, "raw_fragility": _clip100(normalized), "status": "BETA FRAGILITY PROTOTYPE", "limitation": "External DXY/yield sensitivities are included only when genuinely available."}


def _attention_hype(info_table: pd.DataFrame, context: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
    if info_table.empty:
        return pd.DataFrame(), {"score": None, "status": "INSUFFICIENT EVIDENCE", "limitation": "No news attention history."}
    work = info_table.copy()
    work["broker day"] = pd.to_datetime(work["publication timestamp"], utc=True).dt.floor("D")
    daily = work.groupby("broker day").agg(
        article_count=("publication timestamp", "count"),
        novelty=("novelty", "mean"), duplication_rate=("duplicate probability", "mean"),
        information_value=("residual information value", "mean"),
    ).reset_index()
    mean = daily["article_count"].rolling(20, min_periods=3).mean()
    std = daily["article_count"].rolling(20, min_periods=3).std().replace(0, np.nan)
    daily["article-count z-score"] = (daily["article_count"] - mean) / std
    daily["attention acceleration"] = daily["article_count"].diff()
    daily["hype index"] = (
        daily["article-count z-score"].clip(lower=0).fillna(0) * 20
        + daily["duplication_rate"].fillna(0) * 0.45
        + (100 - daily["novelty"].fillna(0)) * 0.25
    ).clip(0, 100)
    daily["abnormal-attention status"] = np.select(
        [daily["hype index"] >= 70, daily["hype index"] >= 45], ["HIGH", "WATCH"], default="NORMAL"
    )
    latest_hype = float(daily["hype index"].iloc[-1]) if len(daily) else 0.0
    return daily.sort_values("broker day", ascending=False), {"score": _clip100(100.0 - latest_hype), "raw_hype": _clip100(latest_hype), "status": "ATTENTION/HYPE PROTOTYPE", "limitation": "Attention is separated from sentiment; no bubble claim is made."}


def _diversity_consensus(numeric: pd.DataFrame, feature_table: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if numeric.empty:
        return pd.DataFrame(), {"score": None, "status": "INSUFFICIENT EVIDENCE", "limitation": "No numeric evidence."}
    latest = numeric.ffill().iloc[-1]
    centered = ((latest - numeric.mean()) / numeric.std(ddof=0).replace(0, np.nan)).fillna(0).clip(-3, 3)
    confidence = centered.abs() / 3.0
    redundancy_map = {}
    if isinstance(feature_table, pd.DataFrame) and not feature_table.empty:
        redundancy_map = dict(zip(feature_table["feature"].astype(str), pd.to_numeric(feature_table["redundancy score"], errors="coerce").fillna(50) / 100.0))
    penalty = pd.Series({column: float(redundancy_map.get(str(column), 0.5)) for column in numeric.columns})
    raw_weight = confidence / max(float(confidence.sum()), 1e-12)
    diversity_weight = confidence * (1.0 - penalty)
    diversity_weight = diversity_weight / max(float(diversity_weight.sum()), 1e-12)
    contribution = centered * diversity_weight
    table = pd.DataFrame({
        "source model": numeric.columns, "raw confidence": (confidence.values * 100).round(2),
        "dependence penalty": (penalty.values * 100).round(2), "raw weight": raw_weight.values,
        "diversity-adjusted weight": diversity_weight.values, "final research contribution": contribution.values,
    }).sort_values("diversity-adjusted weight", ascending=False)
    score = float((1.0 - penalty.mul(diversity_weight).sum()) * 100.0)
    return table, {"score": _clip100(score), "status": "DIVERSITY-WEIGHTED CONSENSUS PROTOTYPE", "weights_sum": float(diversity_weight.sum()), "limitation": "The bounded q parameter remains at the equal-power baseline pending walk-forward validation."}


def _calibration_quality(state: Mapping[str, Any]) -> dict[str, Any]:
    candidates = []
    for key, value in state.items():
        name = str(key).lower()
        if any(token in name for token in ("calibration", "coverage", "brier", "prediction_error", "forecast_error")):
            if isinstance(value, Mapping):
                candidates.extend(_finite(item) for item in value.values())
            else:
                candidates.append(_finite(value))
    finite = [value for value in candidates if value is not None]
    if not finite:
        return {"score": None, "status": "UNAVAILABLE-DATA LIMITATION", "limitation": "No persisted calibration metric was published."}
    # Convert arbitrary percent-like metrics conservatively to a bounded quality.
    normalized = [value * 100 if 0 <= value <= 1 else value for value in finite]
    score = float(np.clip(np.nanmedian(normalized), 0, 100))
    return {"score": _clip100(score), "status": "PUBLISHED CALIBRATION EVIDENCE", "limitation": "Mixed source metrics are displayed with provenance; they are not silently pooled into production."}


def _protective_action(score: float | None, info: Mapping[str, Any], path: Mapping[str, Any], crowding: Mapping[str, Any], validity: Mapping[str, Any], attention: Mapping[str, Any], context: Any) -> tuple[str, str]:
    production = "WAIT"
    try:
        decisions = context.decisions
        if not decisions.empty:
            column = next((c for c in decisions.columns if any(token in str(c).lower() for token in ("master", "decision", "direction"))), None)
            if column:
                production = _decision_label(decisions[column].iloc[-1]) or "WAIT"
    except Exception:
        pass
    crowd = float(crowding.get("raw_crowding") or 100.0)
    hype = float(attention.get("raw_hype") or 0.0)
    validity_score = _finite(validity.get("score"), 0.0) or 0.0
    path_score = _finite(path.get("score"), 0.0) or 0.0
    info_score = _finite(info.get("score"), 0.0) or 0.0
    if score is None or validity_score < 25:
        return "NO TRADE", "Adjusted signal validity or data quality is insufficient."
    if score >= 72 and crowd <= 45 and hype <= 60 and production in {"BUY", "SELL"}:
        return "ALLOWED", "Statistical support, path memory and independent evidence pass the research gates."
    if production in {"BUY", "SELL"} and (crowd >= 55 or hype >= 65 or info_score < 30):
        return "WAIT FOR PULLBACK", "Direction remains published, but crowding, attention or information absorption raises late-entry risk."
    if production in {"BUY", "SELL"} and path_score >= 40:
        return "HOLD AND PROTECT", "Existing direction remains partly supported, but adding exposure is not justified."
    return "NO TRADE", "Evidence is conflicted, redundant, uncalibrated or incomplete."


def _persist(envelope: Mapping[str, Any], path: Path = DB_PATH) -> dict[str, Any]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS imap_rv_runs (
                    signature TEXT PRIMARY KEY, run_id TEXT, generation_id TEXT,
                    completed_broker_candle TEXT, model_version TEXT,
                    score REAL, protective_action TEXT, payload_json TEXT,
                    created_at TEXT
                )
            """)
            metadata = envelope.get("metadata") if isinstance(envelope.get("metadata"), Mapping) else {}
            connection.execute(
                "INSERT OR REPLACE INTO imap_rv_runs VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    str(envelope.get("signature")), str(metadata.get("run_id")), str(metadata.get("generation_id")),
                    str(metadata.get("completed_broker_candle")), VERSION,
                    _finite(envelope.get("imap_rv_score")), str(envelope.get("protective_action")),
                    json.dumps(_jsonable(envelope), default=str, separators=(",", ":")),
                    pd.Timestamp.now(tz="UTC").isoformat(),
                ),
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_imap_candle ON imap_rv_runs(completed_broker_candle)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_imap_run ON imap_rv_runs(run_id, generation_id)")
            connection.commit()
        return {"ok": True, "path": str(path)}
    except Exception as exc:
        return {"ok": False, "path": str(path), "error": f"{type(exc).__name__}: {exc}"}


def run_imap_rv(state: MutableMapping[str, Any], canonical: Mapping[str, Any], *, force: bool = False) -> dict[str, Any]:
    signature = _signature(canonical)
    cached = state.get(CACHE_KEY)
    if not force and isinstance(cached, Mapping) and cached.get("signature") == signature and isinstance(cached.get("envelope"), Mapping):
        envelope = dict(cached["envelope"])
        envelope["cache_status"] = "REUSED_SAME_COMPLETED_CANDLE"
        state[STATE_KEY] = envelope
        return envelope

    started = time.perf_counter()
    context = build_context(state, canonical)
    metadata = _metadata(canonical, context)
    numeric = _numeric_evidence(context)
    information_table, information_meta = _news_information_value(context)
    path_table, path_meta = _path_memory(context)
    raw_corr, clean_corr, covariance_meta = _clean_covariance(numeric)
    crowding_table, crowding_meta = _crowding(numeric, clean_corr)
    validity_table, validity_meta = _signal_validity(context, numeric)
    beta_table, beta_meta = _beta_fragility(context, numeric, crowding_meta)
    attention_table, attention_meta = _attention_hype(information_table, context)
    feature_table = covariance_meta.get("feature_table") if isinstance(covariance_meta.get("feature_table"), pd.DataFrame) else pd.DataFrame()
    consensus_table, consensus_meta = _diversity_consensus(numeric, feature_table)
    calibration_meta = _calibration_quality(state)

    component_raw = {
        "Information Value": information_meta.get("score"),
        "Path-Memory Quality": path_meta.get("score"),
        "Signal Validity": validity_meta.get("score"),
        "Evidence Diversity": covariance_meta.get("score"),
        "Calibration Quality": calibration_meta.get("score"),
        "Crowding Fragility": crowding_meta.get("score"),  # already inverted to quality
        "Attention Instability": attention_meta.get("score"),  # already inverted to quality
        "Multiple-Testing Risk": 100.0 - float(validity_meta.get("multiple_testing_risk") or 100.0),
    }
    available = {key: _clip100(value) for key, value in component_raw.items() if _clip100(value) is not None}
    equal_weight = 1.0 / len(available) if available else 0.0
    rows = []
    for component in COMPONENT_NAMES:
        value = _clip100(component_raw.get(component))
        weight = equal_weight if value is not None else 0.0
        rows.append({
            "component": component, "raw value": component_raw.get(component), "normalized value": value,
            "applied weight": weight, "weighted contribution": (value * weight if value is not None else None),
            "model version": VERSION, "validation status": "EQUAL-WEIGHT BASELINE / UNVALIDATED",
            "data-quality status": "AVAILABLE" if value is not None else "MISSING EVIDENCE",
        })
    decomposition = pd.DataFrame(rows)
    score = float(decomposition["weighted contribution"].sum()) if available else None
    action, reason = _protective_action(score, information_meta, path_meta, crowding_meta, validity_meta, attention_meta, context)
    if action not in PROTECTIVE_ACTIONS:
        action = "NO TRADE"

    envelope: dict[str, Any] = {
        "framework": "IMAP-RV", "version": VERSION, "signature": signature,
        "status": "RESEARCH PROTOTYPE READY" if score is not None else "INSUFFICIENT EVIDENCE",
        "cache_status": "BUILT", "metadata": metadata, "production_values_modified": False,
        "protected_production_direction": (
            _decision_label(context.decisions.iloc[-1].get(next((c for c in context.decisions.columns if "decision" in str(c).lower()), "")))
            if not context.decisions.empty else None
        ),
        "imap_rv_score": round(score, 4) if score is not None else None,
        "protective_action": action, "protective_reason": reason,
        "components": {
            "information_efficiency": information_meta, "path_memory": path_meta,
            "signal_validity": validity_meta, "evidence_covariance": {k: v for k, v in covariance_meta.items() if k != "feature_table"},
            "model_crowding": crowding_meta, "beta_fragility": beta_meta,
            "attention_hype": attention_meta, "diversity_consensus": consensus_meta,
            "calibration_quality": calibration_meta,
        },
        "tables": {
            "information_value_history": information_table,
            "path_memory_history": path_table,
            "signal_validity": validity_table,
            "raw_evidence_correlation": raw_corr,
            "cleaned_evidence_correlation": clean_corr,
            "evidence_feature_dictionary": feature_table,
            "model_crowding": crowding_table,
            "beta_fragility": beta_table,
            "attention_hype": attention_table,
            "diversity_weighted_consensus": consensus_table,
            "imap_rv_reliability_decomposition": decomposition,
        },
        "limitations": [
            "Research prototype; no claim of profitable edge or complete academic replication.",
            "Weights remain an equal-weight baseline until walk-forward validation freezes them before holdout testing.",
            "Unavailable DXY/yield/funding dependencies are reported rather than invented.",
            "Signal inference uses a time-series FDR prototype and requires block-bootstrap/HAC sensitivity analysis for thesis promotion.",
        ],
        "elapsed_seconds": round(time.perf_counter() - started, 6),
    }
    envelope["database"] = _persist(envelope)
    state[CACHE_KEY] = {"signature": signature, "envelope": envelope}
    state[STATE_KEY] = envelope
    return envelope


__all__ = [
    "VERSION", "STATE_KEY", "CACHE_KEY", "PROTECTIVE_ACTIONS", "COMPONENT_NAMES",
    "run_imap_rv",
]

"""Historical EURUSD event-response mining, validation and NLP reliability.

Future price movement is used only as a supervised target.  Feature columns are
restricted to information available at or before each article timestamp.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, brier_score_loss, confusion_matrix,
    f1_score, precision_recall_fscore_support, precision_score, recall_score,
)


def _find_col(df: pd.DataFrame, names: Sequence[str]) -> Optional[str]:
    normalized = {str(c).lower().replace("_", "").replace(" ", ""): c for c in df.columns}
    for name in names:
        key = name.lower().replace("_", "").replace(" ", "")
        if key in normalized:
            return normalized[key]
    return None


def prepare_ohlc(ohlc: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(ohlc, pd.DataFrame) or ohlc.empty:
        return pd.DataFrame()
    time_col = _find_col(ohlc, ["time", "datetime", "timestamp", "date"])
    close_col = _find_col(ohlc, ["close", "c"])
    open_col = _find_col(ohlc, ["open", "o"])
    high_col = _find_col(ohlc, ["high", "h"])
    low_col = _find_col(ohlc, ["low", "l"])
    if close_col is None:
        return pd.DataFrame()
    out = pd.DataFrame()
    if time_col:
        out["time"] = pd.to_datetime(ohlc[time_col], utc=True, errors="coerce")
    else:
        out["time"] = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=len(ohlc), freq="h")
    out["close"] = pd.to_numeric(ohlc[close_col], errors="coerce")
    out["open"] = pd.to_numeric(ohlc[open_col], errors="coerce") if open_col else out["close"]
    out["high"] = pd.to_numeric(ohlc[high_col], errors="coerce") if high_col else out[["open", "close"]].max(axis=1)
    out["low"] = pd.to_numeric(ohlc[low_col], errors="coerce") if low_col else out[["open", "close"]].min(axis=1)
    out = out.dropna(subset=["time", "close"]).sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)
    prev_close = out["close"].shift(1)
    tr = pd.concat([
        out["high"] - out["low"],
        (out["high"] - prev_close).abs(),
        (out["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14, min_periods=5).mean().fillna(tr.expanding(min_periods=1).mean()).ffill().fillna(0.0)
    return out


def _future_row(prices: pd.DataFrame, idx: int, hours: int) -> Optional[pd.Series]:
    target_time = prices.loc[idx, "time"] + pd.Timedelta(hours=int(hours))
    candidates = prices.index[prices["time"] >= target_time]
    if len(candidates) == 0:
        return None
    return prices.loc[int(candidates[0])]


def construct_event_response_dataset(
    articles: pd.DataFrame, ohlc: pd.DataFrame, *, atr_threshold: float = 0.35,
    maximum_match_delay_minutes: int = 90,
) -> pd.DataFrame:
    """Match article timestamps to later prices without using future features.

    Future movement is written only to target/evaluation columns. Text/model
    features remain exactly those known at the article timestamp.
    """
    prices = prepare_ohlc(ohlc)
    if not isinstance(articles, pd.DataFrame) or articles.empty or prices.empty:
        return pd.DataFrame()
    rows: List[Dict[str, Any]] = []
    for _, article in articles.iterrows():
        ts = pd.to_datetime(article.get("timestamp"), utc=True, errors="coerce")
        if pd.isna(ts):
            continue
        candidates = prices.index[prices["time"] >= ts]
        if len(candidates) == 0:
            continue
        idx = int(candidates[0])
        delay = (prices.loc[idx, "time"] - ts).total_seconds() / 60.0
        if delay > maximum_match_delay_minutes:
            continue
        base = float(prices.loc[idx, "close"])
        atr = float(prices.loc[idx, "atr14"] or 0.0)
        if not math.isfinite(base) or base == 0 or not math.isfinite(atr) or atr <= 0:
            continue
        pred = str(article.get("nlp_direction") or "WAIT").upper()
        hour = int(prices.loc[idx, "time"].hour)
        session = "ASIA" if hour < 7 else "LONDON" if hour < 12 else "NY_LONDON_OVERLAP" if hour < 16 else "NEW_YORK" if hour < 21 else "ROLLOVER"
        recent_atr = pd.to_numeric(prices.loc[max(0, idx-120):idx, "atr14"], errors="coerce").dropna()
        med_atr = float(recent_atr.median()) if not recent_atr.empty else atr
        volatility_group = "HIGH" if atr > med_atr * 1.30 else "LOW" if atr < med_atr * 0.75 else "NORMAL"
        eur = float(article.get("eur_relevance_score", 0.0) or 0.0)
        usd = float(article.get("usd_relevance_score", 0.0) or 0.0)
        affected_currency = "BOTH" if eur >= 20 and usd >= 20 else "EUR" if eur > usd else "USD" if usd > eur else "GENERAL"
        confidence = float(article.get("nlp_reliability_score", article.get("sentiment_confidence", 0.0)) or 0.0)
        if confidence <= 1.0:
            confidence *= 100.0
        confidence_bucket = "HIGH" if confidence >= 75 else "MODERATE" if confidence >= 55 else "LOW"
        result = article.to_dict()
        result.update({
            "price_match_time": prices.loc[idx, "time"],
            "price_match_delay_minutes": round(delay, 2),
            "event_close": base,
            "event_atr14": atr,
            "current_volatility_pips": round(atr / 0.0001, 2),
            "volatility_group": volatility_group,
            "market_session": session,
            "affected_currency": affected_currency,
            "confidence_bucket": confidence_bucket,
            "atr_target_threshold": float(atr_threshold),
            "actual_regime_after_event": article.get("actual_regime_after_event"),
        })
        for horizon in (1, 2, 3, 6):
            future = _future_row(prices, idx, horizon)
            if future is None:
                result[f"future_return_{horizon}h"] = np.nan
                result[f"future_move_pips_{horizon}h"] = np.nan
                result[f"direction_label_{horizon}h"] = None
                result[f"predicted_direction_correct_{horizon}h"] = False
                continue
            change = float(future["close"] - base)
            pips = change / 0.0001
            result[f"future_return_{horizon}h"] = change / base
            result[f"future_move_pips_{horizon}h"] = pips
            threshold = atr * float(atr_threshold)
            label = "BUY" if change > threshold else "SELL" if change < -threshold else "WAIT"
            result[f"direction_label_{horizon}h"] = label
            result[f"predicted_direction_correct_{horizon}h"] = bool(pred == label)
            result[f"wait_would_have_been_safer_{horizon}h"] = bool(label == "WAIT" and pred in {"BUY", "SELL"})
        result["direction_label"] = result.get("direction_label_3h")
        result["predicted_direction_correct"] = bool(result.get("predicted_direction_correct_3h"))
        result["wait_would_have_been_safer"] = bool(result.get("wait_would_have_been_safer_3h"))
        end = _future_row(prices, idx, 6)
        if end is not None:
            end_idx = int(end.name)
            window = prices.loc[idx:end_idx]
            up = float((window["high"].max() - base) / 0.0001)
            down = float((base - window["low"].min()) / 0.0001)
            if pred == "SELL":
                favourable, adverse = down, up
            elif pred == "BUY":
                favourable, adverse = up, down
            else:
                favourable, adverse = max(up, down), min(up, down)
            result["maximum_favourable_excursion"] = max(0.0, favourable)
            result["maximum_adverse_excursion"] = max(0.0, adverse)
        else:
            result["maximum_favourable_excursion"] = np.nan
            result["maximum_adverse_excursion"] = np.nan
        move_1h = float(result.get("future_move_pips_1h", np.nan))
        reaction = "BUY" if math.isfinite(move_1h) and move_1h > 0 else "SELL" if math.isfinite(move_1h) and move_1h < 0 else "WAIT"
        result["price_confirmation_status"] = "CONFIRM" if pred in {"BUY", "SELL"} and pred == reaction else "CONTRADICT" if pred in {"BUY", "SELL"} and reaction in {"BUY", "SELL"} else "WAIT / UNAVAILABLE"
        rows.append(result)
    return pd.DataFrame(rows)


def aggregate_event_responses(df: pd.DataFrame, *, minimum_sample_size: int = 12) -> pd.DataFrame:
    """Aggregate event outcomes across useful dimensions and 1H/3H/6H."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    dimensions = [c for c in [
        "event_type", "topic_name", "affected_currency", "current_regime",
        "market_session", "volatility_group", "nlp_direction", "confidence_bucket",
    ] if c in df.columns]
    rows: List[Dict[str, Any]] = []

    def add_group(group: pd.DataFrame, dimension: str, value: Any, horizon: int, extra: Optional[Dict[str, Any]] = None) -> None:
        target = f"direction_label_{horizon}h" if f"direction_label_{horizon}h" in group.columns else "direction_label"
        valid = group.dropna(subset=[target, "nlp_direction"]) if target in group.columns and "nlp_direction" in group.columns else pd.DataFrame()
        if valid.empty:
            return
        correct = valid[target].astype(str) == valid["nlp_direction"].astype(str)
        unsafe = valid["nlp_direction"].astype(str).isin(["BUY", "SELL"])
        move_col = f"future_move_pips_{horizon}h"
        rec: Dict[str, Any] = {
            "group_dimension": dimension, "group_value": str(value), "horizon": f"{horizon}H",
            "sample_size": int(len(valid)),
            "historical_directional_accuracy": round(float(correct.mean() * 100.0), 2),
            "median_movement_pips": round(float(pd.to_numeric(valid.get(move_col), errors="coerce").median()), 2),
            "average_favourable_movement": round(float(pd.to_numeric(valid.get("maximum_favourable_excursion"), errors="coerce").mean()), 2),
            "average_adverse_movement": round(float(pd.to_numeric(valid.get("maximum_adverse_excursion"), errors="coerce").mean()), 2),
            "false_signal_rate": round(float((~correct).mean() * 100.0), 2),
            "unsafe_trade_error_rate": round(float(((~correct) & unsafe).sum() / max(1, unsafe.sum()) * 100.0), 2),
            "reliability_level": "HIGH" if len(valid) >= 50 and correct.mean() >= 0.65 else "MODERATE" if len(valid) >= minimum_sample_size and correct.mean() >= 0.55 else "LOW / INSUFFICIENT",
            "minimum_sample_required": int(minimum_sample_size),
        }
        if extra:
            rec.update(extra)
        rows.append(rec)

    for dim in dimensions:
        for value, group in df.groupby(dim, dropna=False):
            for horizon in (1, 2, 3, 6):
                add_group(group, dim, value, horizon)
    if "event_type" in df.columns and "nlp_direction" in df.columns:
        for (event, direction), group in df.groupby(["event_type", "nlp_direction"], dropna=False):
            for horizon in (1, 2, 3, 6):
                add_group(group, "event_type+direction", f"{event}|{direction}", horizon, {"event_type": event, "nlp_direction": direction})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["sample_size", "historical_directional_accuracy"], ascending=[False, False]).reset_index(drop=True)


def compare_with_shared_outputs(article: Dict[str, Any], shared: Dict[str, Any]) -> Dict[str, Any]:
    nlp = str(article.get("nlp_direction") or "WAIT").upper()
    current = shared.get("current", {}) if isinstance(shared, dict) else {}
    regime = shared.get("regime", {}) if isinstance(shared, dict) else {}
    decision = shared.get("decision", {}) if isinstance(shared, dict) else {}
    powerbi = shared.get("powerbi", {}) if isinstance(shared, dict) else {}
    regime_direction = str(regime.get("direction") or current.get("regime_direction") or "WAIT").upper()
    central_decision = str(decision.get("direction") or current.get("decision") or "WAIT").upper()
    powerbi_direction = str(powerbi.get("direction") or current.get("prediction_direction") or "WAIT").upper()
    price_direction = str(powerbi.get("price_confirmation") or "WAIT").upper()

    def agreement(other: str) -> str:
        if nlp == "WAIT" or other == "WAIT":
            return "NEUTRAL"
        return "AGREE" if nlp == other else "CONFLICT"

    fields = {
        "nlp_regime_agreement": agreement(regime_direction),
        "nlp_powerbi_agreement": agreement(powerbi_direction),
        "nlp_price_agreement": agreement(price_direction),
        "nlp_priority_agreement": agreement(central_decision),
    }
    conflicts = sum(v == "CONFLICT" for v in fields.values())
    level = "HIGH" if conflicts >= 2 else "MODERATE" if conflicts == 1 else "LOW"
    fields.update({
        "nlp_overall_conflict": bool(conflicts),
        "nlp_conflict_level": level,
        "less_risky_nlp_decision": "WAIT" if conflicts or nlp not in {"BUY", "SELL"} else nlp,
    })
    return fields


def calculate_nlp_reliability(
    article: Dict[str, Any], agreement: Dict[str, Any], *, historical_sample_size: int = 0,
    historical_accuracy: float = 0.0,
) -> Dict[str, Any]:
    svm = article.get("svm_confidence")
    finbert = article.get("sentiment_confidence")
    topic = float(article.get("topic_probability", 0.0) or 0.0) / 100.0
    pair = float(article.get("nlp_pair_relevance", article.get("eurusd_pair_relevance", 0.0)) or 0.0) / 100.0
    recency = float(article.get("nlp_recency_weight", 0.0) or 0.0)
    novelty = float(article.get("nlp_novelty", article.get("novelty_score", 0.0)) or 0.0) / 100.0
    source = float(article.get("nlp_source_reliability", 60.0) or 60.0) / 100.0
    svm_component = float(svm) if svm is not None and math.isfinite(float(svm)) else 0.45
    finbert_component = float(finbert) if finbert is not None and math.isfinite(float(finbert)) else 0.50
    hist_component = (historical_accuracy / 100.0) if historical_sample_size >= 12 else 0.35
    raw = 100.0 * (
        0.16 * svm_component + 0.14 * finbert_component + 0.08 * topic +
        0.14 * pair + 0.10 * recency + 0.08 * novelty + 0.08 * source +
        0.12 * hist_component
    )
    penalties = 0.0
    if article.get("duplicate_status") == "DUPLICATE": penalties += 25.0
    if recency < 0.25: penalties += 12.0
    if pair < 0.25: penalties += 18.0
    if historical_sample_size < 12: penalties += 10.0
    if agreement.get("nlp_conflict_level") == "HIGH": penalties += 22.0
    elif agreement.get("nlp_conflict_level") == "MODERATE": penalties += 10.0
    if not str(article.get("display_text") or "").strip(): penalties += 12.0
    score = max(0.0, min(100.0, raw - penalties))
    label = "HIGH" if score >= 78 else "MODERATE" if score >= 58 else "LOW" if score >= 38 else "UNRELIABLE"
    return {
        "nlp_reliability_score": round(score, 2),
        "nlp_reliability_label": label,
        "nlp_reliability_true_false": bool(score >= 58 and agreement.get("nlp_conflict_level") != "HIGH"),
        "nlp_error_risk": round(100.0 - score, 2),
        "nlp_uncertainty": round(min(100.0, 100.0 - abs(float(article.get("nlp_direction_score", 0.0) or 0.0))), 2),
        "nlp_reliability_penalty": round(penalties, 2),
    }


def error_analysis(df: pd.DataFrame, *, target_col: str = "direction_label", pred_col: str = "nlp_direction") -> Dict[str, Any]:
    if not isinstance(df, pd.DataFrame) or df.empty or target_col not in df.columns or pred_col not in df.columns:
        return {"ok": False, "message": "Validation data is unavailable."}
    work = df.dropna(subset=[target_col, pred_col]).copy()
    if work.empty:
        return {"ok": False, "message": "Validation labels are unavailable."}

    def base_metrics(frame: pd.DataFrame, target: str) -> Dict[str, Any]:
        y_true = frame[target].astype(str)
        y_pred = frame[pred_col].astype(str)
        # Always pass the complete production label universe.  This keeps the
        # confusion matrix shape stable and prevents sklearn's single-label
        # warning when a short validation slice contains only one class.
        canonical_labels = ["BUY", "SELL", "WAIT"]
        extras = sorted((set(y_true) | set(y_pred)) - set(canonical_labels))
        labels = canonical_labels + extras
        p_macro, r_macro, f_macro, _ = precision_recall_fscore_support(y_true, y_pred, average="macro", zero_division=0)
        p_weight, r_weight, f_weight, _ = precision_recall_fscore_support(y_true, y_pred, average="weighted", zero_division=0)
        unsafe_mask = y_pred.isin(["BUY", "SELL"])
        out: Dict[str, Any] = {
            "sample_size": int(len(frame)),
            "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
            # sklearn delegates balanced_accuracy_score to confusion_matrix.
            # With one observed label that emits a noisy shape warning even though
            # the metric is mathematically the ordinary accuracy for this sample.
            "balanced_accuracy": round(float(accuracy_score(y_true, y_pred) if len(set(y_true) | set(y_pred)) == 1 else balanced_accuracy_score(y_true, y_pred)), 4),
            "precision_macro": round(float(p_macro), 4), "recall_macro": round(float(r_macro), 4),
            "macro_f1": round(float(f_macro), 4), "precision_weighted": round(float(p_weight), 4),
            "recall_weighted": round(float(r_weight), 4), "weighted_f1": round(float(f_weight), 4),
            "unsafe_trade_error_rate": round(float(((y_true != y_pred) & unsafe_mask).sum() / max(1, unsafe_mask.sum())), 4),
            "confusion_matrix": pd.DataFrame(confusion_matrix(y_true, y_pred, labels=labels), index=[f"Actual {x}" for x in labels], columns=[f"Pred {x}" for x in labels]),
        }
        for label in labels:
            true_label, pred_label = y_true == label, y_pred == label
            tp = int((true_label & pred_label).sum()); fp = int((~true_label & pred_label).sum())
            tn = int((~true_label & ~pred_label).sum())
            out[f"{label.lower()}_precision"] = round(tp / max(1, int(pred_label.sum())), 4)
            out[f"{label.lower()}_false_positive_rate"] = round(fp / max(1, fp + tn), 4)
        actual_trade = y_true.isin(["BUY", "SELL"])
        out["wait_missed_opportunity_rate"] = round(float(((y_pred == "WAIT") & actual_trade).sum() / max(1, actual_trade.sum())), 4)
        return out

    metrics: Dict[str, Any] = {"ok": True, **base_metrics(work, target_col)}
    prob_cols = [c for c in work.columns if c.startswith("svm_probability_")]
    if prob_cols:
        try:
            y_true = work[target_col].astype(str)
            briers = []
            confidence = []
            correctness = []
            for _, row in work.iterrows():
                probs = {label: float(row.get(f"svm_probability_{label.lower()}", 0.0) or 0.0) for label in ["BUY", "SELL", "WAIT"]}
                pred = str(row.get(pred_col, "WAIT"))
                confidence.append(max(probs.values()))
                correctness.append(1.0 if pred == str(row.get(target_col)) else 0.0)
            for label in ["BUY", "SELL", "WAIT"]:
                col = f"svm_probability_{label.lower()}"
                if col in work.columns:
                    briers.append(brier_score_loss((y_true == label).astype(int), pd.to_numeric(work[col], errors="coerce").fillna(0).clip(0, 1)))
            if briers:
                metrics["brier_score"] = round(float(np.mean(briers)), 5)
            bins = pd.cut(pd.Series(confidence), bins=[0,.2,.4,.6,.8,1.000001], include_lowest=True)
            ece = 0.0
            for bucket in bins.dropna().unique():
                mask = bins == bucket
                ece += float(mask.mean()) * abs(float(pd.Series(confidence)[mask].mean()) - float(pd.Series(correctness)[mask].mean()))
            metrics["calibration_error"] = round(float(ece), 5)
        except Exception:
            pass

    group_tables: Dict[str, pd.DataFrame] = {}
    for dim in ["event_type", "topic_name", "current_regime", "market_session", "volatility_group", "confidence_bucket"]:
        if dim not in work.columns:
            continue
        rows = []
        for value, group in work.groupby(dim, dropna=False):
            if len(group) < 2:
                continue
            item = base_metrics(group, target_col)
            rows.append({dim: value, **{k: v for k, v in item.items() if k != "confusion_matrix"}})
        if rows:
            group_tables[dim] = pd.DataFrame(rows).sort_values("sample_size", ascending=False)
    horizon_rows = []
    for horizon in (1, 2, 3, 6):
        target = f"direction_label_{horizon}h"
        if target in df.columns:
            valid = df.dropna(subset=[target, pred_col])
            if not valid.empty:
                item = base_metrics(valid, target)
                horizon_rows.append({"horizon": f"{horizon}H", **{k: v for k, v in item.items() if k != "confusion_matrix"}})
    metrics["performance_by_group"] = group_tables
    metrics["performance_by_horizon"] = pd.DataFrame(horizon_rows)
    return metrics


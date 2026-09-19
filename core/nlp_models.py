"""Optional trainable NLP models for Research: LDA, TF-IDF + LinearSVC,
FinBERT inference and bounded Optuna tuning.

Nothing here runs on page load.  Callers must trigger training/inference from an
existing Research Analyze/Train button.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.metrics import balanced_accuracy_score, f1_score
from sklearn.svm import LinearSVC

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None  # type: ignore

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "nlp"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_TOPIC_NAMES = {
    0: "Central-bank monetary policy",
    1: "Inflation",
    2: "Employment",
    3: "Economic growth",
    4: "Fiscal and government policy",
    5: "Banking and credit risk",
    6: "Geopolitical risk",
    7: "Energy and commodity effects",
    8: "Risk sentiment",
    9: "Unexpected crisis or shock",
}


def _safe_cache_resource(func):
    """Use Streamlit caching when available, including in lightweight tests."""
    decorator = getattr(st, "cache_resource", None) if st is not None else None
    if not callable(decorator):
        return func
    try:
        return decorator(show_spinner=False)(func)
    except Exception:
        return func


def _safe_cache_data(func):
    """Use data caching when available; otherwise leave the function intact."""
    decorator = getattr(st, "cache_data", None) if st is not None else None
    if not callable(decorator):
        return func
    try:
        return decorator(show_spinner=False)(func)
    except Exception:
        return func


def _artifact_paths(name: str) -> Tuple[Path, Path]:
    safe = "".join(c for c in str(name) if c.isalnum() or c in {"_", "-"}) or "model"
    return MODEL_DIR / f"{safe}.joblib", MODEL_DIR / f"{safe}.json"


def save_artifact(name: str, payload: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> None:
    model_path, meta_path = _artifact_paths(name)
    joblib.dump(payload, model_path)
    meta_path.write_text(json.dumps(metadata or {}, indent=2, default=str), encoding="utf-8")


@_safe_cache_resource
def load_artifact(name: str) -> Dict[str, Any]:
    model_path, _ = _artifact_paths(name)
    if not model_path.exists():
        return {}
    try:
        obj = joblib.load(model_path)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def fit_lda_topic_model(
    texts: Sequence[str], *, n_topics: int = 10, max_features: int = 10000,
    min_df: int = 2, max_df: float = 0.95, max_iter: int = 20,
    learning_method: str = "batch", learning_decay: float = 0.7,
    topic_names: Optional[Dict[int, str]] = None,
) -> Dict[str, Any]:
    clean = [str(x).strip() for x in texts if str(x).strip()]
    if len(clean) < max(20, n_topics * 3):
        return {"ok": False, "message": "Insufficient topic history", "sample_size": len(clean)}
    vectorizer = CountVectorizer(
        stop_words="english", ngram_range=(1, 2), min_df=max(1, int(min_df)),
        max_df=float(max_df), max_features=int(max_features),
    )
    matrix = vectorizer.fit_transform(clean)
    if matrix.shape[1] < max(8, n_topics):
        return {"ok": False, "message": "Insufficient topic vocabulary", "sample_size": len(clean)}
    model = LatentDirichletAllocation(
        n_components=max(2, int(n_topics)), max_iter=max(5, int(max_iter)),
        learning_method=learning_method if learning_method in {"batch", "online"} else "batch",
        learning_decay=float(learning_decay), random_state=42,
    )
    distributions = model.fit_transform(matrix)
    terms = np.asarray(vectorizer.get_feature_names_out())
    names = topic_names or DEFAULT_TOPIC_NAMES
    topics = []
    for topic_id, weights in enumerate(model.components_):
        top_terms = terms[np.argsort(weights)[::-1][:12]].tolist()
        topics.append({
            "topic_id": int(topic_id),
            "topic_name": names.get(topic_id, f"Topic {topic_id + 1}"),
            "top_terms": top_terms,
        })
    payload = {
        "ok": True,
        "vectorizer": vectorizer,
        "model": model,
        "topic_names": names,
        "topics": topics,
        "sample_size": len(clean),
        "training_topic_distribution": distributions.mean(axis=0).tolist(),
    }
    save_artifact("lda_topics", payload, {"sample_size": len(clean), "n_topics": n_topics})
    load_artifact.clear() if hasattr(load_artifact, "clear") else None
    return payload


def infer_lda_topics(texts: Sequence[str], artifact: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    art = artifact or load_artifact("lda_topics")
    if not art.get("ok"):
        return pd.DataFrame([{"status": "Insufficient topic history"}])
    clean = [str(x or "") for x in texts]
    try:
        matrix = art["vectorizer"].transform(clean)
        dist = art["model"].transform(matrix)
        baseline = np.asarray(art.get("training_topic_distribution") or np.zeros(dist.shape[1]))
        names = art.get("topic_names") or {}
        rows = []
        for i, probs in enumerate(dist):
            order = np.argsort(probs)[::-1]
            primary = int(order[0])
            secondary = int(order[1]) if len(order) > 1 else primary
            novelty = 100.0 * float(np.abs(probs - baseline).sum() / 2.0) if len(baseline) == len(probs) else 0.0
            rows.append({
                "topic_id": primary,
                "topic_name": names.get(primary, f"Topic {primary + 1}"),
                "topic_probability": round(float(probs[primary]) * 100.0, 2),
                "secondary_topic": names.get(secondary, f"Topic {secondary + 1}"),
                "secondary_probability": round(float(probs[secondary]) * 100.0, 2),
                "topic_novelty": round(min(100.0, novelty), 2),
                "topic_historical_accuracy": None,
            })
        return pd.DataFrame(rows)
    except Exception as exc:
        return pd.DataFrame([{"status": f"Topic inference unavailable: {exc}"}])


def _time_order(df: pd.DataFrame, time_col: Optional[str]) -> pd.DataFrame:
    out = df.copy()
    if time_col and time_col in out.columns:
        out[time_col] = pd.to_datetime(out[time_col], utc=True, errors="coerce")
        out = out.sort_values(time_col, na_position="last")
    return out.reset_index(drop=True)


def train_linear_svm(
    df: pd.DataFrame, *, text_col: str = "model_text", target_col: str = "direction_label",
    time_col: Optional[str] = "timestamp", ngram_range: Tuple[int, int] = (1, 2),
    min_df: int = 2, max_df: float = 0.98, max_features: int = 20000,
    sublinear_tf: bool = True, c_value: float = 1.0, class_weight: Any = "balanced",
    max_iter: int = 5000, calibrate: bool = True, artifact_name: str = "svm_direction",
) -> Dict[str, Any]:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {"ok": False, "message": "No supervised NLP training rows."}
    work = _time_order(df.dropna(subset=[text_col, target_col]), time_col)
    work = work[work[text_col].astype(str).str.strip().astype(bool)].copy()
    if len(work) < 40 or work[target_col].nunique() < 2:
        return {"ok": False, "message": "Too few labelled rows for time-based SVM training.", "sample_size": len(work)}
    split = max(1, min(len(work) - 1, int(len(work) * 0.80)))
    train, test = work.iloc[:split], work.iloc[split:]
    vectorizer = TfidfVectorizer(
        stop_words="english", ngram_range=tuple(ngram_range), min_df=max(1, int(min_df)),
        max_df=float(max_df), max_features=int(max_features), sublinear_tf=bool(sublinear_tf),
    )
    # Preserve chronological order throughout fitting and calibration. The
    # outer 20% test set remains completely untouched until final evaluation.
    base = LinearSVC(C=float(c_value), class_weight=class_weight, max_iter=int(max_iter), random_state=42)
    model: Any = base
    calibrated = False
    calibration_rows = 0

    can_calibrate = (
        bool(calibrate)
        and len(train) >= 80
        and train[target_col].nunique() >= 2
        and train[target_col].value_counts().min() >= 4
    )
    if can_calibrate:
        calibration_split = max(1, min(len(train) - 1, int(len(train) * 0.82)))
        fit_rows = train.iloc[:calibration_split]
        calibration_rows_df = train.iloc[calibration_split:]
        # Calibration needs all fitted classes represented in the later block.
        fit_classes = set(fit_rows[target_col].astype(str).unique())
        calibration_classes = set(calibration_rows_df[target_col].astype(str).unique())
        can_calibrate = bool(
            fit_classes
            and fit_classes == set(train[target_col].astype(str).unique())
            and fit_classes.issubset(calibration_classes)
            and calibration_rows_df[target_col].value_counts().min() >= 2
        )
    if can_calibrate:
        vectorizer.fit(fit_rows[text_col].astype(str))
        x_fit = vectorizer.transform(fit_rows[text_col].astype(str))
        x_cal = vectorizer.transform(calibration_rows_df[text_col].astype(str))
        x_test = vectorizer.transform(test[text_col].astype(str))
        base.fit(x_fit, fit_rows[target_col].astype(str))
        try:
            # Newer scikit-learn uses FrozenEstimator; older versions accept
            # cv="prefit". Both calibrate only on later-in-time rows.
            try:
                from sklearn.frozen import FrozenEstimator
                model = CalibratedClassifierCV(FrozenEstimator(base), method="sigmoid")
            except Exception:
                model = CalibratedClassifierCV(base, method="sigmoid", cv="prefit")
            model.fit(x_cal, calibration_rows_df[target_col].astype(str))
            calibrated = True
            calibration_rows = int(len(calibration_rows_df))
        except Exception:
            # Fall back to an uncalibrated LinearSVC fitted on all past rows.
            vectorizer.fit(train[text_col].astype(str))
            x_train = vectorizer.transform(train[text_col].astype(str))
            x_test = vectorizer.transform(test[text_col].astype(str))
            model = base
            model.fit(x_train, train[target_col].astype(str))
    else:
        vectorizer.fit(train[text_col].astype(str))
        x_train = vectorizer.transform(train[text_col].astype(str))
        x_test = vectorizer.transform(test[text_col].astype(str))
        model.fit(x_train, train[target_col].astype(str))

    pred = model.predict(x_test)
    metrics = {
        "macro_f1": round(float(f1_score(test[target_col], pred, average="macro", zero_division=0)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(test[target_col], pred)), 4),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "classes": sorted(map(str, pd.Series(work[target_col]).dropna().unique().tolist())),
        "calibrated": calibrated,
        "calibration_rows": calibration_rows,
        "time_split": True,
        "calibration_time_split": True,
    }
    payload = {"ok": True, "vectorizer": vectorizer, "model": model, "metrics": metrics, "target_col": target_col, "text_col": text_col}
    save_artifact(artifact_name, payload, metrics)
    load_artifact.clear() if hasattr(load_artifact, "clear") else None
    return payload


def predict_linear_svm(texts: Sequence[str], artifact_name: str = "svm_direction") -> pd.DataFrame:
    art = load_artifact(artifact_name)
    if not art.get("ok"):
        return pd.DataFrame([{"status": "SVM model is not fitted"}])
    clean = [str(x or "") for x in texts]
    try:
        x = art["vectorizer"].transform(clean)
        pred = art["model"].predict(x)
        rows: List[Dict[str, Any]] = []
        probabilities = None
        if hasattr(art["model"], "predict_proba"):
            probabilities = art["model"].predict_proba(x)
            classes = list(map(str, art["model"].classes_))
        else:
            classes = list(map(str, getattr(art["model"], "classes_", [])))
        for i, label in enumerate(pred):
            row = {"svm_label": str(label), "svm_calibrated": bool(probabilities is not None)}
            if probabilities is not None:
                for j, cls in enumerate(classes):
                    row[f"svm_probability_{cls.lower()}"] = round(float(probabilities[i, j]), 4)
                row["svm_confidence"] = round(float(probabilities[i].max()), 4)
            else:
                row["svm_confidence"] = None
            rows.append(row)
        return pd.DataFrame(rows)
    except Exception as exc:
        return pd.DataFrame([{"status": f"SVM inference unavailable: {exc}"}])


@_safe_cache_resource
def load_finbert(model_name: str = "ProsusAI/finbert"):
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
        return pipeline("text-classification", model=model, tokenizer=tokenizer, return_all_scores=True, device=-1)
    except Exception as exc:
        return {"error": str(exc)}


def finbert_inference(texts: Sequence[str], model_name: str = "ProsusAI/finbert", max_chars: int = 1800) -> pd.DataFrame:
    pipe = load_finbert(model_name)
    if isinstance(pipe, dict) and pipe.get("error"):
        return pd.DataFrame([{"status": "FinBERT unavailable; lightweight sentiment fallback remains active", "detail": str(pipe.get("error"))[:180]}])
    rows: List[Dict[str, Any]] = []
    try:
        batch = [str(x or "")[:max_chars] for x in texts]
        outputs = pipe(batch, truncation=True, max_length=256, batch_size=min(8, max(1, len(batch))))
        for item in outputs:
            scores = {str(x.get("label", "")).lower(): float(x.get("score", 0.0)) for x in item}
            positive = scores.get("positive", scores.get("label_0", 0.0))
            negative = scores.get("negative", scores.get("label_1", 0.0))
            neutral = scores.get("neutral", scores.get("label_2", 0.0))
            label = max({"POSITIVE": positive, "NEGATIVE": negative, "NEUTRAL": neutral}, key={"POSITIVE": positive, "NEGATIVE": negative, "NEUTRAL": neutral}.get)
            rows.append({
                "sentiment_label": label,
                "sentiment_positive_probability": round(positive, 4),
                "sentiment_negative_probability": round(negative, 4),
                "sentiment_neutral_probability": round(neutral, 4),
                "sentiment_confidence": round(max(positive, negative, neutral), 4),
                "sentiment_model": model_name,
            })
        return pd.DataFrame(rows)
    except Exception as exc:
        return pd.DataFrame([{"status": f"FinBERT inference failed safely: {str(exc)[:180]}"}])


@_safe_cache_resource
def load_abstractive_model(model_name: str = "google/flan-t5-small"):
    try:
        from transformers import pipeline
        return pipeline("text2text-generation", model=model_name, device=-1)
    except Exception as exc:
        return {"error": str(exc)}


def abstractive_summary(text: str, *, model_name: str = "google/flan-t5-small") -> Dict[str, Any]:
    model = load_abstractive_model(model_name)
    if isinstance(model, dict) and model.get("error"):
        return {"ok": False, "message": "Abstractive model unavailable", "detail": str(model.get("error"))[:180]}
    try:
        prompt = "Summarize this financial news factually in 3 short sentences without inventing details: " + str(text or "")[:4000]
        result = model(prompt, max_new_tokens=120, do_sample=False, truncation=True)
        summary = str(result[0].get("generated_text", "")) if result else ""
        return {"ok": bool(summary), "summary": summary, "model": model_name}
    except Exception as exc:
        return {"ok": False, "message": f"Abstractive summary failed safely: {str(exc)[:180]}"}


def tune_svm_optuna(
    df: pd.DataFrame, *, text_col: str = "model_text", target_col: str = "direction_label",
    time_col: str = "timestamp", trials: int = 20,
) -> Dict[str, Any]:
    try:
        import optuna
    except Exception:
        return {"ok": False, "message": "Optuna is not installed."}
    if not isinstance(df, pd.DataFrame) or len(df) < 60:
        return {"ok": False, "message": "Too few rows for bounded hyperparameter tuning."}
    work = _time_order(df.dropna(subset=[text_col, target_col]), time_col)
    split = max(1, min(len(work) - 1, int(len(work) * 0.80)))
    train, valid = work.iloc[:split], work.iloc[split:]
    if valid.empty or train[target_col].nunique() < 2:
        return {"ok": False, "message": "Time-based validation split is not usable."}

    def objective(trial):
        ngram_max = trial.suggest_int("ngram_max", 1, 2)
        min_df = trial.suggest_int("min_df", 1, min(5, max(1, len(train) // 20)))
        max_features = trial.suggest_categorical("max_features", [5000, 10000, 20000])
        c_value = trial.suggest_float("C", 0.1, 4.0, log=True)
        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, ngram_max), min_df=min_df, max_df=0.98, max_features=max_features, sublinear_tf=True)
        x_train = vec.fit_transform(train[text_col].astype(str))
        x_valid = vec.transform(valid[text_col].astype(str))
        model = LinearSVC(C=c_value, class_weight="balanced", max_iter=4000, random_state=42)
        model.fit(x_train, train[target_col].astype(str))
        pred = model.predict(x_valid)
        macro = f1_score(valid[target_col], pred, average="macro", zero_division=0)
        unsafe_mask = pd.Series(pred).isin(["BUY", "SELL"]).to_numpy()
        incorrect = (pd.Series(pred).to_numpy() != valid[target_col].astype(str).to_numpy())
        unsafe_rate = float((incorrect & unsafe_mask).sum() / max(1, unsafe_mask.sum()))
        return float(macro - 0.35 * unsafe_rate)

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=max(3, min(int(trials), 50)), timeout=180, show_progress_bar=False)
    result = {"ok": True, "best_value": round(float(study.best_value), 5), "best_params": study.best_params, "trials": len(study.trials)}
    _, meta_path = _artifact_paths("svm_tuning")
    meta_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result



def tune_lda_optuna(texts: Sequence[str], *, trials: int = 15) -> Dict[str, Any]:
    """Bounded LDA tuning using held-out perplexity; never runs automatically."""
    try:
        import optuna
    except Exception:
        return {"ok": False, "message": "Optuna is not installed."}
    clean = [str(x).strip() for x in texts if str(x).strip()]
    if len(clean) < 60:
        return {"ok": False, "message": "Need at least 60 news texts for LDA tuning.", "sample_size": len(clean)}
    split = max(40, int(len(clean) * 0.80))
    train, valid = clean[:split], clean[split:]
    if len(valid) < 10:
        return {"ok": False, "message": "Held-out topic validation set is too small."}

    def objective(trial):
        n_topics = trial.suggest_int("n_topics", 4, min(12, max(4, len(train) // 8)))
        learning_method = trial.suggest_categorical("learning_method", ["batch", "online"])
        learning_decay = trial.suggest_float("learning_decay", 0.5, 0.9)
        max_iter = trial.suggest_int("max_iter", 8, 24)
        max_features = trial.suggest_categorical("max_features", [4000, 8000, 12000])
        vec = CountVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2, max_df=0.97, max_features=max_features)
        x_train = vec.fit_transform(train)
        x_valid = vec.transform(valid)
        if x_train.shape[1] < n_topics or x_valid.shape[0] == 0:
            raise optuna.TrialPruned()
        model = LatentDirichletAllocation(
            n_components=n_topics, learning_method=learning_method, learning_decay=learning_decay,
            max_iter=max_iter, random_state=42,
        )
        model.fit(x_train)
        perplexity = float(model.perplexity(x_valid))
        trial.report(perplexity, step=0)
        if trial.should_prune():
            raise optuna.TrialPruned()
        return perplexity

    study = optuna.create_study(
        direction="minimize", sampler=optuna.samplers.TPESampler(seed=42),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=4),
    )
    study.optimize(objective, n_trials=max(3, min(int(trials), 30)), timeout=180, show_progress_bar=False)
    if not study.trials or study.best_trial is None:
        return {"ok": False, "message": "No usable LDA tuning trial completed."}
    result = {"ok": True, "best_perplexity": round(float(study.best_value), 4), "best_params": study.best_params, "trials": len(study.trials), "time_split": True}
    _, meta_path = _artifact_paths("lda_tuning")
    meta_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


def tune_decision_thresholds_optuna(df: pd.DataFrame, *, trials: int = 20) -> Dict[str, Any]:
    """Tune only the NLP evidence layer, never the central trading decision."""
    try:
        import optuna
    except Exception:
        return {"ok": False, "message": "Optuna is not installed."}
    required = {"nlp_direction_score", "future_move_pips_3h", "event_atr14"}
    if not isinstance(df, pd.DataFrame) or len(df) < 60 or not required.issubset(df.columns):
        return {"ok": False, "message": "Too few historical event-response rows for threshold tuning."}
    work = _time_order(df.copy(), "timestamp" if "timestamp" in df.columns else None)
    split = max(40, int(len(work) * 0.80))
    valid = work.iloc[split:].copy()
    if len(valid) < 12:
        return {"ok": False, "message": "Time-based validation split is too small."}

    def objective(trial):
        buy_threshold = trial.suggest_float("buy_threshold", 8.0, 40.0)
        sell_threshold = -trial.suggest_float("sell_threshold_magnitude", 8.0, 40.0)
        atr_target = trial.suggest_float("atr_target_threshold", 0.15, 0.80)
        duplicate_threshold = trial.suggest_float("duplicate_threshold", 0.86, 0.96)
        min_recency = trial.suggest_float("minimum_recency_weight", 0.10, 0.55)
        reliability_threshold = trial.suggest_float("reliability_threshold", 35.0, 75.0)
        score = pd.to_numeric(valid["nlp_direction_score"], errors="coerce").fillna(0.0)
        pred = pd.Series(np.where(score >= buy_threshold, "BUY", np.where(score <= sell_threshold, "SELL", "WAIT")), index=valid.index)
        similarity = pd.to_numeric(valid.get("similarity_to_previous", 0.0), errors="coerce").fillna(0.0)
        recency = pd.to_numeric(valid.get("nlp_recency_weight", 1.0), errors="coerce").fillna(0.0)
        reliability = pd.to_numeric(valid.get("nlp_reliability_score", 50.0), errors="coerce").fillna(0.0)
        pred[(similarity >= duplicate_threshold) | (recency < min_recency) | (reliability < reliability_threshold)] = "WAIT"
        move = pd.to_numeric(valid["future_move_pips_3h"], errors="coerce") * 0.0001
        threshold = pd.to_numeric(valid["event_atr14"], errors="coerce") * atr_target
        target = pd.Series(np.where(move > threshold, "BUY", np.where(move < -threshold, "SELL", "WAIT")), index=valid.index)
        macro = f1_score(target, pred, average="macro", zero_division=0)
        unsafe = pred.isin(["BUY", "SELL"])
        unsafe_rate = float(((pred != target) & unsafe).sum() / max(1, unsafe.sum()))
        trial.report(float(macro - 0.45 * unsafe_rate), step=0)
        if trial.should_prune():
            raise optuna.TrialPruned()
        return float(macro - 0.45 * unsafe_rate)

    study = optuna.create_study(
        direction="maximize", sampler=optuna.samplers.TPESampler(seed=42),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=5),
    )
    study.optimize(objective, n_trials=max(3, min(int(trials), 40)), timeout=180, show_progress_bar=False)
    result = {"ok": True, "best_value": round(float(study.best_value), 5), "best_params": study.best_params, "trials": len(study.trials), "time_split": True, "central_decision_unchanged": True}
    _, meta_path = _artifact_paths("decision_threshold_tuning")
    meta_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result

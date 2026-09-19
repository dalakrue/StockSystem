"""Ten optional Field 10 research methods, isolated from production decisions.

This module is intentionally *not* called by the normal Quick Run.  It is for
explicit validation runs or scheduled settlement jobs.  Every method is
chronological, read-only with respect to protected calculations, and returns
UNAVAILABLE rather than manufacturing a statistic when its evidence contract
is not satisfied.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from math import erf, exp, log, sqrt
from typing import Any, Mapping, Sequence
import json

import numpy as np
import pandas as pd

SCHEMA_VERSION = "field10-shadow-research-20260702-v1"
VALID_STATUSES = {"UNAVAILABLE", "SHADOW", "VALIDATED", "PRODUCTION APPROVED"}


@dataclass(frozen=True, slots=True)
class MethodSpec:
    method_id: str
    paper_title: str
    authors: str
    formula: str
    assumptions: tuple[str, ...]
    required_inputs: tuple[str, ...]
    output_columns: tuple[str, ...]
    minimum_sample_size: int
    chronological_validation: str
    leakage_controls: tuple[str, ...]
    computational_cost: str
    cache_design: str
    production_promotion_criteria: tuple[str, ...]
    failure_fallback: str
    current_status: str = "SHADOW"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


METHOD_SPECS: tuple[MethodSpec, ...] = (
    MethodSpec(
        "HAMILTON_MARKOV_SWITCHING",
        "A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle",
        "James D. Hamilton",
        "P(S_t=j|Y_t) ∝ f(y_t|S_t=j) Σ_i p_ij P(S_{t-1}=i|Y_{t-1})",
        ("finite-state latent regimes", "transition probabilities are locally stable", "completed observations only"),
        ("completed OHLC/features", "canonical identity", "optional settled errors"),
        ("shadow_regime", "regime_probability", "regime_entropy", "expected_duration", "transition_matrix"),
        480,
        "Expanding or rolling origin; fit only on data available at each origin and score the next completed candle.",
        ("no smoothed future state in current decision", "cutoff at completed broker candle", "no production overwrite"),
        "Medium; bounded EM/HMM fit, never in UI reruns.",
        "Fingerprint(symbol,timeframe,completed_candle,feature_hash,method_version).",
        ("two disjoint chronological validation windows", "stable transition matrix", "better settled proper score", "explicit approval"),
        "Return UNAVAILABLE and retain protected Field 3 regime.",
    ),
    MethodSpec(
        "ENGLE_DCC",
        "Dynamic Conditional Correlation: A Simple Class of Multivariate Generalized Autoregressive Conditional Heteroskedasticity Models",
        "Robert F. Engle",
        "Q_t=(1-a-b)Q̄+a z_{t-1}z'_{t-1}+bQ_{t-1}; R_t=diag(Q_t)^(-1/2)Q_tdiag(Q_t)^(-1/2)",
        ("aligned completed returns", "a≥0, b≥0, a+b<1", "locally stable parameters"),
        ("aligned multi-symbol returns", "completed broker candle cutoff"),
        ("conditional_correlation", "correlation_shock", "diversification_loss", "duplicate_exposure_penalty"),
        120,
        "Estimate on an expanding training window and evaluate next-period covariance/correlation loss.",
        ("as-of joins only", "no forward-filled future returns", "symbol-pair identity validation"),
        "Low to medium; recursive O(TK²).",
        "Cache aligned standardized-return matrix and final Q_t by source fingerprint.",
        ("positive-semidefinite matrices", "stable out-of-sample covariance loss", "resource gate", "explicit approval"),
        "Return UNAVAILABLE; set no correlation penalty.",
    ),
    MethodSpec(
        "GIACOMINI_WHITE_CPA",
        "Tests of Conditional Predictive Ability",
        "Raffaella Giacomini and Halbert White",
        "T=n·ḡ'Ω̂⁻¹ḡ, where g_t=h_t·ΔL_t and ΔL_t is the settled loss differential",
        ("fixed/rolling estimation scheme represented in the loss sequence", "finite HAC covariance", "settled comparable forecasts"),
        ("chronologically settled benchmark/challenger forecasts", "conditioning variables"),
        ("condition", "loss", "statistic", "p_value", "effect_size", "candidate_superior"),
        48,
        "Run by forecast origin and condition; require a second non-overlapping validation window.",
        ("settlement after forecast origin", "same targets for both models", "HAC lag by horizon", "no in-sample rows"),
        "Medium; grouped HAC tests.",
        "Cache normalized settled panel by immutable settlement ledger hash.",
        ("p≤0.05 after multiplicity control", "positive effect", "adjacent-window stability", "explicit approval"),
        "Return UNAVAILABLE; do not infer conditional superiority.",
    ),
    MethodSpec(
        "HANSEN_SPA",
        "A Test for Superior Predictive Ability",
        "Peter R. Hansen",
        "T=max_k √n·max(d̄_k,0)/ω̂_k with a studentized block-bootstrap null",
        ("aligned benchmark and candidate losses", "weak dependence handled by blocks", "candidate set fixed before test"),
        ("settled loss panel with benchmark and at least one challenger",),
        ("spa_statistic", "spa_p_value", "best_challenger", "effect_size", "promotion_allowed"),
        60,
        "Test on a sealed chronological OOS window; repeat on a later sealed window.",
        ("candidate registry frozen before OOS", "deterministic block bootstrap", "no cherry-picked loss horizon"),
        "High; block bootstrap, validation job only.",
        "Cache aligned loss panel and deterministic bootstrap seed/results.",
        ("SPA p≤0.05", "minimum 1% loss improvement", "second-window pass", "calibration/resource/rollback gates", "explicit approval"),
        "Return UNAVAILABLE; no best-model claim.",
    ),
    MethodSpec(
        "PBO_CSCV",
        "The Probability of Backtest Overfitting",
        "David H. Bailey, Jonathan M. Borwein, Marcos López de Prado, and Qiji Jim Zhu",
        "PBO=Pr(λ<0), λ=log(ω/(1-ω)); ω is the OOS rank percentile of the IS-selected strategy under CSCV",
        ("multiple pre-registered candidate configurations", "sufficient independent chronological blocks", "same metric across candidates"),
        ("T×N settled candidate performance matrix", "even number of chronological blocks"),
        ("pbo", "logit_rank_distribution", "oos_degradation", "probability_of_loss"),
        120,
        "Combinatorially symmetric cross-validation over contiguous chronological blocks; candidates fixed beforehand.",
        ("no parameter tuning after folds", "purge/embargo overlapping horizons", "all tried candidates included"),
        "High/combinatorial; scheduled validation only.",
        "Cache candidate matrix hash, block plan, and fold ranks.",
        ("PBO below approved ceiling", "positive OOS median", "stable later window", "DSR/SPA gates", "explicit approval"),
        "Return UNAVAILABLE unless at least two real candidates and sufficient blocks exist.",
    ),
    MethodSpec(
        "DEFLATED_SHARPE_RATIO",
        "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality",
        "David H. Bailey and Marcos López de Prado",
        "DSR=Φ(((SR̂*−SR₀)√(T−1))/√(1−γ₃SR₀+((γ₄−1)/4)SR₀²))",
        ("reported trial count includes all attempts", "returns are chronological", "finite skew/kurtosis"),
        ("settled strategy returns", "effective number of trials", "cross-trial Sharpe variance"),
        ("observed_sharpe", "expected_max_noise_sharpe", "deflated_sharpe_probability", "minimum_track_record_length"),
        100,
        "Compute only on sealed OOS returns and repeat on a later OOS block.",
        ("non-annualized formula inputs", "all trials disclosed", "no overlapping return leakage"),
        "Low after trial registry is available.",
        "Cache return-series hash and trial-registry hash.",
        ("DSR probability above governance threshold", "positive net OOS return", "PBO/SPA pass", "explicit approval"),
        "Return UNAVAILABLE when trial count or settled returns are insufficient.",
    ),
    MethodSpec(
        "PROBABILITY_CALIBRATION",
        "Predicting Good Probabilities with Supervised Learning",
        "Alexandru Niculescu-Mizil and Rich Caruana",
        "Platt: p=1/(1+exp(Af+B)); isotonic: min Σ(y_i−m(f_i))² subject to monotone m",
        ("settled binary outcomes", "probabilities correspond to the same event", "calibration mapping stable enough for the window"),
        ("raw probabilities", "settled labels", "current raw probability"),
        ("calibrated_probability", "brier_score", "log_loss", "ece", "calibration_method"),
        100,
        "Train calibrator on past outcomes, select on a later validation slice, report on a final untouched slice.",
        ("strict time split", "no label before settlement", "calibrator selected without test labels"),
        "Low to medium.",
        "Cache calibrator by training-window identity and probability schema.",
        ("Brier/log loss not worse", "ECE improvement", "stable two windows", "explicit approval"),
        "Identity mapping; mark UNAVAILABLE rather than altering protected reliability.",
    ),
    MethodSpec(
        "CONFORMAL_PREDICTIVE_INFERENCE",
        "Distribution-Free Predictive Inference for Regression",
        "Jing Lei, Max G'Sell, Alessandro Rinaldo, Ryan J. Tibshirani, and Larry Wasserman",
        "C_α(x)=[ŷ(x)−q̂_{1−α}, ŷ(x)+q̂_{1−α}] from held-out absolute residual scores",
        ("exchangeability or explicitly adapted sequential assumption", "calibration residuals settled", "same target definition"),
        ("point forecasts", "settled residuals", "target coverage"),
        ("prediction_lower", "prediction_upper", "interval_width", "realized_coverage", "coverage_error"),
        100,
        "Rolling-origin calibration set; score only targets settled after each forecast origin.",
        ("residual cutoff by origin", "no future quantile", "separate model fit/calibration/test windows"),
        "Low; empirical quantile, validation only for coverage history.",
        "Cache ordered residual scores by forecast-ledger fingerprint.",
        ("coverage within tolerance", "width competitive", "drift-aware revalidation", "explicit approval"),
        "Return UNAVAILABLE and keep protected Field 2 bands.",
    ),
    MethodSpec(
        "ADWIN_DRIFT",
        "Learning from Time-Changing Data with Adaptive Windowing",
        "Albert Bifet and Ricard Gavaldà",
        "Signal drift when |μ̂_W0−μ̂_W1| exceeds a concentration bound ε(δ,n₀,n₁,σ̂²)",
        ("ordered stream", "bounded monitored statistic", "chosen false-alarm delta"),
        ("chronological settled error/reliability stream",),
        ("drift_status", "cut_index", "window_size", "magnitude", "detection_time"),
        40,
        "Replay strictly in timestamp order; freeze alert parameters before evaluation.",
        ("no sorting by outcome", "monitor only settled values", "alert does not change protected action"),
        "Low to medium; bounded adaptive window.",
        "Persist compact detector state plus source fingerprint.",
        ("acceptable false-alert rate", "repeatable detection lead time", "recalibration policy validated", "explicit approval"),
        "Return UNAVAILABLE; set drift status to UNKNOWN, not STABLE.",
    ),
    MethodSpec(
        "TIME_DECAYED_NOVELTY_SENTIMENT",
        "All the News That's Fit to Reprint: Do Investors React to Stale Information?",
        "Paul C. Tetlock",
        "S_t=Σ_i exp(−λ·age_i)·novelty_i·relevance_i·sentiment_i / Σ_i weights_i; novelty=1−max cosine similarity to prior as-of stories",
        ("article timestamps are reliable", "prior-story corpus is as-of", "entity/pair relevance is measured"),
        ("timestamped deduplicated news", "sentiment", "entity relevance", "prior-story text/embedding"),
        ("novelty", "staleness", "time_decay_weight", "news_sentiment_shadow", "source_count"),
        30,
        "At each broker candle, compare only to stories timestamped earlier; evaluate settled next-horizon response.",
        ("publication-time cutoff", "title/text hash deduplication", "no revised article text from the future"),
        "Low to medium depending on embeddings.",
        "Cache normalized text hash, prior-story similarity, and time-decay weights.",
        ("incremental OOS information value", "stable across news providers", "latency audit", "explicit approval"),
        "Return UNAVAILABLE and leave protected sentiment unchanged.",
    ),
)

SPEC_BY_ID = {item.method_id: item for item in METHOD_SPECS}


def methodology_catalog() -> list[dict[str, Any]]:
    return [item.to_dict() for item in METHOD_SPECS]


def _unavailable(spec: MethodSpec, reason: str, sample_count: int = 0, **extra: Any) -> dict[str, Any]:
    return {
        "method_id": spec.method_id,
        "paper_title": spec.paper_title,
        "status": "UNAVAILABLE",
        "sample_count": int(sample_count),
        "minimum_sample_size": int(spec.minimum_sample_size),
        "reason": str(reason),
        "production_influence_enabled": False,
        "protected_calculation_changed": False,
        **extra,
    }


def _shadow(spec: MethodSpec, result: Mapping[str, Any], sample_count: int | None = None) -> dict[str, Any]:
    output = dict(result)
    source_status = str(output.get("status") or "").upper()
    if source_status in {"INSUFFICIENT_DATA", "INSUFFICIENT_EVIDENCE", "UNAVAILABLE", "INSUFFICIENT_CONDITIONAL_EVIDENCE"}:
        return _unavailable(spec, source_status, int(output.get("sample_count") or sample_count or 0), source_result=output)
    return {
        "method_id": spec.method_id,
        "paper_title": spec.paper_title,
        "status": "SHADOW",
        "sample_count": int(output.get("sample_count") or sample_count or 0),
        "minimum_sample_size": int(spec.minimum_sample_size),
        "result": output,
        "production_influence_enabled": False,
        "protected_calculation_changed": False,
    }


def probability_of_backtest_overfitting(
    performance_matrix: Any,
    *,
    blocks: int = 8,
    metric_higher_is_better: bool = True,
) -> dict[str, Any]:
    """Deterministic CSCV PBO estimate for pre-registered candidate columns.

    Rows must be chronologically ordered settled returns/scores.  No attempt is
    made to infer or invent missing candidate trials.
    """
    spec = SPEC_BY_ID["PBO_CSCV"]
    try:
        frame = pd.DataFrame(performance_matrix).apply(pd.to_numeric, errors="coerce").dropna()
    except Exception:
        frame = pd.DataFrame()
    n, candidates = frame.shape if not frame.empty else (0, 0)
    blocks = int(blocks)
    if candidates < 2:
        return _unavailable(spec, "At least two genuine pre-registered candidate columns are required.", n, candidate_count=candidates)
    if n < spec.minimum_sample_size or blocks < 4 or blocks % 2 or n < blocks * 5:
        return _unavailable(spec, "Insufficient settled rows or invalid even CSCV block count.", n, candidate_count=candidates, blocks=blocks)
    # Equal contiguous blocks; trim only the oldest remainder to preserve the latest complete plan.
    usable = (n // blocks) * blocks
    values = frame.iloc[-usable:].to_numpy(float).reshape(blocks, usable // blocks, candidates)
    from itertools import combinations
    half = blocks // 2
    logits: list[float] = []
    degradation: list[float] = []
    losses: list[bool] = []
    for train_idx_tuple in combinations(range(blocks), half):
        train_idx = set(train_idx_tuple)
        test_idx = [i for i in range(blocks) if i not in train_idx]
        train = values[list(train_idx)].reshape(-1, candidates)
        test = values[test_idx].reshape(-1, candidates)
        train_perf = np.mean(train, axis=0)
        test_perf = np.mean(test, axis=0)
        chosen = int(np.argmax(train_perf) if metric_higher_is_better else np.argmin(train_perf))
        order = np.argsort(test_perf) if metric_higher_is_better else np.argsort(-test_perf)
        rank_zero = int(np.where(order == chosen)[0][0])
        omega = (rank_zero + 1.0) / (candidates + 1.0)
        omega = float(np.clip(omega, 1e-9, 1 - 1e-9))
        logits.append(float(log(omega / (1.0 - omega))))
        degradation.append(float(train_perf[chosen] - test_perf[chosen]) if metric_higher_is_better else float(test_perf[chosen] - train_perf[chosen]))
        losses.append(bool(test_perf[chosen] < 0.0) if metric_higher_is_better else bool(test_perf[chosen] > 0.0))
    pbo = float(np.mean(np.asarray(logits) < 0.0))
    return {
        "method_id": spec.method_id,
        "paper_title": spec.paper_title,
        "status": "SHADOW",
        "sample_count": n,
        "candidate_count": candidates,
        "blocks": blocks,
        "fold_count": len(logits),
        "pbo": pbo,
        "median_logit_rank": float(np.median(logits)),
        "mean_oos_degradation": float(np.mean(degradation)),
        "probability_of_loss": float(np.mean(losses)),
        "production_influence_enabled": False,
        "protected_calculation_changed": False,
    }


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + erf(value / sqrt(2.0)))


def _normal_ppf(probability: float) -> float:
    # Acklam's rational approximation, avoiding an optional scipy dependency.
    p = float(np.clip(probability, 1e-12, 1 - 1e-12))
    a = (-3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2, 1.383577518672690e2, -3.066479806614716e1, 2.506628277459239)
    b = (-5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2, 6.680131188771972e1, -1.328068155288572e1)
    c = (-7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783)
    d = (7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996, 3.754408661907416)
    plow = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = sqrt(-2 * log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = sqrt(-2 * log(1-p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q*q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def deflated_sharpe_ratio(
    returns: Sequence[float],
    *,
    trial_sharpes: Sequence[float] | None = None,
    effective_trials: int | None = None,
) -> dict[str, Any]:
    spec = SPEC_BY_ID["DEFLATED_SHARPE_RATIO"]
    values = np.asarray(list(returns), dtype=float)
    values = values[np.isfinite(values)]
    n = int(values.size)
    trials = np.asarray(list(trial_sharpes) if trial_sharpes is not None else [], dtype=float)
    trials = trials[np.isfinite(trials)]
    m = int(effective_trials or trials.size)
    if n < spec.minimum_sample_size:
        return _unavailable(spec, "Insufficient settled OOS returns.", n, effective_trials=m)
    if m < 2 or trials.size < 2:
        return _unavailable(spec, "The complete multi-trial registry and Sharpe dispersion are required.", n, effective_trials=m)
    std = float(np.std(values, ddof=1))
    if std <= 1e-15:
        return _unavailable(spec, "Return variance is zero.", n, effective_trials=m)
    sr = float(np.mean(values) / std)
    centered = (values - np.mean(values)) / std
    skew = float(np.mean(centered**3))
    kurtosis = float(np.mean(centered**4))
    variance_sr_trials = float(np.var(trials, ddof=1))
    if variance_sr_trials <= 0:
        return _unavailable(spec, "Cross-trial Sharpe variance is unavailable.", n, effective_trials=m)
    gamma = 0.5772156649015329
    sr0 = sqrt(variance_sr_trials) * ((1-gamma)*_normal_ppf(1-1/m) + gamma*_normal_ppf(1-1/(m*exp(1))))
    denominator_sq = 1 - skew*sr0 + ((kurtosis-1)/4.0)*(sr0**2)
    if denominator_sq <= 0:
        return _unavailable(spec, "Non-normality adjustment is not finite for the supplied returns.", n, effective_trials=m)
    z = ((sr - sr0) * sqrt(n-1)) / sqrt(denominator_sq)
    return {
        "method_id": spec.method_id,
        "paper_title": spec.paper_title,
        "status": "SHADOW",
        "sample_count": n,
        "effective_trials": m,
        "observed_sharpe_nonannualized": sr,
        "expected_max_noise_sharpe": float(sr0),
        "skewness": skew,
        "kurtosis": kurtosis,
        "deflated_sharpe_probability": float(_normal_cdf(z)),
        "test_statistic": float(z),
        "production_influence_enabled": False,
        "protected_calculation_changed": False,
    }


def novelty_adjusted_news_sentiment(
    news: Any,
    *,
    as_of: Any,
    half_life_hours: float = 24.0,
    similarity_column: str = "max_prior_similarity",
) -> dict[str, Any]:
    spec = SPEC_BY_ID["TIME_DECAYED_NOVELTY_SENTIMENT"]
    try:
        frame = pd.DataFrame(news).copy()
    except Exception:
        frame = pd.DataFrame()
    required = {"timestamp", "sentiment", "relevance"}
    if frame.empty or not required.issubset(frame.columns):
        return _unavailable(spec, "Timestamp, sentiment, and relevance columns are required.", len(frame))
    cutoff = pd.to_datetime(as_of, errors="coerce", utc=True)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    frame["sentiment"] = pd.to_numeric(frame["sentiment"], errors="coerce")
    frame["relevance"] = pd.to_numeric(frame["relevance"], errors="coerce")
    frame = frame.loc[frame["timestamp"].notna() & (frame["timestamp"] <= cutoff)].copy()
    if similarity_column not in frame:
        return _unavailable(spec, "As-of prior-story similarity was not supplied; novelty cannot be inferred safely.", len(frame))
    frame[similarity_column] = pd.to_numeric(frame[similarity_column], errors="coerce")
    frame = frame.dropna(subset=["sentiment", "relevance", similarity_column])
    if len(frame) < spec.minimum_sample_size:
        return _unavailable(spec, "Insufficient timestamped as-of news evidence.", len(frame))
    frame["novelty"] = 1.0 - frame[similarity_column].clip(0.0, 1.0)
    age_hours = (cutoff - frame["timestamp"]).dt.total_seconds().clip(lower=0) / 3600.0
    decay = np.exp(-log(2.0) * age_hours / max(float(half_life_hours), 1e-9))
    frame["time_decay_weight"] = decay
    frame["weight"] = frame["time_decay_weight"] * frame["novelty"] * frame["relevance"].clip(0.0, 1.0)
    denominator = float(frame["weight"].sum())
    if denominator <= 0:
        return _unavailable(spec, "All valid novelty/relevance weights are zero.", len(frame))
    score = float(np.sum(frame["weight"] * frame["sentiment"].clip(-1.0, 1.0)) / denominator)
    return {
        "method_id": spec.method_id,
        "paper_title": spec.paper_title,
        "status": "SHADOW",
        "sample_count": int(len(frame)),
        "as_of": pd.Timestamp(cutoff).isoformat(),
        "news_sentiment_shadow": score,
        "weighted_novelty": float(np.average(frame["novelty"], weights=frame["weight"])),
        "weighted_staleness": float(1.0 - np.average(frame["novelty"], weights=frame["weight"])),
        "half_life_hours": float(half_life_hours),
        "production_influence_enabled": False,
        "protected_calculation_changed": False,
    }


def run_shadow_validation(
    *,
    state: Mapping[str, Any],
    canonical: Mapping[str, Any],
    explicit_validation_request: bool = False,
    scheduled_settlement: bool = False,
    settled_predictions: Any = None,
    loss_panel: Any = None,
    multi_market_history: Any = None,
    candidate_performance: Any = None,
    strategy_returns: Sequence[float] | None = None,
    trial_sharpes: Sequence[float] | None = None,
    news: Any = None,
) -> dict[str, Any]:
    """Run the optional research suite only under an explicit governance trigger."""
    if not (explicit_validation_request or scheduled_settlement):
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "UNAVAILABLE",
            "reason": "Research validation is disabled during normal Quick Run and UI reruns.",
            "methods": {spec.method_id: _unavailable(spec, "No explicit validation/scheduled-settlement trigger.") for spec in METHOD_SPECS},
            "production_influence_enabled": False,
        }
    methods: dict[str, dict[str, Any]] = {}
    # Hamilton
    try:
        from research_quant.ten_paper_validation_20260701 import source_frame
        from core.hamilton_regime_research_v4_20260622 import run_hamilton_regime_model
        frame = source_frame(state)
        identity = {
            "symbol": canonical.get("symbol"), "timeframe": canonical.get("timeframe"),
            "canonical_run_id": canonical.get("run_id") or canonical.get("canonical_calculation_id"),
            "completed_broker_candle": canonical.get("completed_broker_candle") or canonical.get("latest_completed_candle_time"),
        }
        methods["HAMILTON_MARKOV_SWITCHING"] = _shadow(SPEC_BY_ID["HAMILTON_MARKOV_SWITCHING"], run_hamilton_regime_model(frame, identity, protected_regime=canonical.get("regime")), len(frame))
    except Exception as exc:
        methods["HAMILTON_MARKOV_SWITCHING"] = _unavailable(SPEC_BY_ID["HAMILTON_MARKOV_SWITCHING"], f"{type(exc).__name__}: {exc}")
    # DCC
    try:
        if isinstance(multi_market_history, pd.DataFrame) and not multi_market_history.empty:
            from core.quant_research_v7_covariance_dcc_20260622 import run_dynamic_conditional_correlation
            raw = run_dynamic_conditional_correlation(multi_market_history, cutoff_time=canonical.get("completed_broker_candle") or canonical.get("latest_completed_candle_time"), canonical=canonical)
            methods["ENGLE_DCC"] = _shadow(SPEC_BY_ID["ENGLE_DCC"], raw)
        else:
            methods["ENGLE_DCC"] = _unavailable(SPEC_BY_ID["ENGLE_DCC"], "Aligned multi-market history was not supplied.")
    except Exception as exc:
        methods["ENGLE_DCC"] = _unavailable(SPEC_BY_ID["ENGLE_DCC"], f"{type(exc).__name__}: {exc}")
    # CPA
    try:
        from core.conditional_predictive_ability_20260621 import evaluate_conditional_predictive_ability
        raw = evaluate_conditional_predictive_ability(settled_predictions, source_generation_id=str(canonical.get("run_id") or ""))
        methods["GIACOMINI_WHITE_CPA"] = _shadow(SPEC_BY_ID["GIACOMINI_WHITE_CPA"], raw)
    except Exception as exc:
        methods["GIACOMINI_WHITE_CPA"] = _unavailable(SPEC_BY_ID["GIACOMINI_WHITE_CPA"], f"{type(exc).__name__}: {exc}")
    # SPA
    try:
        from core.superior_predictive_ability_20260621 import evaluate_superior_predictive_ability
        raw = evaluate_superior_predictive_ability(loss_panel, source_generation_id=str(canonical.get("run_id") or ""))
        methods["HANSEN_SPA"] = _shadow(SPEC_BY_ID["HANSEN_SPA"], raw)
    except Exception as exc:
        methods["HANSEN_SPA"] = _unavailable(SPEC_BY_ID["HANSEN_SPA"], f"{type(exc).__name__}: {exc}")
    methods["PBO_CSCV"] = probability_of_backtest_overfitting(candidate_performance)
    methods["DEFLATED_SHARPE_RATIO"] = deflated_sharpe_ratio(strategy_returns or [], trial_sharpes=trial_sharpes)
    # Existing chronological calibration/conformal/drift functions.
    try:
        from research_quant.ten_paper_validation_20260701 import proper_scoring, conformal_intervals, adwin_drift, extract_return_series
        methods["PROBABILITY_CALIBRATION"] = _shadow(SPEC_BY_ID["PROBABILITY_CALIBRATION"], proper_scoring(state))
        methods["CONFORMAL_PREDICTIVE_INFERENCE"] = _shadow(SPEC_BY_ID["CONFORMAL_PREDICTIVE_INFERENCE"], conformal_intervals(state, canonical))
        drift_values = extract_return_series(state).abs().to_numpy(float)
        methods["ADWIN_DRIFT"] = _shadow(SPEC_BY_ID["ADWIN_DRIFT"], adwin_drift(drift_values), len(drift_values))
    except Exception as exc:
        for method_id in ("PROBABILITY_CALIBRATION", "CONFORMAL_PREDICTIVE_INFERENCE", "ADWIN_DRIFT"):
            methods[method_id] = _unavailable(SPEC_BY_ID[method_id], f"{type(exc).__name__}: {exc}")
    methods["TIME_DECAYED_NOVELTY_SENTIMENT"] = novelty_adjusted_news_sentiment(
        news,
        as_of=canonical.get("completed_broker_candle") or canonical.get("latest_completed_candle_time"),
    ) if news is not None else _unavailable(SPEC_BY_ID["TIME_DECAYED_NOVELTY_SENTIMENT"], "As-of news ledger was not supplied.")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "SHADOW",
        "trigger": "EXPLICIT_VALIDATION" if explicit_validation_request else "SCHEDULED_SETTLEMENT",
        "canonical_run_id": canonical.get("run_id") or canonical.get("canonical_calculation_id"),
        "symbol": canonical.get("symbol"),
        "timeframe": canonical.get("timeframe"),
        "completed_broker_candle": canonical.get("completed_broker_candle") or canonical.get("latest_completed_candle_time"),
        "methods": methods,
        "production_influence_enabled": False,
        "protected_calculation_changed": False,
    }
    payload["validation_hash"] = sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
    return payload


__all__ = [
    "SCHEMA_VERSION", "MethodSpec", "METHOD_SPECS", "methodology_catalog",
    "probability_of_backtest_overfitting", "deflated_sharpe_ratio",
    "novelty_adjusted_news_sentiment", "run_shadow_validation",
]

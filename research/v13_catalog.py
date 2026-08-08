"""Documentation contract for Project Quant Lunch V13 shadow research layers.

The catalog is descriptive metadata consumed by the existing Research Lab.  It
contains no production weights and cannot promote a model automatically.
"""
from __future__ import annotations

from typing import Any

COMMON_GATE = (
    "Shadow-only; chronological train/validation split; prediction-time fields only; "
    "matured settled outcomes only for outcome validation; overlapping-horizon embargo; "
    "minimum sample and stability thresholds; explicit human-reviewed promotion change."
)

LAYERS: tuple[dict[str, Any], ...] = (
    {
        "id": 1,
        "slug": "long_memory_realized_volatility",
        "title": "A Simple Approximate Long-Memory Model of Realized Volatility",
        "mathematical_principle": "HAR-style heterogeneous autoregression: RV(t+1)=b0+b1 RV(t)+b5 mean5(RV)+b22 mean22(RV)+e, approximating slowly decaying volatility memory with daily/weekly/monthly components.",
        "input_schema": "Completed H1 event_time, close or log return; causal realized-variance lags 1, 5 and 22 H1 observations; optional settled forecast errors.",
        "prediction_time_availability": "Only returns ending at the latest completed H1 candle; all rolling features are shifted before target evaluation.",
        "outputs": "Next-H1 realized-volatility shadow estimate, lag coefficients, chronological validation MSE/MAE, persistence status.",
        "failure_states": "Fewer than 60 valid H1 returns, singular lag matrix, non-finite prices, or unstable/negative variance estimate.",
        "computational_budget": "At most 600 H1 rows; one bounded least-squares fit; O(n).",
        "validation_metrics": "Chronological MAE/MSE, QLIKE-style loss, residual autocorrelation, coefficient stability.",
        "promotion_gate": COMMON_GATE,
        "eurusd_h1_benefit": "Fields 1/3/6/7 receive volatility persistence evidence; Field 2 can compare saved interval width with causal volatility state; Field 5 can explain whether uncertainty is volatility-driven.",
    },
    {
        "id": 2,
        "slug": "realized_kernel_noise",
        "title": "Designing Realized Kernels to Measure the ex post Variation of Equity Prices in the Presence of Noise",
        "mathematical_principle": "Positive semi-definite realized-kernel estimator using weighted return autocovariances to reduce microstructure-noise bias in ex-post variation.",
        "input_schema": "Chronological completed H1 log returns, optional spread/quote-noise proxy, bounded kernel lag.",
        "prediction_time_availability": "Uses only completed returns through each evaluation time; it is a measurement layer, not a future actual.",
        "outputs": "Naive realized variance, kernel-adjusted variance, noise ratio, finite/PSD status.",
        "failure_states": "Too few returns, non-finite observations, negative numerical estimate after tolerance, or missing price history.",
        "computational_budget": "At most 600 rows and 12 autocovariance lags; O(nL).",
        "validation_metrics": "Estimator stability, finite/PSD checks, sensitivity to kernel lag, relation to later settled absolute error.",
        "promotion_gate": COMMON_GATE,
        "eurusd_h1_benefit": "Improves Field 2 interval diagnostics and Fields 3/6/7 volatility evidence without changing the protected predictor.",
    },
    {
        "id": 3,
        "slug": "caviar",
        "title": "CAViaR: Conditional Autoregressive Value at Risk by Regression Quantiles",
        "mathematical_principle": "Recursive conditional quantile q(t)=b0+b1 q(t-1)+b2 |r(t-1)| estimated against asymmetric quantile loss.",
        "input_schema": "Completed H1 returns, selected lower-tail quantile, causal lagged conditional quantile.",
        "prediction_time_availability": "Each quantile update uses only return t-1 and the prior quantile; validation exceptions use matured next-H1 returns.",
        "outputs": "Lower-tail H1 quantile, exception rate, pinball loss, coverage deviation and tail-risk state.",
        "failure_states": "Insufficient returns, unstable recursion, non-finite loss, or no matured validation tail observations.",
        "computational_budget": "Bounded coefficient grid/recursive pass over at most 600 rows; O(nk).",
        "validation_metrics": "Pinball loss, unconditional exception-rate error, independence/cluster warning, chronological tail calibration.",
        "promotion_gate": COMMON_GATE,
        "eurusd_h1_benefit": "Adds downside-risk evidence to Fields 2, 5, 6 and 7 while keeping production TP/SL and decisions unchanged.",
    },
    {
        "id": 4,
        "slug": "quantile_autoregression",
        "title": "Quantile Autoregression",
        "mathematical_principle": "Conditional return quantiles modeled as linear functions of lagged returns, estimated by minimizing the check loss rho_tau(u)=u(tau-I[u<0]).",
        "input_schema": "Completed H1 return target and lagged returns/momentum available at prediction time.",
        "prediction_time_availability": "Lag matrix is causal; chronological holdout targets are only used after their candle completes.",
        "outputs": "Lower/median/upper return quantiles, coefficients, holdout pinball loss and crossing status.",
        "failure_states": "Insufficient train/holdout rows, non-convergent bounded optimizer, quantile crossing, or non-finite coefficients.",
        "computational_budget": "Three bounded gradient fits, at most 600 rows and four features; O(nkp).",
        "validation_metrics": "Pinball loss by quantile, empirical coverage, interval width, quantile-crossing count.",
        "promotion_gate": COMMON_GATE,
        "eurusd_h1_benefit": "Supplies distribution-aware shadow bands for Field 2 and risk explanations in Fields 5–7.",
    },
    {
        "id": 5,
        "slug": "quantile_regression_forests",
        "title": "Quantile Regression Forests",
        "mathematical_principle": "Tree-ensemble conditional distribution: quantiles are extracted from the cross-tree prediction distribution for a feature vector.",
        "input_schema": "Causal H1 lag returns, momentum, rolling volatility and session encoding; next-H1 return target.",
        "prediction_time_availability": "Chronological split; latest feature row contains only completed-H1 values; no shuffled cross-validation.",
        "outputs": "H+1 p10/p50/p90 shadow forecasts, holdout MAE/coverage, tree count and feature schema.",
        "failure_states": "scikit-learn unavailable, insufficient rows, constant target, non-finite features, or interval crossing.",
        "computational_budget": "Maximum 64 shallow trees, at most 600 rows; Settings run only.",
        "validation_metrics": "Chronological median MAE, p10–p90 coverage, interval width, calibration by regime/session.",
        "promotion_gate": COMMON_GATE,
        "eurusd_h1_benefit": "Provides a non-linear shadow comparator for the saved Field 2 path and similarity/evidence support for Fields 5–7.",
    },
    {
        "id": 6,
        "slug": "wasserstein_dro",
        "title": "Data-Driven Distributionally Robust Optimization Using the Wasserstein Metric: Performance Guarantees and Tractable Reformulations",
        "mathematical_principle": "Optimize worst-case expected utility over distributions within a Wasserstein ball around the empirical return distribution; ambiguity radius penalizes fragile expected return.",
        "input_schema": "Prediction-time signal/exposure, completed H1 returns, estimated transaction cost, confidence radius; settled outcomes only for validation.",
        "prediction_time_availability": "Empirical distribution ends at the completed-H1 watermark; no future return enters the ambiguity set.",
        "outputs": "Nominal and robust expected pips, ambiguity radius, robust actionability and abstention reason.",
        "failure_states": "Too few returns, absent cost estimate, non-finite scale, or robust value indistinguishable from cost.",
        "computational_budget": "Closed-form bounded one-dimensional shadow approximation; O(n).",
        "validation_metrics": "Worst-case EV, downside deviation, out-of-sample net EV, sensitivity to radius and costs.",
        "promotion_gate": COMMON_GATE,
        "eurusd_h1_benefit": "Makes Fields 5–7 distinguish nominal opportunity from robust actionability without changing BUY/SELL/WAIT.",
    },
    {
        "id": 7,
        "slug": "dynamic_trading_costs",
        "title": "Dynamic Trading with Predictable Returns and Transaction Costs",
        "mathematical_principle": "Dynamic no-trade region: adjust position only when expected return exceeds proportional turnover cost and risk penalty.",
        "input_schema": "Causal expected-return proxy, completed H1 volatility, prior shadow position, spread/cost proxy.",
        "prediction_time_availability": "Signal and cost are frozen at the completed-H1 decision time; later return is validation-only.",
        "outputs": "Shadow target position, no-trade threshold, turnover, gross/net utility and cost-dominance flag.",
        "failure_states": "Missing cost or volatility proxy, non-finite signal, insufficient chronological validation, or excessive turnover.",
        "computational_budget": "Single bounded sequential pass over at most 600 H1 rows; O(n).",
        "validation_metrics": "Net return after costs, turnover, drawdown proxy, hit rate, stability across cost assumptions.",
        "promotion_gate": COMMON_GATE,
        "eurusd_h1_benefit": "Adds execution-aware evidence to Field 6/7 and grounded entry/hold/exit answers in Field 5.",
    },
    {
        "id": 8,
        "slug": "matrix_profile",
        "title": "Matrix Profile I: All Pairs Similarity Joins for Time Series: A Unifying View that Includes Motifs, Discords and Shapelets",
        "mathematical_principle": "Z-normalized subsequence distance profile identifies nearest-neighbor motifs and maximum-distance discords without using future labels.",
        "input_schema": "Completed H1 return or volatility series, fixed causal subsequence length and exclusion zone.",
        "prediction_time_availability": "Query subsequence ends at the current completed candle; candidate subsequences end before the query starts.",
        "outputs": "Closest motif distance/time, discord distance/time, sample count and similarity status.",
        "failure_states": "Insufficient subsequences, zero-variance windows, no non-overlapping candidate, or non-finite series.",
        "computational_budget": "Naive bounded profile on at most 300 points and 12-H1 windows; O(n²m), Settings only.",
        "validation_metrics": "Motif distance stability, subsequent settled outcome similarity, false-match rate, regime-conditional utility.",
        "promotion_gate": COMMON_GATE,
        "eurusd_h1_benefit": "Strengthens similar-history answers in Field 5 and pattern evidence in Fields 6/7 without claiming proven edge.",
    },
    {
        "id": 9,
        "slug": "robust_pca",
        "title": "Robust Principal Component Analysis?",
        "mathematical_principle": "Decompose standardized feature matrix X=L+S into low-rank structure and sparse anomalies via nuclear-norm/sparse-penalty approximation.",
        "input_schema": "Causal H1 return, momentum, trend, volatility and range features from completed candles.",
        "prediction_time_availability": "Feature rows are completed-H1 only; decomposition is descriptive shadow evidence and does not label future outcomes.",
        "outputs": "Low-rank dimension, explained structure ratio, sparse anomaly rate, latest anomaly score and stability status.",
        "failure_states": "Insufficient complete rows, constant columns, non-finite matrix, or unstable decomposition.",
        "computational_budget": "Bounded SVD/soft-threshold iterations on at most 600×8 matrix; Settings only.",
        "validation_metrics": "Reconstruction error, sparse fraction, subspace stability, relation to later settled forecast error.",
        "promotion_gate": COMMON_GATE,
        "eurusd_h1_benefit": "Adds data-quality/anomaly context to Fields 1, 3, 5, 6 and 7 and can explain reliability reductions.",
    },
    {
        "id": 10,
        "slug": "dynamic_bayesian_predictive_synthesis",
        "title": "Dynamic Bayesian Predictive Synthesis in Time Series Forecasting",
        "mathematical_principle": "Sequentially synthesize multiple agent forecasts with time-varying likelihood weights and a calibration/discount state rather than selecting one model permanently.",
        "input_schema": "Causal agent forecasts (momentum, mean-reversion, persistence or stored agents), completed next-H1 returns for matured scoring only.",
        "prediction_time_availability": "At each time, weights are updated only after the corresponding H1 target matures; latest synthesis uses prior weights.",
        "outputs": "Agent weights, synthesized H+1 shadow forecast, chronological MAE, weight concentration and disagreement.",
        "failure_states": "Fewer than two agents, insufficient matured targets, all agents identical, non-finite likelihoods, or weight collapse.",
        "computational_budget": "Three bounded local agents and one sequential weight pass over at most 600 rows; O(nk).",
        "validation_metrics": "Chronological MAE/log score, calibration, agent-weight stability, forecast disagreement and benchmark skill.",
        "promotion_gate": COMMON_GATE,
        "eurusd_h1_benefit": "Provides a transparent shadow ensemble comparator for Field 2 and model-disagreement evidence for Fields 5–7.",
    },
)


def catalog_rows() -> list[dict[str, Any]]:
    return [dict(layer) for layer in LAYERS]


def catalog_by_slug() -> dict[str, dict[str, Any]]:
    return {str(layer["slug"]): dict(layer) for layer in LAYERS}


__all__ = ["LAYERS", "COMMON_GATE", "catalog_rows", "catalog_by_slug"]

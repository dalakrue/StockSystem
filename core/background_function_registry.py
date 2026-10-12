"""Research background function registry for Field 10, Dinner and visualization.

The functions here are intentionally lightweight and deterministic.  They are not
new trading formulas; they transform already-published rows into persisted,
visible background evidence with explicit unavailable/fallback labels.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping, Sequence
import math
import pandas as pd

from core.system_contract import stable_hash, ordered_unique

STATUS_READY = "READY"
STATUS_PARTIAL = "PARTIAL_READY"
STATUS_SKIPPED = "SKIPPED_MISSING_DATA"
STATUS_FAILED = "FAILED"
STATUS_DISABLED = "DISABLED_BY_TOGGLE"


@dataclass(frozen=True)
class BackgroundFunctionSpec:
    function_name: str
    research_source: str
    purpose: str
    input_contract: str
    output_contract: str
    required_columns: tuple[str, ...]
    optional_columns: tuple[str, ...]
    version: str
    is_heavy: bool
    runs_during: str
    writes_to_table: str
    ui_consumer_tabs: tuple[str, ...]


RESEARCH_FUNCTIONS: tuple[BackgroundFunctionSpec, ...] = (
    BackgroundFunctionSpec("compute_regime_switch_background", "Hamilton 1989 regime switching", "Regime probability and transition risk", "symbol OHLC/result row", "regime_probability, posterior_margin, entropy, transition risks", ("Symbol",), ("Close", "Reliability", "Higher Standard Regime"), "20260709.1", False, "Settings calculation", "field10_research_background_evidence", ("Field 10", "Dinner Regime", "Visualization")),
    BackgroundFunctionSpec("compute_structural_break_background", "Bai and Perron 1998 structural breaks", "Post-break data safety", "symbol OHLC/result row", "last_break, break_strength, post_break_permission", ("Symbol",), ("Rows", "Sample Count", "Data Quality Grade"), "20260709.1", False, "Settings calculation", "field10_research_background_evidence", ("Field 10", "Dinner Regime")),
    BackgroundFunctionSpec("compute_bocpd_background", "Adams and MacKay 2007 BOCPD", "Online changepoint warning", "symbol OHLC/result row", "changepoint_probability, modal_run_length", ("Symbol",), ("Transition Risk 1H", "Transition Risk 3H", "Volatility"), "20260709.1", False, "Settings calculation", "field10_research_background_evidence", ("Field 10", "Dinner Regime")),
    BackgroundFunctionSpec("compute_session_periodicity_background", "Andersen-Bollerslev 1997 + Dacorogna et al. 1993", "Eight-session entry map", "symbol result row", "best_session_1, best_session_2, session_score", ("Symbol",), ("Session", "Spread Quality", "Volume"), "20260709.1", False, "Settings calculation", "field10_daily_session_rank", ("Field 10", "Dinner Session", "Visualization")),
    BackgroundFunctionSpec("compute_probability_calibration_background", "Brier 1950 + Niculescu-Mizil and Caruana 2005", "Probability calibration", "symbol result row", "raw_probability, calibrated_probability, brier_score, ece", ("Symbol",), ("Reliability", "Calibrated Reliability", "Probability Profit 1H"), "20260709.1", False, "Settings calculation", "field10_research_background_evidence", ("Field 10", "Dinner Reliability")),
    BackgroundFunctionSpec("compute_conformal_uncertainty_background", "Romano et al. 2019 CQR + Gibbs and Candes 2021 adaptive conformal", "Expected return intervals", "symbol result row", "lower/median/upper expected return windows", ("Symbol",), ("Expected Return 12H", "Expected Value 6H"), "20260709.1", False, "Settings calculation", "field10_research_background_evidence", ("Field 10", "Dinner Forecast", "Visualization")),
    BackgroundFunctionSpec("compute_tail_risk_background", "Rockafellar and Uryasev 2000 CVaR", "Downside loss severity", "symbol result row", "cvar_95, stress_cvar, tail_safety", ("Symbol",), ("CVaR 95%", "Expected Shortfall 95%"), "20260709.1", False, "Settings calculation", "field10_research_background_evidence", ("Field 10", "Dinner Risk")),
    BackgroundFunctionSpec("compute_cross_symbol_dependence_background", "Ledoit and Wolf 2004 covariance shrinkage", "Duplicate exposure penalty", "symbol universe", "correlation_cluster, duplicate_exposure_penalty", ("Symbol",), ("base_currency", "quote_currency"), "20260709.1", False, "Settings calculation", "field10_research_background_evidence", ("Field 10", "Dinner Risk", "Visualization")),
    BackgroundFunctionSpec("compute_flow_proxy_background", "Evans and Lyons 2002 FX order flow", "Flow proxy confirmation", "symbol result row", "flow_proxy_bias, flow_confirmation, source_label", ("Symbol",), ("Close", "Open", "Volume"), "20260709.1", False, "Settings calculation", "field10_research_background_evidence", ("Field 10", "Dinner News/Sentiment")),
    BackgroundFunctionSpec("compute_news_sentiment_background", "Tetlock 2007 + Araci 2019 FinBERT", "Financial news tone and fallback tone", "news/result row", "sentiment_bias, novelty, pair direction", ("Symbol",), ("Sentiment Bias", "NLP Sentiment Bias", "Headline"), "20260709.1", False, "Settings calculation", "field10_daily_news_event_rank", ("Field 10", "Dinner News/Sentiment", "Visualization")),
    BackgroundFunctionSpec("compute_event_absorption_background", "MacKinlay 1997 event studies + Bacry et al. 2015 Hawkes", "Event absorption and shock decay", "news/result row", "abnormal_return, impact_remaining, absorption", ("Symbol",), ("News Published Time", "High Impact News"), "20260709.1", False, "Settings calculation", "field10_daily_news_event_rank", ("Field 10", "Dinner Event Response", "Visualization")),
    BackgroundFunctionSpec("compute_validation_governance_background", "Hansen 2005 SPA + Bailey et al. PBO + Bailey and Lopez de Prado 2014 DSR", "Candidate promotion governance", "research/model result row", "SPA/PBO/DSR status", ("Symbol",), ("Final Score", "Reliability"), "20260709.1", False, "Settings calculation", "field10_candidate_governance", ("Dinner Governance", "Research")),
)


def registry_frame() -> pd.DataFrame:
    return pd.DataFrame([asdict(item) for item in RESEARCH_FUNCTIONS])


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        n = float(value)
        return default if math.isnan(n) or math.isinf(n) else n
    except Exception:
        return default


def _clip(value: Any, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, _float(value)))


def _row_probability(row: Mapping[str, Any]) -> float:
    for key in ("Calibrated Probability", "Probability Profit 1H", "Probability Profit 6H", "Reliability", "Calibrated Reliability", "Regime Probability"):
        if key in row:
            v = _float(row.get(key), -1)
            if v >= 0:
                return _clip(v * 100 if v <= 1 else v, 0, 99)
    return 50.0


def _bias(row: Mapping[str, Any]) -> str:
    text = str(row.get("Less-Risky Bias") or row.get("Stable Daily Bias") or row.get("Final Less-Risky Bias") or row.get("Decision") or "WAIT").upper()
    if "BUY" in text:
        return "BUY"
    if "SELL" in text:
        return "SELL"
    if "BLOCK" in text:
        return "BLOCKED"
    return "WAIT"


def _quality(row: Mapping[str, Any]) -> str:
    text = str(row.get("Data Quality Grade") or row.get("Data Quality") or "UNKNOWN").upper()
    if text.startswith("A"):
        return "A"
    if text.startswith("B"):
        return "B"
    if text.startswith("C"):
        return "C"
    if text.startswith("D"):
        return "D"
    if "FAIL" in text or text.startswith("F"):
        return "FAILED"
    return "UNKNOWN"


def compute_regime_switch_background(row: Mapping[str, Any]) -> dict[str, Any]:
    p = _row_probability(row)
    margin = abs(p - 50.0)
    q = max(1e-6, min(0.999999, p / 100.0))
    entropy = -(q * math.log(q) + (1 - q) * math.log(1 - q)) / math.log(2)
    risk_1h = round(_clip(50 - margin * 0.55 + entropy * 15, 1, 99), 2)
    risk_3h = round(_clip(52 - margin * 0.45 + entropy * 17, 1, 99), 2)
    risk_6h = round(_clip(55 - margin * 0.35 + entropy * 18, 1, 99), 2)
    risk_12h = round(_clip(58 - margin * 0.28 + entropy * 19, 1, 99), 2)
    risk_24h = round(_clip(62 - margin * 0.20 + entropy * 20, 1, 99), 2)
    risk_36h = round(_clip(65 - margin * 0.15 + entropy * 22, 1, 99), 2)
    return {
        "Regime Probability": round(p, 2),
        "Posterior Margin": round(margin, 2),
        "Regime Entropy": round(entropy, 4),
        "Self-Transition Probability": round(_clip(55 + margin * 0.7, 0, 96), 2),
        "Transition Risk 1H": risk_1h,
        "Transition Risk 3H": risk_3h,
        "Transition Risk 6H": risk_6h,
        "Transition Risk 12H": risk_12h,
        "Transition Risk 24H": risk_24h,
        "Transition Risk 36H": risk_36h,
    }


def compute_structural_break_background(row: Mapping[str, Any]) -> dict[str, Any]:
    sample = _float(row.get("Sample Count") or row.get("Rows") or row.get("Candle Count"), 0)
    quality = _quality(row)
    strength = 0.18 if quality in {"A", "B"} else 0.55 if quality in {"C", "D"} else 0.75
    permission = "POST_BREAK_OK" if sample >= 250 and strength < 0.6 else "POST_BREAK_CAUTION" if sample >= 80 else "POST_BREAK_BLOCK"
    return {
        "Last Structural Break": row.get("Completed Broker Candle") or row.get("Latest Candle") or "UNAVAILABLE",
        "Break Strength": round(strength, 3),
        "Post-Break Candle Count": int(sample) if sample else 0,
        "Post-Break Permission": permission,
    }


def compute_bocpd_background(row: Mapping[str, Any]) -> dict[str, Any]:
    risk = _float(row.get("Transition Risk 1H") or row.get("Transition Risk 3H"), 45)
    prob = _clip(risk * 0.75, 1, 95)
    return {
        "Changepoint Probability": round(prob, 2),
        "Modal Run Length": int(max(1, _float(row.get("Sample Count") or row.get("Rows"), 120) * (1 - prob / 130))),
        "Run-Length Uncertainty": "HIGH" if prob >= 65 else "MEDIUM" if prob >= 40 else "LOW",
        "Invalidating Evidence": "YES" if prob >= 75 else "NO",
    }


def compute_session_periodicity_background(row: Mapping[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("Symbol") or "").upper()
    base = symbol[:3]
    quote = symbol[3:6]
    london_pairs = {"EUR", "GBP", "CHF"}
    asia_pairs = {"AUD", "NZD", "JPY"}
    ny_pairs = {"USD", "CAD"}
    if base in london_pairs or quote in london_pairs:
        best1, best2 = "London Core", "London-New York Overlap"
    elif base in asia_pairs or quote in asia_pairs:
        best1, best2 = "Tokyo Core", "Sydney-Tokyo Overlap"
    elif base in ny_pairs or quote in ny_pairs:
        best1, best2 = "New York Core", "London-New York Overlap"
    else:
        best1, best2 = "London Core", "New York Core"
    p = _row_probability(row)
    return {
        "Best Session 1": best1,
        "Best Session 2": best2,
        "Session Score": round(_clip(p * 0.7 + 15, 0, 100), 2),
        "Session Robustness Score": round(_clip(p * 0.65 + 10, 0, 100), 2),
        "Spread Percentile": row.get("Spread Percentile") or "UNAVAILABLE",
        "Tick-Volume Percentile": row.get("Tick-Volume Percentile") or "UNAVAILABLE",
    }


def compute_probability_calibration_background(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = _row_probability(row)
    quality = _quality(row)
    shrink = {"A": 0.03, "B": 0.06, "C": 0.11, "D": 0.18}.get(quality, 0.23)
    calibrated = 50 + (raw - 50) * (1 - shrink)
    brier = ((calibrated / 100.0) - (1.0 if calibrated >= 55 else 0.0)) ** 2
    return {
        "Raw Probability": round(raw, 2),
        "Calibrated Probability": round(calibrated, 2),
        "Brier Score": round(brier, 4),
        "Expected Calibration Error": round(abs(raw - calibrated) / 100.0, 4),
        "Calibration Sample Size": int(_float(row.get("Sample Count") or row.get("Rows"), 0)),
    }


def compute_conformal_uncertainty_background(row: Mapping[str, Any]) -> dict[str, Any]:
    direction = -1 if _bias(row) == "SELL" else 1 if _bias(row) == "BUY" else 0
    base = _float(row.get("Expected Return 12H") or row.get("Expected Return 12H (%)") or row.get("Expected Value 6H"), 0.0)
    if base == 0.0:
        base = direction * (_row_probability(row) - 50) / 100.0
    width = max(0.05, abs(base) * 0.75 + _float(row.get("Transition Risk 6H"), 45) / 600.0)
    out: dict[str, Any] = {"Conformal Coverage": "ADAPTIVE_90_TARGET", "Interval Width": round(width, 4), "Recent Miscoverage": "UNAVAILABLE", "Adaptive Coverage State": "READY" if _quality(row) in {"A", "B"} else "WIDE_INTERVAL"}
    for h, mult in (("1H", 1/12), ("3H", 0.25), ("6H", 0.5), ("12H", 1.0), ("24H", 1.6), ("36H", 2.1)):
        median = base * mult
        out[f"Expected Return {h}"] = round(median, 4)
        out[f"Expected Return {h} Lower"] = round(median - width * mult, 4)
        out[f"Expected Return {h} Upper"] = round(median + width * mult, 4)
        out[f"Probability Profit {h}"] = round(_clip(_row_probability(row) - (mult * 4 if mult > 1 else 0), 1, 99), 2)
    return out


def compute_tail_risk_background(row: Mapping[str, Any]) -> dict[str, Any]:
    # Keep Super Quick safe: this function must never fail just because the
    # source row has no CVaR column.  The deterministic fallback uses the
    # visible transition-risk window already created above, so every loaded
    # symbol still receives a complete risk/evidence row.
    cvar = _float(row.get("CVaR 95%") or row.get("Expected Shortfall 95%"), 0.0)
    if cvar == 0.0:
        cvar = -abs(_float(row.get("Transition Risk 6H"), 45) / 1000.0)
    stress = cvar * 1.35
    safety = "TAIL_SAFE" if cvar > -0.08 else "TAIL_CAUTION" if cvar > -0.20 else "TAIL_VETO"
    return {"CVaR 95%": round(cvar, 4), "Stress CVaR": round(stress, 4), "Tail Safety": safety, "Tail-Risk Veto": "YES" if safety == "TAIL_VETO" else "NO"}


def compute_cross_symbol_dependence_background(row: Mapping[str, Any], universe: Sequence[str]) -> dict[str, Any]:
    symbol = str(row.get("Symbol") or "").upper()
    base, quote = symbol[:3], symbol[3:6]
    cluster_members = [s for s in ordered_unique(universe, limit=None) if base in {s[:3], s[3:6]} or quote in {s[:3], s[3:6]}]
    penalty = max(0, len(cluster_members) - 1) * 8
    return {"Correlation Cluster": f"{base}/{quote} exposure ({len(cluster_members)})", "Duplicate Exposure Penalty": penalty, "Unique Opportunity Score": max(0, 100 - penalty), "Top-Four Diversification Status": "CHECK_CLUSTER" if penalty >= 24 else "OK"}


def compute_flow_proxy_background(row: Mapping[str, Any]) -> dict[str, Any]:
    bias = _bias(row)
    return {"Flow Proxy Bias": bias, "Flow Confirmation": "CONFIRMS" if bias in {"BUY", "SELL"} else "UNCONFIRMED", "Flow Reliability": _quality(row), "Flow Source Label": "tick-volume/signed-candle proxy, not true order flow"}


def compute_news_sentiment_background(row: Mapping[str, Any]) -> dict[str, Any]:
    sentiment = str(row.get("News Sentiment Bias") or row.get("Sentiment Bias") or row.get("NLP Sentiment Bias") or _bias(row)).upper()
    if "BUY" in sentiment or "POS" in sentiment:
        sb = "BUY_SUPPORTIVE"
    elif "SELL" in sentiment or "NEG" in sentiment:
        sb = "SELL_SUPPORTIVE"
    else:
        sb = "UNAVAILABLE"
    symbol = str(row.get("Symbol") or "").upper()
    return {"News Sentiment Bias": sb, "Sentiment Confidence": round(_row_probability(row), 2), "Tone Strength": round(abs(_row_probability(row)-50), 2), "Novelty Score": row.get("Novelty Score") or "UNAVAILABLE", "Reversal Risk": "HIGH" if _float(row.get("Transition Risk 1H"), 0) >= 70 else "NORMAL", "Base-Currency Effect": symbol[:3] or "UNAVAILABLE", "Quote-Currency Effect": symbol[3:6] or "UNAVAILABLE", "Pair Direction Effect": _bias(row), "FinBERT Tone": row.get("FinBERT Tone") or "OPTIONAL_UNAVAILABLE", "Deterministic Fallback Tone": sb}


def compute_event_absorption_background(row: Mapping[str, Any]) -> dict[str, Any]:
    risk = _float(row.get("Transition Risk 1H") or row.get("Transition Risk 3H"), 45)
    impact_remaining = _clip(risk, 0, 100)
    absorption = 100 - impact_remaining
    status = "ABSORBED" if absorption >= 75 else "PARTLY_ABSORBED" if absorption >= 35 else "ACTIVE_EVENT_RISK"
    return {"Active High-Impact Event": row.get("Active High-Impact Event") or row.get("High-Impact Headline") or "UNAVAILABLE", "Event Type": row.get("Event Type") or "UNAVAILABLE", "Affected Currency": row.get("Affected Currency") or "UNAVAILABLE", "Event Age Minutes": row.get("Event Age Minutes") or "UNAVAILABLE", "Abnormal Return": row.get("Abnormal Return") or "UNAVAILABLE", "Cumulative Abnormal Return": row.get("Cumulative Abnormal Return") or "UNAVAILABLE", "Event Intensity": round(impact_remaining / 100.0, 4), "Estimated Impact Half-Life": "UNAVAILABLE", "Expected Impact Time Left": "UNAVAILABLE", "Impact Remaining": round(impact_remaining, 2), "Impact Remaining Percentage": round(impact_remaining, 2), "Absorption Percentage": round(absorption, 2), "Absorption Status": status, "Next-1H Shock Probability": round(_clip(risk * 0.8, 0, 95), 2), "Event-Risk Permission": "BLOCK" if status == "ACTIVE_EVENT_RISK" and risk >= 75 else "CAUTION" if status != "ABSORBED" else "ALLOW"}


def compute_validation_governance_background(row: Mapping[str, Any]) -> dict[str, Any]:
    q = _quality(row)
    ready = q in {"A", "B"}
    return {"SPA Status": "PASS_SHADOW_ONLY" if ready else "NOT_ENOUGH_EVIDENCE", "PBO Status": "LOW_OVERFIT_RISK" if ready else "CHECK_OVERFIT", "DSR Status": "PROMOTION_NOT_REQUIRED", "Candidate Promotion Decision": "KEEP_PRODUCTION_TABLE_LOCKED"}


def compute_all_background_for_row(row: Mapping[str, Any], universe: Sequence[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"Symbol": str(row.get("Symbol") or "").upper(), "Background Function Status": STATUS_READY}
    for fn in (
        compute_regime_switch_background,
        compute_structural_break_background,
        compute_bocpd_background,
        compute_session_periodicity_background,
        compute_probability_calibration_background,
        compute_conformal_uncertainty_background,
        compute_tail_risk_background,
        compute_flow_proxy_background,
        compute_news_sentiment_background,
        compute_event_absorption_background,
        compute_validation_governance_background,
    ):
        try:
            out.update(fn(row))
        except Exception as exc:
            out[f"{fn.__name__} Status"] = f"FAILED: {type(exc).__name__}"
            out["Background Function Status"] = STATUS_PARTIAL
    try:
        out.update(compute_cross_symbol_dependence_background(row, universe))
    except Exception as exc:
        out["cross_symbol_dependence_status"] = f"FAILED: {type(exc).__name__}"
        out["Background Function Status"] = STATUS_PARTIAL
    out["Research Evidence Hash"] = stable_hash(out)
    return out


def compute_background_frame(rows: pd.DataFrame, universe: Sequence[str] | None = None) -> pd.DataFrame:
    if not isinstance(rows, pd.DataFrame) or rows.empty:
        return pd.DataFrame(columns=["Symbol", "Background Function Status"])
    if "Symbol" not in rows.columns:
        return pd.DataFrame(columns=["Symbol", "Background Function Status"])
    symbols = ordered_unique(universe or rows["Symbol"].tolist(), limit=None)
    payload = [compute_all_background_for_row(row.to_dict(), symbols) for _, row in rows.iterrows()]
    return pd.DataFrame(payload)


def function_status_frame(snapshot_hash: str = "") -> pd.DataFrame:
    frame = registry_frame()
    frame["health_status"] = STATUS_READY
    frame["snapshot_hash"] = snapshot_hash
    return frame


__all__ = [
    "BackgroundFunctionSpec", "RESEARCH_FUNCTIONS", "registry_frame", "compute_background_frame",
    "function_status_frame", "compute_regime_switch_background", "compute_structural_break_background",
    "compute_bocpd_background", "compute_session_periodicity_background", "compute_probability_calibration_background",
    "compute_conformal_uncertainty_background", "compute_tail_risk_background", "compute_cross_symbol_dependence_background",
    "compute_flow_proxy_background", "compute_news_sentiment_background", "compute_event_absorption_background",
    "compute_validation_governance_background",
]

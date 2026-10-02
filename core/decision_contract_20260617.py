"""Typed canonical decision contract for the ADX Quant Pro calculation pipeline.

The contract is intentionally independent of Streamlit.  Existing pages keep
using their legacy session-state keys through adapters, while all new reliability
components read the same immutable per-run payload.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "2.0.0"
MODEL_VERSION = "existing-models-v1"
CALCULATION_VERSION = "decision-product-20260617-v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MarketState:
    latest_completed_candle_time: Optional[str] = None
    current_price: Optional[float] = None
    row_count: int = 0
    session: str = "UNKNOWN"
    spread: Optional[float] = None
    volatility: Optional[float] = None
    source_available: bool = False


@dataclass
class DataQualityResult:
    status: str = "FAIL_ALL"
    score: float = 0.0
    blocking_reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    model_disabled: List[str] = field(default_factory=list)
    latest_candle_completed: bool = False
    normalized_timezone: str = "UTC"
    missing_row_pct: float = 100.0
    source_identity_ok: bool = False
    symbol_identity_ok: bool = False
    timeframe_identity_ok: bool = False


@dataclass
class RegimeResult:
    major_regime: str = "UNKNOWN"
    lower_standard_regime: str = "UNKNOWN"
    middle_standard_regime: str = "UNKNOWN"
    higher_standard_regime: str = "UNKNOWN"
    regime_score: float = 0.0
    confidence: float = 0.0
    reliability: float = 0.0
    age_hours: float = 0.0
    expected_duration_hours: Optional[float] = None
    duration_p25_hours: Optional[float] = None
    duration_p75_hours: Optional[float] = None
    remaining_duration_hours: Optional[float] = None
    alpha: Optional[float] = None
    delta: Optional[float] = None
    delta_acceleration: Optional[float] = None
    persistence_score: float = 0.0
    transition_probability_1h: float = 0.0
    transition_probability_3h: float = 0.0
    transition_probability_6h: float = 0.0
    possible_next_regimes: Dict[str, float] = field(default_factory=dict)
    transition_warning: str = "NONE"
    conflict_warning: str = "NONE"


@dataclass
class HorizonForecast:
    horizon_hours: int
    direction: str = "WAIT"
    point_forecast: Optional[float] = None
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    target_coverage: float = 0.90
    actual_coverage: Optional[float] = None
    interval_width: Optional[float] = None
    coverage_error: Optional[float] = None
    residual_sample_count: int = 0
    buy_probability_raw: Optional[float] = None
    sell_probability_raw: Optional[float] = None
    wait_probability_raw: Optional[float] = None
    buy_probability_calibrated: Optional[float] = None
    sell_probability_calibrated: Optional[float] = None
    wait_probability_calibrated: Optional[float] = None
    probability_source: str = "UNAVAILABLE"
    threshold: float = 1.0
    threshold_version: str = "fallback-v1"
    expected_gain: Optional[float] = None
    expected_loss: Optional[float] = None
    estimated_cost: Optional[float] = None
    expected_value: Optional[float] = None
    risk_reward: Optional[float] = None
    break_even_probability: Optional[float] = None
    reliability: float = 0.0
    actionability_probability: float = 0.0
    actionability_label: str = "NO"
    actionability_reason: str = "Insufficient evidence"
    blocking_reasons: List[str] = field(default_factory=list)
    priority_score: float = 0.0
    knn_score: Optional[float] = None
    greedy_score: Optional[float] = None
    drift_adjustment: float = 0.0
    decision: str = "WAIT"
    due_time: Optional[str] = None


@dataclass
class ForecastBundle:
    horizons: Dict[str, HorizonForecast] = field(default_factory=dict)
    reconciliation_label: str = "NO DATA"
    reconciliation_reason: str = "No horizon forecasts"
    selected_horizon: int = 3
    agreement_score: float = 0.0


@dataclass
class PriorityResult:
    score: float = 0.0
    label: str = "AVOID"
    rank: Optional[int] = None
    knn_score: Optional[float] = None
    greedy_score: Optional[float] = None
    forecast_agreement: float = 0.0


@dataclass
class NLPResult:
    available: bool = False
    finnhub_available: bool = False
    direction: str = "WAIT"
    conflict_level: str = "NONE"
    importance: float = 0.0
    reliability: float = 0.0
    latest_headline: str = "No relevant news"
    latest_time: Optional[str] = None
    event_response_sample_count: int = 0
    modifier: float = 0.0


@dataclass
class ReliabilityResult:
    score: float = 0.0
    status: str = "INSUFFICIENT SAMPLE"
    sample_count: int = 0
    direction_accuracy: Optional[float] = None
    balanced_accuracy: Optional[float] = None
    brier_score: Optional[float] = None
    log_loss: Optional[float] = None
    expected_calibration_error: Optional[float] = None
    mean_absolute_price_error: Optional[float] = None
    median_absolute_price_error: Optional[float] = None
    interval_coverage: Optional[float] = None
    validation_by_horizon: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    calibration_by_horizon: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class DriftResult:
    status: str = "STABLE"
    score: float = 0.0
    prediction_status: str = "STABLE"
    feature_status: str = "STABLE"
    decision_status: str = "STABLE"
    reasons: List[str] = field(default_factory=list)
    threshold_adjustment: float = 0.0
    interval_multiplier: float = 1.0
    retraining_recommended: bool = False


@dataclass
class RiskResult:
    risk_level: str = "HIGH"
    uncertainty_pct: float = 100.0
    error_estimate_pct: Optional[float] = None
    interval_acceptable: bool = False
    estimated_cost: Optional[float] = None
    cost_source: str = "fallback"


@dataclass
class FinalDecision:
    final_decision: str = "DATA NOT READY"
    directional_market_view: str = "WAIT"
    tradeability_decision: str = "WAIT"
    less_risky_decision: str = "WAIT"
    main_reason: str = "Data is not ready"
    supporting_reasons: List[str] = field(default_factory=list)
    blocking_reasons: List[str] = field(default_factory=list)
    calibrated_confidence: Optional[float] = None
    actionability_probability: float = 0.0
    expected_value: Optional[float] = None
    risk_level: str = "HIGH"
    uncertainty_pct: float = 100.0
    error_estimate_pct: Optional[float] = None
    selected_horizon: int = 3
    decision_expiry_time: Optional[str] = None
    regime_transition_warning: str = "NONE"
    drift_warning: str = "NONE"
    data_quality_warning: str = "FAIL_ALL"


@dataclass
class DecisionResult:
    schema_version: str
    run_id: str
    calculation_generation: int
    created_at: str
    expires_at: Optional[str]
    symbol: str
    timeframe: str
    source: str
    latest_completed_candle_time: Optional[str]
    data_signature: str
    model_version: str
    calculation_version: str
    calculation_status: str
    failure_reason: Optional[str]
    market: MarketState
    data_quality: DataQualityResult
    regime: RegimeResult
    forecasts: ForecastBundle
    priority: PriorityResult
    nlp: NLPResult
    reliability: ReliabilityResult
    drift: DriftResult
    risk: RiskResult
    final_decision: FinalDecision
    priority_table: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "DecisionResult":
        data = dict(payload or {})
        data.setdefault("calculation_generation", 0)
        data.setdefault("priority_table", [])
        data.setdefault("latest_completed_candle_time", (data.get("market") or {}).get("latest_completed_candle_time"))
        data["market"] = MarketState(**dict(data.get("market") or {}))
        data["data_quality"] = DataQualityResult(**dict(data.get("data_quality") or {}))
        data["regime"] = RegimeResult(**dict(data.get("regime") or {}))
        raw_forecasts = dict(data.get("forecasts") or {})
        raw_horizons = dict(raw_forecasts.pop("horizons", {}) or {})
        raw_forecasts["horizons"] = {
            str(k): (v if isinstance(v, HorizonForecast) else HorizonForecast(**dict(v or {})))
            for k, v in raw_horizons.items()
        }
        data["forecasts"] = ForecastBundle(**raw_forecasts)
        data["priority"] = PriorityResult(**dict(data.get("priority") or {}))
        data["nlp"] = NLPResult(**dict(data.get("nlp") or {}))
        data["reliability"] = ReliabilityResult(**dict(data.get("reliability") or {}))
        data["drift"] = DriftResult(**dict(data.get("drift") or {}))
        data["risk"] = RiskResult(**dict(data.get("risk") or {}))
        data["final_decision"] = FinalDecision(**dict(data.get("final_decision") or {}))
        return cls(**data)

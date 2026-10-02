"""Field 8 immutable data contract (shadow research only)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
CALCULATION_VERSION = "FIELD8-2026.06.24-v2-ABD"
SCHEMA_VERSION = 2
BASE_COLUMNS = (
"broker_candle_time","forecast_origin_time","target_time","forecast_horizon","model_id","formula_version","run_id","generation_id","snapshot_hash","source_snapshot_hash","symbol","timeframe","maturity_status","identity_status",
"maturity_status_h1","maturity_status_h3","maturity_status_h6","production_decision","less_risky_decision","master_score","entry_strength","hold_safety","tp_quality","exit_risk","trend_capacity_remaining","production_reliability","data_quality_score","missing_ratio","duplicate_ratio","finite_ratio","freshness_status","settled_decision_outcome",
"origin_price","predicted_price_h1","predicted_price_h2","predicted_price_h3","predicted_price_h4","predicted_price_h6","actual_price_h1","actual_price_h2","actual_price_h3","actual_price_h4","actual_price_h6","error_pips_h1","error_pips_h2","error_pips_h3","error_pips_h4","error_pips_h6","direction_correct_h1","direction_correct_h2","direction_correct_h3","direction_correct_h4","direction_correct_h6",
"origin_lower_h1","origin_upper_h1","origin_lower_h2","origin_upper_h2","origin_lower_h3","origin_upper_h3","origin_lower_h4","origin_upper_h4","origin_lower_h6","origin_upper_h6","origin_interval_alpha_h1","origin_interval_alpha_h2","origin_interval_alpha_h3","origin_interval_alpha_h4","origin_interval_alpha_h6","lower_interval","upper_interval","interval_width","interval_covered","interval_score","mae","crps","crps_method",
"base_forecast","reconciled_forecast","pre_reconciliation_coherence_error","post_reconciliation_coherence_error","horizon_disagreement","dynamic_model_weight","dynamic_model_status","model_weights","weight_entropy","effective_model_count","dominant_model","weight_turnover","model_confidence_set_status","mcs_p_value","dm_statistic","dm_p_value","reality_check_p_value","validation_status","path_reliability",
"alpha_h","alpha_z_h","alpha_decay_h","delta_alpha_h","delta_acceleration_h","alpha_beta_delta_state",
"beta_volatility","beta_regime","beta_usd_factor","beta_session","beta_liquidity","beta_interval_width","beta_covariance_trace","beta_uncertainty","beta_instability","beta_update_status",
"regime","regime_probability","regime_probability_entropy","most_likely_regime","second_most_likely_regime","probability_margin","regime_age","expected_remaining_duration","transition_probability","transition_probability_h1","transition_probability_h3","transition_probability_h6","regime_survival_probability_h1","regime_survival_probability_h3","regime_survival_probability_h6","duration_model_status","change_point_probability","run_length_posterior_mean","run_length_posterior_mode","run_length_entropy","change_state","predicted_next_regime","settled_next_regime","regime_correct","regime_brier_score","regime_log_score","duration_error","regime_reliability",
"three_standard_agreement","combined_regime_probability","combined_transition_risk","field1_field2_agreement","field2_field3_agreement","all_fields_agreement","structural_break_state","rolling_coverage","rolling_normalized_interval_width","conformal_coverage_debt","interval_efficiency_score","calibration_sample_count","legacy_integrated_trust_score","research_integrated_trust_score","integrated_trust_score","evidence_status","shadow_recommendation","reason_codes","calculation_version")
TABLE_COLUMNS=BASE_COLUMNS
@dataclass(frozen=True)
class Field8Bundle:
    run_id: str; generation_id: str; snapshot_hash: str; symbol: str; timeframe: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION
    calculation_version: str = CALCULATION_VERSION
    published: bool = False
    def validate_identity(self) -> None:
        if not self.run_id or not self.generation_id or not self.snapshot_hash: raise ValueError("Field 8 requires run_id, generation_id and snapshot_hash")
        if self.symbol != "EURUSD" or self.timeframe != "H1": raise ValueError("Field 8 is restricted to EURUSD H1")
        for r in self.rows:
            if str(r.get("run_id"))!=self.run_id or str(r.get("generation_id"))!=self.generation_id or str(r.get("snapshot_hash"))!=self.snapshot_hash: raise ValueError("mixed Field 8 identity")

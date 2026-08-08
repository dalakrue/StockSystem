"""Persisted Field 10 crowd-psychology and final multi-symbol synthesis.

The module is intentionally additive and shadow-only.  It extends the existing
Field 10 daily snapshot; it does not create a second production ranking truth.
All heavy feature construction runs from the Settings-owned multi-symbol
orchestrator.  Lunch loaders are read-only SQLite queries.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import math
import sqlite3

import numpy as np
import pandas as pd

from core.sqlite_readonly_20260704 import connect_readonly

from core.multi_symbol_field10_20260701 import DB_PATH, normalize_symbol

VERSION = "field10-crowd-final-20260704-v1"
CROWD_MODEL_VERSION = "field10_crowd_psychology_candidate_v1"
FINAL_MODEL_VERSION = "field10_final_multi_symbol_candidate_v1"
CROWD_FORMULA_VERSION = "field10-crowd-psychology-formula-v1"
FINAL_FORMULA_VERSION = "field10-final-multi-symbol-fusion-v1"
THRESHOLD_VERSION = "field10-crowd-final-threshold-registry-v1"
SESSION_MODEL_VERSION = "field10-eight-session-entry-map-v1"
VALUE_UNIT = "PERCENT_RETURN"
REQUIRED_CANDLES = 600

SESSION_DEFINITIONS: tuple[tuple[str, tuple[int, ...]], ...] = (
    ("ASIA_EARLY", (0, 1, 2)),
    ("TOKYO", (3, 4, 5)),
    ("LONDON_PREOPEN", (6, 7)),
    ("LONDON", (8, 9, 10)),
    ("LONDON_NEW_YORK_OVERLAP", (11, 12, 13)),
    ("NEW_YORK", (14, 15, 16)),
    ("NEW_YORK_LATE", (17, 18, 19)),
    ("ROLLOVER", (20, 21, 22, 23)),
)

FORMULA_AND_THRESHOLD_REGISTRY: dict[str, Any] = {
    "registry_version": THRESHOLD_VERSION,
    "status": "SHADOW_ONLY_NOT_PRODUCTION_VALIDATED",
    "value_unit": VALUE_UNIT,
    "required_completed_h1_candles": REQUIRED_CANDLES,
    "crowd_model": {
        "model_version": CROWD_MODEL_VERSION,
        "formula_version": CROWD_FORMULA_VERSION,
        "weights": {
            "positioning_pressure": 0.18,
            "price_volume_behavior": 0.16,
            "volatility_psychology": 0.14,
            "news_sentiment_contribution": 0.12,
            "event_absorption_safety": 0.10,
            "crowd_momentum": 0.10,
            "cross_symbol_crowd_agreement": 0.08,
            "flow_proxy_confirmation": 0.07,
            "social_sentiment_contribution": 0.05,
        },
        "penalty_scales": {
            "herding_extreme": 0.12,
            "panic": 0.16,
            "late_crowd": 0.12,
            "divergence_conflict": 0.16,
            "data_quality": 0.15,
        },
        "state_thresholds": {
            "strong": 70.0,
            "bullish": 45.0,
            "mild": 20.0,
            "panic": 70.0,
            "fomo": 65.0,
            "exhaustion": 65.0,
            "contrarian": 65.0,
            "mixed_conflict": 60.0,
        },
        "minimum_evidence_completeness": 55.0,
        "minimum_ev_samples": 60,
    },
    "final_model": {
        "model_version": FINAL_MODEL_VERSION,
        "formula_version": FINAL_FORMULA_VERSION,
        "weights": {
            "technical_fundamental_quality": 0.32,
            "session_opportunity_quality": 0.20,
            "news_event_safety": 0.18,
            "crowd_psychology_quality": 0.18,
            "cross_source_agreement": 0.12,
        },
        "penalty_scales": {
            "transition_risk": 0.16,
            "tail_risk": 0.14,
            "news_shock": 0.15,
            "crowd_exhaustion": 0.12,
            "execution": 0.12,
            "evidence_completeness": 0.15,
        },
        "ev_lambdas": {
            "cvar95": 0.35,
            "uncertainty_width": 0.20,
            "calibration_error": 0.20,
            "evidence_incompleteness": 0.25,
        },
        "hold_transition_risk_max": 35.0,
        "caution_transition_risk_max": 65.0,
        "minimum_final_confidence": 60.0,
        "minimum_evidence_completeness": 70.0,
        "minimum_supporting_sources": 3,
        "near_zero_ev_abs_pct": 0.005,
        "tail_risk_block_abs_pct": 0.75,
    },
    "sessions": {name: list(hours) for name, hours in SESSION_DEFINITIONS},
}

# Physical columns are deliberately explicit: the database is an auditable
# evidence store, not a JSON-only blob.  JSON columns retain component lineage.
CROWD_COLUMN_TYPES: dict[str, str] = {
    "daily_snapshot_id": "TEXT NOT NULL",
    "run_id": "TEXT",
    "parent_run_id": "TEXT NOT NULL",
    "broker_day": "TEXT NOT NULL",
    "completed_h1_candle": "TEXT NOT NULL",
    "universe_hash": "TEXT NOT NULL",
    "symbol": "TEXT NOT NULL",
    "source_identity": "TEXT",
    "snapshot_hash": "TEXT",
    "crowd_rank": "INTEGER",
    "crowd_state": "TEXT NOT NULL",
    "crowd_direction": "TEXT NOT NULL",
    "crowd_psychology_score": "REAL",
    "crowd_confidence": "REAL",
    "evidence_completeness": "REAL",
    "data_freshness": "TEXT",
    "calculation_status": "TEXT NOT NULL",
    "herding_pressure": "REAL",
    "fomo_pressure": "REAL",
    "panic_pressure": "REAL",
    "greed_pressure": "REAL",
    "fear_pressure": "REAL",
    "capitulation_probability": "REAL",
    "crowd_exhaustion_probability": "REAL",
    "contrarian_reversal_probability": "REAL",
    "retail_trap_probability": "REAL",
    "stop_hunt_vulnerability": "REAL",
    "late_crowd_entry_risk": "REAL",
    "crowd_momentum_1h": "REAL",
    "crowd_momentum_6h": "REAL",
    "crowd_momentum_12h": "REAL",
    "crowd_momentum_24h": "REAL",
    "price_momentum_1h": "REAL",
    "price_momentum_6h": "REAL",
    "sentiment_price_divergence_1h": "REAL",
    "sentiment_price_divergence_6h": "REAL",
    "sentiment_price_divergence_12h": "REAL",
    "sentiment_price_divergence_24h": "REAL",
    "divergence_direction": "TEXT",
    "divergence_severity": "REAL",
    "divergence_persistence": "REAL",
    "retail_long_percentage": "REAL",
    "retail_short_percentage": "REAL",
    "retail_positioning_bias": "TEXT",
    "positioning_extreme_percentile": "REAL",
    "positioning_change_1h": "REAL",
    "positioning_change_6h": "REAL",
    "flow_proxy_bias": "TEXT",
    "flow_proxy_strength": "REAL",
    "signed_candle_pressure": "REAL",
    "abnormal_tick_volume_pressure": "REAL",
    "spread_stress_pressure": "REAL",
    "liquidity_withdrawal_risk": "REAL",
    "true_flow_data_available": "INTEGER NOT NULL DEFAULT 0",
    "positioning_data_available": "INTEGER NOT NULL DEFAULT 0",
    "volatility_fear_index": "REAL",
    "volatility_expansion_score": "REAL",
    "volatility_compression_score": "REAL",
    "panic_volatility_probability": "REAL",
    "calm_complacency_probability": "REAL",
    "session_normalized_volatility": "REAL",
    "volatility_regime": "TEXT",
    "volatility_transition_risk": "REAL",
    "finnhub_news_sentiment_contribution": "REAL",
    "high_impact_event_contribution": "REAL",
    "event_absorption_contribution": "REAL",
    "social_sentiment_contribution": "REAL",
    "social_sentiment_momentum": "REAL",
    "social_evidence_source": "TEXT",
    "news_social_agreement": "TEXT",
    "news_crowd_conflict": "TEXT",
    "active_event_risk": "TEXT",
    "base_currency_crowd_effect": "REAL",
    "quote_currency_crowd_effect": "REAL",
    "pair_crowd_effect": "REAL",
    "base_quote_agreement": "REAL",
    "currency_basket_crowd_score": "REAL",
    "cross_symbol_crowd_agreement": "REAL",
    "usd_crowd_regime": "TEXT",
    "eur_crowd_regime": "TEXT",
    "pair_specific_crowd_reliability": "REAL",
    "crowd_less_risky_bias": "TEXT",
    "crowd_entry_permission": "TEXT",
    "crowd_hold_permission": "TEXT",
    "crowd_reversal_warning": "TEXT",
    "crowd_transition_risk_1h": "REAL",
    "crowd_transition_risk_6h": "REAL",
    "crowd_transition_risk_12h": "REAL",
    "crowd_transition_risk_24h": "REAL",
    "crowd_expected_value_1h": "REAL",
    "crowd_expected_value_6h": "REAL",
    "crowd_expected_value_12h": "REAL",
    "crowd_expected_value_24h": "REAL",
    "crowd_risk_adjusted_ev_1h": "REAL",
    "crowd_risk_adjusted_ev_6h": "REAL",
    "crowd_risk_adjusted_ev_12h": "REAL",
    "crowd_risk_adjusted_ev_24h": "REAL",
    "crowd_cvar_95": "REAL",
    "crowd_explanation": "TEXT",
    "crowd_no_trade_reason": "TEXT",
    "model_version": "TEXT NOT NULL",
    "formula_version": "TEXT NOT NULL",
    "threshold_registry_version": "TEXT NOT NULL",
    "validation_status": "TEXT NOT NULL",
    "evidence_sample_size": "INTEGER NOT NULL DEFAULT 0",
    "value_unit": "TEXT NOT NULL",
    "component_json": "TEXT NOT NULL",
    "penalty_json": "TEXT NOT NULL",
    "source_provenance_json": "TEXT NOT NULL",
    "source_hashes_json": "TEXT NOT NULL",
    "publication_status": "TEXT NOT NULL",
    "content_hash": "TEXT NOT NULL",
    "created_broker_time": "TEXT NOT NULL",
    "created_system_time": "TEXT NOT NULL",
}

FINAL_COLUMN_TYPES: dict[str, str] = {
    "daily_snapshot_id": "TEXT NOT NULL",
    "run_id": "TEXT",
    "parent_run_id": "TEXT NOT NULL",
    "broker_day": "TEXT NOT NULL",
    "completed_h1_candle": "TEXT NOT NULL",
    "universe_hash": "TEXT NOT NULL",
    "symbol": "TEXT NOT NULL",
    "source_identity": "TEXT",
    "snapshot_hash": "TEXT",
    "final_rank": "INTEGER",
    "rank_icon": "TEXT",
    "final_score": "REAL",
    "previous_final_rank": "INTEGER",
    "rank_change": "INTEGER",
    "final_lock_status": "TEXT NOT NULL",
    "locked_at_broker_time": "TEXT NOT NULL",
    "locked_until_broker_time": "TEXT NOT NULL",
    "final_publication_hash": "TEXT NOT NULL",
    "technical_fundamental_rank": "INTEGER",
    "technical_fundamental_score": "REAL",
    "technical_fundamental_bias": "TEXT",
    "best_session_rank": "INTEGER",
    "best_session_1": "TEXT",
    "best_session_2": "TEXT",
    "session_score": "REAL",
    "session_bias": "TEXT",
    "news_sentiment_rank": "INTEGER",
    "news_sentiment_bias": "TEXT",
    "event_risk_permission": "TEXT",
    "impact_remaining_percentage": "REAL",
    "absorption_percentage": "REAL",
    "crowd_psychology_rank": "INTEGER",
    "crowd_psychology_score": "REAL",
    "crowd_state": "TEXT",
    "crowd_direction": "TEXT",
    "crowd_confidence": "REAL",
    "final_less_risky_bias_to_hold": "TEXT NOT NULL",
    "final_less_risky_bias_confidence": "REAL",
    "final_bias_agreement": "REAL",
    "final_bias_conflict": "REAL",
    "final_hold_permission": "TEXT",
    "final_entry_permission": "TEXT",
    "final_exit_risk_warning": "TEXT",
    "bias_source_majority": "TEXT",
    "strongest_supporting_source": "TEXT",
    "strongest_conflicting_source": "TEXT",
    "no_trade_reason": "TEXT",
    "final_explanation": "TEXT",
    "final_transition_bias_risk_1h": "REAL",
    "final_transition_bias_risk_6h": "REAL",
    "final_transition_bias_risk_12h": "REAL",
    "final_transition_bias_risk_24h": "REAL",
    "transition_direction_1h": "TEXT",
    "transition_direction_6h": "TEXT",
    "transition_direction_12h": "TEXT",
    "transition_direction_24h": "TEXT",
    "probability_bias_remains_1h": "REAL",
    "probability_bias_remains_6h": "REAL",
    "probability_bias_remains_12h": "REAL",
    "probability_bias_remains_24h": "REAL",
    "probability_bias_reverses_1h": "REAL",
    "probability_bias_reverses_6h": "REAL",
    "probability_bias_reverses_12h": "REAL",
    "probability_bias_reverses_24h": "REAL",
    "transition_risk_confidence": "REAL",
    "main_transition_risk_driver": "TEXT",
    "regime_transition_contribution": "REAL",
    "crowd_transition_contribution": "REAL",
    "news_transition_contribution": "REAL",
    "session_transition_contribution": "REAL",
    "expected_value_1h": "REAL",
    "expected_value_6h": "REAL",
    "expected_value_12h": "REAL",
    "expected_value_24h": "REAL",
    "risk_adjusted_expected_value_1h": "REAL",
    "risk_adjusted_expected_value_6h": "REAL",
    "risk_adjusted_expected_value_12h": "REAL",
    "risk_adjusted_expected_value_24h": "REAL",
    "expected_return_1h": "REAL",
    "expected_return_6h": "REAL",
    "expected_return_12h": "REAL",
    "expected_return_24h": "REAL",
    "probability_of_profit_1h": "REAL",
    "probability_of_profit_6h": "REAL",
    "probability_of_profit_12h": "REAL",
    "probability_of_profit_24h": "REAL",
    "probability_reach_expected_value_1h": "REAL",
    "probability_reach_expected_value_6h": "REAL",
    "probability_reach_expected_value_12h": "REAL",
    "probability_reach_expected_value_24h": "REAL",
    "expected_mfe_1h": "REAL",
    "expected_mfe_6h": "REAL",
    "expected_mfe_12h": "REAL",
    "expected_mfe_24h": "REAL",
    "expected_mae_1h": "REAL",
    "expected_mae_6h": "REAL",
    "expected_mae_12h": "REAL",
    "expected_mae_24h": "REAL",
    "cvar_95_1h": "REAL",
    "cvar_95_6h": "REAL",
    "cvar_95_12h": "REAL",
    "cvar_95_24h": "REAL",
    "expected_spread_cost": "REAL",
    "expected_slippage_cost": "REAL",
    "net_expected_value_after_cost": "REAL",
    "value_unit": "TEXT NOT NULL",
    "evidence_lineage_json": "TEXT NOT NULL",
    "four_source_row_references_json": "TEXT NOT NULL",
    "four_source_hashes_json": "TEXT NOT NULL",
    "horizon_probability_json": "TEXT NOT NULL",
    "horizon_ev_component_json": "TEXT NOT NULL",
    "transition_risk_component_json": "TEXT NOT NULL",
    "fusion_component_json": "TEXT NOT NULL",
    "penalty_json": "TEXT NOT NULL",
    "formula_version": "TEXT NOT NULL",
    "model_version": "TEXT NOT NULL",
    "threshold_registry_version": "TEXT NOT NULL",
    "validation_status": "TEXT NOT NULL",
    "lock_status": "TEXT NOT NULL",
    "publication_status": "TEXT NOT NULL",
    "content_hash": "TEXT NOT NULL",
    "created_broker_time": "TEXT NOT NULL",
    "created_system_time": "TEXT NOT NULL",
}

CROWD_DISPLAY_MAP: dict[str, str] = {
    "crowd_rank": "Crowd Rank", "symbol": "Symbol", "broker_day": "Broker Day",
    "completed_h1_candle": "Completed H1 Candle", "crowd_state": "Crowd State",
    "crowd_direction": "Crowd Direction", "crowd_psychology_score": "Crowd Psychology Score",
    "crowd_confidence": "Crowd Confidence", "evidence_completeness": "Evidence Completeness",
    "data_freshness": "Data Freshness", "calculation_status": "Calculation Status",
    "herding_pressure": "Herding Pressure", "fomo_pressure": "FOMO Pressure",
    "panic_pressure": "Panic Pressure", "greed_pressure": "Greed Pressure",
    "fear_pressure": "Fear Pressure", "capitulation_probability": "Capitulation Probability",
    "crowd_exhaustion_probability": "Crowd Exhaustion Probability",
    "contrarian_reversal_probability": "Contrarian Reversal Probability",
    "retail_trap_probability": "Retail Trap Probability", "stop_hunt_vulnerability": "Stop-Hunt Vulnerability",
    "late_crowd_entry_risk": "Late-Crowd Entry Risk", "crowd_momentum_1h": "Crowd Momentum 1H",
    "crowd_momentum_6h": "Crowd Momentum 6H", "crowd_momentum_12h": "Crowd Momentum 12H",
    "crowd_momentum_24h": "Crowd Momentum 24H", "price_momentum_1h": "Price Momentum 1H",
    "price_momentum_6h": "Price Momentum 6H", "sentiment_price_divergence_1h": "Sentiment–Price Divergence 1H",
    "sentiment_price_divergence_6h": "Sentiment–Price Divergence 6H",
    "sentiment_price_divergence_12h": "Sentiment–Price Divergence 12H",
    "sentiment_price_divergence_24h": "Sentiment–Price Divergence 24H",
    "divergence_direction": "Divergence Direction", "divergence_severity": "Divergence Severity",
    "divergence_persistence": "Divergence Persistence", "retail_long_percentage": "Retail Long Percentage",
    "retail_short_percentage": "Retail Short Percentage", "retail_positioning_bias": "Retail Positioning Bias",
    "positioning_extreme_percentile": "Positioning Extreme Percentile", "positioning_change_1h": "Positioning Change 1H",
    "positioning_change_6h": "Positioning Change 6H", "flow_proxy_bias": "Flow Proxy Bias",
    "flow_proxy_strength": "Flow Proxy Strength", "signed_candle_pressure": "Signed Candle Pressure",
    "abnormal_tick_volume_pressure": "Abnormal Tick-Volume Pressure", "spread_stress_pressure": "Spread-Stress Pressure",
    "liquidity_withdrawal_risk": "Liquidity Withdrawal Risk", "true_flow_data_available": "True Flow Data Available",
    "positioning_data_available": "Positioning Data Available", "volatility_fear_index": "Volatility Fear Index",
    "volatility_expansion_score": "Volatility Expansion Score", "volatility_compression_score": "Volatility Compression Score",
    "panic_volatility_probability": "Panic Volatility Probability", "calm_complacency_probability": "Calm-Complacency Probability",
    "session_normalized_volatility": "Session-Normalized Volatility", "volatility_regime": "Volatility Regime",
    "volatility_transition_risk": "Volatility Transition Risk",
    "finnhub_news_sentiment_contribution": "Finnhub News Sentiment Contribution",
    "high_impact_event_contribution": "High-Impact Event Contribution",
    "event_absorption_contribution": "Event Absorption Contribution",
    "social_sentiment_contribution": "Social Sentiment Contribution", "social_sentiment_momentum": "Social Sentiment Momentum",
    "social_evidence_source": "Social Evidence Source", "news_social_agreement": "News/Social Agreement",
    "news_crowd_conflict": "News/Crowd Conflict", "active_event_risk": "Active Event Risk",
    "base_currency_crowd_effect": "Base-Currency Crowd Effect", "quote_currency_crowd_effect": "Quote-Currency Crowd Effect",
    "pair_crowd_effect": "Pair Crowd Effect", "base_quote_agreement": "Base/Quote Agreement",
    "currency_basket_crowd_score": "Currency-Basket Crowd Score", "cross_symbol_crowd_agreement": "Cross-Symbol Crowd Agreement",
    "usd_crowd_regime": "USD Crowd Regime", "eur_crowd_regime": "EUR Crowd Regime",
    "pair_specific_crowd_reliability": "Pair-Specific Crowd Reliability",
    "crowd_less_risky_bias": "Crowd Less-Risky Bias", "crowd_entry_permission": "Crowd Entry Permission",
    "crowd_hold_permission": "Crowd Hold Permission", "crowd_reversal_warning": "Crowd Reversal Warning",
    "crowd_transition_risk_1h": "Crowd Transition Risk 1H", "crowd_transition_risk_6h": "Crowd Transition Risk 6H",
    "crowd_transition_risk_12h": "Crowd Transition Risk 12H", "crowd_transition_risk_24h": "Crowd Transition Risk 24H",
    "crowd_expected_value_1h": "Crowd Expected Value 1H", "crowd_expected_value_6h": "Crowd Expected Value 6H",
    "crowd_expected_value_12h": "Crowd Expected Value 12H", "crowd_expected_value_24h": "Crowd Expected Value 24H",
    "crowd_risk_adjusted_ev_1h": "Crowd Risk-Adjusted EV 1H", "crowd_risk_adjusted_ev_6h": "Crowd Risk-Adjusted EV 6H",
    "crowd_risk_adjusted_ev_12h": "Crowd Risk-Adjusted EV 12H", "crowd_risk_adjusted_ev_24h": "Crowd Risk-Adjusted EV 24H",
    "crowd_cvar_95": "Crowd CVaR 95%", "crowd_explanation": "Crowd Explanation",
    "crowd_no_trade_reason": "Crowd No-Trade Reason", "model_version": "Model Version",
    "formula_version": "Formula Version", "validation_status": "Validation Status",
    "evidence_sample_size": "Evidence Sample Size", "value_unit": "Value Unit",
}

FINAL_DISPLAY_MAP: dict[str, str] = {
    "final_rank": "Final Rank", "rank_icon": "Rank Icon", "symbol": "Symbol", "final_score": "Final Score",
    "previous_final_rank": "Previous Final Rank", "rank_change": "Rank Change", "broker_day": "Broker Day",
    "completed_h1_candle": "Completed H1 Candle", "daily_snapshot_id": "Daily Snapshot ID",
    "final_lock_status": "Final Lock Status", "locked_at_broker_time": "Locked At Broker Time",
    "locked_until_broker_time": "Locked Until Broker Time", "final_publication_hash": "Final Publication Hash",
    "technical_fundamental_rank": "Technical/Fundamental Rank", "technical_fundamental_score": "Technical/Fundamental Score",
    "technical_fundamental_bias": "Technical/Fundamental Bias", "best_session_rank": "Best Session Rank",
    "best_session_1": "Best Session 1", "best_session_2": "Best Session 2", "session_score": "Session Score",
    "session_bias": "Session Bias", "news_sentiment_rank": "News/Sentiment Rank",
    "news_sentiment_bias": "News Sentiment Bias", "event_risk_permission": "Event-Risk Permission",
    "impact_remaining_percentage": "Impact Remaining Percentage", "absorption_percentage": "Absorption Percentage",
    "crowd_psychology_rank": "Crowd Psychology Rank", "crowd_psychology_score": "Crowd Psychology Score",
    "crowd_state": "Crowd State", "crowd_direction": "Crowd Direction", "crowd_confidence": "Crowd Confidence",
    "final_less_risky_bias_to_hold": "Final Less-Risky Bias to Hold",
    "final_less_risky_bias_confidence": "Final Less-Risky Bias Confidence",
    "final_bias_agreement": "Final Bias Agreement", "final_bias_conflict": "Final Bias Conflict",
    "final_hold_permission": "Final Hold Permission", "final_entry_permission": "Final Entry Permission",
    "final_exit_risk_warning": "Final Exit/Risk Warning", "bias_source_majority": "Bias Source Majority",
    "strongest_supporting_source": "Strongest Supporting Source", "strongest_conflicting_source": "Strongest Conflicting Source",
    "no_trade_reason": "No-Trade Reason", "final_explanation": "Final Explanation",
    "final_transition_bias_risk_1h": "Final Transition Bias Risk 1H",
    "final_transition_bias_risk_6h": "Final Transition Bias Risk 6H",
    "final_transition_bias_risk_12h": "Final Transition Bias Risk 12H",
    "final_transition_bias_risk_24h": "Final Transition Bias Risk 24H",
    "transition_direction_1h": "Transition Direction 1H", "transition_direction_6h": "Transition Direction 6H",
    "transition_direction_12h": "Transition Direction 12H", "transition_direction_24h": "Transition Direction 24H",
    "probability_bias_remains_1h": "Probability Bias Remains 1H", "probability_bias_remains_6h": "Probability Bias Remains 6H",
    "probability_bias_remains_12h": "Probability Bias Remains 12H", "probability_bias_remains_24h": "Probability Bias Remains 24H",
    "probability_bias_reverses_1h": "Probability Bias Reverses 1H", "probability_bias_reverses_6h": "Probability Bias Reverses 6H",
    "probability_bias_reverses_12h": "Probability Bias Reverses 12H", "probability_bias_reverses_24h": "Probability Bias Reverses 24H",
    "transition_risk_confidence": "Transition-Risk Confidence", "main_transition_risk_driver": "Main Transition-Risk Driver",
    "regime_transition_contribution": "Regime Transition Contribution", "crowd_transition_contribution": "Crowd Transition Contribution",
    "news_transition_contribution": "News Transition Contribution", "session_transition_contribution": "Session Transition Contribution",
    "expected_value_1h": "Expected Value 1H", "expected_value_6h": "Expected Value 6H",
    "expected_value_12h": "Expected Value 12H", "expected_value_24h": "Expected Value 24H",
    "risk_adjusted_expected_value_1h": "Risk-Adjusted Expected Value 1H",
    "risk_adjusted_expected_value_6h": "Risk-Adjusted Expected Value 6H",
    "risk_adjusted_expected_value_12h": "Risk-Adjusted Expected Value 12H",
    "risk_adjusted_expected_value_24h": "Risk-Adjusted Expected Value 24H",
    "expected_return_1h": "Expected Return 1H", "expected_return_6h": "Expected Return 6H",
    "expected_return_12h": "Expected Return 12H", "expected_return_24h": "Expected Return 24H",
    "probability_of_profit_1h": "Probability of Profit 1H", "probability_of_profit_6h": "Probability of Profit 6H",
    "probability_of_profit_12h": "Probability of Profit 12H", "probability_of_profit_24h": "Probability of Profit 24H",
    "probability_reach_expected_value_1h": "Probability Reach Expected Value 1H",
    "probability_reach_expected_value_6h": "Probability Reach Expected Value 6H",
    "probability_reach_expected_value_12h": "Probability Reach Expected Value 12H",
    "probability_reach_expected_value_24h": "Probability Reach Expected Value 24H",
    "expected_mfe_1h": "Expected MFE 1H", "expected_mfe_6h": "Expected MFE 6H",
    "expected_mfe_12h": "Expected MFE 12H", "expected_mfe_24h": "Expected MFE 24H",
    "expected_mae_1h": "Expected MAE 1H", "expected_mae_6h": "Expected MAE 6H",
    "expected_mae_12h": "Expected MAE 12H", "expected_mae_24h": "Expected MAE 24H",
    "cvar_95_1h": "CVaR 95% 1H", "cvar_95_6h": "CVaR 95% 6H", "cvar_95_12h": "CVaR 95% 12H",
    "cvar_95_24h": "CVaR 95% 24H", "expected_spread_cost": "Expected Spread Cost",
    "expected_slippage_cost": "Expected Slippage Cost", "net_expected_value_after_cost": "Net Expected Value After Cost",
    "value_unit": "Value Unit", "validation_status": "Validation Status", "model_version": "Model Version",
    "formula_version": "Formula Version", "publication_status": "Publication Status",
    "evidence_lineage_json": "Evidence Lineage",
    "four_source_row_references_json": "Four-Source Row References",
    "four_source_hashes_json": "Four-Source Evidence Hashes",
    "threshold_registry_version": "Threshold Registry Version",
    "content_hash": "Content Hash",
}

MOBILE_FINAL_COLUMNS: tuple[str, ...] = (
    "Final Rank", "Symbol", "Final Less-Risky Bias to Hold",
    "Final Hold Permission", "Final Entry Permission", "Final Less-Risky Bias Confidence",
    "Final Transition Bias Risk 1H", "Final Transition Bias Risk 6H",
    "Expected Value 1H", "Expected Value 6H",
)


def _connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    return conn


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return sha256(_json(value).encode("utf-8")).hexdigest()


def _audit_now() -> str:
    # System time is audit-only.  Market identity comes exclusively from the
    # persisted broker snapshot and completed candle.
    return pd.Timestamp.now(tz="UTC").isoformat()


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _pct(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    if 0.0 <= number <= 1.0:
        number *= 100.0
    return float(np.clip(number, 0.0, 100.0))


def _clip100(value: Any) -> float | None:
    number = _number(value)
    return None if number is None else float(np.clip(number, 0.0, 100.0))


def _signed100(value: Any) -> float | None:
    number = _number(value)
    return None if number is None else float(np.clip(number, -100.0, 100.0))


def _bias(value: Any) -> str | None:
    text = str(value or "").upper()
    if "BUY" in text or "BULL" in text or "LONG" in text:
        return "BUY"
    if "SELL" in text or "BEAR" in text or "SHORT" in text:
        return "SELL"
    if any(token in text for token in ("WAIT", "NEUTRAL", "BALANCED", "HOLD")):
        return "WAIT"
    return None


def pair_parts(symbol: Any) -> tuple[str, str]:
    normalized = normalize_symbol(symbol)
    currencies = {"USD", "EUR", "JPY", "GBP", "CHF", "AUD", "NZD", "CAD"}
    if len(normalized) >= 6 and normalized[:3] in currencies and normalized[3:6] in currencies:
        return normalized[:3], normalized[3:6]
    return normalized[:3], normalized[3:6] if len(normalized) >= 6 else ""


def pair_direction_from_currency_evidence(symbol: Any, currency: str, positive: bool) -> str:
    """Map currency-leg evidence to pair direction for all supported FX legs."""
    base, quote = pair_parts(symbol)
    cur = str(currency or "").upper()
    if cur == base:
        return "BUY" if positive else "SELL"
    if cur == quote:
        return "SELL" if positive else "BUY"
    return "WAIT"


def _create_dynamic_table(conn: sqlite3.Connection, table: str, columns: Mapping[str, str], primary_key: str, foreign_key: str) -> None:
    definitions = [f'"{name}" {sql_type}' for name, sql_type in columns.items()]
    definitions.append(f"PRIMARY KEY({primary_key})")
    definitions.append(foreign_key)
    conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({",".join(definitions)})')
    existing = {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}
    for name, sql_type in columns.items():
        if name not in existing:
            safe_type = sql_type.replace(" NOT NULL", "").replace(" DEFAULT 0", "")
            conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {safe_type}')


def migrate_crowd_final_database(path: Path | str = DB_PATH) -> dict[str, Any]:
    """Idempotent, non-destructive migration for crowd/final child evidence."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        _create_dynamic_table(
            conn, "field10_daily_crowd_psychology_rank", CROWD_COLUMN_TYPES,
            '"daily_snapshot_id","symbol"',
            'FOREIGN KEY("daily_snapshot_id","symbol") REFERENCES field10_daily_snapshot_symbol("daily_snapshot_id","symbol")',
        )
        _create_dynamic_table(
            conn, "field10_daily_final_multi_symbol_rank", FINAL_COLUMN_TYPES,
            '"daily_snapshot_id","symbol"',
            'FOREIGN KEY("daily_snapshot_id","symbol") REFERENCES field10_daily_snapshot_symbol("daily_snapshot_id","symbol")',
        )
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS field10_daily_session_entry_map (
                daily_snapshot_id TEXT NOT NULL,
                broker_day TEXT NOT NULL,
                completed_h1_candle TEXT NOT NULL,
                parent_run_id TEXT NOT NULL,
                run_id TEXT,
                universe_hash TEXT NOT NULL,
                symbol TEXT NOT NULL,
                session_name TEXT NOT NULL,
                session_rank INTEGER,
                session_score REAL,
                session_bias TEXT,
                entry_permission TEXT,
                sample_size INTEGER NOT NULL DEFAULT 0,
                mean_return_1h REAL,
                median_return_1h REAL,
                win_rate REAL,
                session_volatility REAL,
                source_row_id TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                snapshot_hash TEXT,
                formula_version TEXT NOT NULL,
                model_version TEXT NOT NULL,
                publication_status TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                created_broker_time TEXT NOT NULL,
                created_system_time TEXT NOT NULL,
                PRIMARY KEY(daily_snapshot_id,symbol,session_name),
                FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
            );
            CREATE TABLE IF NOT EXISTS field10_crowd_psychology_outcome (
                outcome_id TEXT PRIMARY KEY,
                daily_snapshot_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                prediction_content_hash TEXT NOT NULL,
                horizon_hours INTEGER NOT NULL,
                realized_return_pct REAL,
                realized_direction TEXT,
                direction_correct INTEGER,
                realized_mfe_pct REAL,
                realized_mae_pct REAL,
                evaluation_json TEXT NOT NULL,
                outcome_hash TEXT NOT NULL UNIQUE,
                settled_broker_time TEXT NOT NULL,
                created_system_time TEXT NOT NULL,
                FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_crowd_psychology_rank(daily_snapshot_id,symbol)
            );
            CREATE TABLE IF NOT EXISTS field10_final_multi_symbol_outcome (
                outcome_id TEXT PRIMARY KEY,
                daily_snapshot_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                prediction_content_hash TEXT NOT NULL,
                horizon_hours INTEGER NOT NULL,
                realized_return_pct REAL,
                realized_direction TEXT,
                direction_correct INTEGER,
                realized_mfe_pct REAL,
                realized_mae_pct REAL,
                realized_net_return_pct REAL,
                evaluation_json TEXT NOT NULL,
                outcome_hash TEXT NOT NULL UNIQUE,
                settled_broker_time TEXT NOT NULL,
                created_system_time TEXT NOT NULL,
                FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_final_multi_symbol_rank(daily_snapshot_id,symbol)
            );
            CREATE TABLE IF NOT EXISTS field10_crowd_final_migration_audit (
                migration_id TEXT PRIMARY KEY,
                migration_version TEXT NOT NULL,
                status TEXT NOT NULL,
                details_json TEXT NOT NULL,
                applied_system_time TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_f10_crowd_broker_day ON field10_daily_crowd_psychology_rank(broker_day,crowd_rank);
            CREATE INDEX IF NOT EXISTS idx_f10_crowd_snapshot ON field10_daily_crowd_psychology_rank(daily_snapshot_id,crowd_rank);
            CREATE INDEX IF NOT EXISTS idx_f10_crowd_symbol ON field10_daily_crowd_psychology_rank(symbol,broker_day DESC);
            CREATE INDEX IF NOT EXISTS idx_f10_crowd_publication ON field10_daily_crowd_psychology_rank(publication_status,broker_day);
            CREATE INDEX IF NOT EXISTS idx_f10_crowd_completed ON field10_daily_crowd_psychology_rank(completed_h1_candle);
            CREATE INDEX IF NOT EXISTS idx_f10_final_broker_day ON field10_daily_final_multi_symbol_rank(broker_day,final_rank);
            CREATE INDEX IF NOT EXISTS idx_f10_final_snapshot ON field10_daily_final_multi_symbol_rank(daily_snapshot_id,final_rank);
            CREATE INDEX IF NOT EXISTS idx_f10_final_symbol ON field10_daily_final_multi_symbol_rank(symbol,broker_day DESC);
            CREATE INDEX IF NOT EXISTS idx_f10_final_publication ON field10_daily_final_multi_symbol_rank(publication_status,broker_day);
            CREATE INDEX IF NOT EXISTS idx_f10_final_lock ON field10_daily_final_multi_symbol_rank(lock_status,broker_day);
            CREATE INDEX IF NOT EXISTS idx_f10_final_completed ON field10_daily_final_multi_symbol_rank(completed_h1_candle);
            CREATE INDEX IF NOT EXISTS idx_f10_session_snapshot ON field10_daily_session_entry_map(daily_snapshot_id,symbol,session_rank);
            CREATE INDEX IF NOT EXISTS idx_f10_session_broker_day ON field10_daily_session_entry_map(broker_day,session_rank);
            CREATE INDEX IF NOT EXISTS idx_f10_crowd_outcome_snapshot ON field10_crowd_psychology_outcome(daily_snapshot_id,symbol,horizon_hours);
            CREATE INDEX IF NOT EXISTS idx_f10_final_outcome_snapshot ON field10_final_multi_symbol_outcome(daily_snapshot_id,symbol,horizon_hours);
            """
        )
        required = {
            "field10_daily_crowd_psychology_rank": set(CROWD_COLUMN_TYPES),
            "field10_daily_final_multi_symbol_rank": set(FINAL_COLUMN_TYPES),
            "field10_daily_session_entry_map": {"daily_snapshot_id", "symbol", "session_name", "source_hash", "content_hash"},
            "field10_crowd_psychology_outcome": {"outcome_id", "prediction_content_hash", "outcome_hash"},
            "field10_final_multi_symbol_outcome": {"outcome_id", "prediction_content_hash", "outcome_hash"},
        }
        missing: dict[str, list[str]] = {}
        secret_issues: dict[str, list[str]] = {}
        for table, expected in required.items():
            actual = {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}
            absent = sorted(expected - actual)
            if absent:
                missing[table] = absent
            bad = sorted(col for col in actual if any(tok in col.lower() for tok in ("api_key", "password", "secret", "credential", "access_token")))
            if bad:
                secret_issues[table] = bad
        fk_issues = [tuple(row) for row in conn.execute("PRAGMA foreign_key_check")]
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        details = {
            "missing_columns": missing,
            "secret_column_issues": secret_issues,
            "foreign_key_issues": fk_issues,
            "integrity_check": integrity,
            "tables": sorted(required),
        }
        ok = not missing and not secret_issues and not fk_issues and integrity.lower() == "ok"
        migration_id = _hash({"version": VERSION, "path": str(path.resolve()), "details": details})
        conn.execute(
            "INSERT OR REPLACE INTO field10_crowd_final_migration_audit(migration_id,migration_version,status,details_json,applied_system_time) VALUES(?,?,?,?,?)",
            (migration_id, VERSION, "PASS" if ok else "FAIL", _json(details), _audit_now()),
        )
        conn.commit()
    return {
        "ok": ok, "status": "PASS" if ok else "FAIL", "path": str(path),
        "migration_version": VERSION, "missing_columns": missing,
        "secret_column_issues": secret_issues, "foreign_key_issue_count": len(fk_issues),
        "integrity_check": integrity,
    }


def verify_crowd_final_database(path: Path | str = DB_PATH) -> dict[str, Any]:
    return migrate_crowd_final_database(path)


def _snapshot_identity(path: Path | str, daily_snapshot_id: str | None = None) -> dict[str, Any]:
    with connect_readonly(path, timeout=30) as conn:
        if daily_snapshot_id:
            row = conn.execute("SELECT * FROM field10_daily_snapshot WHERE daily_snapshot_id=?", (daily_snapshot_id,)).fetchone()
        else:
            row = conn.execute("SELECT * FROM field10_daily_snapshot ORDER BY broker_day DESC LIMIT 1").fetchone()
        return dict(row) if row else {}


def _snapshot_symbol_rows(path: Path | str, snapshot_id: str) -> list[dict[str, Any]]:
    with connect_readonly(path, timeout=30) as conn:
        rows = conn.execute(
            "SELECT * FROM field10_daily_snapshot_symbol WHERE daily_snapshot_id=? ORDER BY COALESCE(daily_rank,999999),symbol",
            (snapshot_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _load_states(symbols: Sequence[str]) -> dict[str, dict[str, Any]]:
    try:
        from core.field10_daily_snapshot_contract_20260702 import _load_cached_states
        return {normalize_symbol(k): dict(v) for k, v in _load_cached_states(symbols).items() if isinstance(v, Mapping)}
    except Exception:
        return {}


def _find_column(frame: pd.DataFrame, *aliases: str) -> str | None:
    normalized = {str(c).strip().lower().replace("_", " ").replace("-", " "): str(c) for c in frame.columns}
    for alias in aliases:
        key = alias.strip().lower().replace("_", " ").replace("-", " ")
        if key in normalized:
            return normalized[key]
    return None


def extract_exact_completed_h1(state: Mapping[str, Any], completed_h1_candle: Any, required: int = REQUIRED_CANDLES) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return exactly the last completed H1 candles, never the forming candle."""
    raw = pd.DataFrame()
    for key in ("canonical_completed_ohlc_df_20260617", "calculation_staging_ohlc_df_20260617", "last_df", "dv_pp_df"):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            raw = value.copy(deep=False)
            break
    cutoff = pd.to_datetime(completed_h1_candle, errors="coerce", utc=True)
    if raw.empty or pd.isna(cutoff):
        return pd.DataFrame(), {"status": "INSUFFICIENT_EVIDENCE", "sample_count": 0, "forming_candle_excluded": True}
    time_col = _find_column(raw, "broker candle time", "time", "datetime", "timestamp", "date", "event time utc")
    cols = {name: _find_column(raw, name, name[0]) for name in ("open", "high", "low", "close")}
    if time_col is None or any(value is None for value in cols.values()):
        return pd.DataFrame(), {"status": "INSUFFICIENT_EVIDENCE", "sample_count": 0, "forming_candle_excluded": True, "reason": "OHLC/time columns missing"}
    result = pd.DataFrame({"time": pd.to_datetime(raw[time_col], errors="coerce", utc=True)})
    for name, source in cols.items():
        result[name] = pd.to_numeric(raw[source], errors="coerce")
    volume_col = _find_column(raw, "tick volume", "tick_volume", "volume", "real volume")
    spread_col = _find_column(raw, "spread pct", "spread percentage", "spread", "average spread")
    slippage_col = _find_column(raw, "slippage pct", "slippage percentage", "slippage")
    if volume_col:
        result["tick_volume"] = pd.to_numeric(raw[volume_col], errors="coerce")
    if spread_col:
        result["spread_raw"] = pd.to_numeric(raw[spread_col], errors="coerce")
        result.attrs["spread_column"] = spread_col
    if slippage_col:
        result["slippage_raw"] = pd.to_numeric(raw[slippage_col], errors="coerce")
        result.attrs["slippage_column"] = slippage_col
    result = result.dropna(subset=["time", "open", "high", "low", "close"])
    result = result.loc[result["time"] <= cutoff].sort_values("time", kind="mergesort")
    result = result.drop_duplicates("time", keep="last").tail(required).reset_index(drop=True)
    status = "PASS" if len(result) == required and (result.empty or result["time"].max() == cutoff) else "INSUFFICIENT_EVIDENCE"
    report = {
        "status": status,
        "sample_count": int(len(result)),
        "required_candles": required,
        "window_start": None if result.empty else result["time"].min().isoformat(),
        "window_end": None if result.empty else result["time"].max().isoformat(),
        "forming_candle_excluded": bool(result.empty or result["time"].max() <= cutoff),
        "cutoff": None if pd.isna(cutoff) else cutoff.isoformat(),
    }
    return result, report


def _session_name(hour: int) -> str:
    for name, hours in SESSION_DEFINITIONS:
        if int(hour) in hours:
            return name
    return "UNAVAILABLE"


def _execution_cost_pct(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame or frame.empty:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return None
    raw = float(values.tail(24).median())
    source_name = str(frame.attrs.get("spread_column" if column == "spread_raw" else "slippage_column") or "").lower()
    if "pct" in source_name or "percent" in source_name:
        return abs(raw)
    close = float(pd.to_numeric(frame["close"], errors="coerce").dropna().iloc[-1])
    if close <= 0:
        return None
    # Explicit price-unit spread/slippage converted to percentage-return units.
    return abs(raw / close * 100.0)


def _persist_session_map(path: Path | str, snapshot: Mapping[str, Any], symbol_rows: Sequence[Mapping[str, Any]], states: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    inserted = 0
    with _connect(path) as conn:
        for source in symbol_rows:
            symbol = normalize_symbol(source.get("symbol"))
            frame, validation = extract_exact_completed_h1(states.get(symbol, {}), snapshot.get("latest_completed_h1"))
            rows: list[dict[str, Any]] = []
            if not frame.empty:
                working = frame.copy()
                working["forward_1h"] = working["close"].shift(-1).div(working["close"]).sub(1.0).mul(100.0)
                working["session_name"] = working["time"].dt.hour.map(_session_name)
                for name, _hours in SESSION_DEFINITIONS:
                    sample = working.loc[working["session_name"].eq(name), "forward_1h"].dropna()
                    if sample.empty:
                        rows.append({"session_name": name, "session_score": None, "session_bias": "UNAVAILABLE", "entry_permission": "INSUFFICIENT_EVIDENCE", "sample_size": 0, "mean_return_1h": None, "median_return_1h": None, "win_rate": None, "session_volatility": None})
                        continue
                    mean = float(sample.mean())
                    median = float(sample.median())
                    win = float((sample > 0).mean() * 100.0)
                    vol = float(sample.std(ddof=0)) if len(sample) > 1 else 0.0
                    direction = "BUY" if mean > 0 else ("SELL" if mean < 0 else "WAIT")
                    quality = float(np.clip(50.0 + abs(mean) / max(vol, 1e-9) * 18.0 + abs(win - 50.0) * 0.45, 0.0, 100.0))
                    permission = "ALLOW" if len(sample) >= 20 and quality >= 58 else ("CAUTION" if len(sample) >= 10 else "INSUFFICIENT_EVIDENCE")
                    rows.append({"session_name": name, "session_score": quality, "session_bias": direction, "entry_permission": permission, "sample_size": int(len(sample)), "mean_return_1h": mean, "median_return_1h": median, "win_rate": win, "session_volatility": vol})
            else:
                rows = [{"session_name": name, "session_score": None, "session_bias": "UNAVAILABLE", "entry_permission": "INSUFFICIENT_EVIDENCE", "sample_size": 0, "mean_return_1h": None, "median_return_1h": None, "win_rate": None, "session_volatility": None} for name, _ in SESSION_DEFINITIONS]
            ranked = sorted(rows, key=lambda row: (row["session_score"] is None, -(row["session_score"] or -1), row["session_name"]))
            for rank, row in enumerate(ranked, start=1):
                row["session_rank"] = rank if row["session_score"] is not None else None
            for row in rows:
                source_row_id = f"{snapshot.get('daily_snapshot_id')}:{symbol}:{row['session_name']}"
                payload = {
                    "daily_snapshot_id": snapshot.get("daily_snapshot_id"), "broker_day": snapshot.get("broker_day"),
                    "completed_h1_candle": snapshot.get("latest_completed_h1"), "parent_run_id": snapshot.get("parent_run_id"),
                    "run_id": source.get("canonical_run_id"), "universe_hash": snapshot.get("universe_hash"), "symbol": symbol,
                    **row, "source_row_id": source_row_id, "source_hash": _hash({"source": source.get("content_hash"), "validation": validation}),
                    "snapshot_hash": source.get("snapshot_hash"), "formula_version": "field10-eight-session-formula-v1",
                    "model_version": SESSION_MODEL_VERSION, "publication_status": "PUBLISHED_LOCKED_CHILD",
                    "created_broker_time": snapshot.get("published_at_broker_time") or snapshot.get("created_at_broker_time"),
                    "created_system_time": _audit_now(),
                }
                payload["content_hash"] = _hash({k: v for k, v in payload.items() if k not in {"content_hash", "created_system_time"}})
                cols = list(payload)
                before = conn.total_changes
                conn.execute(
                    f"INSERT OR IGNORE INTO field10_daily_session_entry_map({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",
                    tuple(payload[c] for c in cols),
                )
                inserted += conn.total_changes - before
        conn.commit()
    return {
        "ok": True,
        "status": "PERSISTED_OR_ALREADY_EXISTS",
        "rows_considered": len(symbol_rows) * len(SESSION_DEFINITIONS),
        "rows_inserted": int(inserted),
    }


def _news_aggregate(path: Path | str, snapshot_id: str, symbol: str) -> dict[str, Any]:
    with _connect(path) as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM field10_daily_news_event_rank WHERE daily_snapshot_id=? AND symbol=? ORDER BY COALESCE(news_rank,999999),event_id",
            (snapshot_id, symbol),
        ).fetchall()]
    if not rows:
        return {"available": False, "bias": "UNAVAILABLE", "contribution": None, "permission": "UNAVAILABLE", "impact_remaining": None, "absorption": None, "rank": None, "source_rows": [], "source_hashes": []}
    weights = np.array([max(1.0, _number(row.get("pair_relevance")) or 0.0) * max(0.1, (_number(row.get("source_quality")) or 50.0) / 100.0) for row in rows], dtype=float)
    signed = np.array([1.0 if _bias(row.get("sentiment_bias")) == "BUY" else (-1.0 if _bias(row.get("sentiment_bias")) == "SELL" else 0.0) for row in rows])
    probabilities = np.array([(_pct(row.get("sentiment_probability")) or 50.0) / 100.0 for row in rows])
    contribution = float(np.clip(np.average(signed * probabilities * 100.0, weights=weights), -100.0, 100.0))
    permissions = [str(row.get("event_risk_permission") or "UNAVAILABLE").upper() for row in rows]
    permission = "BLOCK" if "BLOCK" in permissions else ("CAUTION" if "CAUTION" in permissions else "ALLOW")
    impact = float(np.average([_pct(row.get("impact_remaining_pct")) or 0.0 for row in rows], weights=weights))
    absorption = float(np.average([_pct(row.get("absorption_pct")) or 0.0 for row in rows], weights=weights))
    return {
        "available": True, "bias": "BUY" if contribution > 5 else ("SELL" if contribution < -5 else "WAIT"),
        "contribution": contribution, "permission": permission, "impact_remaining": impact,
        "absorption": absorption, "rank": min((_number(row.get("news_rank")) for row in rows if _number(row.get("news_rank")) is not None), default=None),
        "source_rows": [f"{snapshot_id}:{symbol}:{row.get('event_id')}" for row in rows],
        "source_hashes": [str(row.get("content_hash") or "") for row in rows],
    }


def _momentum_pct(close: pd.Series, horizon: int) -> float | None:
    values = pd.to_numeric(close, errors="coerce").dropna()
    if len(values) <= horizon or values.iloc[-horizon-1] == 0:
        return None
    return float((values.iloc[-1] / values.iloc[-horizon-1] - 1.0) * 100.0)


def _normalized_momentum(close: pd.Series, horizon: int) -> float | None:
    momentum = _momentum_pct(close, horizon)
    returns = pd.to_numeric(close, errors="coerce").pct_change().dropna().mul(100.0)
    if momentum is None or returns.empty:
        return None
    scale = float(returns.tail(120).std(ddof=0) * math.sqrt(max(1, horizon)))
    if not np.isfinite(scale) or scale <= 1e-12:
        return 0.0
    return float(np.tanh(momentum / (2.0 * scale)) * 100.0)


def _empirical_horizon(frame: pd.DataFrame, horizon: int, direction: str, transition_risk: float | None, impact_remaining: float | None, evidence_completeness: float) -> dict[str, Any]:
    sign = 1.0 if direction == "BUY" else (-1.0 if direction == "SELL" else 0.0)
    if sign == 0.0 or len(frame) <= horizon + 30:
        return {"status": "INSUFFICIENT_EVIDENCE", "sample_size": 0}
    close = pd.to_numeric(frame["close"], errors="coerce")
    future = close.shift(-horizon).div(close).sub(1.0).mul(100.0).mul(sign).dropna()
    if len(future) < FORMULA_AND_THRESHOLD_REGISTRY["crowd_model"]["minimum_ev_samples"]:
        return {"status": "INSUFFICIENT_EVIDENCE", "sample_size": int(len(future))}
    positive = future[future > 0]
    negative = future[future < 0]
    p_profit = float((future > 0).mean())
    p_loss = float((future < 0).mean())
    med_pos = float(positive.median()) if not positive.empty else None
    med_neg = abs(float(negative.median())) if not negative.empty else None
    spread_cost = _execution_cost_pct(frame, "spread_raw")
    slippage_cost = _execution_cost_pct(frame, "slippage_raw")
    q = float(future.quantile(0.05))
    cvar = float(future[future <= q].mean()) if (future <= q).any() else q
    tail_penalty = abs(min(0.0, cvar)) * 0.25
    transition_penalty = ((_pct(transition_risk) or 0.0) / 100.0) * float(future.abs().median()) if transition_risk is not None else None
    news_penalty = ((_pct(impact_remaining) or 0.0) / 100.0) * float(future.abs().median()) * 0.35 if impact_remaining is not None else None
    costs_available = spread_cost is not None and slippage_cost is not None
    penalties_available = transition_penalty is not None and news_penalty is not None
    ev = None
    if med_pos is not None and med_neg is not None and costs_available and penalties_available:
        ev = p_profit * med_pos - p_loss * med_neg - spread_cost - slippage_cost - tail_penalty - transition_penalty - news_penalty
    uncertainty = float(future.quantile(0.75) - future.quantile(0.25))
    calibration_error = None  # unavailable until immutable OOS outcomes exist
    lambdas = FORMULA_AND_THRESHOLD_REGISTRY["final_model"]["ev_lambdas"]
    risk_adjusted = None
    if ev is not None and calibration_error is not None:
        risk_adjusted = ev - lambdas["cvar95"] * abs(min(0.0, cvar)) - lambdas["uncertainty_width"] * uncertainty - lambdas["calibration_error"] * calibration_error - lambdas["evidence_incompleteness"] * ((100.0 - evidence_completeness) / 100.0)
    # MFE/MAE are computed from historical paths fully contained in the 600-candle window.
    mfes: list[float] = []
    maes: list[float] = []
    arr = close.to_numpy(dtype=float)
    for i in range(0, len(arr) - horizon):
        if not np.isfinite(arr[i]) or arr[i] == 0:
            continue
        path = (arr[i + 1:i + horizon + 1] / arr[i] - 1.0) * 100.0 * sign
        if len(path):
            mfes.append(float(np.nanmax(path)))
            maes.append(float(np.nanmin(path)))
    expected_return = float(future.median())
    reach_probability = float((future >= expected_return).mean() * 100.0)
    return {
        "status": "ESTIMATED_SHADOW" if ev is not None else "INSUFFICIENT_EXECUTION_OR_CALIBRATION_EVIDENCE",
        "sample_size": int(len(future)), "probability_profit": p_profit * 100.0,
        "probability_loss": p_loss * 100.0, "median_positive_return": med_pos,
        "absolute_median_negative_return": med_neg, "expected_return": expected_return,
        "probability_reach_expected_value": reach_probability, "expected_mfe": float(np.median(mfes)) if mfes else None,
        "expected_mae": float(np.median(maes)) if maes else None, "cvar95": cvar,
        "expected_spread_cost": spread_cost, "expected_slippage_cost": slippage_cost,
        "tail_risk_penalty": tail_penalty, "transition_risk_penalty": transition_penalty,
        "residual_news_shock_penalty": news_penalty, "uncertainty_width": uncertainty,
        "calibration_error": calibration_error, "ev": ev, "risk_adjusted_ev": risk_adjusted,
        "value_unit": VALUE_UNIT,
    }


def _available_weighted(components: Mapping[str, Mapping[str, Any]], weights: Mapping[str, float]) -> tuple[float | None, float, dict[str, Any]]:
    available = {name: data for name, data in components.items() if data.get("value") is not None and name in weights}
    total_available = sum(weights[name] for name in available)
    total_configured = sum(weights.values())
    if total_available <= 0:
        return None, 0.0, {name: {**dict(data), "configured_weight": weights.get(name), "effective_weight": None} for name, data in components.items()}
    score = 0.0
    detail: dict[str, Any] = {}
    for name, data in components.items():
        configured = weights.get(name, 0.0)
        effective = configured / total_available if name in available else None
        contribution = None if effective is None else float(data["value"]) * effective
        if contribution is not None:
            score += contribution
        detail[name] = {**dict(data), "configured_weight": configured, "effective_weight": effective, "contribution": contribution}
    completeness = total_available / total_configured * 100.0 if total_configured else 0.0
    return float(score), float(completeness), detail


def _regime_label(value: float | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value >= 45:
        return "BULLISH"
    if value <= -45:
        return "BEARISH"
    return "BALANCED"


def _base_crowd_record(symbol: str, frame: pd.DataFrame, validation: Mapping[str, Any], news: Mapping[str, Any]) -> dict[str, Any]:
    if frame.empty:
        return {"symbol": symbol, "validation": validation, "news": news, "calculation_status": "INSUFFICIENT_EVIDENCE"}
    close = frame["close"]
    returns = pd.to_numeric(close, errors="coerce").pct_change().dropna().mul(100.0)
    ranges = (frame["high"] - frame["low"]).replace(0, np.nan)
    candle_pressure = ((frame["close"] - frame["open"]) / ranges * 100.0).replace([np.inf, -np.inf], np.nan).dropna().tail(24)
    signed_candle = float(candle_pressure.mean()) if not candle_pressure.empty else None
    volume_pressure = None
    if "tick_volume" in frame:
        volume = pd.to_numeric(frame["tick_volume"], errors="coerce")
        baseline = volume.tail(120)
        std = float(baseline.std(ddof=0)) if baseline.notna().sum() > 10 else 0.0
        if std > 0:
            volume_pressure = float(np.clip((volume.iloc[-1] - baseline.mean()) / std * 20.0, -100.0, 100.0))
    spread_stress = None
    if "spread_raw" in frame:
        spread = pd.to_numeric(frame["spread_raw"], errors="coerce")
        baseline = spread.tail(120)
        std = float(baseline.std(ddof=0)) if baseline.notna().sum() > 10 else 0.0
        if std > 0:
            spread_stress = float(np.clip(max(0.0, (spread.iloc[-1] - baseline.mean()) / std * 25.0), 0.0, 100.0))
    vol24 = float(returns.tail(24).std(ddof=0)) if len(returns) >= 24 else None
    vol120 = float(returns.tail(120).std(ddof=0)) if len(returns) >= 120 else None
    expansion = None if vol24 is None or vol120 is None or vol120 <= 0 else float(np.clip((vol24 / vol120 - 0.5) * 65.0, 0.0, 100.0))
    compression = None if expansion is None else 100.0 - expansion
    momenta = {h: _normalized_momentum(close, h) for h in (1, 6, 12, 24)}
    price_mom = {h: _momentum_pct(close, h) for h in (1, 6, 12, 24)}
    crowd_momentum = float(np.nanmean([v for v in momenta.values() if v is not None])) if any(v is not None for v in momenta.values()) else None
    price_volume = None
    pv_values = [v for v in (crowd_momentum, signed_candle, volume_pressure) if v is not None]
    if pv_values:
        price_volume = float(np.mean(pv_values))
    volatility_psych = None
    if expansion is not None:
        sign = 1.0 if (crowd_momentum or 0.0) >= 0 else -1.0
        volatility_psych = float(np.clip(sign * expansion, -100.0, 100.0))
    flow_values = [v for v in (signed_candle, volume_pressure) if v is not None]
    flow_proxy = float(np.mean(flow_values)) if flow_values else None
    event_absorption_safety = news.get("absorption") if news.get("available") else None
    event_absorption_signed = None
    if event_absorption_safety is not None:
        event_absorption_signed = float(np.clip((event_absorption_safety - 50.0) * 2.0, -100.0, 100.0))
    news_contribution = news.get("contribution") if news.get("available") else None
    divergences: dict[int, float | None] = {}
    for horizon in (1, 6, 12, 24):
        pm = momenta[horizon]
        divergences[horizon] = None if news_contribution is None or pm is None else float(np.clip(news_contribution - pm, -100.0, 100.0))
    divergence_abs = [abs(v) for v in divergences.values() if v is not None]
    divergence_severity = float(np.mean(divergence_abs)) if divergence_abs else None
    divergence_persistence = float(sum(v >= 35.0 for v in divergence_abs) / len(divergence_abs) * 100.0) if divergence_abs else None
    herding = float(np.clip(0.65 * abs(crowd_momentum or 0.0) + 0.35 * abs(signed_candle or 0.0), 0.0, 100.0))
    fear = float(np.clip(0.65 * (expansion or 0.0) + 0.35 * max(0.0, -(crowd_momentum or 0.0)), 0.0, 100.0))
    greed = float(np.clip(0.55 * max(0.0, crowd_momentum or 0.0) + 0.25 * herding + 0.20 * (compression or 0.0), 0.0, 100.0))
    panic = float(np.clip(0.55 * (expansion or 0.0) + 0.30 * fear + 0.15 * abs(volume_pressure or 0.0), 0.0, 100.0))
    fomo = float(np.clip(0.50 * herding + 0.30 * max(0.0, abs(crowd_momentum or 0.0) - 35.0) + 0.20 * (expansion or 0.0), 0.0, 100.0))
    exhaustion = float(np.clip(0.40 * herding + 0.30 * (divergence_severity or 0.0) + 0.30 * (expansion or 0.0), 0.0, 100.0))
    contrarian = float(np.clip(0.50 * (divergence_severity or 0.0) + 0.30 * exhaustion + 0.20 * max(0.0, herding - 65.0), 0.0, 100.0))
    late_risk = float(np.clip(0.45 * herding + 0.35 * exhaustion + 0.20 * fomo, 0.0, 100.0))
    retail_trap = float(np.clip(0.55 * contrarian + 0.45 * max(0.0, herding - abs(crowd_momentum or 0.0)), 0.0, 100.0))
    stop_hunt = float(np.clip(0.45 * (expansion or 0.0) + 0.35 * abs(volume_pressure or 0.0) + 0.20 * (spread_stress or 0.0), 0.0, 100.0))
    components = {
        "positioning_pressure": {"value": None, "status": "UNAVAILABLE_NO_LEGITIMATE_POSITIONING_SOURCE"},
        "price_volume_behavior": {"value": price_volume, "status": "AVAILABLE" if price_volume is not None else "UNAVAILABLE"},
        "volatility_psychology": {"value": volatility_psych, "status": "AVAILABLE" if volatility_psych is not None else "UNAVAILABLE"},
        "news_sentiment_contribution": {"value": news_contribution, "status": "AVAILABLE" if news_contribution is not None else "UNAVAILABLE"},
        "event_absorption_safety": {"value": event_absorption_signed, "status": "AVAILABLE" if event_absorption_signed is not None else "UNAVAILABLE"},
        "crowd_momentum": {"value": crowd_momentum, "status": "AVAILABLE" if crowd_momentum is not None else "UNAVAILABLE"},
        "cross_symbol_crowd_agreement": {"value": None, "status": "PENDING_CROSS_SYMBOL_PASS"},
        "flow_proxy_confirmation": {"value": flow_proxy, "status": "AVAILABLE_PROXY_NOT_TRUE_FLOW" if flow_proxy is not None else "UNAVAILABLE"},
        "social_sentiment_contribution": {"value": None, "status": "UNAVAILABLE_NO_LEGITIMATE_SOCIAL_SOURCE"},
    }
    score, completeness, component_detail = _available_weighted(components, FORMULA_AND_THRESHOLD_REGISTRY["crowd_model"]["weights"])
    return {
        "symbol": symbol, "frame": frame, "validation": validation, "news": news,
        "momenta": momenta, "price_mom": price_mom, "divergences": divergences,
        "signed_candle": signed_candle, "volume_pressure": volume_pressure, "spread_stress": spread_stress,
        "expansion": expansion, "compression": compression, "crowd_momentum": crowd_momentum,
        "price_volume": price_volume, "volatility_psych": volatility_psych, "flow_proxy": flow_proxy,
        "herding": herding, "fear": fear, "greed": greed, "panic": panic, "fomo": fomo,
        "exhaustion": exhaustion, "contrarian": contrarian, "late_risk": late_risk,
        "retail_trap": retail_trap, "stop_hunt": stop_hunt,
        "divergence_severity": divergence_severity, "divergence_persistence": divergence_persistence,
        "components": component_detail, "preliminary_score": score, "preliminary_completeness": completeness,
        "calculation_status": "CALCULATED_SHADOW" if validation.get("status") == "PASS" else "INSUFFICIENT_EVIDENCE",
    }


def _crowd_state(score: float | None, record: Mapping[str, Any]) -> str:
    if score is None or record.get("calculation_status") != "CALCULATED_SHADOW":
        return "INSUFFICIENT_EVIDENCE"
    thresholds = FORMULA_AND_THRESHOLD_REGISTRY["crowd_model"]["state_thresholds"]
    if (record.get("panic") or 0.0) >= thresholds["panic"]:
        return "PANIC_BUYING" if score > 0 else "PANIC_SELLING"
    if (record.get("contrarian") or 0.0) >= thresholds["contrarian"]:
        return "CONTRARIAN_REVERSAL_RISK"
    if (record.get("exhaustion") or 0.0) >= thresholds["exhaustion"]:
        return "CROWD_EXHAUSTION"
    if (record.get("fomo") or 0.0) >= thresholds["fomo"]:
        return "FOMO_BUYING" if score > 0 else "FOMO_SELLING"
    if (record.get("divergence_severity") or 0.0) >= thresholds["mixed_conflict"]:
        return "MIXED_OR_CONFLICTED"
    if score >= thresholds["strong"]: return "STRONG_BULLISH_CROWD"
    if score >= thresholds["bullish"]: return "BULLISH_CROWD"
    if score >= thresholds["mild"]: return "MILD_BULLISH_CROWD"
    if score <= -thresholds["strong"]: return "STRONG_BEARISH_CROWD"
    if score <= -thresholds["bullish"]: return "BEARISH_CROWD"
    if score <= -thresholds["mild"]: return "MILD_BEARISH_CROWD"
    return "BALANCED"


def _build_crowd_rows(path: Path | str, snapshot: Mapping[str, Any], symbol_rows: Sequence[Mapping[str, Any]], states: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source in symbol_rows:
        symbol = normalize_symbol(source.get("symbol"))
        frame, validation = extract_exact_completed_h1(states.get(symbol, {}), snapshot.get("latest_completed_h1"))
        news = _news_aggregate(path, str(snapshot.get("daily_snapshot_id")), symbol)
        record = _base_crowd_record(symbol, frame, validation, news)
        record["source"] = dict(source)
        records.append(record)
    currency_values: dict[str, list[float]] = defaultdict(list)
    for record in records:
        score = _number(record.get("preliminary_score"))
        base, quote = pair_parts(record["symbol"])
        if score is not None and base and quote:
            currency_values[base].append(score)
            currency_values[quote].append(-score)
    baskets = {currency: float(np.mean(values)) for currency, values in currency_values.items() if values}
    built: list[dict[str, Any]] = []
    for record in records:
        symbol = record["symbol"]
        source = record["source"]
        base, quote = pair_parts(symbol)
        base_effect = baskets.get(base)
        quote_effect = baskets.get(quote)
        pair_effect = None if base_effect is None or quote_effect is None else float(np.clip((base_effect - quote_effect) / 2.0, -100.0, 100.0))
        preliminary = _number(record.get("preliminary_score"))
        cross_agreement = None
        if pair_effect is not None and preliminary is not None:
            cross_agreement = float(np.clip(100.0 - abs(pair_effect - preliminary), 0.0, 100.0))
            cross_signed = cross_agreement * (1.0 if pair_effect >= 0 else -1.0)
        else:
            cross_signed = None
        components = {name: dict(value) for name, value in record.get("components", {}).items()}
        components["cross_symbol_crowd_agreement"] = {"value": cross_signed, "status": "AVAILABLE" if cross_signed is not None else "UNAVAILABLE"}
        raw_score, completeness, detail = _available_weighted(components, FORMULA_AND_THRESHOLD_REGISTRY["crowd_model"]["weights"])
        penalties = {
            "herding_extreme_penalty": max(0.0, (record.get("herding") or 0.0) - 70.0) * FORMULA_AND_THRESHOLD_REGISTRY["crowd_model"]["penalty_scales"]["herding_extreme"],
            "panic_penalty": (record.get("panic") or 0.0) * FORMULA_AND_THRESHOLD_REGISTRY["crowd_model"]["penalty_scales"]["panic"],
            "late_crowd_penalty": (record.get("late_risk") or 0.0) * FORMULA_AND_THRESHOLD_REGISTRY["crowd_model"]["penalty_scales"]["late_crowd"],
            "divergence_conflict_penalty": (record.get("divergence_severity") or 0.0) * FORMULA_AND_THRESHOLD_REGISTRY["crowd_model"]["penalty_scales"]["divergence_conflict"],
            "data_quality_penalty": (100.0 - completeness) * FORMULA_AND_THRESHOLD_REGISTRY["crowd_model"]["penalty_scales"]["data_quality"],
        }
        penalty_total = sum(penalties.values())
        if raw_score is None:
            score = None
        else:
            score = float(np.clip(raw_score - math.copysign(penalty_total, raw_score if raw_score != 0 else 1.0), -100.0, 100.0))
        state = _crowd_state(score, record)
        direction = "BUY" if (score or 0.0) > 15 else ("SELL" if (score or 0.0) < -15 else "WAIT")
        confidence = None if score is None else float(np.clip(completeness * (0.55 + abs(score) / 225.0) - record.get("contrarian", 0.0) * 0.20, 0.0, 100.0))
        transition_base = float(np.clip(0.28 * (record.get("expansion") or 0.0) + 0.30 * (record.get("contrarian") or 0.0) + 0.22 * (record.get("divergence_severity") or 0.0) + 0.20 * (record.get("exhaustion") or 0.0), 0.0, 100.0))
        transition = {h: float(np.clip(100.0 * (1.0 - (1.0 - transition_base / 100.0) ** max(1.0, h / 6.0)), 0.0, 100.0)) for h in (1, 6, 12, 24)}
        ev = {h: _empirical_horizon(record.get("frame", pd.DataFrame()), h, direction, transition[h], record.get("news", {}).get("impact_remaining"), completeness) for h in (1, 6, 12, 24)}
        cvars = [data.get("cvar95") for data in ev.values() if data.get("cvar95") is not None]
        severe_reversal = (record.get("contrarian") or 0.0) >= 65.0 or state in {"CONTRARIAN_REVERSAL_RISK", "CROWD_EXHAUSTION"}
        event_permission = str(record.get("news", {}).get("permission") or "UNAVAILABLE")
        no_trade_reasons: list[str] = []
        if record.get("validation", {}).get("status") != "PASS": no_trade_reasons.append("exact 600 completed H1 evidence unavailable")
        if completeness < FORMULA_AND_THRESHOLD_REGISTRY["crowd_model"]["minimum_evidence_completeness"]: no_trade_reasons.append("crowd evidence completeness below shadow threshold")
        if severe_reversal: no_trade_reasons.append("crowd exhaustion or contrarian reversal risk elevated")
        if event_permission == "BLOCK": no_trade_reasons.append("unabsorbed high-impact event risk")
        entry_permission = "BLOCK" if event_permission == "BLOCK" else ("CAUTION" if severe_reversal or transition[1] >= 65 else ("ALLOW" if direction in {"BUY", "SELL"} and not no_trade_reasons else "WAIT"))
        hold_permission = "EXIT_OR_REDUCE" if severe_reversal and transition[1] >= 65 else ("CAUTION" if severe_reversal else ("HOLD" if direction in {"BUY", "SELL"} else "WAIT"))
        row = {
            "daily_snapshot_id": snapshot.get("daily_snapshot_id"), "run_id": source.get("canonical_run_id"),
            "parent_run_id": snapshot.get("parent_run_id"), "broker_day": snapshot.get("broker_day"),
            "completed_h1_candle": snapshot.get("latest_completed_h1"), "universe_hash": snapshot.get("universe_hash"),
            "symbol": symbol, "source_identity": source.get("source_id"), "snapshot_hash": source.get("snapshot_hash"),
            "crowd_rank": None, "crowd_state": state, "crowd_direction": direction,
            "crowd_psychology_score": score, "crowd_confidence": confidence, "evidence_completeness": completeness,
            "data_freshness": "CURRENT_COMPLETED_H1" if record.get("validation", {}).get("status") == "PASS" else "STALE_OR_INCOMPLETE",
            "calculation_status": record.get("calculation_status"), "herding_pressure": record.get("herding"),
            "fomo_pressure": record.get("fomo"), "panic_pressure": record.get("panic"), "greed_pressure": record.get("greed"),
            "fear_pressure": record.get("fear"), "capitulation_probability": float(np.clip(0.55 * record.get("panic", 0.0) + 0.45 * record.get("fear", 0.0), 0, 100)),
            "crowd_exhaustion_probability": record.get("exhaustion"), "contrarian_reversal_probability": record.get("contrarian"),
            "retail_trap_probability": record.get("retail_trap"), "stop_hunt_vulnerability": record.get("stop_hunt"),
            "late_crowd_entry_risk": record.get("late_risk"),
            "crowd_momentum_1h": record.get("momenta", {}).get(1), "crowd_momentum_6h": record.get("momenta", {}).get(6),
            "crowd_momentum_12h": record.get("momenta", {}).get(12), "crowd_momentum_24h": record.get("momenta", {}).get(24),
            "price_momentum_1h": record.get("price_mom", {}).get(1), "price_momentum_6h": record.get("price_mom", {}).get(6),
            "sentiment_price_divergence_1h": record.get("divergences", {}).get(1), "sentiment_price_divergence_6h": record.get("divergences", {}).get(6),
            "sentiment_price_divergence_12h": record.get("divergences", {}).get(12), "sentiment_price_divergence_24h": record.get("divergences", {}).get(24),
            "divergence_direction": "NEWS_MORE_BULLISH" if (record.get("divergences", {}).get(6) or 0.0) > 10 else ("NEWS_MORE_BEARISH" if (record.get("divergences", {}).get(6) or 0.0) < -10 else "ALIGNED_OR_UNAVAILABLE"),
            "divergence_severity": record.get("divergence_severity"), "divergence_persistence": record.get("divergence_persistence"),
            "retail_long_percentage": None, "retail_short_percentage": None, "retail_positioning_bias": "UNAVAILABLE",
            "positioning_extreme_percentile": None, "positioning_change_1h": None, "positioning_change_6h": None,
            "flow_proxy_bias": "BUY" if (record.get("flow_proxy") or 0.0) > 5 else ("SELL" if (record.get("flow_proxy") or 0.0) < -5 else "WAIT"),
            "flow_proxy_strength": abs(record.get("flow_proxy")) if record.get("flow_proxy") is not None else None,
            "signed_candle_pressure": record.get("signed_candle"), "abnormal_tick_volume_pressure": record.get("volume_pressure"),
            "spread_stress_pressure": record.get("spread_stress"), "liquidity_withdrawal_risk": float(np.nanmean([v for v in (record.get("spread_stress"), record.get("expansion")) if v is not None])) if any(v is not None for v in (record.get("spread_stress"), record.get("expansion"))) else None,
            "true_flow_data_available": 0, "positioning_data_available": 0,
            "volatility_fear_index": record.get("fear"), "volatility_expansion_score": record.get("expansion"),
            "volatility_compression_score": record.get("compression"), "panic_volatility_probability": record.get("panic"),
            "calm_complacency_probability": record.get("compression"), "session_normalized_volatility": record.get("expansion"),
            "volatility_regime": "EXPANSION" if (record.get("expansion") or 0.0) >= 60 else ("COMPRESSION" if (record.get("compression") or 0.0) >= 60 else "NORMAL"),
            "volatility_transition_risk": transition_base,
            "finnhub_news_sentiment_contribution": record.get("news", {}).get("contribution"),
            "high_impact_event_contribution": None if not record.get("news", {}).get("available") else -float(record.get("news", {}).get("impact_remaining") or 0.0),
            "event_absorption_contribution": record.get("news", {}).get("absorption"),
            "social_sentiment_contribution": None, "social_sentiment_momentum": None, "social_evidence_source": "UNAVAILABLE",
            "news_social_agreement": "UNAVAILABLE", "news_crowd_conflict": "YES" if record.get("news", {}).get("bias") not in {"UNAVAILABLE", "WAIT", direction} else "NO_OR_UNAVAILABLE",
            "active_event_risk": event_permission, "base_currency_crowd_effect": base_effect,
            "quote_currency_crowd_effect": quote_effect, "pair_crowd_effect": pair_effect,
            "base_quote_agreement": cross_agreement, "currency_basket_crowd_score": pair_effect,
            "cross_symbol_crowd_agreement": cross_agreement, "usd_crowd_regime": _regime_label(baskets.get("USD")),
            "eur_crowd_regime": _regime_label(baskets.get("EUR")), "pair_specific_crowd_reliability": confidence,
            "crowd_less_risky_bias": direction, "crowd_entry_permission": entry_permission,
            "crowd_hold_permission": hold_permission, "crowd_reversal_warning": "ACTIVE" if severe_reversal else "CLEAR",
            "crowd_transition_risk_1h": transition[1], "crowd_transition_risk_6h": transition[6],
            "crowd_transition_risk_12h": transition[12], "crowd_transition_risk_24h": transition[24],
            "crowd_expected_value_1h": ev[1].get("ev"), "crowd_expected_value_6h": ev[6].get("ev"),
            "crowd_expected_value_12h": ev[12].get("ev"), "crowd_expected_value_24h": ev[24].get("ev"),
            "crowd_risk_adjusted_ev_1h": ev[1].get("risk_adjusted_ev"), "crowd_risk_adjusted_ev_6h": ev[6].get("risk_adjusted_ev"),
            "crowd_risk_adjusted_ev_12h": ev[12].get("risk_adjusted_ev"), "crowd_risk_adjusted_ev_24h": ev[24].get("risk_adjusted_ev"),
            "crowd_cvar_95": min(cvars) if cvars else None,
            "crowd_explanation": f"Shadow crowd score from available price/volume, volatility, news absorption, momentum, cross-symbol and proxy-flow evidence; optional unavailable sources were not replaced with zero. State={state}; direction={direction}.",
            "crowd_no_trade_reason": "; ".join(no_trade_reasons) if no_trade_reasons else "NONE",
            "model_version": CROWD_MODEL_VERSION, "formula_version": CROWD_FORMULA_VERSION,
            "threshold_registry_version": THRESHOLD_VERSION, "validation_status": "SHADOW_ONLY_NOT_PROMOTED",
            "evidence_sample_size": int(record.get("validation", {}).get("sample_count") or 0), "value_unit": VALUE_UNIT,
            "component_json": _json({"components": detail, "horizon_ev": ev, "currency_baskets": baskets}),
            "penalty_json": _json(penalties),
            "source_provenance_json": _json({"daily_snapshot_symbol": f"{snapshot.get('daily_snapshot_id')}:{symbol}", "news_rows": record.get("news", {}).get("source_rows", []), "frame_validation": record.get("validation")}),
            "source_hashes_json": _json({"daily_snapshot_symbol": source.get("content_hash"), "news": record.get("news", {}).get("source_hashes", [])}),
            "publication_status": "PUBLISHED_LOCKED_CHILD_SHADOW", "content_hash": "",
            "created_broker_time": snapshot.get("published_at_broker_time") or snapshot.get("created_at_broker_time"),
            "created_system_time": _audit_now(),
        }
        row["content_hash"] = _hash({k: v for k, v in row.items() if k not in {"content_hash", "created_system_time", "crowd_rank"}})
        built.append(row)
    ranked = sorted(built, key=lambda row: (row["crowd_psychology_score"] is None, -(row["crowd_psychology_score"] or -999), row["symbol"]))
    for rank, row in enumerate(ranked, start=1):
        row["crowd_rank"] = rank if row["crowd_psychology_score"] is not None else None
        row["content_hash"] = _hash({k: v for k, v in row.items() if k not in {"content_hash", "created_system_time"}})
    return built


def _insert_rows(conn: sqlite3.Connection, table: str, rows: Sequence[Mapping[str, Any]], columns: Mapping[str, str]) -> int:
    names = list(columns)
    sql = f'INSERT OR IGNORE INTO "{table}"({",".join(f"\"{name}\"" for name in names)}) VALUES({",".join("?" for _ in names)})'
    before = conn.total_changes
    for row in rows:
        conn.execute(sql, tuple(row.get(name) for name in names))
    return conn.total_changes - before


def _previous_ranks(conn: sqlite3.Connection, broker_day: str) -> dict[str, int]:
    previous_day = conn.execute("SELECT broker_day FROM field10_daily_final_multi_symbol_rank WHERE broker_day<? ORDER BY broker_day DESC LIMIT 1", (broker_day,)).fetchone()
    if not previous_day:
        return {}
    return {str(row[0]): int(row[1]) for row in conn.execute("SELECT symbol,final_rank FROM field10_daily_final_multi_symbol_rank WHERE broker_day=? AND final_rank IS NOT NULL", (previous_day[0],))}


def _aggregate_session(conn: sqlite3.Connection, snapshot_id: str, symbol: str) -> dict[str, Any]:
    rows = [dict(row) for row in conn.execute("SELECT * FROM field10_daily_session_entry_map WHERE daily_snapshot_id=? AND symbol=? ORDER BY COALESCE(session_rank,999999),session_name", (snapshot_id, symbol)).fetchall()]
    available = [row for row in rows if _number(row.get("session_score")) is not None]
    if not available:
        return {"available": False, "rows": rows, "best1": None, "best2": None, "score": None, "bias": "UNAVAILABLE", "rank": None, "hashes": []}
    top = available[:2]
    weighted_bias = sum((1 if _bias(row.get("session_bias")) == "BUY" else -1 if _bias(row.get("session_bias")) == "SELL" else 0) * float(row.get("session_score") or 0.0) for row in top)
    return {"available": True, "rows": rows, "best1": top[0].get("session_name"), "best2": top[1].get("session_name") if len(top) > 1 else None, "score": float(np.mean([float(row["session_score"]) for row in top])), "bias": "BUY" if weighted_bias > 0 else ("SELL" if weighted_bias < 0 else "WAIT"), "rank": top[0].get("session_rank"), "hashes": [row.get("content_hash") for row in top], "refs": [row.get("source_row_id") for row in top]}


def _final_ev_from_crowd(crowd: Mapping[str, Any], horizon: int, transition_risk: float, impact: float | None, completeness: float) -> dict[str, Any]:
    try:
        components = json.loads(str(crowd.get("component_json") or "{}"))
        source = components.get("horizon_ev", {}).get(str(horizon)) or components.get("horizon_ev", {}).get(horizon) or {}
    except Exception:
        source = {}
    p_profit = _pct(source.get("probability_profit"))
    p_loss = _pct(source.get("probability_loss"))
    med_pos = _number(source.get("median_positive_return"))
    med_neg = _number(source.get("absolute_median_negative_return"))
    spread = _number(source.get("expected_spread_cost"))
    slippage = _number(source.get("expected_slippage_cost"))
    cvar = _number(source.get("cvar95"))
    uncertainty = _number(source.get("uncertainty_width"))
    calibration_error = _number(source.get("calibration_error"))
    tail_penalty = abs(min(0.0, cvar)) * 0.25 if cvar is not None else None
    typical = None
    if med_pos is not None and med_neg is not None:
        typical = (med_pos + med_neg) / 2.0
    transition_penalty = None if typical is None else transition_risk / 100.0 * typical
    news_penalty = None if typical is None or impact is None else impact / 100.0 * typical * 0.35
    ev = None
    if None not in (p_profit, p_loss, med_pos, med_neg, spread, slippage, tail_penalty, transition_penalty, news_penalty):
        ev = (p_profit / 100.0) * med_pos - (p_loss / 100.0) * med_neg - spread - slippage - tail_penalty - transition_penalty - news_penalty
    lambdas = FORMULA_AND_THRESHOLD_REGISTRY["final_model"]["ev_lambdas"]
    risk_adjusted = None
    if ev is not None and None not in (cvar, uncertainty, calibration_error):
        risk_adjusted = ev - lambdas["cvar95"] * abs(min(0.0, cvar)) - lambdas["uncertainty_width"] * uncertainty - lambdas["calibration_error"] * calibration_error - lambdas["evidence_incompleteness"] * ((100.0 - completeness) / 100.0)
    return {**source, "ev": ev, "risk_adjusted_ev": risk_adjusted, "tail_risk_penalty": tail_penalty, "transition_risk_penalty": transition_penalty, "residual_news_shock_penalty": news_penalty, "value_unit": VALUE_UNIT}


def _build_final_rows(path: Path | str, snapshot: Mapping[str, Any], symbol_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    snapshot_id = str(snapshot.get("daily_snapshot_id"))
    with _connect(path) as conn:
        previous = _previous_ranks(conn, str(snapshot.get("broker_day")))
        crowd_by_symbol = {str(row["symbol"]): dict(row) for row in conn.execute("SELECT * FROM field10_daily_crowd_psychology_rank WHERE daily_snapshot_id=?", (snapshot_id,))}
        built: list[dict[str, Any]] = []
        for technical in symbol_rows:
            symbol = normalize_symbol(technical.get("symbol"))
            crowd = crowd_by_symbol.get(symbol, {})
            session = _aggregate_session(conn, snapshot_id, symbol)
            news = _news_aggregate(path, snapshot_id, symbol)
            tech_bias = _bias(technical.get("stable_daily_bias") or technical.get("less_risky_bias")) or "UNAVAILABLE"
            tech_score = _number(technical.get("institutional_score"))
            if tech_score is None: tech_score = _number(technical.get("existing_rank_score"))
            technical_quality = tech_score
            session_quality = session.get("score")
            news_safety = None if not news.get("available") else float(np.clip(100.0 - (news.get("impact_remaining") or 0.0), 0.0, 100.0))
            crowd_score = _number(crowd.get("crowd_psychology_score"))
            crowd_quality = None if crowd_score is None else float(np.clip(50.0 + abs(crowd_score) / 2.0, 0.0, 100.0))
            votes = {
                "TECHNICAL_FUNDAMENTAL": tech_bias,
                "SESSION": session.get("bias") or "UNAVAILABLE",
                "NEWS_SENTIMENT": news.get("bias") or "UNAVAILABLE",
                "CROWD_PSYCHOLOGY": crowd.get("crowd_direction") or "UNAVAILABLE",
            }
            directional = [value for value in votes.values() if value in {"BUY", "SELL"}]
            buy_count, sell_count = directional.count("BUY"), directional.count("SELL")
            majority = "BUY" if buy_count > sell_count else ("SELL" if sell_count > buy_count else "WAIT")
            agreement = max(buy_count, sell_count) / 4.0 * 100.0
            conflict = min(buy_count, sell_count) / 4.0 * 100.0
            components = {
                "technical_fundamental_quality": {"value": technical_quality, "status": "AVAILABLE" if technical_quality is not None else "UNAVAILABLE"},
                "session_opportunity_quality": {"value": session_quality, "status": "AVAILABLE" if session_quality is not None else "UNAVAILABLE"},
                "news_event_safety": {"value": news_safety, "status": "AVAILABLE" if news_safety is not None else "UNAVAILABLE"},
                "crowd_psychology_quality": {"value": crowd_quality, "status": "AVAILABLE" if crowd_quality is not None else "UNAVAILABLE"},
                "cross_source_agreement": {"value": agreement, "status": "AVAILABLE"},
            }
            raw_score, completeness, detail = _available_weighted(components, FORMULA_AND_THRESHOLD_REGISTRY["final_model"]["weights"])
            regime6 = _pct(technical.get("transition_risk_6h"))
            regime24 = _pct(technical.get("transition_risk_24h"))
            crowd_risks = {h: _pct(crowd.get(f"crowd_transition_risk_{h}h")) for h in (1, 6, 12, 24)}
            news_contribution = _pct(news.get("impact_remaining")) if news.get("available") else None
            session_contribution = None if session_quality is None else 100.0 - session_quality
            risks: dict[int, float] = {}
            risk_parts: dict[int, dict[str, Any]] = {}
            for h in (1, 6, 12, 24):
                regime = regime6 if h <= 6 else regime24
                available = [v for v in (regime, crowd_risks[h], news_contribution, session_contribution) if v is not None]
                risk = float(np.clip(np.mean(available) if available else 100.0, 0.0, 100.0))
                risks[h] = risk
                risk_parts[h] = {"regime": regime, "crowd": crowd_risks[h], "news": news_contribution, "session": session_contribution}
            final_ev = {h: _final_ev_from_crowd(crowd, h, risks[h], news.get("impact_remaining"), completeness) for h in (1, 6, 12, 24)}
            tail_values = [_number(final_ev[h].get("cvar95")) for h in (1, 6, 12, 24)]
            worst_cvar = min((v for v in tail_values if v is not None), default=None)
            penalties = {
                "transition_risk_penalty": float(np.mean(list(risks.values()))) * FORMULA_AND_THRESHOLD_REGISTRY["final_model"]["penalty_scales"]["transition_risk"],
                "tail_risk_penalty": abs(min(0.0, worst_cvar)) * 100.0 * FORMULA_AND_THRESHOLD_REGISTRY["final_model"]["penalty_scales"]["tail_risk"] if worst_cvar is not None else 0.0,
                "news_shock_penalty": (news.get("impact_remaining") or 0.0) * FORMULA_AND_THRESHOLD_REGISTRY["final_model"]["penalty_scales"]["news_shock"],
                "crowd_exhaustion_penalty": (_pct(crowd.get("crowd_exhaustion_probability")) or 0.0) * FORMULA_AND_THRESHOLD_REGISTRY["final_model"]["penalty_scales"]["crowd_exhaustion"],
                "execution_penalty": 0.0 if final_ev[1].get("expected_spread_cost") is not None and final_ev[1].get("expected_slippage_cost") is not None else 15.0,
                "evidence_completeness_penalty": (100.0 - completeness) * FORMULA_AND_THRESHOLD_REGISTRY["final_model"]["penalty_scales"]["evidence_completeness"],
            }
            final_score = None if raw_score is None else float(np.clip(raw_score - sum(penalties.values()), 0.0, 100.0))
            critical_missing = [name for name, value in (("technical/fundamental", technical_quality), ("session", session_quality), ("crowd", crowd_quality)) if value is None]
            identity_inconsistent = any(str(value or "") != str(snapshot.get(field) or "") for value, field in ((technical.get("broker_day"), "broker_day"), (technical.get("completed_candle"), "latest_completed_h1")))
            event_permission = str(news.get("permission") or "UNAVAILABLE")
            severe_crowd = str(crowd.get("crowd_state") or "") in {"CROWD_EXHAUSTION", "CONTRARIAN_REVERSAL_RISK", "PANIC_BUYING", "PANIC_SELLING"} or (_pct(crowd.get("contrarian_reversal_probability")) or 0.0) >= 70.0
            anchor = tech_bias if tech_bias in {"BUY", "SELL"} else majority
            supporters = sum(1 for value in votes.values() if value == anchor)
            ev6 = _number(final_ev[6].get("ev"))
            near_zero = ev6 is None or abs(ev6) <= FORMULA_AND_THRESHOLD_REGISTRY["final_model"]["near_zero_ev_abs_pct"]
            block_reason = None
            if identity_inconsistent: block_reason = "data identity inconsistent"
            elif str(crowd.get("data_freshness")) == "STALE_OR_INCOMPLETE": block_reason = "evidence stale or incomplete"
            elif event_permission == "BLOCK": block_reason = "severe unabsorbed event active"
            elif worst_cvar is not None and abs(min(0.0, worst_cvar)) >= FORMULA_AND_THRESHOLD_REGISTRY["final_model"]["tail_risk_block_abs_pct"]: block_reason = "tail risk beyond shadow threshold"
            if block_reason and anchor in {"BUY", "SELL"}:
                final_bias = f"BLOCK_{anchor}"
            elif critical_missing or completeness < FORMULA_AND_THRESHOLD_REGISTRY["final_model"]["minimum_evidence_completeness"]:
                final_bias = "INSUFFICIENT_EVIDENCE"
            elif anchor not in {"BUY", "SELL"} or majority == "WAIT" or near_zero:
                final_bias = "WAIT"
            elif supporters >= FORMULA_AND_THRESHOLD_REGISTRY["final_model"]["minimum_supporting_sources"] and ev6 is not None and ev6 > 0 and risks[6] < FORMULA_AND_THRESHOLD_REGISTRY["final_model"]["hold_transition_risk_max"] and not severe_crowd and event_permission != "BLOCK":
                final_bias = f"HOLD_{anchor}"
            else:
                final_bias = f"CAUTION_{anchor}"
            hold_permission = "BLOCK" if final_bias.startswith("BLOCK") else ("HOLD" if final_bias.startswith("HOLD") else ("CAUTION" if final_bias.startswith("CAUTION") else "WAIT"))
            entry_permission = "BLOCK" if final_bias.startswith("BLOCK") else ("ALLOW" if final_bias.startswith("HOLD") and event_permission == "ALLOW" else ("CAUTION" if anchor in {"BUY", "SELL"} and final_bias != "INSUFFICIENT_EVIDENCE" else "WAIT"))
            exit_warning = "NONE"
            if severe_crowd and risks[1] >= 65 and anchor in {"BUY", "SELL"}:
                final_bias = f"EXIT_OR_REDUCE_{anchor}"
                exit_warning = final_bias
                hold_permission = "EXIT_OR_REDUCE"
                entry_permission = "BLOCK"
            source_strength = {
                "TECHNICAL_FUNDAMENTAL": technical_quality, "SESSION": session_quality,
                "NEWS_SENTIMENT": news_safety, "CROWD_PSYCHOLOGY": crowd_quality,
            }
            supporting = [(name, score) for name, score in source_strength.items() if votes.get(name) == anchor and score is not None]
            conflicting = [(name, score) for name, score in source_strength.items() if votes.get(name) in {"BUY", "SELL"} and votes.get(name) != anchor and score is not None]
            strongest_support = max(supporting, key=lambda item: item[1])[0] if supporting else "NONE"
            strongest_conflict = max(conflicting, key=lambda item: item[1])[0] if conflicting else "NONE"
            no_trade = block_reason or ("; ".join(f"missing {name}" for name in critical_missing) if critical_missing else ("expected value unavailable or near zero" if near_zero else "NONE"))
            confidence = float(np.clip(0.45 * agreement + 0.35 * completeness + 0.20 * (final_score or 0.0), 0.0, 100.0))
            refs = {
                "technical_fundamental": f"field10_daily_snapshot_symbol:{snapshot_id}:{symbol}",
                "sessions": session.get("refs", []),
                "news": news.get("source_rows", []),
                "crowd": f"field10_daily_crowd_psychology_rank:{snapshot_id}:{symbol}",
            }
            hashes = {
                "technical_fundamental": technical.get("content_hash"), "sessions": session.get("hashes", []),
                "news": news.get("source_hashes", []), "crowd": crowd.get("content_hash"),
            }
            publication_payload = {"snapshot": snapshot_id, "symbol": symbol, "score": final_score, "bias": final_bias, "refs": refs, "hashes": hashes}
            publication_hash = _hash(publication_payload)
            previous_rank = previous.get(symbol)
            row = {
                "daily_snapshot_id": snapshot_id, "run_id": technical.get("canonical_run_id"), "parent_run_id": snapshot.get("parent_run_id"),
                "broker_day": snapshot.get("broker_day"), "completed_h1_candle": snapshot.get("latest_completed_h1"),
                "universe_hash": snapshot.get("universe_hash"), "symbol": symbol, "source_identity": technical.get("source_id"),
                "snapshot_hash": technical.get("snapshot_hash"), "final_rank": None, "rank_icon": None, "final_score": final_score,
                "previous_final_rank": previous_rank, "rank_change": None, "final_lock_status": "LOCKED_DAILY_PUBLICATION",
                "locked_at_broker_time": snapshot.get("published_at_broker_time"), "locked_until_broker_time": snapshot.get("locked_until_broker_time"),
                "final_publication_hash": publication_hash, "technical_fundamental_rank": technical.get("daily_rank"),
                "technical_fundamental_score": technical_quality, "technical_fundamental_bias": tech_bias,
                "best_session_rank": session.get("rank"), "best_session_1": session.get("best1"), "best_session_2": session.get("best2"),
                "session_score": session_quality, "session_bias": session.get("bias"), "news_sentiment_rank": news.get("rank"),
                "news_sentiment_bias": news.get("bias"), "event_risk_permission": event_permission,
                "impact_remaining_percentage": news.get("impact_remaining"), "absorption_percentage": news.get("absorption"),
                "crowd_psychology_rank": crowd.get("crowd_rank"), "crowd_psychology_score": crowd_score,
                "crowd_state": crowd.get("crowd_state"), "crowd_direction": crowd.get("crowd_direction"), "crowd_confidence": crowd.get("crowd_confidence"),
                "final_less_risky_bias_to_hold": final_bias, "final_less_risky_bias_confidence": confidence,
                "final_bias_agreement": agreement, "final_bias_conflict": conflict, "final_hold_permission": hold_permission,
                "final_entry_permission": entry_permission, "final_exit_risk_warning": exit_warning,
                "bias_source_majority": f"{majority}:{max(buy_count,sell_count)}/4", "strongest_supporting_source": strongest_support,
                "strongest_conflicting_source": strongest_conflict, "no_trade_reason": no_trade,
                "final_explanation": f"Shadow fusion used four persisted child sources only. Anchor={anchor}; majority={majority}; supporters={supporters}/4; score={final_score}; transition6H={risks[6]:.2f}; EV6H={ev6}.",
                "final_transition_bias_risk_1h": risks[1], "final_transition_bias_risk_6h": risks[6],
                "final_transition_bias_risk_12h": risks[12], "final_transition_bias_risk_24h": risks[24],
                "transition_direction_1h": "REVERSAL_OR_WAIT" if risks[1] >= 65 else "BIAS_LIKELY_REMAINS",
                "transition_direction_6h": "REVERSAL_OR_WAIT" if risks[6] >= 65 else "BIAS_LIKELY_REMAINS",
                "transition_direction_12h": "REVERSAL_OR_WAIT" if risks[12] >= 65 else "BIAS_LIKELY_REMAINS",
                "transition_direction_24h": "REVERSAL_OR_WAIT" if risks[24] >= 65 else "BIAS_LIKELY_REMAINS",
                "probability_bias_remains_1h": 100.0-risks[1], "probability_bias_remains_6h": 100.0-risks[6],
                "probability_bias_remains_12h": 100.0-risks[12], "probability_bias_remains_24h": 100.0-risks[24],
                "probability_bias_reverses_1h": risks[1] * conflict/100.0, "probability_bias_reverses_6h": risks[6] * conflict/100.0,
                "probability_bias_reverses_12h": risks[12] * conflict/100.0, "probability_bias_reverses_24h": risks[24] * conflict/100.0,
                "transition_risk_confidence": completeness, "main_transition_risk_driver": max((("REGIME", regime6 or 0.0), ("CROWD", crowd_risks[6] or 0.0), ("NEWS", news_contribution or 0.0), ("SESSION", session_contribution or 0.0)), key=lambda item:item[1])[0],
                "regime_transition_contribution": regime6, "crowd_transition_contribution": crowd_risks[6],
                "news_transition_contribution": news_contribution, "session_transition_contribution": session_contribution,
                "expected_value_1h": final_ev[1].get("ev"), "expected_value_6h": final_ev[6].get("ev"),
                "expected_value_12h": final_ev[12].get("ev"), "expected_value_24h": final_ev[24].get("ev"),
                "risk_adjusted_expected_value_1h": final_ev[1].get("risk_adjusted_ev"), "risk_adjusted_expected_value_6h": final_ev[6].get("risk_adjusted_ev"),
                "risk_adjusted_expected_value_12h": final_ev[12].get("risk_adjusted_ev"), "risk_adjusted_expected_value_24h": final_ev[24].get("risk_adjusted_ev"),
                "expected_return_1h": final_ev[1].get("expected_return"), "expected_return_6h": final_ev[6].get("expected_return"),
                "expected_return_12h": final_ev[12].get("expected_return"), "expected_return_24h": final_ev[24].get("expected_return"),
                "probability_of_profit_1h": final_ev[1].get("probability_profit"), "probability_of_profit_6h": final_ev[6].get("probability_profit"),
                "probability_of_profit_12h": final_ev[12].get("probability_profit"), "probability_of_profit_24h": final_ev[24].get("probability_profit"),
                "probability_reach_expected_value_1h": final_ev[1].get("probability_reach_expected_value"), "probability_reach_expected_value_6h": final_ev[6].get("probability_reach_expected_value"),
                "probability_reach_expected_value_12h": final_ev[12].get("probability_reach_expected_value"), "probability_reach_expected_value_24h": final_ev[24].get("probability_reach_expected_value"),
                "expected_mfe_1h": final_ev[1].get("expected_mfe"), "expected_mfe_6h": final_ev[6].get("expected_mfe"),
                "expected_mfe_12h": final_ev[12].get("expected_mfe"), "expected_mfe_24h": final_ev[24].get("expected_mfe"),
                "expected_mae_1h": final_ev[1].get("expected_mae"), "expected_mae_6h": final_ev[6].get("expected_mae"),
                "expected_mae_12h": final_ev[12].get("expected_mae"), "expected_mae_24h": final_ev[24].get("expected_mae"),
                "cvar_95_1h": final_ev[1].get("cvar95"), "cvar_95_6h": final_ev[6].get("cvar95"),
                "cvar_95_12h": final_ev[12].get("cvar95"), "cvar_95_24h": final_ev[24].get("cvar95"),
                "expected_spread_cost": final_ev[1].get("expected_spread_cost"), "expected_slippage_cost": final_ev[1].get("expected_slippage_cost"),
                "net_expected_value_after_cost": final_ev[1].get("ev"), "value_unit": VALUE_UNIT,
                "evidence_lineage_json": _json({"source_rows": refs, "source_hashes": hashes}),
                "four_source_row_references_json": _json(refs), "four_source_hashes_json": _json(hashes),
                "horizon_probability_json": _json({h: {"profit": final_ev[h].get("probability_profit"), "remains": 100.0-risks[h], "reverses": risks[h]*conflict/100.0} for h in (1,6,12,24)}),
                "horizon_ev_component_json": _json(final_ev), "transition_risk_component_json": _json(risk_parts),
                "fusion_component_json": _json({"components": detail, "votes": votes, "supporters": supporters, "completeness": completeness}),
                "penalty_json": _json(penalties), "formula_version": FINAL_FORMULA_VERSION, "model_version": FINAL_MODEL_VERSION,
                "threshold_registry_version": THRESHOLD_VERSION, "validation_status": "SHADOW_ONLY_NOT_PROMOTED",
                "lock_status": "LOCKED", "publication_status": "PUBLISHED_LOCKED_CHILD_SHADOW", "content_hash": "",
                "created_broker_time": snapshot.get("published_at_broker_time") or snapshot.get("created_at_broker_time"),
                "created_system_time": _audit_now(),
            }
            row["content_hash"] = _hash({k:v for k,v in row.items() if k not in {"content_hash","created_system_time","final_rank","rank_icon","rank_change"}})
            built.append(row)
        ranked = sorted(built, key=lambda row: (row["final_score"] is None, -(row["final_score"] or -999), row["symbol"]))
        for rank, row in enumerate(ranked, start=1):
            row["final_rank"] = rank if row["final_score"] is not None else None
            row["rank_icon"] = f"★ {rank}" if rank <= 4 and row["final_score"] is not None else (str(rank) if row["final_score"] is not None else "—")
            previous_rank = row.get("previous_final_rank")
            row["rank_change"] = None if previous_rank is None or row["final_rank"] is None else int(previous_rank) - int(row["final_rank"])
            row["content_hash"] = _hash({k:v for k,v in row.items() if k not in {"content_hash","created_system_time"}})
    return built


def publish_crowd_and_final_tables(
    state: MutableMapping[str, Any], *, daily_snapshot_id: str | None,
    selected_symbols: Sequence[str], path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Heavy Settings-only publication from the existing canonical snapshot."""
    migration = migrate_crowd_final_database(path)
    snapshot = _snapshot_identity(path, daily_snapshot_id)
    if not snapshot:
        return {"ok": False, "status": "NO_DAILY_SNAPSHOT", "migration": migration}
    snapshot_id = str(snapshot["daily_snapshot_id"])
    symbol_rows = _snapshot_symbol_rows(path, snapshot_id)
    if not symbol_rows:
        return {"ok": False, "status": "NO_DAILY_SYMBOL_ROWS", "daily_snapshot_id": snapshot_id, "migration": migration}
    states = _load_states([row["symbol"] for row in symbol_rows])
    session_report = _persist_session_map(path, snapshot, symbol_rows, states)
    crowd_rows = _build_crowd_rows(path, snapshot, symbol_rows, states)
    with _connect(path) as conn:
        crowd_inserted = _insert_rows(conn, "field10_daily_crowd_psychology_rank", crowd_rows, CROWD_COLUMN_TYPES)
        conn.commit()
    final_rows = _build_final_rows(path, snapshot, symbol_rows)
    with _connect(path) as conn:
        final_inserted = _insert_rows(conn, "field10_daily_final_multi_symbol_rank", final_rows, FINAL_COLUMN_TYPES)
        conn.commit()
        counts = {
            "session": int(conn.execute("SELECT COUNT(*) FROM field10_daily_session_entry_map WHERE daily_snapshot_id=?", (snapshot_id,)).fetchone()[0]),
            "crowd": int(conn.execute("SELECT COUNT(*) FROM field10_daily_crowd_psychology_rank WHERE daily_snapshot_id=?", (snapshot_id,)).fetchone()[0]),
            "final": int(conn.execute("SELECT COUNT(*) FROM field10_daily_final_multi_symbol_rank WHERE daily_snapshot_id=?", (snapshot_id,)).fetchone()[0]),
        }
    report = {
        "ok": counts["crowd"] == len(symbol_rows) and counts["final"] == len(symbol_rows),
        "status": "PUBLISHED_LOCKED_CHILD_SHADOW", "daily_snapshot_id": snapshot_id,
        "broker_day": snapshot.get("broker_day"), "completed_h1_candle": snapshot.get("latest_completed_h1"),
        "parent_run_id": snapshot.get("parent_run_id"), "universe_hash": snapshot.get("universe_hash"),
        "session_report": session_report, "crowd_rows_inserted": crowd_inserted,
        "final_rows_inserted": final_inserted, "persisted_counts": counts,
        "models": [CROWD_MODEL_VERSION, FINAL_MODEL_VERSION], "validation_status": "SHADOW_ONLY_NOT_PROMOTED",
        "migration": migration,
    }
    state["field10_crowd_final_report_20260704"] = report
    return report


def _display_frame(rows: Sequence[Mapping[str, Any]], mapping: Mapping[str, str], preferred: Sequence[str] = ()) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=list(mapping.values()))
    frame = pd.DataFrame([{mapping[key]: row.get(key) for key in mapping} for row in rows])
    first = [column for column in preferred if column in frame.columns]
    return frame.loc[:, first + [column for column in frame.columns if column not in first]]


def load_session_entry_map(*, daily_snapshot_id: str | None = None, path: Path | str = DB_PATH) -> pd.DataFrame:
    snapshot = _snapshot_identity(path, daily_snapshot_id)
    if not snapshot:
        return pd.DataFrame()
    with connect_readonly(path, timeout=30) as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM field10_daily_session_entry_map WHERE daily_snapshot_id=? ORDER BY COALESCE(session_rank,999999),symbol,session_name",
            (snapshot["daily_snapshot_id"],),
        ).fetchall()]
    labels = {
        "session_rank": "Session Rank", "symbol": "Symbol", "session_name": "Session",
        "session_score": "Session Score", "session_bias": "Session Bias", "entry_permission": "Entry Permission",
        "sample_size": "Evidence Sample Size", "mean_return_1h": "Mean Return 1H (%)",
        "median_return_1h": "Median Return 1H (%)", "win_rate": "Win Rate (%)",
        "session_volatility": "Session Volatility (%)", "broker_day": "Broker Day",
        "completed_h1_candle": "Completed H1 Candle", "publication_status": "Publication Status",
    }
    return _display_frame(rows, labels)


def load_crowd_psychology_rank(*, daily_snapshot_id: str | None = None, path: Path | str = DB_PATH) -> pd.DataFrame:
    snapshot = _snapshot_identity(path, daily_snapshot_id)
    if not snapshot:
        return pd.DataFrame(columns=list(CROWD_DISPLAY_MAP.values()))
    with connect_readonly(path, timeout=30) as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM field10_daily_crowd_psychology_rank WHERE daily_snapshot_id=? ORDER BY COALESCE(crowd_rank,999999),symbol",
            (snapshot["daily_snapshot_id"],),
        ).fetchall()]
    return _display_frame(rows, CROWD_DISPLAY_MAP, ("Crowd Rank", "Symbol", "Crowd State", "Crowd Direction", "Crowd Less-Risky Bias", "Crowd Entry Permission", "Crowd Hold Permission"))


def _latest_safety(conn: sqlite3.Connection, snapshot_id: str) -> dict[str, str]:
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='field10_daily_safety_event'").fetchone():
        return {}
    rows = conn.execute(
        "SELECT s.symbol,s.safety_veto FROM field10_daily_safety_event s JOIN (SELECT symbol,MAX(observed_at_broker_time) observed FROM field10_daily_safety_event WHERE daily_snapshot_id=? GROUP BY symbol) latest ON latest.symbol=s.symbol AND latest.observed=s.observed_at_broker_time WHERE s.daily_snapshot_id=?",
        (snapshot_id, snapshot_id),
    ).fetchall()
    return {str(row[0]): str(row[1] or "CLEAR").upper() for row in rows}


def apply_live_safety_overlay(frame: pd.DataFrame, safety_by_symbol: Mapping[str, str]) -> pd.DataFrame:
    """Downgrade permissions without changing locked rank or historical bias."""
    if frame.empty:
        return frame
    view = frame.copy()
    for index, row in view.iterrows():
        symbol = str(row.get("Symbol") or "")
        veto = str(safety_by_symbol.get(symbol, "CLEAR")).upper()
        if veto in {"BLOCK", "PROTECT", "EXIT_OR_REDUCE"}:
            view.at[index, "Final Entry Permission"] = "BLOCK"
            view.at[index, "Final Hold Permission"] = "EXIT_OR_REDUCE" if veto in {"PROTECT", "EXIT_OR_REDUCE"} else "BLOCK"
            view.at[index, "Final Exit/Risk Warning"] = "LIVE_SAFETY_DOWNGRADE_ONLY"
        elif veto == "CAUTION":
            if str(row.get("Final Entry Permission")) == "ALLOW":
                view.at[index, "Final Entry Permission"] = "CAUTION"
            if str(row.get("Final Hold Permission")) == "HOLD":
                view.at[index, "Final Hold Permission"] = "CAUTION"
    return view


def load_final_multi_symbol_rank(*, daily_snapshot_id: str | None = None, path: Path | str = DB_PATH, apply_live_safety: bool = True) -> pd.DataFrame:
    snapshot = _snapshot_identity(path, daily_snapshot_id)
    if not snapshot:
        return pd.DataFrame(columns=list(FINAL_DISPLAY_MAP.values()))
    with connect_readonly(path, timeout=30) as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM field10_daily_final_multi_symbol_rank WHERE daily_snapshot_id=? ORDER BY COALESCE(final_rank,999999),symbol",
            (snapshot["daily_snapshot_id"],),
        ).fetchall()]
        safety = _latest_safety(conn, str(snapshot["daily_snapshot_id"])) if apply_live_safety else {}
    frame = _display_frame(rows, FINAL_DISPLAY_MAP, MOBILE_FINAL_COLUMNS)
    return apply_live_safety_overlay(frame, safety) if apply_live_safety else frame


def record_immutable_outcome(*, table: str, daily_snapshot_id: str, symbol: str, prediction_content_hash: str, horizon_hours: int, realized_return_pct: float | None, realized_direction: str | None, direction_correct: bool | None, realized_mfe_pct: float | None, realized_mae_pct: float | None, settled_broker_time: str, evaluation: Mapping[str, Any], realized_net_return_pct: float | None = None, path: Path | str = DB_PATH) -> dict[str, Any]:
    """Insert outcome evidence without updating the original prediction."""
    if table not in {"crowd", "final"}:
        raise ValueError("table must be 'crowd' or 'final'")
    migrate_crowd_final_database(path)
    payload = {
        "daily_snapshot_id": daily_snapshot_id, "symbol": normalize_symbol(symbol),
        "prediction_content_hash": prediction_content_hash, "horizon_hours": int(horizon_hours),
        "realized_return_pct": realized_return_pct, "realized_direction": realized_direction,
        "direction_correct": None if direction_correct is None else int(bool(direction_correct)),
        "realized_mfe_pct": realized_mfe_pct, "realized_mae_pct": realized_mae_pct,
        "settled_broker_time": settled_broker_time, "evaluation": dict(evaluation),
        "realized_net_return_pct": realized_net_return_pct,
    }
    outcome_hash = _hash(payload)
    outcome_id = f"F10OUT-{outcome_hash[:24]}"
    table_name = "field10_crowd_psychology_outcome" if table == "crowd" else "field10_final_multi_symbol_outcome"
    with _connect(path) as conn:
        if table == "crowd":
            conn.execute(
                f"INSERT OR IGNORE INTO {table_name}(outcome_id,daily_snapshot_id,symbol,prediction_content_hash,horizon_hours,realized_return_pct,realized_direction,direction_correct,realized_mfe_pct,realized_mae_pct,evaluation_json,outcome_hash,settled_broker_time,created_system_time) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (outcome_id,daily_snapshot_id,normalize_symbol(symbol),prediction_content_hash,int(horizon_hours),realized_return_pct,realized_direction,None if direction_correct is None else int(bool(direction_correct)),realized_mfe_pct,realized_mae_pct,_json(evaluation),outcome_hash,settled_broker_time,_audit_now()),
            )
        else:
            conn.execute(
                f"INSERT OR IGNORE INTO {table_name}(outcome_id,daily_snapshot_id,symbol,prediction_content_hash,horizon_hours,realized_return_pct,realized_direction,direction_correct,realized_mfe_pct,realized_mae_pct,realized_net_return_pct,evaluation_json,outcome_hash,settled_broker_time,created_system_time) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (outcome_id,daily_snapshot_id,normalize_symbol(symbol),prediction_content_hash,int(horizon_hours),realized_return_pct,realized_direction,None if direction_correct is None else int(bool(direction_correct)),realized_mfe_pct,realized_mae_pct,realized_net_return_pct,_json(evaluation),outcome_hash,settled_broker_time,_audit_now()),
            )
        conn.commit()
    return {"ok": True, "status": "INSERTED_OR_ALREADY_EXISTS", "outcome_id": outcome_id, "outcome_hash": outcome_hash}


__all__ = [
    "CROWD_MODEL_VERSION", "FINAL_MODEL_VERSION", "FORMULA_AND_THRESHOLD_REGISTRY",
    "MOBILE_FINAL_COLUMNS", "VALUE_UNIT", "extract_exact_completed_h1",
    "pair_direction_from_currency_evidence", "migrate_crowd_final_database",
    "verify_crowd_final_database", "publish_crowd_and_final_tables",
    "load_session_entry_map", "load_crowd_psychology_rank",
    "load_final_multi_symbol_rank", "apply_live_safety_overlay",
    "record_immutable_outcome",
]

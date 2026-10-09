"""Central thresholds for settled trust validation.

These values control classification only. They never modify the protected Full
Metric formulas or create a direction.
"""
from __future__ import annotations

TRUST_CONFIG = {
    "validated_min_samples": 100,
    "developing_min_samples": 30,
    "minimum_calibration_samples": 30,
    "minimum_dm_samples": 30,
    "minimum_spa_samples": 40,
    "minimum_pbo_configurations": 2,
    "minimum_pbo_folds": 4,
    "target_interval_coverage": 0.80,
    "acceptable_ece": 0.12,
    "acceptable_mce": 0.22,
    "acceptable_coverage_error": 0.15,
    "minimum_profit_factor": 1.0,
    "pip_size": 0.0001,
    "default_cost_pips": 1.2,
    "safety_buffer_pips": 0.4,
    "maximum_display_rows_phone": 48,
    "maximum_display_rows_desktop": 160,
}

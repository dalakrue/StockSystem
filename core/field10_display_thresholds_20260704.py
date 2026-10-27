"""Versioned display-only thresholds for Field 10 semantic styling."""
VERSION = "field10-display-thresholds-20260704-v1"
THRESHOLDS = {
    "expected_value": {"negative": 0.0, "strong": 0.05},
    "probability": {"low": 45.0, "high": 60.0},
    "transition_risk": {"stable": 35.0, "high": 65.0},
    "volume_z": {"normal": 2.0, "extreme": 4.0},
    "severity": {"caution": 40.0, "protect": 70.0, "block": 90.0},
}

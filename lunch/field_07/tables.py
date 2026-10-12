"""Field 7 history projection and lightweight filtering."""
from __future__ import annotations
from typing import Any
import pandas as pd

HISTORY_COLUMNS = [
    "run_id", "broker_candle_time", "symbol", "timeframe", "session",
    "canonical_decision", "research_approved_action", "approved_horizons",
    "abstained_horizons", "change_probability", "regime_age",
    "forecastability_1h", "forecastability_3h", "forecastability_6h",
    "eligible_model_set", "forecast_bias_1h", "forecast_bias_3h",
    "coverage_1h", "coverage_3h", "nominal_ev", "robust_ev", "tail_risk",
    "decision_stability", "regime_remaining_edge", "event_state",
    "overfitting_risk", "research_trust_score", "risk_multiplier",
    "settled_outcome", "realized_pips",
]


def prepare_history(frame: pd.DataFrame, query: str = "", limit: int = 25) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    output = frame.copy()
    for column in HISTORY_COLUMNS:
        if column not in output.columns:
            output[column] = None
    output = output[HISTORY_COLUMNS]
    if "broker_candle_time" in output.columns:
        parsed = pd.to_datetime(output["broker_candle_time"], errors="coerce", utc=True)
        output = output.assign(_sort_time=parsed).sort_values("_sort_time", ascending=False).drop(columns="_sort_time")
    if query:
        mask = output.astype(str).apply(lambda column: column.str.contains(query, case=False, na=False)).any(axis=1)
        output = output.loc[mask]
    return output.head(int(limit)).reset_index(drop=True)

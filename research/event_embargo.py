"""Configurable event embargo projection from canonical sentiment/event evidence."""
from __future__ import annotations
from typing import Any, Mapping
from research._utils import deep_find, number

EVENTS = ("ECB", "FEDERAL RESERVE", "CPI", "PCE", "NFP", "EUROZONE CPI", "PMI", "GDP", "CENTRAL-BANK SPEECH")


def evaluate(sentiment: Mapping[str, Any]) -> dict[str, Any]:
    text = str(sentiment).upper()
    minutes = number(deep_find(sentiment, ("minutes_to_event", "event_minutes", "time_to_event_minutes")), None)
    matched = next((event for event in EVENTS if event in text), None)
    if not matched:
        return {"state": "NORMAL", "event": None, "minutes_to_event": minutes, "trust_multiplier": 1.0}
    if minutes is None:
        state, multiplier = "PRE-EVENT REDUCED TRUST", 0.75
    elif -60 <= minutes < 0:
        state, multiplier = "POST-EVENT PRICE DISCOVERY", 0.45
    elif 0 <= minutes <= 60:
        state, multiplier = "PRE-EVENT NO NEW ENTRY", 0.35
    elif -180 <= minutes < -60:
        state, multiplier = "POST-EVENT NORMALIZATION", 0.75
    else:
        state, multiplier = "PRE-EVENT REDUCED TRUST", 0.75
    return {"state": state, "event": matched, "minutes_to_event": minutes, "trust_multiplier": multiplier}

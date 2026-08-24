from __future__ import annotations
import re
from typing import Any

MAP = {"STRONG BUY":1.0,"BUY":.75,"WEAK BUY":.35,"HOLD BULLISH":.15,"WAIT":0.0,"WAIT PULLBACK":0.0,"HOLD":0.0,"HOLD BEARISH":-.15,"WEAK SELL":-.35,"SELL":-.75,"STRONG SELL":-1.0}

def normalize_label(value: Any) -> str:
    text = re.sub(r"[_\-]+", " ", str(value or "").upper()).strip()
    text = re.sub(r"\s+", " ", text)
    for label in sorted(MAP, key=len, reverse=True):
        if label in text: return label
    return ""

def map_decision(value: Any, intended_direction: str | None = None) -> dict[str, Any]:
    raw = "" if value is None else str(value)
    label = normalize_label(raw)
    intended = str(intended_direction or "").upper().strip()
    if not intended and label == "WAIT PULLBACK":
        if "BUY" in raw.upper() or "BULL" in raw.upper(): intended = "BUY"
        elif "SELL" in raw.upper() or "BEAR" in raw.upper(): intended = "SELL"
    if not intended and label == "HOLD BULLISH": intended = "BUY"
    if not intended and label == "HOLD BEARISH": intended = "SELL"
    action = MAP.get(label, 0.0)
    reason = "blank decision treated as non-directional" if not label else f"mapped by ARCEF-SV standard: {label}"
    return {"raw_label":raw,"normalized_label":label or "BLANK","standardized_action":action,"intended_direction":intended or "NONE","mapping_reason":reason}

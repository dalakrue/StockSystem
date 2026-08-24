from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class DriftRegistry:
    events: list[dict[str, Any]] = field(default_factory=list)
    def record(self, monitor_name: str, result: dict[str, Any], candle: Any, affected_model: str) -> None:
        if result.get("drift"):
            self.events.append({"monitor_name": monitor_name, "detection_candle": candle, "affected_model": affected_model, **result})

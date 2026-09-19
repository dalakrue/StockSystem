"""Immutable canonical contract for Project Quant V12 shadow research."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from types import MappingProxyType
from typing import Any, Mapping
import json

SCHEMA_VERSION = "research-run-snapshot-v12.1"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def stable_hash(value: Any) -> str:
    payload = json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("utf-8")).hexdigest()


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, tuple):
        return tuple(_freeze(v) for v in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return value


@dataclass(frozen=True)
class ResearchRunSnapshot:
    run_id: str
    calculation_generation: str
    snapshot_hash: str
    broker_time: str
    candle_time: str
    symbol: str
    timeframe: str
    settled_outcome_cutoff: str
    source_hashes: Mapping[str, str] = field(default_factory=dict)
    configuration_hash: str = ""
    schema_version: str = SCHEMA_VERSION
    module_statuses: Mapping[str, str] = field(default_factory=dict)
    sample_sizes: Mapping[str, int] = field(default_factory=dict)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    compact_results: Mapping[str, Any] = field(default_factory=dict)
    full_results: Mapping[str, Any] = field(default_factory=dict)
    created_at_utc: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_hashes", _freeze(dict(self.source_hashes)))
        object.__setattr__(self, "module_statuses", _freeze(dict(self.module_statuses)))
        object.__setattr__(self, "sample_sizes", _freeze(dict(self.sample_sizes)))
        object.__setattr__(self, "warnings", tuple(str(v) for v in self.warnings))
        object.__setattr__(self, "compact_results", _freeze(dict(self.compact_results)))
        object.__setattr__(self, "full_results", _freeze(dict(self.full_results)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "calculation_generation": self.calculation_generation,
            "snapshot_hash": self.snapshot_hash,
            "broker_time": self.broker_time,
            "candle_time": self.candle_time,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "settled_outcome_cutoff": self.settled_outcome_cutoff,
            "source_hashes": _thaw(self.source_hashes),
            "configuration_hash": self.configuration_hash,
            "schema_version": self.schema_version,
            "module_statuses": _thaw(self.module_statuses),
            "sample_sizes": _thaw(self.sample_sizes),
            "warnings": list(self.warnings),
            "compact_results": _thaw(self.compact_results),
            "full_results": _thaw(self.full_results),
            "created_at_utc": self.created_at_utc,
        }

    @classmethod
    def build(cls, *, run_id: str, calculation_generation: str, broker_time: str, candle_time: str, symbol: str, timeframe: str, settled_outcome_cutoff: str, source_hashes: Mapping[str, str], configuration: Mapping[str, Any], module_statuses: Mapping[str, str], sample_sizes: Mapping[str, int], warnings: list[str] | tuple[str, ...], compact_results: Mapping[str, Any], full_results: Mapping[str, Any], created_at_utc: str | None = None) -> "ResearchRunSnapshot":
        created = created_at_utc or datetime.now(timezone.utc).isoformat()
        config_hash = stable_hash(configuration)
        content = {
            "run_id": str(run_id),
            "calculation_generation": str(calculation_generation),
            "broker_time": str(broker_time),
            "candle_time": str(candle_time),
            "symbol": str(symbol).upper(),
            "timeframe": str(timeframe).upper(),
            "settled_outcome_cutoff": str(settled_outcome_cutoff),
            "source_hashes": dict(source_hashes),
            "configuration_hash": config_hash,
            "schema_version": SCHEMA_VERSION,
            "module_statuses": dict(module_statuses),
            "sample_sizes": dict(sample_sizes),
            "warnings": list(warnings),
            "compact_results": dict(compact_results),
            "full_results": dict(full_results),
            "created_at_utc": created,
        }
        return cls(snapshot_hash=stable_hash(content), **content)


__all__ = ["ResearchRunSnapshot", "SCHEMA_VERSION", "stable_hash"]

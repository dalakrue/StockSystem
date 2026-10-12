"""System-wide contracts for ADX Quant Pro.

This file remains backward compatible with the previous facade by importing the
legacy implementation first, then exposing the canonical snapshot/view-model
contracts used by the 2026-07-09 Field 10/Dinner/export authority layer.
"""
from __future__ import annotations

try:  # preserve every old import name
    from core.legacy_impl.system_contract_impl import *  # type: ignore  # noqa: F401,F403
except Exception:  # pragma: no cover - the new contracts are still usable
    pass

from dataclasses import dataclass, field, asdict
from enum import Enum
from hashlib import sha256
from typing import Any, Mapping, Sequence
import json


class PublicationStatus(str, Enum):
    DRAFT = "DRAFT"
    PARTIAL_READY = "PARTIAL_READY"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    STALE = "STALE"
    SYNC_ERROR = "SYNC_ERROR"
    NEEDS_LOAD = "NEEDS_LOAD"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    RESEARCH_ONLY = "RESEARCH_ONLY"


class DataQualityStatus(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"


class ProviderStatus(str, Enum):
    READY = "READY"
    PARTIAL_READY = "PARTIAL_READY"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CACHE_USED = "CACHE_USED"
    UNAVAILABLE = "UNAVAILABLE"


def ordered_unique(values: Any, *, limit: int | None = 12) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Sequence):
        return []
    out: list[str] = []
    for value in values:
        text = str(value or "").strip().upper().replace("/", "").replace("_", "").replace(" ", "")
        if text and text not in out:
            out.append(text)
        if limit is not None and len(out) >= int(limit):
            break
    return out


def stable_hash(payload: Mapping[str, Any] | Sequence[Any] | str | None) -> str:
    def normalize(value: Any) -> Any:
        if hasattr(value, "to_dict"):
            try:
                return value.to_dict(orient="records")
            except Exception:
                pass
        if isinstance(value, Mapping):
            return {str(k): normalize(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
        if isinstance(value, (list, tuple)):
            return [normalize(v) for v in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)
    raw = json.dumps(normalize(payload), sort_keys=True, ensure_ascii=False, default=str)
    return sha256(raw.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class RunSnapshot:
    parent_run_id: str
    generation_id: str
    daily_snapshot_id: str
    broker_day: str
    broker_time: str
    timeframe: str
    completed_broker_candle: str
    ordered_symbol_universe: list[str]
    loaded_symbol_count: int
    failed_symbol_count: int
    provider_summary: str = "UNAVAILABLE"
    data_quality_summary: str = "UNKNOWN"
    input_hash: str = ""
    output_hash: str = ""
    snapshot_hash: str = ""
    publication_status: str = PublicationStatus.PARTIAL_READY.value
    created_at_broker_time: str = ""
    model_version: str = "field10_research_authority_20260709"
    formula_version: str = "non_destructive_v1"
    ui_version: str = "mobile_export_v1"
    migration_version: str = "20260709_field10_research_authority"

    def __post_init__(self):
        if not self.input_hash:
            object.__setattr__(self, "input_hash", stable_hash({
                "parent_run_id": self.parent_run_id,
                "generation_id": self.generation_id,
                "broker_day": self.broker_day,
                "timeframe": self.timeframe,
                "completed_broker_candle": self.completed_broker_candle,
                "ordered_symbol_universe": self.ordered_symbol_universe,
            }))
        if not self.snapshot_hash:
            object.__setattr__(self, "snapshot_hash", stable_hash({
                "input_hash": self.input_hash,
                "loaded": self.loaded_symbol_count,
                "failed": self.failed_symbol_count,
                "publication_status": self.publication_status,
            }))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SymbolSnapshot:
    daily_snapshot_id: str
    parent_run_id: str
    generation_id: str
    broker_day: str
    timeframe: str
    completed_broker_candle: str
    symbol: str
    model_version: str = "field10_research_authority_20260709"
    formula_version: str = "non_destructive_v1"
    input_hash: str = ""
    output_hash: str = ""
    created_at_broker_time: str = ""
    publication_status: str = PublicationStatus.PARTIAL_READY.value
    incomplete_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Field10ViewModel:
    snapshot_hash: str
    table_name: str = "Field 10 Unified Daily Locked Rank Table"
    rows: list[dict[str, Any]] = field(default_factory=list)
    supporting_rows: list[dict[str, Any]] = field(default_factory=list)
    publication_status: str = PublicationStatus.PARTIAL_READY.value
    trusted_reason: str = "Complete snapshot identity required before publishing final rank."


@dataclass
class DinnerViewModel:
    snapshot_hash: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    research_model_version: str = "dinner_research_background_20260709"
    publication_status: str = PublicationStatus.PARTIAL_READY.value


@dataclass
class VisualizationViewModel:
    snapshot_hash: str
    rank_rows: list[dict[str, Any]] = field(default_factory=list)
    risk_rows: list[dict[str, Any]] = field(default_factory=list)
    session_rows: list[dict[str, Any]] = field(default_factory=list)
    publication_status: str = PublicationStatus.PARTIAL_READY.value


@dataclass
class ExportManifest:
    snapshot_hash: str
    parent_run_id: str = ""
    broker_day: str = ""
    timeframe: str = "H4"
    completed_broker_candle: str = ""
    files: list[str] = field(default_factory=list)
    publication_status: str = PublicationStatus.PARTIAL_READY.value


@dataclass
class MobileLayoutState:
    active_tab: str = "Settings"
    selected_symbol: str = "EURUSD"
    download_mode: bool = False
    export_panel_open: bool = False
    snapshot_hash: str = ""


try:
    from core.legacy_impl.system_contract_impl import __all__ as _legacy_all  # type: ignore
except Exception:
    _legacy_all = []

__all__ = sorted(set(list(_legacy_all) + [
    "PublicationStatus", "DataQualityStatus", "ProviderStatus", "RunSnapshot", "SymbolSnapshot",
    "Field10ViewModel", "DinnerViewModel", "VisualizationViewModel", "ExportManifest", "MobileLayoutState",
    "ordered_unique", "stable_hash",
]))

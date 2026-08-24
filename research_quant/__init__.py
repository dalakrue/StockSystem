"""Canonical Regime-Calibrated Evidence Fusion with Selective Validation.

The public API is loaded lazily so importing the Streamlit shell does not load
research persistence, NumPy, pandas, or optional model adapters before the
controlled Settings run asks for them.
"""
from __future__ import annotations

from typing import Any


def build_crcef_sv_result(*args: Any, **kwargs: Any):
    from research_quant.orchestrator import build_crcef_sv_result as implementation
    return implementation(*args, **kwargs)


def build_crcef_sv_research(*args: Any, **kwargs: Any):
    return build_crcef_sv_result(*args, **kwargs)


def publish_crcef_sv_research(*args: Any, **kwargs: Any):
    from research_quant.orchestrator import publish_crcef_sv_research as implementation
    return implementation(*args, **kwargs)


def __getattr__(name: str):
    if name in {"ResearchStatus", "PromotionStatus"}:
        from research_quant.schemas import ResearchStatus, PromotionStatus
        return {"ResearchStatus": ResearchStatus, "PromotionStatus": PromotionStatus}[name]
    raise AttributeError(name)


__all__ = [
    "build_crcef_sv_result", "build_crcef_sv_research", "publish_crcef_sv_research",
    "ResearchStatus", "PromotionStatus",
]

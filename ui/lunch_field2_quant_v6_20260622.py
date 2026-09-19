"""Compatibility renderer for the preserved Field 2 projection charts.

This module is display-only. It reads the already-published Power BI cache and
does not calculate or mutate forecasts.
"""
from __future__ import annotations
from typing import Any, MutableMapping


def render_field2_three_visuals(state: MutableMapping[str, Any]) -> None:
    from ui.powerbi_cached_renderer_20260619 import render_cached_powerbi_projection
    render_cached_powerbi_projection(state=state)


__all__ = ["render_field2_three_visuals"]

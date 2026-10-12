"""Compatibility delegate for preserved production Power BI charts."""
from __future__ import annotations

def render_existing_charts(state) -> None:
    from ui.lunch_field2_quant_v6_20260622 import render_field2_three_visuals
    render_field2_three_visuals(state)

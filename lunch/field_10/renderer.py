"""Compatibility renderer for Lunch Field 10."""
from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any


def render_field_10(state: MutableMapping[str, Any] | None = None) -> None:
    from ui.lunch_field10_multi_symbol_20260701 import render_field10_gate
    render_field10_gate(state)

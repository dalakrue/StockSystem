"""Standalone Field 3 page — slim build: banner + Middle Standard Regime Ranking only."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import streamlit as st


def show(runtime_context: Mapping[str, Any] | None = None) -> None:
    del runtime_context
    state = st.session_state
    from ui.field3_multisymbol_regime_summary_20260722 import render_multisymbol_regime_summary
    render_multisymbol_regime_summary(st, state)


__all__ = ["show"]

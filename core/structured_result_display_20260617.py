"""Structured result display guard for Streamlit (2026-06-17).

This is a UI-only compatibility layer. It converts raw calculation dictionaries,
Series, DataFrames, and list-of-record outputs passed to ``st.write``/``st.json``
into tables. Normal explanatory strings, charts, widgets, and existing metrics are
left unchanged.
"""
from __future__ import annotations

import json
from typing import Any


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _compact(value: Any, limit: int = 600) -> str:
    if _is_scalar(value):
        return "-" if value is None else str(value)
    try:
        text = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    except Exception:
        text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _to_dataframe(value: Any):
    try:
        import pandas as pd
    except Exception:
        return None

    if isinstance(value, pd.DataFrame):
        return value
    if isinstance(value, pd.Series):
        name = str(value.name or "Value")
        return value.rename(name).reset_index()
    if isinstance(value, dict):
        if not value:
            return pd.DataFrame([{"Status": "No structured result available"}])
        return pd.DataFrame(
            [{"Metric": str(key), "Value": _compact(item)} for key, item in value.items()]
        )
    if isinstance(value, (list, tuple)):
        if not value:
            return pd.DataFrame([{"Status": "No structured result available"}])
        if all(isinstance(item, dict) for item in value):
            try:
                return pd.DataFrame(list(value))
            except Exception:
                pass
        if all(_is_scalar(item) for item in value):
            return pd.DataFrame({"Value": list(value)})
        return pd.DataFrame(
            [{"Row": idx + 1, "Value": _compact(item)} for idx, item in enumerate(value)]
        )
    return None


def install_structured_result_display() -> None:
    """Install once per process; safe across Streamlit reruns."""
    try:
        import streamlit as st
    except Exception:
        return

    if getattr(st, "_new7_structured_result_display_installed", False):
        return

    original_write = st.write
    original_json = getattr(st, "json", None)

    def structured_write(*args: Any, **kwargs: Any):
        # Preserve Streamlit's normal handling for text/mixed prose. Structured
        # objects are rendered separately so calculation results are not dumped
        # as raw Python/JSON text.
        rendered_any = False
        pending_text = []
        for arg in args:
            frame = _to_dataframe(arg)
            if frame is None:
                pending_text.append(arg)
                continue
            if pending_text:
                original_write(*pending_text, **kwargs)
                pending_text = []
            try:
                st.dataframe(frame, use_container_width=True, hide_index=True)
            except Exception:
                original_write(arg, **kwargs)
            rendered_any = True
        if pending_text:
            return original_write(*pending_text, **kwargs)
        return None if rendered_any else original_write(*args, **kwargs)

    def structured_json(body: Any, *args: Any, **kwargs: Any):
        frame = _to_dataframe(body)
        if frame is not None:
            try:
                return st.dataframe(frame, use_container_width=True, hide_index=True)
            except Exception:
                pass
        if callable(original_json):
            return original_json(body, *args, **kwargs)
        return original_write(body)

    st.write = structured_write
    if callable(original_json):
        st.json = structured_json
    st._new7_structured_result_display_installed = True

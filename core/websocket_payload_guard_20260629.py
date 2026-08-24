"""Global Streamlit payload guard for mobile/WebSocket stability.

This module changes display transport only. It does not modify calculations or
canonical data stored in session_state. Large tables/JSON/charts are compacted
before Streamlit serializes them for the browser, which prevents oversized or
fragmented ForwardMsg payloads from destabilising mobile WebSocket clients.
"""
from __future__ import annotations

import copy
import json
import math
from typing import Any

_MAX_JSON_BYTES_PHONE = 90_000
_MAX_JSON_BYTES_DESKTOP = 350_000
_MAX_TABLE_ROWS_PHONE = 300
_MAX_TABLE_ROWS_DESKTOP = 1200
_MAX_TABLE_COLS_PHONE = 45
_MAX_TABLE_COLS_DESKTOP = 100
_MAX_CHART_POINTS_PHONE = 1200
_MAX_CHART_POINTS_DESKTOP = 5000


def _phone_mode(st: Any) -> bool:
    try:
        return bool(
            st.session_state.get("phone_mode", False)
            or st.session_state.get("extreme_mobile_lite_mode_20260628", False)
            or st.session_state.get("mobile_lite_mode_20260628", False)
        )
    except Exception:
        return False


def _json_safe(value: Any, *, depth: int = 0, max_depth: int = 6, list_limit: int = 120) -> Any:
    if depth > max_depth:
        return "<nested data compacted>"
    try:
        import numpy as np
        import pandas as pd
        if isinstance(value, pd.DataFrame):
            return value.head(list_limit).to_dict("records")
        if isinstance(value, pd.Series):
            return value.head(list_limit).to_dict()
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            x = float(value)
            return x if math.isfinite(x) else None
        if isinstance(value, np.ndarray):
            return [_json_safe(x, depth=depth + 1, max_depth=max_depth, list_limit=list_limit) for x in value[:list_limit].tolist()]
    except Exception:
        pass
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")[:4000]
    if isinstance(value, dict):
        out = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= list_limit:
                out["__compacted__"] = f"{len(value) - list_limit} additional keys hidden"
                break
            out[str(key)] = _json_safe(item, depth=depth + 1, max_depth=max_depth, list_limit=list_limit)
        return out
    if isinstance(value, (list, tuple, set)):
        seq = list(value)
        out = [_json_safe(x, depth=depth + 1, max_depth=max_depth, list_limit=list_limit) for x in seq[:list_limit]]
        if len(seq) > list_limit:
            out.append(f"<{len(seq) - list_limit} additional items hidden>")
        return out
    try:
        return str(value)
    except Exception:
        return "<unserializable value>"


def _compact_json(value: Any, max_bytes: int) -> Any:
    safe = _json_safe(value)
    try:
        raw = json.dumps(safe, ensure_ascii=False, default=str).encode("utf-8")
    except Exception:
        return str(safe)[:max_bytes]
    if len(raw) <= max_bytes:
        return safe

    # Progressively reduce list/key limits instead of slicing JSON into invalid data.
    for limit in (80, 50, 25, 10):
        safe = _json_safe(value, max_depth=5, list_limit=limit)
        raw = json.dumps(safe, ensure_ascii=False, default=str).encode("utf-8")
        if len(raw) <= max_bytes:
            if isinstance(safe, dict):
                safe.setdefault("__display_notice__", "Large payload compacted for browser stability; source calculation is unchanged.")
            return safe
    return {
        "display_notice": "Large payload was not sent to the browser to protect the connection.",
        "payload_type": type(value).__name__,
        "estimated_bytes": len(raw),
    }


def _compact_dataframe(data: Any, *, phone: bool):
    try:
        import pandas as pd
        from core.streamlit_safe_dataframe import make_arrow_safe_dataframe
        if not isinstance(data, pd.DataFrame):
            return make_arrow_safe_dataframe(data)
        max_rows = _MAX_TABLE_ROWS_PHONE if phone else _MAX_TABLE_ROWS_DESKTOP
        max_cols = _MAX_TABLE_COLS_PHONE if phone else _MAX_TABLE_COLS_DESKTOP
        safe = data
        if len(safe) > max_rows:
            safe = safe.tail(max_rows)
        if len(safe.columns) > max_cols:
            # Keep the first columns because this project places identity/time/
            # decision fields first. Calculations and exports remain untouched.
            safe = safe.iloc[:, :max_cols]
        return make_arrow_safe_dataframe(safe.copy())
    except Exception:
        return data


def _compact_plotly_figure(fig: Any, *, phone: bool) -> Any:
    limit = _MAX_CHART_POINTS_PHONE if phone else _MAX_CHART_POINTS_DESKTOP
    try:
        cloned = copy.deepcopy(fig)
        for trace in getattr(cloned, "data", ()):
            lengths = []
            for attr in ("x", "y", "z", "open", "high", "low", "close", "text", "customdata"):
                value = getattr(trace, attr, None)
                try:
                    if value is not None:
                        lengths.append(len(value))
                except Exception:
                    pass
            n = max(lengths) if lengths else 0
            if n <= limit:
                continue
            step = max(1, math.ceil(n / limit))
            for attr in ("x", "y", "z", "open", "high", "low", "close", "text", "customdata"):
                value = getattr(trace, attr, None)
                try:
                    if value is not None and len(value) == n:
                        setattr(trace, attr, value[::step])
                except Exception:
                    pass
        return cloned
    except Exception:
        return fig


def install_websocket_payload_guard() -> None:
    """Install idempotent global transport guards around heavy Streamlit widgets."""
    import streamlit as st

    if getattr(st, "_adx_websocket_payload_guard_20260629", False):
        return

    original_dataframe = st.dataframe
    original_data_editor = getattr(st, "data_editor", None)
    original_json = st.json
    original_plotly_chart = getattr(st, "plotly_chart", None)

    def guarded_dataframe(data=None, *args, **kwargs):
        return original_dataframe(_compact_dataframe(data, phone=_phone_mode(st)), *args, **kwargs)

    def guarded_data_editor(data=None, *args, **kwargs):
        if original_data_editor is None:
            return guarded_dataframe(data, *args, **kwargs)
        return original_data_editor(_compact_dataframe(data, phone=_phone_mode(st)), *args, **kwargs)

    def guarded_json(body, *args, **kwargs):
        max_bytes = _MAX_JSON_BYTES_PHONE if _phone_mode(st) else _MAX_JSON_BYTES_DESKTOP
        return original_json(_compact_json(body, max_bytes), *args, **kwargs)

    def guarded_plotly_chart(figure_or_data, *args, **kwargs):
        if original_plotly_chart is None:
            return None
        compact = _compact_plotly_figure(figure_or_data, phone=_phone_mode(st))
        return original_plotly_chart(compact, *args, **kwargs)

    st.dataframe = guarded_dataframe
    if original_data_editor is not None:
        st.data_editor = guarded_data_editor
    st.json = guarded_json
    if original_plotly_chart is not None:
        st.plotly_chart = guarded_plotly_chart
    st._adx_websocket_payload_guard_20260629 = True

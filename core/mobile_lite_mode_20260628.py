"""Extreme Mobile Lite Mode state and bounded-view helpers.

This module changes presentation/orchestration only.  It never changes a market
calculation, model input, canonical value, history value, or production decision.
Automatic detection is one-shot and optional; the manual override is authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
import re
from typing import Any, Mapping, MutableMapping

import pandas as pd

MODE_KEY = "mobile_ui_mode_20260628"
ENABLED_KEY = "extreme_mobile_lite_mode_20260628"
DETECTION_KEY = "mobile_viewport_checked_20260628"
WIDTH_KEY = "mobile_viewport_width_20260628"
DETECTION_SOURCE_KEY = "mobile_detection_source_20260628"
MODES = ("AUTO", "MOBILE LITE", "FULL INTERFACE")
MOBILE_PAGE_SIZES = (10, 25)
DESKTOP_PAGE_SIZES = (25, 50, 100)


@dataclass(frozen=True)
class MobileLiteState:
    mode: str
    enabled: bool
    viewport_width: int | None
    detection_source: str


def _normalize_mode(value: Any) -> str:
    text = str(value or "AUTO").strip().upper().replace("_", " ")
    aliases = {
        "PHONE": "MOBILE LITE", "MOBILE": "MOBILE LITE", "LITE": "MOBILE LITE",
        "LAPTOP": "FULL INTERFACE", "DESKTOP": "FULL INTERFACE", "FULL": "FULL INTERFACE",
    }
    text = aliases.get(text, text)
    return text if text in MODES else "AUTO"


def _query_value(st: Any, name: str) -> str | None:
    try:
        value = st.query_params.get(name)
        if isinstance(value, list):
            return str(value[-1]) if value else None
        return str(value) if value is not None else None
    except Exception:
        try:
            params = st.experimental_get_query_params()
            value = params.get(name)
            if isinstance(value, list):
                return str(value[-1]) if value else None
            return str(value) if value is not None else None
        except Exception:
            return None


def _header_user_agent(st: Any) -> str:
    try:
        headers = getattr(getattr(st, "context", None), "headers", None)
        if headers:
            return str(headers.get("User-Agent") or headers.get("user-agent") or "")
    except Exception:
        pass
    return ""


def _mobile_user_agent(user_agent: str) -> bool:
    if not user_agent:
        return False
    return bool(re.search(r"android|iphone|ipad|ipod|mobile|windows phone|opera mini", user_agent, flags=re.I))


def _optional_viewport_width(st: Any, state: MutableMapping[str, Any]) -> int | None:
    """Evaluate viewport width at most once when the optional component exists."""
    if state.get(DETECTION_KEY):
        value = state.get(WIDTH_KEY)
        try:
            return int(value) if value is not None else None
        except Exception:
            return None
    try:
        from streamlit_js_eval import streamlit_js_eval  # type: ignore
        value = streamlit_js_eval(js_expressions="window.innerWidth", key="mobile_width_once_20260628")
        if value is not None:
            width = int(float(value))
            state[WIDTH_KEY] = width
            state[DETECTION_KEY] = True
            state[DETECTION_SOURCE_KEY] = "ONE_SHOT_VIEWPORT"
            return width
    except Exception:
        pass
    return None


def initialize_mobile_lite_mode(st: Any, state: MutableMapping[str, Any]) -> MobileLiteState:
    """Resolve one presentation mode without polling or triggering calculations."""
    requested = _query_value(st, "ui_mode") or _query_value(st, "mobile")
    if requested:
        state[MODE_KEY] = _normalize_mode(requested)
    state[MODE_KEY] = _normalize_mode(state.get(MODE_KEY, "AUTO"))
    mode = state[MODE_KEY]

    width: int | None = None
    source = str(state.get(DETECTION_SOURCE_KEY) or "SESSION_DEFAULT")
    if mode == "MOBILE LITE":
        enabled = True
        source = "MANUAL_OVERRIDE"
    elif mode == "FULL INTERFACE":
        enabled = False
        source = "MANUAL_OVERRIDE"
    else:
        width = _optional_viewport_width(st, state)
        if width is not None:
            enabled = width <= 768
            source = "ONE_SHOT_VIEWPORT"
        else:
            user_agent = _header_user_agent(st)
            if user_agent:
                enabled = _mobile_user_agent(user_agent)
                source = "USER_AGENT_FALLBACK"
                state[DETECTION_KEY] = True
            else:
                # Preserve an already chosen phone state; otherwise remain full.
                enabled = bool(state.get(ENABLED_KEY, state.get("phone_mode", False)))
                source = "SESSION_DEFAULT"
    state[ENABLED_KEY] = bool(enabled)
    state["phone_mode"] = bool(enabled)
    state["logic_first_mobile_20260618"] = bool(enabled)
    state[DETECTION_SOURCE_KEY] = source
    if width is None:
        try:
            width = int(state.get(WIDTH_KEY)) if state.get(WIDTH_KEY) is not None else None
        except Exception:
            width = None
    return MobileLiteState(mode=mode, enabled=bool(enabled), viewport_width=width, detection_source=source)


def set_mobile_mode(state: MutableMapping[str, Any], mode: str) -> MobileLiteState:
    normalized = _normalize_mode(mode)
    state[MODE_KEY] = normalized
    if normalized == "MOBILE LITE":
        enabled = True
    elif normalized == "FULL INTERFACE":
        enabled = False
    else:
        enabled = bool(state.get(WIDTH_KEY, 9999) <= 768) if state.get(WIDTH_KEY) is not None else bool(state.get("phone_mode", False))
    state[ENABLED_KEY] = enabled
    state["phone_mode"] = enabled
    state[DETECTION_SOURCE_KEY] = "MANUAL_OVERRIDE" if normalized != "AUTO" else "AUTO_SESSION"
    return MobileLiteState(normalized, enabled, state.get(WIDTH_KEY), str(state[DETECTION_SOURCE_KEY]))


def render_mobile_mode_control(st: Any, state: MutableMapping[str, Any], *, key: str) -> MobileLiteState:
    current = _normalize_mode(state.get(MODE_KEY, "AUTO"))
    if bool(state.get("hide_interface_mode_control_20260709", True)):
        return set_mobile_mode(state, current)
    selected = st.radio(
        "Interface mode",
        MODES,
        index=MODES.index(current),
        horizontal=True,
        key=f"{key}_mode_radio",
        help="Mobile Lite changes rendering and data transfer only. Calculated values remain identical.",
    )
    resolved = set_mobile_mode(state, selected)
    status = "ON" if resolved.enabled else "OFF"
    width = f" · width {resolved.viewport_width}px" if resolved.viewport_width else ""
    st.caption(f"Extreme Mobile Lite: {status} · {resolved.detection_source}{width}")
    return resolved


def cache_identity(canonical: Mapping[str, Any], *, component: str, version: str = "1") -> str:
    values = [
        canonical.get("run_id"), canonical.get("canonical_calculation_id"),
        canonical.get("generation_id"), canonical.get("calculation_generation"),
        canonical.get("completed_broker_candle"), canonical.get("latest_completed_candle_time"),
        canonical.get("symbol"), canonical.get("timeframe"), canonical.get("source_snapshot_hash"),
        component, version,
    ]
    return sha256("|".join(str(value or "") for value in values).encode("utf-8", "ignore")).hexdigest()


def bounded_frame(
    frame: pd.DataFrame,
    *,
    mobile: bool,
    page: int = 1,
    page_size: int | None = None,
    columns: list[str] | tuple[str, ...] | None = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Return only selected rows and columns; never mutate the source frame."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=list(columns or [])), {"page": 1, "page_size": 0, "total_rows": 0, "total_pages": 1}
    allowed = MOBILE_PAGE_SIZES if mobile else DESKTOP_PAGE_SIZES
    size = int(page_size or allowed[0])
    if size not in allowed:
        size = min(allowed, key=lambda item: abs(item - size))
    total = len(frame)
    pages = max(1, int(math.ceil(total / size)))
    page = max(1, min(int(page), pages))
    start = (page - 1) * size
    selected_columns = [column for column in (columns or list(frame.columns)) if column in frame.columns]
    view = frame.iloc[start:start + size].loc[:, selected_columns].copy(deep=False)
    return view, {"page": page, "page_size": size, "total_rows": total, "total_pages": pages}


def extreme_mobile_css(enabled: bool) -> str:
    if not enabled:
        return "<style>@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;}}</style>"
    return r"""
<style id="extreme-mobile-lite-css-20260628">
:root{--mobile-lite-gap:.28rem;}
*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important;}
.stApp,.stApp::before,.stApp::after{background:#f7fafc!important;background-image:none!important;filter:none!important;}
.main .block-container{max-width:100%!important;padding:.28rem .32rem .8rem!important;}
[class*="glass"],[class*="hero"],[class*="glow"],[class*="animated"],[class*="background"]{
  box-shadow:none!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important;
  filter:none!important;transform:none!important;background-image:none!important;
}
.new7-card,.new7-top-status,.new7-health-card,[data-testid="stMetric"],div[data-testid="stExpander"]{
  box-shadow:none!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important;
  border-radius:10px!important;background:#fff!important;border:1px solid rgba(15,23,42,.10)!important;
}
div[data-testid="stHorizontalBlock"]{gap:var(--mobile-lite-gap)!important;flex-wrap:wrap!important;}
div[data-testid="stHorizontalBlock"]>div[data-testid="column"]{min-width:145px!important;flex:1 1 calc(50% - var(--mobile-lite-gap))!important;}
[data-testid="stMetric"]{padding:.38rem .42rem!important;min-height:66px!important;}
[data-testid="stMetricValue"]{font-size:1.05rem!important;line-height:1.05!important;white-space:normal!important;overflow-wrap:anywhere!important;}
[data-testid="stMetricLabel"]{font-size:.70rem!important;line-height:1.08!important;}
.stButton>button,.stDownloadButton>button{min-height:40px!important;border-radius:9px!important;box-shadow:none!important;}
div[data-testid="stDataFrame"],div[data-testid="stTable"]{font-size:.76rem!important;max-width:100%!important;overflow:auto!important;}
.stTabs [data-baseweb="tab-list"]{box-shadow:none!important;backdrop-filter:none!important;background:#fff!important;padding:.2rem!important;}
.stTabs [data-baseweb="tab"]{font-size:.72rem!important;padding:.25rem .35rem!important;}
section[data-testid="stSidebar"]{display:none!important;}
iframe{max-width:100%!important;}
</style>
"""


__all__ = [
    "MODE_KEY", "ENABLED_KEY", "MODES", "MobileLiteState", "initialize_mobile_lite_mode",
    "set_mobile_mode", "render_mobile_mode_control", "cache_identity", "bounded_frame",
    "extreme_mobile_css",
]

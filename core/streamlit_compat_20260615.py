"""Streamlit 1.56+ compatibility shim (2026-06-15).

Purpose
-------
The project intentionally keeps many older tab files for downgrade safety. Some
of those files still call deprecated Streamlit APIs such as
``use_container_width`` and ``streamlit.components.v1.html``.  Editing hundreds
of historical files increases regression risk, so the app installs one small
runtime shim at startup.

This module is display/API compatibility only. It never changes trading logic,
ML calculations, regime logic, PowerBI formulas, exports, or stored data.
"""
from __future__ import annotations

import functools
import inspect
from typing import Any, Callable


def _supports_kw(fn: Callable[..., Any], name: str) -> bool:
    try:
        sig = inspect.signature(fn)
        if name in sig.parameters:
            return True
        return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    except Exception:
        return False


def _wrap_width(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Translate deprecated use_container_width to width when supported.

    Works for both module-level ``st.dataframe`` and DeltaGenerator methods such
    as ``col.button``. If the runtime is older and has no ``width`` argument, the
    old keyword is left intact for backward compatibility.
    """
    if getattr(fn, "_new7_width_compat_20260615", False):
        return fn
    supports_width = _supports_kw(fn, "width")
    supports_use = _supports_kw(fn, "use_container_width")

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if "use_container_width" in kwargs and supports_width:
            use_value = kwargs.pop("use_container_width")
            kwargs.setdefault("width", "stretch" if bool(use_value) else "content")
        elif "use_container_width" in kwargs and not supports_use:
            # Future Streamlit removed the old keyword and this function also has
            # no width parameter. Drop it rather than crash.
            kwargs.pop("use_container_width", None)
        return fn(*args, **kwargs)

    wrapper._new7_width_compat_20260615 = True  # type: ignore[attr-defined]
    return wrapper


def _wrap_safe_slider(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Render a static non-slider fallback when the available range collapses."""
    if getattr(fn, "_new7_safe_slider_20260702", False):
        return fn

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # st.slider(label, min_value, max_value, value, step, ...)
        args_list = list(args)
        try:
            min_value = kwargs.get("min_value", args_list[1] if len(args_list) > 1 else None)
            max_value = kwargs.get("max_value", args_list[2] if len(args_list) > 2 else None)
            value = kwargs.get("value", args_list[3] if len(args_list) > 3 else None)
            if min_value is not None and max_value is not None and min_value >= max_value:
                fallback = (min_value, max_value) if isinstance(value, (tuple, list)) else min_value
                label = kwargs.get("label", args_list[0] if args_list else "Selection")
                # Do not create a slider with an invented range. The single real
                # value is displayed as read-only text and returned unchanged.
                try:
                    import streamlit as st  # type: ignore
                    st.caption(f"{label}: {fallback} · only one value is available")
                except Exception:
                    pass
                return fallback
        except (TypeError, ValueError):
            pass
        return fn(*args_list, **kwargs)

    wrapper._new7_safe_slider_20260702 = True  # type: ignore[attr-defined]
    return wrapper


def _wrap_component_html(st: Any, original: Callable[..., Any]) -> Callable[..., Any]:
    """Route components.html through st.iframe when the new API exists."""
    if getattr(original, "_new7_iframe_compat_20260615", False):
        return original

    @functools.wraps(original)
    def wrapper(html: Any, width: Any = None, height: Any = None, scrolling: bool = False, *, tab_index: Any = None, **kwargs: Any) -> Any:
        iframe = getattr(st, "iframe", None)
        if callable(iframe):
            iframe_kwargs = {}
            # st.iframe width accepts "stretch"/"content" or an int. Preserve
            # explicit integer widths, otherwise stretch to parent like old UI.
            iframe_kwargs["width"] = width if width is not None else "stretch"
            # For old components.html, height default was 150. Use that instead
            # of iframe's content auto-height so old copy/timer components keep
            # their designed box size.
            iframe_kwargs["height"] = height if height is not None else 150
            if tab_index is not None:
                iframe_kwargs["tab_index"] = tab_index
            return iframe(str(html or ""), **iframe_kwargs)
        return original(html, width=width, height=height, scrolling=scrolling, tab_index=tab_index, **kwargs)

    wrapper._new7_iframe_compat_20260615 = True  # type: ignore[attr-defined]
    return wrapper


def _wrap_component_iframe(st: Any, original: Callable[..., Any]) -> Callable[..., Any]:
    """Route components.iframe through st.iframe when available."""
    if getattr(original, "_new7_iframe_compat_20260615", False):
        return original

    @functools.wraps(original)
    def wrapper(src: Any, width: Any = None, height: Any = None, scrolling: bool = False, *, tab_index: Any = None, **kwargs: Any) -> Any:
        iframe = getattr(st, "iframe", None)
        if callable(iframe):
            iframe_kwargs = {"width": width if width is not None else "stretch", "height": height if height is not None else 150}
            if tab_index is not None:
                iframe_kwargs["tab_index"] = tab_index
            return iframe(src, **iframe_kwargs)
        return original(src, width=width, height=height, scrolling=scrolling, tab_index=tab_index, **kwargs)

    wrapper._new7_iframe_compat_20260615 = True  # type: ignore[attr-defined]
    return wrapper


def install_streamlit_compat() -> None:
    """Install runtime compatibility patches exactly once."""
    try:
        import streamlit as st  # type: ignore
    except Exception:
        return

    if getattr(st, "_new7_streamlit_compat_installed_20260615", False):
        return

    names = [
        "button",
        "download_button",
        "dataframe",
        "data_editor",
        "table",
        "plotly_chart",
        "line_chart",
        "area_chart",
        "bar_chart",
        "scatter_chart",
        "altair_chart",
        "vega_lite_chart",
        "pyplot",
        "graphviz_chart",
        "map",
        "image",
        "audio",
        "video",
        "metric",
        "tabs",
        "radio",
        "selectbox",
        "multiselect",
        "slider",
        "text_input",
        "text_area",
    ]
    for name in names:
        try:
            obj = getattr(st, name, None)
            if callable(obj):
                patched = _wrap_width(obj)
                if name == "slider":
                    patched = _wrap_safe_slider(patched)
                setattr(st, name, patched)
        except Exception:
            pass

    # Patch column/container/sidebar methods too. Many warnings come from
    # c1.button(...) and other DeltaGenerator calls.
    try:
        from streamlit.delta_generator import DeltaGenerator  # type: ignore
        for name in names:
            try:
                obj = getattr(DeltaGenerator, name, None)
                if callable(obj):
                    patched = _wrap_width(obj)
                    if name == "slider":
                        patched = _wrap_safe_slider(patched)
                    setattr(DeltaGenerator, name, patched)
            except Exception:
                pass
    except Exception:
        pass

    # Patch deprecated components iframe/html while retaining old call sites.
    try:
        import streamlit.components.v1 as components  # type: ignore
        html_fn = getattr(components, "html", None)
        if callable(html_fn):
            components.html = _wrap_component_html(st, html_fn)  # type: ignore[assignment]
        iframe_fn = getattr(components, "iframe", None)
        if callable(iframe_fn):
            components.iframe = _wrap_component_iframe(st, iframe_fn)  # type: ignore[assignment]
    except Exception:
        pass

    try:
        st._new7_streamlit_compat_installed_20260615 = True
    except Exception:
        pass
    try:
        st.session_state["streamlit_compat_installed_20260615"] = True
    except Exception:
        pass

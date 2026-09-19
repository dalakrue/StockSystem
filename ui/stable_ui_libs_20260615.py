"""Optional modern UI adapters for the 2026-06-15 stable UI upgrade.

This module is intentionally display-only.  It imports the requested UI
libraries defensively and always falls back to native Streamlit widgets so a
missing optional package cannot crash the trading app.
"""
from __future__ import annotations

from typing import Any, Iterable, List, Optional

import streamlit as st

try:
    import streamlit_antd_components as sac  # type: ignore
except Exception:  # pragma: no cover
    sac = None  # type: ignore

try:
    import streamlit_shadcn_ui as ui  # type: ignore
except Exception:  # pragma: no cover
    ui = None  # type: ignore

try:
    from streamlit_modal import Modal  # type: ignore
except Exception:  # pragma: no cover
    Modal = None  # type: ignore

try:
    from st_aggrid import AgGrid, GridOptionsBuilder  # type: ignore
except Exception:  # pragma: no cover
    AgGrid = None  # type: ignore
    GridOptionsBuilder = None  # type: ignore


def inject_stable_ui_css() -> None:
    st.markdown(
        """
<style id="new7-stable-ui-libs-20260615">
.new7-modern-card{border:1px solid rgba(15,23,42,.08);border-radius:22px;padding:12px 14px;margin:.30rem 0 .60rem;background:linear-gradient(135deg,rgba(255,255,255,.84),rgba(239,246,255,.58));box-shadow:0 12px 30px rgba(15,23,42,.055)}
.new7-modern-card b{color:#0f172a;font-weight:950}.new7-modern-card span{color:#64748b;font-size:.78rem;font-weight:750}.new7-modern-grid{display:flex;flex-wrap:wrap;gap:7px;margin:.20rem 0 .30rem}.new7-status-badge{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:5px 10px;border:1px solid rgba(15,23,42,.08);background:rgba(255,255,255,.68);font-size:.74rem;font-weight:950;color:#0f172a;box-shadow:0 5px 12px rgba(15,23,42,.035)}
.new7-status-badge.buy{background:rgba(220,252,231,.80);color:#166534}.new7-status-badge.sell{background:rgba(254,226,226,.80);color:#991b1b}.new7-status-badge.wait{background:rgba(254,249,195,.84);color:#854d0e}.new7-status-badge.risk{background:rgba(255,237,213,.86);color:#9a3412}.new7-status-badge.connected{background:rgba(219,234,254,.84);color:#1d4ed8}.new7-status-badge.disconnected{background:rgba(241,245,249,.92);color:#475569}
.new7-floating-control{position:sticky;top:.25rem;z-index:50;border-radius:24px;border:1px solid rgba(14,165,233,.16);background:linear-gradient(135deg,rgba(255,255,255,.90),rgba(236,253,245,.62));box-shadow:0 16px 38px rgba(15,23,42,.075);padding:10px 11px;margin:.22rem 0 .55rem;backdrop-filter:blur(14px)}
@media(max-width:430px){.new7-modern-card{border-radius:17px;padding:9px 10px;margin:.18rem 0 .42rem}.new7-floating-control{border-radius:18px;padding:8px;top:.05rem}.new7-status-badge{font-size:.68rem;padding:4px 8px}}
</style>
        """,
        unsafe_allow_html=True,
    )


def badge(label: str, tone: str = "wait") -> str:
    tone = str(tone or "wait").lower().replace(" ", "-")
    return f'<span class="new7-status-badge {tone}">{label}</span>'


def render_badges(items: Iterable[tuple[str, str]]) -> None:
    inject_stable_ui_css()
    html = "<div class='new7-modern-grid'>" + "".join(badge(label, tone) for label, tone in items) + "</div>"
    st.markdown(html, unsafe_allow_html=True)


def render_card(title: str, body: str = "", badge_items: Optional[Iterable[tuple[str, str]]] = None) -> None:
    inject_stable_ui_css()
    badges = ""
    if badge_items:
        badges = "<div class='new7-modern-grid'>" + "".join(badge(label, tone) for label, tone in badge_items) + "</div>"
    st.markdown(
        f"<div class='new7-modern-card'><b>{title}</b><br><span>{body}</span>{badges}</div>",
        unsafe_allow_html=True,
    )


def segmented_choice(label: str, options: List[str], key: str, default: Optional[str] = None) -> str:
    """Stable segmented/menu choice with AntD first and Streamlit fallback."""
    if not options:
        return ""
    current = st.session_state.get(key, default or options[0])
    if current not in options:
        current = default if default in options else options[0]
        st.session_state[key] = current
    try:
        if sac is not None:
            idx = options.index(current)
            value = sac.segmented(
                items=[sac.SegmentedItem(label=o, value=o) for o in options],
                index=idx,
                key=key + "_sac",
                size="sm",
                align="center",
                use_container_width=True,
            )
            if value in options and value != st.session_state.get(key):
                st.session_state[key] = value
            return st.session_state.get(key, current)
    except Exception:
        pass
    cols = st.columns(min(len(options), 4))
    for i, opt in enumerate(options):
        with cols[i % len(cols)]:
            if st.button(("✅ " if opt == current else "") + opt, key=f"{key}_btn_{i}_{opt}", use_container_width=True):
                st.session_state[key] = opt
    return st.session_state.get(key, current)


def tab_choice(label: str, options: List[str], key: str, default: Optional[str] = None) -> str:
    """AntD tab choice wrapper; never crashes if package is absent."""
    if not options:
        return ""
    current = st.session_state.get(key, default or options[0])
    if current not in options:
        current = default if default in options else options[0]
        st.session_state[key] = current
    try:
        if sac is not None:
            idx = options.index(current)
            value = sac.tabs(
                items=[sac.TabsItem(label=o) for o in options],
                index=idx,
                key=key + "_sac_tabs",
                align="center",
                size="sm",
                use_container_width=True,
            )
            if value in options:
                st.session_state[key] = value
            return st.session_state.get(key, current)
    except Exception:
        pass
    return st.radio(label, options, index=options.index(current), horizontal=True, key=key + "_radio")


def optional_modal_button(title: str, button_label: str, body_renderer: Any, key: str) -> None:
    """Render a popup detail window if streamlit-modal is present; fallback expander."""
    try:
        if Modal is not None:
            modal = Modal(title, key=key, max_width=900)
            if st.button(button_label, key=key + "_open", use_container_width=True):
                modal.open()
            if modal.is_open():
                with modal.container():
                    body_renderer()
            return
    except Exception:
        pass
    with st.expander(button_label.replace("Open", "Open / Close"), expanded=False):
        body_renderer()


def modern_table(df: Any, key: str, height: int = 320) -> None:
    """Use AgGrid only for existing tables; fallback to st.dataframe."""
    try:
        if AgGrid is not None and GridOptionsBuilder is not None and getattr(df, "empty", True) is False:
            gb = GridOptionsBuilder.from_dataframe(df)
            gb.configure_default_column(filter=True, sortable=True, resizable=True)
            gb.configure_pagination(paginationAutoPageSize=True)
            AgGrid(df, gridOptions=gb.build(), height=height, key=key, fit_columns_on_grid_load=False)
            return
    except Exception:
        pass
    st.dataframe(df, use_container_width=True, hide_index=True, height=height)

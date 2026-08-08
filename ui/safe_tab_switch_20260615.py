
"""Safe tab-choice switcher and lightweight UI polish (2026-06-15).

Display-only helper. It writes only Streamlit session_state navigation/UI keys and
never changes prediction formulas, ML models, regime logic, PowerBI logic, data
exports, copy buttons, or calculations.
"""
from __future__ import annotations

import time
from typing import Iterable, List, Optional

import streamlit as st

try:  # optional library requested for stronger mobile tab switching
    from streamlit_option_menu import option_menu  # type: ignore
    OPTION_MENU_AVAILABLE = True
except Exception:  # pragma: no cover
    option_menu = None  # type: ignore
    OPTION_MENU_AVAILABLE = False


def _safe_rerun() -> None:
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def inject_motion_background_css() -> None:
    """Soft background / pop-up / motion polish with no JS dependency."""
    st.markdown(
        """
<style id="new7-safe-tab-switch-motion-20260615">
.block-container::before{
  content:"";position:fixed;inset:-18% -18% auto auto;width:420px;height:420px;z-index:-2;
  background:radial-gradient(circle,rgba(59,130,246,.12),rgba(125,211,252,.04) 48%,transparent 70%);
  filter:blur(2px);animation:new7floatGlow 11s ease-in-out infinite alternate;pointer-events:none;
}
.block-container::after{
  content:"";position:fixed;left:-12%;bottom:-18%;width:360px;height:360px;z-index:-2;
  background:radial-gradient(circle,rgba(168,85,247,.10),rgba(14,165,233,.04) 45%,transparent 72%);
  animation:new7floatGlow2 13s ease-in-out infinite alternate;pointer-events:none;
}
@keyframes new7floatGlow{from{transform:translate3d(0,0,0) scale(1)}to{transform:translate3d(-32px,28px,0) scale(1.05)}}
@keyframes new7floatGlow2{from{transform:translate3d(0,0,0) scale(1)}to{transform:translate3d(38px,-26px,0) scale(1.07)}}
.new7-switch-card{
  border:1px solid rgba(99,102,241,.14);border-radius:20px;padding:10px 12px;margin:.25rem 0 .55rem 0;
  background:linear-gradient(135deg,rgba(255,255,255,.86),rgba(239,246,255,.70));
  box-shadow:0 12px 30px rgba(15,23,42,.065);animation:new7softPop .26s ease-out both;
}
@keyframes new7softPop{from{opacity:.55;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
@media(max-width:430px){
  .new7-switch-card{border-radius:16px;padding:8px 9px;box-shadow:0 7px 18px rgba(15,23,42,.05)}
  .nav-link{font-size:.76rem!important;padding:.32rem .38rem!important;white-space:normal!important;line-height:1.05!important;}
  div[data-testid="stRadio"] label{font-size:.76rem!important;line-height:1.05!important;}
}
@media (prefers-reduced-motion: reduce){
  .block-container::before,.block-container::after,.new7-switch-card{animation:none!important;}
}
</style>
        """,
        unsafe_allow_html=True,
    )


def safe_tab_choice(
    *,
    label: str,
    options: Iterable[str],
    state_key: str,
    widget_key: str,
    default: Optional[str] = None,
    icons: Optional[List[str]] = None,
    horizontal: bool = True,
    rerun_on_change: bool = False,
) -> str:
    """Return selected option using option-menu first, then st.radio fallback.

    This avoids fragile multi-button tab switching. It works on mobile because one
    widget owns the selection and writes to one session_state key.
    """
    opts = [str(x) for x in options if str(x)]
    if not opts:
        return ""
    current = str(st.session_state.get(state_key, default or opts[0]) or (default or opts[0]))
    if current not in opts:
        current = default if default in opts else opts[0]
        st.session_state[state_key] = current
    idx = opts.index(current)
    inject_motion_background_css()
    st.markdown(f'<div class="new7-switch-card"><b>{label}</b><br><span style="font-size:.76rem;color:#64748b;">Fast mobile-safe tab choice. Uses streamlit-option-menu when installed, radio fallback when not.</span></div>', unsafe_allow_html=True)
    selected = current
    used_option_menu = False
    if OPTION_MENU_AVAILABLE:
        try:
            icon_list = icons if icons and len(icons) == len(opts) else ["circle"] * len(opts)
            selected = option_menu(
                None,
                opts,
                icons=icon_list,
                menu_icon="cast",
                default_index=idx,
                orientation="horizontal" if horizontal else "vertical",
                key=widget_key,
                styles={
                    "container": {"padding": "2px", "background-color": "rgba(255,255,255,.02)", "border-radius": "16px"},
                    "nav-link": {"font-size": "0.82rem", "font-weight": "800", "border-radius": "14px", "margin": "2px", "padding": "0.42rem 0.55rem"},
                    "nav-link-selected": {"font-weight": "900"},
                },
            )
            used_option_menu = True
        except Exception as exc:
            st.caption(f"Tab-choice library failed safely; using radio fallback. {exc}")
    if not used_option_menu:
        selected = st.radio(
            label,
            opts,
            index=idx,
            horizontal=horizontal,
            key=widget_key + "_radio_fallback",
        )
    selected = str(selected or current)
    if selected not in opts:
        selected = current
    if selected != st.session_state.get(state_key):
        st.session_state[state_key] = selected
        st.session_state["ui_navigation_click_ts"] = time.time()
        st.session_state["fast_tab_switch_active"] = True
        if rerun_on_change:
            _safe_rerun()
    return str(st.session_state.get(state_key, selected))

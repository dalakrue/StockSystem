"""Compatibility facade for refactored architecture.

The original implementation is preserved in `core.ui.legacy_impl.styles_impl`. This lightweight
facade keeps all existing imports working while making this active file easy to
upgrade safely.
"""

from core.ui.legacy_impl.styles_impl import *  # noqa: F401,F403

try:
    from core.ui.legacy_impl.styles_impl import __all__ as __all__  # type: ignore
except Exception:
    __all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]

# 2026-06-12 SIDEBAR NATIVE STABILITY PATCH
# This replaces the previous DOM/JavaScript force-close patch.
# Streamlit owns the real sidebar open/close state; this layer only applies
# soft CSS and exposes compatibility functions used by older tabs.  The goal is
# reliability: no hidden body class, no DOM-click helpers, and no duplicate
# close buttons that can break after Streamlit updates.
try:
    _qx_legacy_apply_global_styles_20260612 = apply_global_styles  # type: ignore[name-defined]
except Exception:  # pragma: no cover
    _qx_legacy_apply_global_styles_20260612 = None


def sidebar_native_stability_css() -> None:
    import streamlit as st
    st.markdown(
        """
<style id="new7-sidebar-native-stability-20260612">
/* Softer sidebar border + mobile app feel. */
section[data-testid="stSidebar"]{
  background:linear-gradient(180deg,rgba(248,250,252,.97),rgba(239,246,255,.94))!important;
  border-right:1px solid rgba(15,23,42,.06)!important;
  box-shadow:10px 0 28px rgba(15,23,42,.055)!important;
}
section[data-testid="stSidebar"] .block-container{
  padding:.70rem .62rem .95rem .62rem!important;
}
section[data-testid="stSidebar"] button{
  border-radius:16px!important;
  min-height:40px!important;
  border:1px solid rgba(99,102,241,.10)!important;
  box-shadow:0 7px 18px rgba(15,23,42,.055)!important;
}
section[data-testid="stSidebar"] div[data-testid="stExpander"] details{
  border-radius:20px!important;
  border:1px solid rgba(99,102,241,.12)!important;
  box-shadow:0 8px 22px rgba(15,23,42,.045)!important;
  background:rgba(255,255,255,.62)!important;
}
section[data-testid="stSidebar"] div[data-testid="stExpander"] summary{
  border-radius:20px!important;
}

/* Stable main-page fallback menu card. */
.new7-stable-menu-card{
  border:1px solid rgba(99,102,241,.13);
  border-radius:24px;
  padding:12px 14px;
  margin:.15rem 0 .65rem 0;
  background:linear-gradient(135deg,rgba(255,255,255,.78),rgba(239,246,255,.68));
  box-shadow:0 12px 30px rgba(15,23,42,.065);
}
.new7-stable-menu-title{font-weight:950;color:#0f172a;font-size:1rem;margin-bottom:2px;}
.new7-stable-menu-sub{font-size:.78rem;color:#64748b;line-height:1.28;}

@media(max-width:780px){
  section[data-testid="stSidebar"]{width:min(18rem,86vw)!important;min-width:min(18rem,86vw)!important;}
  section[data-testid="stSidebar"] .block-container{padding:.58rem .50rem .85rem .50rem!important;}
  section[data-testid="stSidebar"] button{min-height:44px!important;font-size:.86rem!important;}
  .main .block-container{max-width:100vw!important;overflow-x:hidden!important;padding-left:.55rem!important;padding-right:.55rem!important;}
}
</style>
        """,
        unsafe_allow_html=True,
    )


# Backward-compatible names used across older tabs.  These now intentionally do
# not inject JavaScript or click Streamlit's private DOM.  The native sidebar
# control and the main-page expander are the reliable open/close systems.
def sidebar_reliable_open_close_script() -> None:
    sidebar_native_stability_css()


def auto_close_sidebar_script(always_close: bool = False) -> None:
    sidebar_native_stability_css()
    try:
        import streamlit as st
        if always_close:
            st.session_state["sidebar_close_requested_native_only"] = True
    except Exception:
        pass


def request_close_sidebar() -> None:
    auto_close_sidebar_script(always_close=True)


def apply_global_styles(phone_mode: bool = False):
    if callable(_qx_legacy_apply_global_styles_20260612):
        _qx_legacy_apply_global_styles_20260612(phone_mode=phone_mode)
    sidebar_native_stability_css()


try:
    if isinstance(__all__, list):
        for _name in [
            'sidebar_native_stability_css',
            'sidebar_reliable_open_close_script',
            'auto_close_sidebar_script',
            'request_close_sidebar',
            'apply_global_styles',
        ]:
            if _name not in __all__:
                __all__.append(_name)
except Exception:
    pass


# 2026-06-15 LEGACY SIDEBAR DOM-CLICK REMOVAL
# Older 2026-06-14 hard-close helpers were intentionally neutralized.
# Navigation now uses Ant Design + Main Page Menu; native sidebar is optional backup only.
def _sidebar_force_hidden_css_20260614() -> None:
    return None


def _sidebar_js_close_retry_20260614() -> None:
    return None


def _new7_sidebar_unforce_css_20260614() -> None:
    return None


# 2026-06-14 FINAL LONG-TERM SIDEBAR HARD LOCK OVERRIDE
# Last definitions win over older experimental patches above. Native Streamlit
# sidebar is locked closed by default; the session_state main-page menu is the
# reliable replacement.
def sidebar_native_stability_css() -> None:  # type: ignore[override]
    try:
        from ui.sidebar_hard_lock import init_sidebar_policy, inject_sidebar_policy_css
        init_sidebar_policy()
        inject_sidebar_policy_css()
    except Exception:
        pass


def auto_close_sidebar_script(always_close: bool = False) -> None:  # type: ignore[override]
    try:
        from ui.sidebar_hard_lock import init_sidebar_policy, disable_native_sidebar, inject_sidebar_policy_css
        init_sidebar_policy()
        if always_close:
            disable_native_sidebar("Native sidebar closed and locked by stable hard-lock policy.")
        inject_sidebar_policy_css()
    except Exception:
        pass


def request_close_sidebar() -> None:  # type: ignore[override]
    auto_close_sidebar_script(always_close=True)


def request_open_sidebar() -> None:  # type: ignore[override]
    try:
        from ui.sidebar_hard_lock import enable_native_sidebar_backup, inject_sidebar_policy_css
        enable_native_sidebar_backup()
        inject_sidebar_policy_css()
        from ui.native_sidebar_js import request_open_native_sidebar
        request_open_native_sidebar()
    except Exception:
        pass


def apply_global_styles(phone_mode: bool = False):  # type: ignore[override]
    try:
        if callable(_qx_legacy_apply_global_styles_20260612):
            _qx_legacy_apply_global_styles_20260612(phone_mode=phone_mode)
    except Exception:
        pass
    sidebar_native_stability_css()

try:
    if isinstance(__all__, list):
        for _name in ['request_open_sidebar', 'request_close_sidebar', 'auto_close_sidebar_script', 'sidebar_native_stability_css', 'apply_global_styles']:
            if _name not in __all__:
                __all__.append(_name)
except Exception:
    pass

# 2026-06-15 FINAL NO-JAVASCRIPT SIDEBAR COMPATIBILITY OVERRIDE
# Last definitions win. These helpers only update the optional native-sidebar
# backup policy; they never click Streamlit private DOM controls.
def sidebar_native_stability_css() -> None:  # type: ignore[override]
    try:
        from ui.sidebar_hard_lock import init_sidebar_policy, inject_sidebar_policy_css
        init_sidebar_policy()
        inject_sidebar_policy_css()
    except Exception:
        pass


def auto_close_sidebar_script(always_close: bool = False) -> None:  # type: ignore[override]
    try:
        from ui.sidebar_hard_lock import init_sidebar_policy, inject_sidebar_policy_css
        init_sidebar_policy()
        # 2026-06-15 user fix: never lock the native backup sidebar off from
        # normal page/tab clicks. Streamlit owns real open/close; this only
        # records intent and keeps the soft CSS. This prevents the old problem
        # where the sidebar could not open again after a close request.
        if always_close:
            import streamlit as st
            st.session_state["new7_native_sidebar_status_20260614"] = "Close requested; native backup remains available and can be opened again."
            st.session_state["sidebar_close_requested_native_only"] = True
        inject_sidebar_policy_css()
    except Exception:
        pass


def request_close_sidebar() -> None:  # type: ignore[override]
    auto_close_sidebar_script(always_close=True)


def request_open_sidebar() -> None:  # type: ignore[override]
    try:
        from ui.sidebar_hard_lock import enable_native_sidebar_backup, inject_sidebar_policy_css
        enable_native_sidebar_backup()
        inject_sidebar_policy_css()
    except Exception:
        pass


def apply_global_styles(phone_mode: bool = False):  # type: ignore[override]
    try:
        if callable(_qx_legacy_apply_global_styles_20260612):
            _qx_legacy_apply_global_styles_20260612(phone_mode=phone_mode)
    except Exception:
        pass
    sidebar_native_stability_css()


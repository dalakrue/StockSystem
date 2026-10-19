import inspect
import streamlit as st
from core.system_upgrade import render_market_pulse
from core.uiux import render_universal_header, render_data_quality_card, render_mobile_hint_once
from core.ui_relationship import render_transition_popup
from core.system_contract import start_tab_timing, finish_tab_timing, render_relationship_matrix
from core.ui.effects import render_effect_styles_once, render_popup_queue, render_connection_guard
from core.code_quality import render_code_quality_panel
from core.pro_quality_upgrade import repair_session_contract

def _safe_run_page(tab_name, show_func, runtime_context=None):
    start_perf = start_tab_timing(tab_name)
    try:
        # Keep the repeated global status/header/relationship area lightweight.
        # Streamlit still executes expander contents while closed, so heavy status
        # panels are now loaded only after the user presses the button inside.
        repair_session_contract()
        render_effect_styles_once()
        render_transition_popup()
        render_popup_queue()
        # Slim build: the data-source HUD (render_global_effects), the quality
        # HUD (render_quality_hud), the command bar and the relationship footer
        # were removed per user request. Only the connection guard remains.
        render_connection_guard(tab_name)
        # Slim build: merged Lunch/Home status snapshot removed (single-page app).
        try:
            signature = inspect.signature(show_func)
            accepts_context = "runtime_context" in signature.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()
            )
        except Exception:
            accepts_context = False
        if accepts_context:
            show_func(runtime_context=runtime_context)
        else:
            show_func()
        # Slim build: relationship footer removed.
        finish_tab_timing(tab_name, start_perf, ok=True)
    except Exception as exc:
        finish_tab_timing(tab_name, start_perf, ok=False, error=str(exc))
        st.error(f"{tab_name} page failed to load.")
        with st.expander("Show error detail"):
            st.exception(exc)

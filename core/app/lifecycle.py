import inspect
import streamlit as st
from core.system_upgrade import render_market_pulse
from core.uiux import render_universal_header, render_data_quality_card, render_mobile_hint_once
from core.ui_relationship import render_command_bar, render_transition_popup, render_relation_footer
from core.system_contract import start_tab_timing, finish_tab_timing, render_relationship_matrix
from core.ui.effects import render_effect_styles_once, render_global_effects, render_popup_queue, render_connection_guard
from core.code_quality import render_code_quality_panel
from core.pro_quality_upgrade import render_quality_hud, repair_session_contract

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
        render_global_effects(tab_name)
        render_connection_guard(tab_name)
        compact_merged_lunch = tab_name in {"Lunch", "Home"} and bool(st.session_state.get("lunch_merge_global_status_20260612", True))
        if not compact_merged_lunch:
            render_quality_hud(tab_name)
            render_command_bar(tab_name)
            with st.expander("📡 Open page status + system relationship", expanded=False):
                rows = len(st.session_state.get("last_df")) if st.session_state.get("last_df") is not None else 0
                st.caption(
                    f"{tab_name} | {st.session_state.get('source', 'DISCONNECTED')} | "
                    f"{st.session_state.get('symbol', 'XAUUSD')} | {st.session_state.get('timeframe', 'M1')} | rows={rows:,}"
                )
                if tab_name in {"Dinner", "Regime"}:
                    st.caption("Full status is synchronized automatically from the single Settings calculation; no Regime/Dinner Load button is required.")
                elif st.button("Load full status for this tab", key=f"load_full_status_{tab_name}"):
                    render_universal_header(tab_name)
                    render_data_quality_card()
                    render_mobile_hint_once()
                    try:
                        render_market_pulse("page_status")
                    except Exception:
                        pass
                    render_relationship_matrix(location=f"tab_{tab_name}", compact=True)
                    render_code_quality_panel(location=f"tab_{tab_name}")
        else:
            st.session_state["page_status_relationship_snapshot_20260612"] = {
                "tab": tab_name,
                "source": st.session_state.get("source", "DISCONNECTED"),
                "symbol": st.session_state.get("symbol", "EURUSD"),
                "timeframe": st.session_state.get("timeframe", "H1"),
                "rows": len(st.session_state.get("last_df")) if st.session_state.get("last_df") is not None else 0,
                "location": "merged NY/London open/close section",
            }
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
        if not compact_merged_lunch:
            render_relation_footer(tab_name)
        finish_tab_timing(tab_name, start_perf, ok=True)
    except Exception as exc:
        finish_tab_timing(tab_name, start_perf, ok=False, error=str(exc))
        st.error(f"{tab_name} page failed to load.")
        with st.expander("Show error detail"):
            st.exception(exc)


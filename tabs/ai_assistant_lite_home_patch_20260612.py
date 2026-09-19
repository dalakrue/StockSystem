"""Install AI Assistant Lite as a Home/Lunch inner tab."""
from __future__ import annotations


def install(ns: dict) -> None:
    import time
    import streamlit as st

    UNIQUE = "20260612_ai_lite_home_patch"

    try:
        from .ai_assistant_lite import render_ai_assistant_lite_tab
    except Exception:
        from tabs.ai_assistant_lite import render_ai_assistant_lite_tab

    prev_lunch = ns.get("_render_metric_home_combined_inner_tab")
    prev_data = ns.get("_render_lunch_data_visualization_inner_tab")
    prev_research = ns.get("_render_home_research_inner_20260612")
    prev_doo = ns.get("_render_doo_prime_inner_tab")
    footer = ns.get("render_tab_footer")
    build_copy = ns.get("_build_lunch_all_copy_text")

    def _copy_button(label: str, text: str, key: str) -> None:
        try:
            from streamlit_copy_button import copy_button
            copy_button(text, label, key=key)
        except Exception:
            try:
                from core.pro_terminal_uiux import render_mobile_copy_button
                render_mobile_copy_button(label, text, key)
            except Exception:
                st.text_area(label, text, height=180, key=key + "_fallback")

    def _selector() -> str:
        choices = [("Lunch", "🍱"), ("Data Visualization", "📊"), ("AI Assistant Lite", "🤖"), ("Research", "🎓"), ("Doo Prime", "🏦")]
        current = st.session_state.get("home_inner_tab", "Lunch")
        names = [x[0] for x in choices]
        if current not in names:
            current = "Lunch"
            st.session_state["home_inner_tab"] = current
        cols = st.columns(len(choices))
        for idx, (name, icon) in enumerate(choices):
            active = st.session_state.get("home_inner_tab", current) == name
            label = ("✅ " if active else "") + f"{icon} {name}"
            if cols[idx].button(label, use_container_width=True, key=f"home_inner_ai_{idx}_{UNIQUE}"):
                st.session_state["home_inner_tab"] = name
                st.session_state["ui_navigation_click_ts"] = time.time()
                try:
                    st.rerun()
                except Exception:
                    pass
        return st.session_state.get("home_inner_tab", current)

    def _top_copy_once() -> None:
        if callable(build_copy):
            try:
                text = build_copy()
            except Exception:
                text = "Copy text is not ready yet. Run Calculation first."
        else:
            text = "Copy text is not ready yet."
        extra = st.session_state.get("ai_lite_messages", [])
        if extra:
            chat = "\n\n".join([f"{m.get('role','').upper()}: {m.get('content','')}" for m in extra[-10:]])
            text = str(text) + "\n\nAI ASSISTANT LITE RECENT CHAT\n" + "=" * 70 + "\n" + chat
        _copy_button("📋 Copy Full Home H1 — includes AI Assistant Lite", text, f"copy_home_ai_lite_full_{UNIQUE}")

    def _show_home_with_ai_lite() -> None:
        try:
            from core.streamlit_safe_dataframe import install_safe_dataframe_patch
            install_safe_dataframe_patch()
        except Exception:
            pass
        try:
            from core.styles import request_close_sidebar
            request_close_sidebar()
        except Exception:
            pass
        selected = _selector()
        _top_copy_once()
        if selected == "Lunch":
            if callable(prev_lunch):
                prev_lunch()
        elif selected == "Data Visualization":
            if callable(prev_data):
                prev_data()
        elif selected == "AI Assistant Lite":
            render_ai_assistant_lite_tab()
        elif selected == "Research":
            if callable(prev_research):
                prev_research()
            else:
                try:
                    import tabs.research as research
                    research.show()
                except Exception as exc:
                    st.error("Research tab could not load.")
                    st.exception(exc)
        else:
            if callable(prev_doo):
                prev_doo()
        # Do not show the generic bottom status footer inside the
        # AI Assistant tab.  The user asked for this tab to stay clean and not
        # display the extra status expander below the chat.
        if callable(footer) and selected != "AI Assistant Lite":
            try:
                footer("Lunch")
            except Exception:
                pass

    ns["render_ai_assistant_lite_tab"] = render_ai_assistant_lite_tab
    ns["show"] = _show_home_with_ai_lite

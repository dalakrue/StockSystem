"""Small top status bar for the future-proof app shell."""
from __future__ import annotations
import html
import streamlit as st


def _tone(value: str) -> str:
    v = str(value or "").upper()
    if "CONNECTED" in v and "DIS" not in v:
        return "connected"
    if "DIS" in v or "FAIL" in v:
        return "disconnected"
    if v in {"BUY", "BULL"}:
        return "buy"
    if v in {"SELL", "BEAR"}:
        return "sell"
    if "RISK" in v or "DANGER" in v:
        return "risk"
    return "wait"


def render_top_status_bar(active_tab: str | None = None) -> None:
    try:
        from ui.stable_ui_libs_20260615 import inject_stable_ui_css, badge
        inject_stable_ui_css()
    except Exception:
        def badge(label, tone="wait"):
            return f'<span class="new7-pill">{html.escape(str(label))}</span>'

    tab = active_tab or st.session_state.get("active_page", st.session_state.get("tab_choice", "Home"))
    try:
        from core.symbol_context_20260702 import resolve_symbol_context
        context = resolve_symbol_context(st.session_state, str(tab))
        is_lunch = str(tab).strip().lower().startswith("lunch")
        symbol = context.lunch_display_symbol if is_lunch else context.settings_main_symbol
        timeframe = context.timeframe
        st.session_state["top_market_symbol_20260702"] = symbol
        if is_lunch:
            checks = {
                "top_market_symbol": symbol,
                "lunch_display_symbol": context.lunch_display_symbol,
                "active_snapshot_symbol": context.active_snapshot_symbol,
            }
            mismatches = {key: value for key, value in checks.items() if value != context.lunch_display_symbol}
            st.session_state["lunch_identity_invariant_20260702"] = {
                "ok": not mismatches, "expected": context.lunch_display_symbol, "mismatches": mismatches,
            }
    except Exception as exc:
        context = None
        symbol = st.session_state.get("multi_symbol_main_symbol_20260702") or "EURUSD"
        timeframe = st.session_state.get("timeframe", "H1")
        st.session_state["lunch_identity_invariant_20260702"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    source = st.session_state.get("source", "DISCONNECTED")
    decision = st.session_state.get("last_decision", st.session_state.get("decision", "WAIT"))
    regime = st.session_state.get("current_regime", st.session_state.get("major_regime", "REGIME"))
    try:
        df = st.session_state.get("last_df")
        rows = len(df) if df is not None else 0
    except Exception:
        rows = 0
    badge_items = [
        badge("Page: " + html.escape(str(tab)), "connected"),
        badge("MARKET: " + html.escape(str(symbol)), "connected"),
    ]
    if context is not None and str(tab).strip().lower().startswith("lunch") and context.settings_main_symbol != context.lunch_display_symbol:
        badge_items.append(badge("MAIN: " + html.escape(context.settings_main_symbol), "wait"))
    badge_items.extend([
        badge(html.escape(str(timeframe)), "connected"),
        badge(html.escape(str(source)), _tone(str(source))),
        badge("Rows: " + f"{rows:,}", "wait"),
        badge(html.escape(str(decision)), _tone(str(decision))),
        badge(html.escape(str(regime))[:26], _tone(str(regime))),
    ])
    badges = "".join(badge_items)
    st.markdown(f'''
<div class="new7-top-status">
  <div style="font-weight:950;color:#0f172a;font-size:.96rem;">⚡ Quant Control Center</div>
  <div class="new7-status-line">{badges}</div>
</div>
''', unsafe_allow_html=True)

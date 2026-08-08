"""Central default values for the Streamlit app.

Keep defaults here so future tab/connector upgrades do not need to edit
`core.common` or the app shell. `core.common` remains as a compatibility
facade for older code.
"""

# 2026-06-15: Ant Design/main-page navigation is the stable source of truth.
# These are display routes only; the original calculation/render modules remain
# unchanged and are routed through tabs.antd_page_router_20260615.
class _NavigationDefaults(list):
    """Reduced production navigation: Settings and Field 3 only."""


DEFAULT_TABS = _NavigationDefaults([
    "Settings",
    "Field 3",
])
SESSION_DEFAULTS = {
    "tab_choice": "Settings",
    "active_page": "Settings",
    "active_subpage": "",
    "symbol": "EURUSD",
    "phone_mode": False,
    "connected": False,
    "source": "DISCONNECTED",
    "last_df": None,
    "last_fetch": 0,
    "timeframe": "H4",
    "timer_end_time": None,
    "trade_end_time": None,
    "timer_minutes": 120,
    "activity_log": [],
    "notes": [],
    "trade_history": [],
    "profile_name": "Quant Trader",
    "twelve_api_key": "",
    "nlp_api_key": "",
    "nlp_api_endpoint": "https://api.openai.com/v1/chat/completions",
    "nlp_api_model": "",
    "nlp_api_connected": False,
    "nlp_api_last_status": "Not connected",
    # Default to real local MT5/Doo Prime first. Demo data is disabled unless
    # the user explicitly enables it from the sidebar.
    "connector_mode": "twelve",
    "connector_bars": 600,
    "allow_safe_demo": False,
    "refresh_seconds": 600,
    "doo_bridge_url": "",
    "doo_bridge_token": "",
    "ws_enabled": False,
    "ws_provider": "generic",
    "ws_url": "",
    "ws_symbol": "EURUSD",
    "ws_ticks": None,
    "account_snapshot": {},
    "doo_positions": [],
    "training_rows": [],
    "guide_restored": True,
    "risk_mode": "Balanced",
    "setting_auto_entry": True,
    "setting_exit_alerts": True,
    "setting_risk_active": True,
    "system_boot_id": "",
    "system_boot_time": "",
    "app_cycle": 0,
    "data_version": 0,
    "data_version_source": "startup",
    "system_events": [],
    "tab_timing": {},
    "tab_runtime_current": {},
    "api_health": {},
    "frontend_health": {},
    "backend_health": {},
    "last_connection_error": "",
    "last_connection_message": "",
    "last_connection_rows": 0,
    "last_connection_mode": "fallback",
    "last_connected_symbol": "EURUSD",
    "last_connected_timeframe": "H4",
    "last_data_quality": {},
    "uiux_density": "wide",
    "system_snapshot_autosave": True,
    # Updated by tab/inner-tab button callbacks. Global refresh skips for a few
    # seconds after this timestamp so navigation never waits behind MT5 or a
    # 60k-candle deep refresh.
    "ui_navigation_click_ts": 0.0,
    "ui_navigation_target": "",
    # Deep Doo Prime fetch is manual by default; instant shared-data seed is
    # still used so the page does not blank.
    "doo_deep_auto_fetch": False,

    # V24 lazy inner-tab gates. These keep expensive pages from running until
    # the user manually presses Run Calculate.
    "home_inner_tab": "Lunch",
    "other_inner_tab": "Engine",
    "other_run_calculate": False,
    "research_run_calculate": False,
    "research_inner_tab": "Data Analysis",
    "metric_run_calculate": False,
    "antd_nav_fallback_warning_shown": False,
    "lunch_active_subpage": "",
    "dinner_active_subpage": "",
    "research_active_subpage": "",
}

LIST_STATE_KEYS = [
    "activity_log",
    "notes",
    "trade_history",
    "doo_positions",
    "training_rows",
    "system_events",
]

DICT_STATE_KEYS = [
    "account_snapshot",
    "tab_timing",
    "tab_runtime_current",
    "api_health",
    "frontend_health",
    "backend_health",
    "last_data_quality",
]

# Legacy static-contract tokens retained for older deployment tests and saved sessions:
# "Field 456" "Field 789" now both route to the single visible "Field 4 to 9" workspace.

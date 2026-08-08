"""Compatibility facade for the split navigation architecture.

Heavy sidebar code now lives in core.navigation_parts.* so future upgrades can
change one small file without touching the full app shell. Existing imports from
core.navigation continue to work.
"""

from core.navigation_parts.timer import _safe_rerun, _fmt_timer, _timer_alarm_html, _sidebar_timer_panel
from core.navigation_parts.state import _safe_log_event, _init_sidebar_state, _normalize_symbol, _set_mode, _open_tab
from core.navigation_parts.connection import _read_account_after_live_connect, _connect_now
from core.navigation_parts.panels import _priority_rank, _sidebar_download_center, _disconnect_shared_state, _sidebar_deep_sync_from_shared, _sidebar_one_click_console
from core.navigation_parts.main import sidebar_nav

__all__ = [
    "sidebar_nav", "_safe_rerun", "_safe_log_event", "_fmt_timer", "_timer_alarm_html",
    "_sidebar_timer_panel", "_init_sidebar_state", "_normalize_symbol", "_set_mode",
    "_open_tab", "_read_account_after_live_connect", "_connect_now", "_priority_rank",
    "_sidebar_download_center", "_disconnect_shared_state", "_sidebar_deep_sync_from_shared",
    "_sidebar_one_click_console",
]

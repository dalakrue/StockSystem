"""Backward-compatible common facade.

The old app imported many helpers from `core.common`. For faster future
upgrades, the real implementation is now split into focused modules while this
file keeps every old import path working.
"""

from core.config.defaults import DEFAULT_TABS, SESSION_DEFAULTS  # noqa: F401
from core.utils.numeric import safe_float, safe_int  # noqa: F401
from core.utils.symbols import normalize_symbol  # noqa: F401
from core.utils.timer import (  # noqa: F401
    format_timer,
    remaining_time,
    remaining_seconds,
    start_timer,
    stop_timer,
)
from core.data.synthetic import synthetic_ohlc  # noqa: F401
from core.state.session_state import init_state, repair_state, log_event, is_phone_mode  # noqa: F401

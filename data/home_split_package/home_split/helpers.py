# Future-upgrade split module.
# Re-exports functions from the unchanged original implementation.
# You can later move the function bodies here one by one.

from .implementation import (
    _safe_num,
    _safe_int,
    _safe_text,
    _safe_append_csv,
    _safe_read_csv,
    _safe_rerun,
    _safe_log_event,
    _safe_close_sidebar,
    _save_once_per_60_seconds,
)

# Future-upgrade split module.
# Re-exports functions from the unchanged original implementation.
# You can later move the function bodies here one by one.

from .implementation import (
    _safe_manual_connect,
    _safe_mt5_account_info,
    _normalize_account_info,
    _safe_quant_stack,
)

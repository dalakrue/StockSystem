"""Compatibility facade for refactored architecture.

The original implementation is preserved in `core.legacy_impl.global_upgrade_impl`. This lightweight
facade keeps all existing imports working while making this active file easy to
upgrade safely.
"""

from core.legacy_impl.global_upgrade_impl import *  # noqa: F401,F403

try:
    from core.legacy_impl.global_upgrade_impl import __all__ as __all__  # type: ignore
except Exception:
    __all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]

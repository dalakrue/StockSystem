"""Compatibility facade for refactored architecture.

The original implementation is preserved in `tabs.pre_clean_split.legacy_impl.exit_survivability_impl`. This lightweight
facade keeps all existing imports working while making this active file easy to
upgrade safely.
"""

from tabs.pre_clean_split.legacy_impl.exit_survivability_impl import *  # noqa: F401,F403

try:
    from tabs.pre_clean_split.legacy_impl.exit_survivability_impl import __all__ as __all__  # type: ignore
except Exception:
    __all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]

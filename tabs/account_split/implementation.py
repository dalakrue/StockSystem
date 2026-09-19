"""Doo Prime/Account implementation compatibility facade.

The large preserved implementation was moved to
`tabs.account_split.legacy.implementation`. Older imports remain valid,
including underscore-prefixed helper imports used by split modules.
"""

from .legacy import implementation as _legacy

for _name in dir(_legacy):
    if not (_name.startswith("__") and _name.endswith("__")):
        globals()[_name] = getattr(_legacy, _name)


def __getattr__(name):
    return getattr(_legacy, name)


__all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]

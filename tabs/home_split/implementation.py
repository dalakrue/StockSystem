"""Home implementation compatibility facade.

The large preserved Home implementation was moved to
`tabs.home_split.legacy.implementation`. Keep importing from this file in older
patches; new upgrades should add focused modules beside this facade.
"""

from .legacy import implementation as _legacy

for _name in dir(_legacy):
    if not (_name.startswith("__") and _name.endswith("__")):
        globals()[_name] = getattr(_legacy, _name)


def __getattr__(name):
    return getattr(_legacy, name)


__all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]

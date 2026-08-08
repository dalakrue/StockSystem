"""Compatibility loader for split Home module.

Original source was divided into small chunk modules for future CSS/UIUX
and feature upgrades while keeping runtime behavior identical.
"""

from importlib import import_module as _import_module

_PART_MODULES = ['part_01', 'part_02', 'part_03']


def _load_original_source():
    chunks = []
    base = __package__ + ".implementation_parts"
    for name in _PART_MODULES:
        chunks.append(_import_module(base + "." + name).PART)
    return "".join(chunks)


_ORIGINAL_SOURCE = _load_original_source()
exec(compile(_ORIGINAL_SOURCE, __file__, "exec"), globals(), globals())

try:
    __all__
except NameError:
    __all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]

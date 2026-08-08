"""Load the exact pre-split implementation into one shared module namespace."""
from __future__ import annotations
from importlib import import_module
from pathlib import Path

_PARTS = ['part_001', 'part_002']
_source = "".join(
    line
    for part_name in _PARTS
    for line in import_module(f"core.full_metric_canonical_adapter_20260618_v9_parts.{part_name}").SOURCE_LINES
)
_ORIGINAL_FILE = str(Path(__file__).resolve().parent.parent / 'full_metric_canonical_adapter_20260618.py')
NAMESPACE = {
    "__name__": 'core.full_metric_canonical_adapter_20260618',
    "__package__": 'core',
    "__file__": _ORIGINAL_FILE,
    "__builtins__": __builtins__,
}
exec(compile(_source, _ORIGINAL_FILE, "exec"), NAMESPACE, NAMESPACE)

__all__ = [name for name in NAMESPACE if not name.startswith("__")]

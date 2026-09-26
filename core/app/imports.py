"""Small import utilities for fast, safe tab transitions."""

from functools import lru_cache
import importlib
from typing import Any


@lru_cache(maxsize=64)
def import_module_cached(module_path: str):
    """Import once and reuse during the Streamlit process.

    Streamlit reruns the script often. Python's module cache already helps, but
    this explicit cache gives a single, testable place for future import timing,
    warmup, and diagnostics.
    """
    return importlib.import_module(module_path)


def import_attr(module_path: str, attr_name: str) -> Any:
    module = import_module_cached(str(module_path))
    return getattr(module, str(attr_name))


def clear_import_cache():
    import_module_cached.cache_clear()

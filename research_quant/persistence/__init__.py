"""Safe additive CRCEF-SV persistence with lazy imports.

Keeping the package initializer lightweight allows
``python -m research_quant.persistence.research_store`` to run without the
runpy double-import warning.
"""
from __future__ import annotations

from typing import Any


def initialize_database(*args: Any, **kwargs: Any):
    from .research_store import initialize_database as implementation
    return implementation(*args, **kwargs)


def store_canonical_snapshot(*args: Any, **kwargs: Any):
    from .research_store import store_canonical_snapshot as implementation
    return implementation(*args, **kwargs)


def store_research_result(*args: Any, **kwargs: Any):
    from .research_store import store_research_result as implementation
    return implementation(*args, **kwargs)


def store_audit_row(*args: Any, **kwargs: Any):
    from .research_store import store_audit_row as implementation
    return implementation(*args, **kwargs)


__all__ = ["initialize_database", "store_canonical_snapshot", "store_research_result", "store_audit_row"]

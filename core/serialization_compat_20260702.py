"""Deployment-safe serializer compatibility layer.

Cloudpickle is preferred because it can serialize a wider range of Python
objects.  Streamlit deployments should install it explicitly, but the app must
still start when a package resolver omits it.  In that case the standard-library
pickle module provides a safe fallback for the bounded dictionaries, pandas
objects, and primitive values used by the runtime cache.
"""
from __future__ import annotations

from typing import Any

try:  # Preferred deployment backend.
    import cloudpickle as _serializer  # type: ignore
    SERIALIZER_BACKEND = "cloudpickle"
    CLOUDPICKLE_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only on minimal deployments.
    import pickle as _serializer
    SERIALIZER_BACKEND = "pickle"
    CLOUDPICKLE_AVAILABLE = False


def dumps(value: Any, protocol: int = 5) -> bytes:
    """Serialize *value* using the best available backend."""
    return _serializer.dumps(value, protocol=protocol)


def loads(payload: bytes) -> Any:
    """Deserialize *payload* using the active backend."""
    return _serializer.loads(payload)


__all__ = ["dumps", "loads", "SERIALIZER_BACKEND", "CLOUDPICKLE_AVAILABLE"]

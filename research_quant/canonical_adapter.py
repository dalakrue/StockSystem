from __future__ import annotations
from hashlib import sha256
import json
from typing import Any, Mapping

from core.canonical_identity_20260627 import build_canonical_identity, normalize_identity_aliases


def adapt_canonical(canonical: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_identity_aliases(canonical, state)
    identity = build_canonical_identity(normalized, state=state, require_complete=True)
    result = dict(normalized)
    result.update(identity.as_dict())
    return result


def feature_hash(features: Mapping[str, Any]) -> str:
    def safe(value: Any):
        if isinstance(value, Mapping):
            return {str(k): safe(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
        if isinstance(value, (list, tuple)):
            return [safe(v) for v in value]
        try:
            return value.item()
        except Exception:
            return str(value) if not isinstance(value, (str, int, float, bool, type(None))) else value
    raw = json.dumps(safe(features), sort_keys=True, separators=(",", ":"), default=str)
    return sha256(raw.encode("utf-8")).hexdigest()

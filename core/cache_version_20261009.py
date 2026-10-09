"""Cache versioning for signals / exit params / replay results (2026-10-09).

Every cached artefact is keyed by its FULL input identity:
  equation IDs + strategy engine version, exit params version, check schedule +
  timezone, admission rules, filters, cost model, intrabar priority,
  holding/censorship policy, source data SHA.

A cache entry whose fingerprint does not match the current inputs is REJECTED
as stale — saved older-engine results are never displayed as current.
Result descriptions always carry the config + data period.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


class StaleCacheError(ValueError):
    """Raised when a cached artefact's input identity does not match."""


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def fingerprint(*, equation_ids: list, engine_version: str,
                exit_params_version: str, check_schedule: dict,
                admission_rules: dict, filters: dict, cost_model: dict,
                intrabar_priority: str, holding_policy: dict,
                censorship_policy: str, source_sha256: str) -> str:
    """Fingerprint the full input identity of a replay result."""
    identity = {
        "equation_ids": sorted(str(x) for x in equation_ids),
        "engine_version": engine_version,
        "exit_params_version": exit_params_version,
        "check_schedule": check_schedule,
        "admission_rules": admission_rules,
        "filters": filters,
        "cost_model": cost_model,
        "intrabar_priority": intrabar_priority,
        "holding_policy": holding_policy,
        "censorship_policy": censorship_policy,
        "source_sha256": source_sha256,
    }
    return hashlib.sha256(_canon(identity).encode()).hexdigest()


def describe(*, config_label: str, data_period: str, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Human/machine-readable result description — always carries config +
    data period so a saved result can never be mistaken for current work."""
    out = {"config": config_label, "data_period": data_period,
           "warning": "do not display as current unless the fingerprint matches the live inputs"}
    if extra:
        out.update(extra)
    return out


def check(entry: Dict[str, Any], *, current_fingerprint: str) -> Dict[str, Any]:
    """Validate a cache entry against the current inputs. Raises
    StaleCacheError on mismatch; returns the entry otherwise."""
    saved = entry.get("input_fingerprint")
    if saved != current_fingerprint:
        raise StaleCacheError(
            "stale cache rejected: saved fingerprint "
            f"{str(saved)[:16]}… != current {current_fingerprint[:16]}…; "
            "saved older-engine results are never displayed as current")
    return entry


def wrap(result: Dict[str, Any], *, input_fingerprint: str,
         config_label: str, data_period: str) -> Dict[str, Any]:
    result = dict(result)
    result["input_fingerprint"] = input_fingerprint
    result["description"] = describe(config_label=config_label, data_period=data_period)
    return result


from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping, MutableMapping


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, 'to_dict'):
        try:
            return dict(value.to_dict())
        except Exception:
            return {}
    if hasattr(value, '__dict__'):
        return {k: v for k, v in vars(value).items() if not k.startswith('_')}
    return {}


def deterministic_snapshot_hash(payload: Mapping[str, Any]) -> str:
    def _clean(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(k): _clean(v) for k, v in sorted(value.items()) if str(k) != 'snapshot_hash'}
        if isinstance(value, (list, tuple)):
            return [_clean(v) for v in value]
        if hasattr(value, 'isoformat'):
            try:
                return value.isoformat()
            except Exception:
                return str(value)
        return value
    clean = _clean(dict(payload))
    blob = json.dumps(clean, sort_keys=True, default=str, separators=(',', ':'))
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if value not in (None, ''):
            return str(value)
    return ''


def freeze_publication_identity(state: Mapping[str, Any] | None = None, canonical: Any | None = None) -> dict[str, str]:
    source = _mapping(canonical)
    snapshot_report: Mapping[str, Any] = {}
    if not source and isinstance(state, Mapping):
        try:
            from core.canonical_sync_v9 import snapshot_identity
            report = snapshot_identity(dict(state))
            if isinstance(report, Mapping):
                snapshot_report = dict(report)
                if report.get('ok'):
                    source = dict(report)
        except Exception:
            snapshot_report = {}
        if not source:
            try:
                from core.canonical.snapshot import load_canonical_snapshot
                snap = load_canonical_snapshot(dict(state))
                source = _mapping(snap)
            except Exception:
                source = {}
        if not source:
            for key in ('canonical_decision_result_20260617', 'last_valid_canonical_decision_result_20260617', 'adx_shared_calc_result_20260615'):
                value = state.get(key)
                if isinstance(value, Mapping) and value:
                    source = dict(value)
                    break
    state_map = state if isinstance(state, Mapping) else {}
    run_id = _first_non_empty(
        source.get('run_id'),
        source.get('canonical_calculation_id'),
        snapshot_report.get('run_id'),
        state_map.get('canonical_run_id_20260617'),
        state_map.get('canonical_calculation_id_20260617'),
        state_map.get('canonical_run_id_v9'),
    )
    generation_id = _first_non_empty(
        source.get('generation_id'),
        source.get('calculation_generation'),
        snapshot_report.get('generation_id'),
        snapshot_report.get('calculation_generation'),
        state_map.get('canonical_calculation_generation_20260617'),
        state_map.get('successful_calculation_generation_20260617'),
        state_map.get('calculation_generation'),
        run_id,
    )
    snapshot_hash = _first_non_empty(
        source.get('snapshot_hash'),
        source.get('source_snapshot_hash'),
        snapshot_report.get('snapshot_hash'),
        state_map.get('canonical_snapshot_hash_20260617'),
        state_map.get('canonical_snapshot_hash_v9'),
    )
    if not snapshot_hash and source:
        snapshot_hash = deterministic_snapshot_hash(source)
    identity = {
        'run_id': run_id,
        'generation_id': generation_id,
        'snapshot_hash': snapshot_hash,
    }
    if isinstance(state, MutableMapping):
        state['publication_identity_20260625'] = identity
    return identity


def identity_matches(obj: Any, identity: Mapping[str, Any]) -> bool:
    source = _mapping(obj)
    if not source:
        return True
    for key in ('run_id', 'generation_id', 'snapshot_hash'):
        expected = str(identity.get(key) or '')
        actual = str(source.get(key) or source.get('source_snapshot_hash' if key == 'snapshot_hash' else key) or '')
        if expected and actual and expected != actual:
            return False
    return True


__all__ = ['deterministic_snapshot_hash', 'freeze_publication_identity', 'identity_matches']

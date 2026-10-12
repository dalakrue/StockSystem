"""Single-load, read-only access to the v1 research candidate pack.

Coefficients are loaded exactly once per process (functools.lru_cache) and
returned as an immutable view. Nothing here fits, retrains, or mutates.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

PACK_VERSION = 'research-candidates-v1-20261009'
PACK_DIR = Path(__file__).resolve().parent
EQUATIONS_FILE = PACK_DIR / 'candidate_equations_120_v1.json'
SOURCE_SHA256 = 'ecd370589d42135f1f4a0343125ec9bf5034b8d6c0438c6b9a86f60eb8a0059d'


def _key_to_s_id(key: str) -> str:
    """JSON integer key k is the zero-based equation index; key k -> S{k+1}."""
    return f'S{int(key) + 1}'


@functools.lru_cache(maxsize=1)
def load_pack() -> dict:
    """Load and validate the 120-equation pack once. Returns
    {'version', 'manifest', 'equations'}. Raises on any integrity failure."""
    import hashlib
    raw = EQUATIONS_FILE.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError(
            f'candidate_equations_120_v1.json integrity failure: '
            f'expected {SOURCE_SHA256}, got {digest}')
    data = json.loads(raw.decode('utf-8'))
    equations = data.get('equations')
    if not isinstance(equations, dict) or len(equations) != 120:
        raise ValueError('pack must contain exactly 120 equations')
    manifest = data.get('manifest', {})
    if manifest.get('fresh_unseen_available'):
        raise ValueError('pack claims fresh unseen evidence it does not have')
    for key, spec in equations.items():
        if spec.get('strict_valid'):
            raise ValueError(f'equation {key}: strict_valid must stay false')
        model = spec.get('model') or {}
        for field in ('features', 'mean', 'scale', 'kind', 'threshold'):
            if field not in model:
                raise ValueError(f'equation {key}: model missing {field!r}')
        if spec.get('side') not in (1, -1):
            raise ValueError(f'equation {key}: side must be +1/-1')
        ex = spec.get('exit') or {}
        for field in ('tp_atr', 'sl_atr', 'tp_min', 'tp_max', 'sl_min', 'sl_max'):
            if field not in ex:
                raise ValueError(f'equation {key}: exit missing {field!r}')
    return {'version': PACK_VERSION, 'manifest': manifest, 'equations': equations}


def get_equation(zero_based_key) -> dict:
    """Return the frozen spec for one equation plus its S id. Key k -> S{k+1}."""
    pack = load_pack()
    key = str(int(zero_based_key))
    spec = pack['equations'][key]
    return {'s_id': _key_to_s_id(key), 'zero_based_key': key, 'spec': spec}


def replaced_s_ids() -> list:
    """S ids replaced by this pack, e.g. ['S3', ...]."""
    pack = load_pack()
    return sorted((_key_to_s_id(k) for k in pack['equations']),
                  key=lambda s: int(s[1:]))

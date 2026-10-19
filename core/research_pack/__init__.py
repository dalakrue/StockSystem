"""Versioned research candidate pack (v1) — 2026-10-09.

120 provisional replacement equations from the 2026-10-08 research bundle.
INTEGRATION STATUS: research-only. NOT wired into live ranking defaults.

Rules:
- Every equation keeps Strict_Valid = false (no fresh unseen validation).
- The frozen S1-S240 equation engine is the default; this pack is available
  only through an explicit, separately-labeled research evaluation path.
- Coefficients are loaded ONCE per version (loader.load_pack) and never
  retrained or mutated at refresh time.
- Rollback: delete this directory; no other module imports it by default.

Equation key mapping: JSON integer key k (string) is the zero-based equation
index; key k maps to S{k+1} in core/equation_column_map.json.
"""
from .loader import PACK_VERSION, load_pack, get_equation, replaced_s_ids

__all__ = ['PACK_VERSION', 'load_pack', 'get_equation', 'replaced_s_ids']

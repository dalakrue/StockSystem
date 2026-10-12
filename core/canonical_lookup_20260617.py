"""Backward-compatible canonical lookup alias.

Older presentation modules import the 20260617 name. The maintained read-only
resolver lives in :mod:`core.canonical_lookup_20260626`.
"""
from core.canonical_lookup_20260626 import resolve_canonical

__all__ = ["resolve_canonical"]

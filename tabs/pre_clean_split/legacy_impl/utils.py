"""Compatibility re-export for dynamically reconstructed legacy modules.

The split source is executed with ``tabs.pre_clean_split.legacy_impl`` as its
package, so historical ``from .utils`` imports resolve here.  The maintained
implementation remains in the parent package.
"""
from tabs.pre_clean_split.utils import *  # noqa: F401,F403

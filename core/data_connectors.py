# Compatibility wrapper. New code lives in core/connectors/data_connectors.py
# IMPORTANT:
# `from module import *` does not re-export underscore-prefixed helpers unless the
# source module defines __all__. Several upgraded modules import private
# compatibility helpers directly:
#   from core.data_connectors import _normalize_ohlc, _clean_symbol
# So this wrapper must expose those names explicitly.

from core.connectors.data_connectors import *  # noqa: F401,F403
from core.connectors.data_connectors import _normalize_ohlc, _clean_symbol  # noqa: F401

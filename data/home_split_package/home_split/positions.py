# Future-upgrade split module.
# Re-exports functions from the unchanged original implementation.
# You can later move the function bodies here one by one.

from .implementation import (
    _position_to_dict,
    _guess_pip_size,
    _calc_pips,
    _positions_frame,
)

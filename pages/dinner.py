"""Compatibility page wrapper. Existing logic remains in tabs.other."""
def show():
    from tabs.other import show as _show
    return _show()

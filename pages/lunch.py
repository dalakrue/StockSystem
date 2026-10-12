"""Compatibility page wrapper. Existing tab logic remains in tabs.home."""
def show():
    from tabs.home import show as _show
    return _show()

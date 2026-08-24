try:
    from .account import show
except Exception:
    def show():
        raise RuntimeError('account_split.show failed to import')

__all__ = ['show']

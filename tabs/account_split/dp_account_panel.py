# Future-upgrade split module.
# Safe Doo Prime panel re-exports from unchanged implementation.

try:
    from .implementation import doo_prime_account_panel, doo_prime_panel
except Exception as exc:
    import streamlit as st

    def doo_prime_account_panel():
        st.markdown('### 🏦 Doo Prime / MT5 Account Reader')
        st.error('Original doo_prime_account_panel could not be imported.')
        st.caption(f'Import error: {exc}')

    def doo_prime_panel():
        st.markdown('### 🏦 Doo Prime')
        st.error('Original doo_prime_panel could not be imported.')
        st.caption(f'Import error: {exc}')

__all__ = ['doo_prime_account_panel', 'doo_prime_panel']

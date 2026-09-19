HOW TO USE

Copy into your project like this:

tabs/
  engine.py
  engine_split/
    __init__.py
    combined_engine.py
    connectors.py
    shared_state.py
    original_engine_inner.py
    original_prelive_inner.py
    original_backtest_inner.py

Your app still imports:
from tabs.engine import show

What this does:
- The outer Engine tab has MT5 / Twelve / Fallback connectors.
- Connected data is stored in st.session_state['last_df'].
- Prelive inner tab reads the same session data.
- Backtest original session keys are filled from the same data.
- Original uploaded code files are preserved as original_* modules.
- No original function body is mixed into another file.

If you still see old Backtest in sidebar, remove Backtest from core/common.py DEFAULT_TABS.

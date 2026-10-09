# Compatibility wrapper.
# Keeps old imports working inside older Streamlit entry points.

try:
    from .profile_dashboard import show
except Exception:
    from tabs.profile_dashboard_split.profile_dashboard import show

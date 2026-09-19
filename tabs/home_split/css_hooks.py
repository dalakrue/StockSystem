"""Home CSS/UIUX extension point.

Add future Home-only visual changes here instead of editing the large legacy
logic. This keeps Home styling isolated and upgrade-safe.
"""

import streamlit as st


def apply_home_css():
    st.markdown(
        """
        <style>
        .home-mini-note {font-size: .78rem; opacity: .78;}
        .home-upgrade-box {border-radius: 18px; padding: .75rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )

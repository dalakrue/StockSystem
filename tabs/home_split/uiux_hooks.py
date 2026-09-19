"""Small Home UI helpers for future phone/glass/animation upgrades."""

import streamlit as st


def home_section(title, expanded=False):
    """Return a Streamlit expander used by new Home sections."""
    return st.expander(title, expanded=expanded)


def compact_caption(text):
    st.markdown(f"<div class='home-mini-note'>{text}</div>", unsafe_allow_html=True)

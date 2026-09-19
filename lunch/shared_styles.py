"""Field-independent responsive CSS."""
from __future__ import annotations
import streamlit as st


def inject() -> None:
    st.markdown(
        """<style>
        @media (max-width: 640px) {
          div[data-testid="stHorizontalBlock"] { gap: .35rem; }
          div[data-testid="stMetric"] { padding: .45rem; }
          .stDataFrame { font-size: .76rem; }
        }
        </style>""",
        unsafe_allow_html=True,
    )

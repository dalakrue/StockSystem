"""Shared glass theme (user order 2026-11-28): ONE glass
stylesheet for the whole app, injected once at the app entry
(core/app/runner.py) so every section — check, precheck,
Replay, Memory Building, history — sits in the same visual
language: translucent panels with backdrop blur, soft 1 px
borders, rounded corners, subtle shadows.

Pure CSS via st.markdown — no JavaScript, no new
dependencies, no render-path cost beyond one style block.
It styles Streamlit's own containers (bordered containers,
expanders, dataframes, tables, metrics, buttons) rather than
any section's markup, so section logic is untouched. The
rules are written to read correctly on both the dark and
light Streamlit themes (translucency over the app backdrop,
with a light-scheme adjustment for panel tint).
"""
from __future__ import annotations

GLASS_THEME_CSS = """
<style>
/* ===== Glass theme 2026-11-28 — one language, whole app ===== */
.stApp {
    background: linear-gradient(160deg, #0b1220 0%, #111c33 48%,
                #0b1220 100%);
    background-attachment: fixed;
}
@media (prefers-color-scheme: light) {
    .stApp {
        background: linear-gradient(160deg, #eef2f7 0%, #dfe7f0 48%,
                    #eef2f7 100%);
        background-attachment: fixed;
    }
}
/* Bordered containers become glass panels. */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(255,255,255,.07);
    border: 1px solid rgba(255,255,255,.16) !important;
    border-radius: 16px !important;
    box-shadow: 0 8px 24px rgba(2,6,23,.18);
    backdrop-filter: blur(12px) saturate(150%);
    -webkit-backdrop-filter: blur(12px) saturate(150%);
}
@media (prefers-color-scheme: light) {
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(255,255,255,.55);
        border-color: rgba(15,23,42,.10) !important;
        box-shadow: 0 8px 24px rgba(15,23,42,.08);
    }
}
/* Expanders as glass panels too. */
[data-testid="stExpander"] {
    background: rgba(255,255,255,.06);
    border: 1px solid rgba(255,255,255,.14) !important;
    border-radius: 14px !important;
    backdrop-filter: blur(10px) saturate(150%);
    -webkit-backdrop-filter: blur(10px) saturate(150%);
}
@media (prefers-color-scheme: light) {
    [data-testid="stExpander"] {
        background: rgba(255,255,255,.5);
        border-color: rgba(15,23,42,.10) !important;
    }
}
/* Tables / dataframes: rounded glass frames. */
[data-testid="stDataFrame"], [data-testid="stTable"] {
    border: 1px solid rgba(255,255,255,.16);
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 14px rgba(2,6,23,.12);
}
@media (prefers-color-scheme: light) {
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        border-color: rgba(15,23,42,.10);
        box-shadow: 0 4px 14px rgba(15,23,42,.06);
    }
}
/* Metrics as small glass tiles. */
[data-testid="stMetric"] {
    background: rgba(255,255,255,.07);
    border: 1px solid rgba(255,255,255,.15);
    border-radius: 12px;
    padding: 8px 12px;
    backdrop-filter: blur(8px) saturate(150%);
    -webkit-backdrop-filter: blur(8px) saturate(150%);
}
@media (prefers-color-scheme: light) {
    [data-testid="stMetric"] {
        background: rgba(255,255,255,.55);
        border-color: rgba(15,23,42,.10);
    }
}
/* Buttons: glass pills. */
.stButton > button, .stDownloadButton > button {
    border-radius: 999px !important;
    border: 1px solid rgba(255,255,255,.25) !important;
    background: rgba(255,255,255,.10) !important;
    backdrop-filter: blur(8px) saturate(150%);
    -webkit-backdrop-filter: blur(8px) saturate(150%);
    box-shadow: 0 2px 8px rgba(2,6,23,.15);
}
@media (prefers-color-scheme: light) {
    .stButton > button, .stDownloadButton > button {
        border-color: rgba(15,23,42,.15) !important;
        background: rgba(255,255,255,.6) !important;
    }
}
/* Sidebar in the same glass language. */
section[data-testid="stSidebar"] {
    backdrop-filter: blur(14px) saturate(150%);
    -webkit-backdrop-filter: blur(14px) saturate(150%);
    border-right: 1px solid rgba(255,255,255,.12);
}
/* Highlight accent (Twelve Data API Memory Building). */
.fx-accent-glow {
    box-shadow: 0 0 0 2px rgba(14,165,233,.45),
                0 0 22px rgba(14,165,233,.40);
}
</style>
"""


def inject_glass_theme(st=None):
    """Emit the shared glass stylesheet once per render.
    Never raises — a style failure must not cost a page."""
    try:
        if st is None:
            import streamlit as st
        st.markdown(GLASS_THEME_CSS, unsafe_allow_html=True)
    except Exception:
        pass

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

/* ===== Round 2 (user order 2026-11-28): readable text,
   watery glass, click effects, display modes, card grid == */
/* Bigger, readable base text on phone AND laptop. */
.stApp, .stApp p, .stApp li, .stApp label {
    font-size: 1.06rem;
    line-height: 1.5;
}
[data-testid="stMarkdownContainer"] p { font-size: 1.06rem; }
[data-testid="stCaptionContainer"], .stApp small {
    font-size: .92rem !important;
}
h1 { font-size: 2.1rem !important; }
h2 { font-size: 1.65rem !important; }
h3 { font-size: 1.35rem !important; }
h4 { font-size: 1.15rem !important; }
/* Tables: larger cell text. */
[data-testid="stDataFrame"] { font-size: .98rem; }
[data-testid="stTable"] td, [data-testid="stTable"] th {
    font-size: 1rem !important;
    padding: .45rem .6rem !important;
}
/* Metrics: larger values. */
[data-testid="stMetricValue"] { font-size: 1.9rem !important; }
[data-testid="stMetricLabel"] { font-size: 1rem !important; }
/* Expander headers read as section openers. */
[data-testid="stExpander"] summary {
    font-size: 1.12rem !important;
    font-weight: 700;
    padding: .55rem .8rem;
}
/* Sidebar: VERY watery glass — clearly see-through (user
   order 2026-11-28 round 2). */
section[data-testid="stSidebar"] {
    background: rgba(255,255,255,.16) !important;
    backdrop-filter: blur(22px) saturate(1.6);
    -webkit-backdrop-filter: blur(22px) saturate(1.6);
    border-right: 1px solid rgba(255,255,255,.35);
}
@media (prefers-color-scheme: dark) {
    section[data-testid="stSidebar"] {
        background: rgba(15,23,42,.30) !important;
    }
}
/* Click effects (CSS only): hover lift + active press on
   buttons, cards, expanders; smooth everywhere. */
.stButton > button, .stDownloadButton > button {
    transition: transform .13s ease, box-shadow .13s ease,
                background .13s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 16px rgba(2,6,23,.22);
}
.stButton > button:active, .stDownloadButton > button:active {
    transform: translateY(1px) scale(.98);
    box-shadow: 0 1px 4px rgba(2,6,23,.18);
}
[data-testid="stExpander"] {
    transition: box-shadow .15s ease, transform .15s ease;
}
[data-testid="stExpander"]:hover {
    box-shadow: 0 6px 18px rgba(2,6,23,.16);
}
[data-testid="stMetric"] {
    transition: transform .13s ease, box-shadow .13s ease;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 16px rgba(2,6,23,.16);
}
/* Subtle section-open animation for expanders. */
@keyframes fxFadeSlide {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
}
[data-testid="stExpander"] > div[role="group"] {
    animation: fxFadeSlide .18s ease;
}
/* Widen toggle: expand the main container (and back). */
html.fx-wide-on .block-container,
html.fx-wide-on [data-testid="stAppViewContainer"] .main
.block-container {
    max-width: 96vw !important;
    padding-left: 1.2rem !important;
    padding-right: 1.2rem !important;
}
/* Display modes: density + single/multi column behaviour.
   Phone = roomier touch targets, everything stacked;
   Laptop = denser. Auto (no class) follows the viewport. */
html.fx-mode-phone .block-container {
    max-width: 100vw !important;
    padding-left: .6rem !important;
    padding-right: .6rem !important;
}
html.fx-mode-phone .stButton > button { min-height: 48px; }
html.fx-mode-phone [data-testid="stHorizontalBlock"] {
    flex-wrap: wrap;
}
html.fx-mode-phone [data-testid="stColumn"] {
    flex: 1 1 100% !important;
    min-width: 100% !important;
}
html.fx-mode-laptop [data-testid="stMetricValue"] {
    font-size: 1.7rem !important;
}
@media (max-width: 760px) {
    .stApp, .stApp p, .stApp li, .stApp label {
        font-size: 1.08rem;
    }
    .stButton > button { min-height: 46px; }
    [data-testid="stMetricValue"] { font-size: 1.6rem !important; }
}
/* Responsive card grid for the new sections (MT5 Live):
   2 across on laptop, 1 across on phone; the mode classes
   force the same behaviour when manually chosen. */
.fx-card-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
    margin: 6px 0;
}
@media (max-width: 760px) {
    .fx-card-grid { grid-template-columns: 1fr; }
}
html.fx-mode-phone .fx-card-grid { grid-template-columns: 1fr; }
html.fx-mode-laptop .fx-card-grid {
    grid-template-columns: repeat(2, 1fr);
}
.fx-pos-card {
    background: rgba(255,255,255,.08);
    border: 1px solid rgba(255,255,255,.18);
    border-radius: 14px;
    padding: 10px 12px;
    backdrop-filter: blur(10px) saturate(150%);
    -webkit-backdrop-filter: blur(10px) saturate(150%);
    box-shadow: 0 4px 14px rgba(2,6,23,.12);
    transition: transform .13s ease, box-shadow .13s ease;
}
.fx-pos-card:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 20px rgba(2,6,23,.18);
}
@media (prefers-color-scheme: light) {
    .fx-pos-card {
        background: rgba(255,255,255,.55);
        border-color: rgba(15,23,42,.10);
    }
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

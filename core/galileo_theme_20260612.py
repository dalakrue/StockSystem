"""Low-CPU Galileo-style CSS polish for New7.

CSS-only visual upgrade. No canvas, no repeated JS timers, no data calculations.
Designed to make Home/Data Visualization look more like a real mobile app while
keeping RAM/CPU low on iPhone 11 Pro.
"""
from __future__ import annotations

import streamlit as st


def apply_galileo_theme() -> None:
    st.markdown(
        """
        <style>
        :root{
          --new7-purple:#7c3aed;
          --new7-cyan:#06b6d4;
          --new7-ink:#172033;
          --new7-muted:#64748b;
          --new7-card:rgba(255,255,255,.68);
        }
        [data-testid="stAppViewContainer"]{
          background:
            radial-gradient(circle at 8% 0%, rgba(168,85,247,.16), transparent 24%),
            radial-gradient(circle at 92% 8%, rgba(34,211,238,.14), transparent 22%),
            linear-gradient(135deg,#f8f5ff 0%,#e8f7ff 50%,#fff7fb 100%) !important;
        }
        .block-container{padding-top:.65rem!important;}
        [data-testid="stSidebar"]{
          background:linear-gradient(180deg,rgba(248,250,252,.97),rgba(239,246,255,.94))!important;
          border-right:1px solid rgba(15,23,42,.06)!important;
          box-shadow:10px 0 28px rgba(15,23,42,.055)!important;
          width:min(18rem,86vw)!important;
        }
        [data-testid="stSidebar"] .stButton>button{
          min-height:38px!important;font-size:.82rem!important;border-radius:14px!important;
          box-shadow:0 8px 18px rgba(79,70,229,.10)!important;
        }
        .stButton>button{
          border-radius:16px!important;font-weight:900!important;transition:transform .10s ease, box-shadow .10s ease!important;
        }
        .stButton>button:hover{transform:translateY(-1px);box-shadow:0 12px 24px rgba(79,70,229,.17)!important;}
        [data-testid="stMetric"], .stMetric{
          background:var(--new7-card)!important;border:1px solid rgba(124,58,237,.13)!important;border-radius:22px!important;
          padding:12px 14px!important;box-shadow:0 12px 32px rgba(30,41,59,.07)!important;backdrop-filter:blur(10px);
        }
        div[data-testid="stExpander"] details{
          border-radius:22px!important;border:1px solid rgba(124,58,237,.16)!important;
          background:rgba(255,255,255,.62)!important;box-shadow:0 12px 30px rgba(30,41,59,.06)!important;overflow:hidden;
        }
        div[data-testid="stExpander"] summary{
          min-height:42px!important;font-weight:950!important;color:#334155!important;
          background:linear-gradient(135deg,rgba(255,255,255,.84),rgba(224,242,254,.68))!important;
        }
        div[data-baseweb="radio"]{gap:8px!important;flex-wrap:wrap!important;}
        div[data-baseweb="radio"] label{
          border-radius:999px!important;padding:6px 9px!important;margin:2px!important;
          background:rgba(255,255,255,.70)!important;border:1px solid rgba(124,58,237,.12)!important;
        }
        input, textarea, [data-baseweb="select"] > div{
          border-radius:15px!important;background:rgba(255,255,255,.83)!important;
        }
        .stDataFrame, [data-testid="stDataFrame"]{
          border-radius:18px!important;overflow:hidden!important;border:1px solid rgba(124,58,237,.12)!important;
        }
        .new7-pro-card{border-radius:24px;padding:16px;background:rgba(255,255,255,.65);border:1px solid rgba(124,58,237,.14);box-shadow:0 12px 32px rgba(30,41,59,.07)}
        @media(max-width:820px){
          .block-container{padding-left:.55rem!important;padding-right:.55rem!important;}
          [data-testid="stMetric"], .stMetric{border-radius:18px!important;padding:10px!important;}
          div[data-testid="stExpander"] summary{font-size:.86rem!important;}
          .stButton>button{min-height:44px!important;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
